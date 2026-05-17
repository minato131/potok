from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from accounts.utils import create_notification
from .models import Report, Ban, ModerationLog, UnbanTicket
from .forms import ReportForm, BanForm, ModerationActionForm
from posts.models import Post, Comment
from communities.models import Community, CommunityPost, CommunityMembership
from django.contrib.auth import get_user_model

User = get_user_model()


def is_moderator(user):
    """Проверка: модератор площадки"""
    return user.is_authenticated and (user.is_staff or user.is_superuser or user.is_platform_moderator)


@login_required
def create_report(request, content_type, object_id):
    """
    Создание жалобы на контент
    """
    # Получаем объект, на который жалуются
    try:
        content_type_obj = ContentType.objects.get(model=content_type)
        content_object = content_type_obj.get_object_for_this_type(id=object_id)
    except:
        messages.error(request, 'Объект не найден')
        return redirect('posts:post_list')

    # Проверяем, не жаловался ли уже пользователь
    existing_report = Report.objects.filter(
        reporter=request.user,
        content_type=content_type_obj,
        object_id=object_id,
        status='pending'
    ).exists()

    if existing_report:
        messages.warning(request, 'Вы уже отправили жалобу на этот контент')
        return redirect(request.META.get('HTTP_REFERER', 'posts:post_list'))

    if request.method == 'POST':
        form = ReportForm(request.POST, content_object=content_object, reporter=request.user)
        if form.is_valid():
            report = form.save()

            # Логируем действие
            ModerationLog.objects.create(
                moderator=request.user,
                action='report_created',
                content_type=content_type_obj,
                object_id=object_id,
                description=f'Создана жалоба #{report.id} типа {report.get_report_type_display()}',
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, 'Жалоба отправлена! Модераторы рассмотрят её в ближайшее время.')
            return redirect(request.META.get('HTTP_REFERER', 'posts:post_list'))
    else:
        form = ReportForm()

    return render(request, 'moderation/create_report.html', {
        'form': form,
        'content_object': content_object,
        'content_type': content_type,
    })


@login_required
@user_passes_test(is_moderator)
def moderation_panel(request):
    """Панель модератора площадки"""
    from django.utils import timezone
    from django.contrib.contenttypes.models import ContentType

    today = timezone.now().date()

    stats = {
        'pending_reports': Report.objects.filter(status='pending').count(),
        'resolved_today': ModerationLog.objects.filter(
            created_at__date=today
        ).count(),
        'active_bans': Ban.objects.filter(lifted_at__isnull=True).count(),
        'total_users': User.objects.count(),
    }

    pending_reports = Report.objects.filter(status='pending').select_related('reporter').order_by('-created_at')[:10]

    # Добавляем content_preview
    for report in pending_reports:
        if report.content_object:
            if hasattr(report.content_object, 'title'):
                report.content_preview = report.content_object.title[:50]
            elif hasattr(report.content_object, 'content'):
                report.content_preview = report.content_object.content[:50]

    active_bans = Ban.objects.filter(lifted_at__isnull=True).select_related('user').order_by('-created_at')[:10]
    recent_users = User.objects.order_by('-date_joined')[:10]

    context = {
        'stats': stats,
        'pending_reports': pending_reports,
        'active_bans': active_bans,
        'recent_users': recent_users,
    }
    return render(request, 'moderation/moderation_panel.html', context)


@login_required
@user_passes_test(is_moderator)
def report_list(request):
    reports = Report.objects.select_related('reporter', 'moderated_by').order_by('-created_at')
    lifted_count = Report.objects.filter(status='lifted').count()

    # Статус
    status = request.GET.get('status', 'all')
    if status == 'pending':
        reports = reports.filter(status='pending')
    elif status == 'approved':
        reports = reports.filter(status='approved')
    elif status == 'rejected':
        reports = reports.filter(status='rejected')
    elif status == 'lifted':
        reports = reports.filter(status='lifted')

    # Тип
    report_type = request.GET.get('type')
    if report_type and report_type != 'all':
        reports = reports.filter(report_type=report_type)

    # Сортировка
    sort = request.GET.get('sort', 'newest')
    if sort == 'oldest':
        reports = reports.order_by('created_at')
    else:
        reports = reports.order_by('-created_at')

    # Поиск
    query = request.GET.get('q')
    if query:
        reports = reports.filter(
            Q(reporter__username__icontains=query) |
            Q(description__icontains=query)
        )

    # Счётчики
    total_count = Report.objects.count()
    pending_count = Report.objects.filter(status='pending').count()
    approved_count = Report.objects.filter(status='approved').count()
    rejected_count = Report.objects.filter(status='rejected').count()

    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'moderation/report_list.html', {
        'reports': page_obj,  # ← reports вместо page_obj
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'current_status': status,
        'current_type': report_type,
        'current_sort': sort,
        'total_count': total_count,
        'pending_count': pending_count,
        'resolved_count': approved_count,
        'dismissed_count': rejected_count,
        'lifted_count': lifted_count,
    })


@login_required
@user_passes_test(is_moderator)
def report_detail(request, report_id):
    report = get_object_or_404(Report.objects.select_related('reporter'), id=report_id)

    # Получаем автора контента если есть
    content_author = None
    if report.content_object:
        if hasattr(report.content_object, 'author'):
            content_author = report.content_object.author

    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')

        if action == 'approve':
            report.approve(request.user, comment)
            messages.success(request, 'Жалоба одобрена')
        elif action == 'reject':
            report.reject(request.user, comment)
            messages.success(request, 'Жалоба отклонена')

        return redirect('moderation:report_list')

    return render(request, 'moderation/report_detail.html', {
        'report': report,
        'content_author': content_author,
    })

@login_required
@user_passes_test(is_moderator)
def ban_user(request, user_id):
    """
    Блокировка пользователя
    """
    user_to_ban = get_object_or_404(User, id=user_id)

    # Проверяем, не заблокирован ли уже
    active_ban = Ban.objects.filter(user=user_to_ban, lifted_at__isnull=True).first()
    if active_ban:
        messages.warning(request, f'Пользователь уже заблокирован до {active_ban.expires_at}')
        return redirect('moderation:user_detail', user_id=user_id)

    if request.method == 'POST':
        form = BanForm(request.POST)
        if form.is_valid():
            ban = form.save(commit=False)
            ban.user = user_to_ban
            ban.banned_by = request.user
            ban.save()

            # Логируем действие
            ModerationLog.objects.create(
                moderator=request.user,
                action='ban_user',
                description=f'Заблокирован пользователь {user_to_ban.username}: {ban.reason}',
                ip_address=request.META.get('REMOTE_ADDR')
            )

            messages.success(request, f'Пользователь {user_to_ban.username} заблокирован')
            return redirect('moderation:user_detail', user_id=user_id)
    else:
        form = BanForm()

    return render(request, 'moderation/ban_user.html', {
        'form': form,
        'user_to_ban': user_to_ban
    })


@login_required
@user_passes_test(is_moderator)
def lift_ban(request, ban_id):
    """
    Снятие блокировки
    """
    ban = get_object_or_404(Ban, id=ban_id, lifted_at__isnull=True)

    if request.method == 'POST':
        ban.lift(request.user)

        # Логируем действие
        ModerationLog.objects.create(
            moderator=request.user,
            action='lift_ban',
            description=f'Снята блокировка с пользователя {ban.user.username}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        messages.success(request, f'Блокировка снята с пользователя {ban.user.username}')
        return redirect('moderation:user_detail', user_id=ban.user.id)

    return render(request, 'moderation/lift_ban.html', {'ban': ban})


@login_required
@user_passes_test(is_moderator)
def hide_content(request, content_type, object_id):
    """
    Скрытие контента
    """
    try:
        content_type_obj = ContentType.objects.get(model=content_type)
        content_object = content_type_obj.get_object_for_this_type(id=object_id)
    except:
        messages.error(request, 'Объект не найден')
        return redirect('moderation:panel')

    if hasattr(content_object, 'is_hidden'):
        content_object.is_hidden = True
        content_object.save()

        # Логируем действие
        ModerationLog.objects.create(
            moderator=request.user,
            action='hide_content',
            content_type=content_type_obj,
            object_id=object_id,
            description=f'Скрыт контент: {content_object}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        messages.success(request, 'Контент скрыт')

    return redirect(request.META.get('HTTP_REFERER', 'moderation:panel'))


@login_required
@user_passes_test(is_moderator)
def user_detail(request, user_id):
    user = get_object_or_404(User, id=user_id)

    stats = {
        'posts': user.posts.count(),
        'comments': Comment.objects.filter(author=user).count(),
        'communities': user.communities.count(),
        'reports_made': Report.objects.filter(reporter=user).count(),
    }

    active_bans = Ban.objects.filter(user=user, lifted_at__isnull=True)

    # Жалобы на ПОСТЫ пользователя
    post_ct = ContentType.objects.get_for_model(Post)
    post_ids = user.posts.values_list('id', flat=True)
    post_reports = Report.objects.filter(content_type=post_ct, object_id__in=post_ids)

    # Жалобы на КОММЕНТАРИИ пользователя
    comment_ct = ContentType.objects.get_for_model(Comment)
    comment_ids = Comment.objects.filter(author=user).values_list('id', flat=True)
    comment_reports = Report.objects.filter(content_type=comment_ct, object_id__in=comment_ids)

    # Все жалобы на контент пользователя
    from django.db.models import Q
    reports = Report.objects.filter(
        Q(content_type=post_ct, object_id__in=post_ids) |
        Q(content_type=comment_ct, object_id__in=comment_ids)
    ).select_related('reporter').order_by('-created_at')[:20]

    context = {
        'target_user': user,
        'stats': stats,
        'active_bans': active_bans,
        'reports': reports,
    }
    return render(request, 'moderation/user_detail.html', context)


@login_required
def community_moderation_panel(request, slug):
    """Панель модерации сообщества"""
    community = get_object_or_404(Community, slug=slug)

    # Проверка прав — только админ или модератор сообщества
    membership = CommunityMembership.objects.filter(
        user=request.user, community=community,
        role__in=['admin', 'moderator'], status='active'
    ).first()
    if not membership:
        messages.error(request, 'Нет доступа')
        return redirect('communities:community_detail', slug=slug)

    # Жалобы на контент этого сообщества
    from django.contrib.contenttypes.models import ContentType
    post_ct = ContentType.objects.get_for_model(Post)
    community_post_ids = CommunityPost.objects.filter(community=community).values_list('post_id', flat=True)

    pending_reports = Report.objects.filter(
        content_type=post_ct,
        object_id__in=community_post_ids,
        status='pending'
    ).select_related('reporter')[:20]

    # Участники
    members = CommunityMembership.objects.filter(
        community=community
    ).select_related('user').order_by('-role', 'joined_at')

    banned_members = members.filter(status='banned')
    active_members = members.filter(status='active')

    context = {
        'community': community,
        'pending_reports': pending_reports,
        'pending_reports_count': pending_reports.count(),
        'members': active_members,
        'banned_members': banned_members,
        'banned_count': banned_members.count(),
        'total_members': active_members.count(),
    }
    return render(request, 'moderation/community_moderation_panel.html', context)


@login_required
def approve_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    report.approve(request.user)

    # Скрываем контент
    if report.content_object and hasattr(report.content_object, 'is_hidden'):
        report.content_object.is_hidden = True
        report.content_object.save()

    return JsonResponse({'status': 'ok'})

@login_required
def reject_report(request, report_id):
    report = get_object_or_404(Report, id=report_id)
    report.reject(request.user)
    return JsonResponse({'status': 'ok'})


def banned_page(request):
    """Страница забаненного пользователя"""
    if not request.user.is_authenticated:
        return redirect('accounts:login')

    active_ban = Ban.objects.filter(
        user=request.user,
        lifted_at__isnull=True
    ).first()

    if not active_ban:
        return redirect('posts:post_list')

    existing_ticket = UnbanTicket.objects.filter(
        user=request.user,
        ban=active_ban,
        status='pending'
    ).first()

    return render(request, 'moderation/banned_page.html', {
        'active_ban': active_ban,
        'existing_ticket': existing_ticket,
    })


@login_required
def create_unban_ticket(request):
    """Создание тикета на разбан"""
    if request.method == 'POST':
        active_ban = Ban.objects.filter(
            user=request.user,
            lifted_at__isnull=True
        ).first()

        if not active_ban:
            return redirect('posts:post_list')

        # Проверка на существующий тикет
        existing = UnbanTicket.objects.filter(
            user=request.user,
            ban=active_ban,
            status='pending'
        ).exists()

        if existing:
            messages.warning(request, 'Вы уже отправили заявку')
            return redirect('moderation:banned_page')

        message = request.POST.get('message', '').strip()
        if not message:
            messages.error(request, 'Введите сообщение')
            return redirect('moderation:banned_page')

        UnbanTicket.objects.create(
            user=request.user,
            ban=active_ban,
            message=message
        )

        messages.success(request, 'Заявка отправлена! Ожидайте решения.')
        return redirect('moderation:banned_page')

    return redirect('moderation:banned_page')


@login_required
def submit_report(request):
    if request.method == 'POST':
        # Определяем тип контента
        post_id = request.POST.get('post_id')
        comment_id = request.POST.get('comment_id')
        reason = request.POST.get('reason', '')
        report_type = request.POST.get('report_type', 'other')

        if not post_id and not comment_id:
            return JsonResponse({'status': 'error', 'message': 'Контент не указан'})
        print('POST data:', request.POST)

        # Жалоба на комментарий
        if comment_id:
            try:
                comment = Comment.objects.get(id=comment_id)
            except Comment.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Комментарий не найден'})

            content_type = ContentType.objects.get_for_model(Comment)
            obj_id = comment.id

            # Проверка дубликата
            existing = Report.objects.filter(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                status='pending'
            ).first()

            if existing:
                return JsonResponse({'status': 'duplicate', 'message': '⚠️ Вы уже отправляли похожую жалобу на этот комментарий.'})

            Report.objects.create(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason
            )

            return JsonResponse({'status': 'ok', 'message': '✅ Жалоба на комментарий отправлена. Модераторы рассмотрят её.'})

        # Жалоба на пост
        if post_id:
            try:
                post = Post.objects.get(id=post_id)
            except Post.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Пост не найден'})

            content_type = ContentType.objects.get_for_model(Post)
            obj_id = post.id

            existing = Report.objects.filter(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                status='pending'
            ).first()

            if existing:
                return JsonResponse({'status': 'duplicate', 'message': '⚠️ Вы уже отправляли похожую жалобу на этот пост.'})

            Report.objects.create(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason
            )

            return JsonResponse({'status': 'ok', 'message': '✅ Жалоба отправлена. Модераторы рассмотрят её в ближайшее время.'})

    return JsonResponse({'status': 'error', 'message': 'Метод не поддерживается'})


@login_required
@user_passes_test(is_moderator)
def unhide_content(request, content_type, object_id):
    try:
        ct = ContentType.objects.get(model=content_type)
        obj = ct.get_object_for_this_type(id=object_id)
    except:
        messages.error(request, 'Объект не найден')
        return redirect('moderation:panel')

    if hasattr(obj, 'is_hidden'):
        obj.is_hidden = False
        obj.save()

        ModerationLog.objects.create(
            moderator=request.user,
            action='unhide_content',
            content_type=ct,
            object_id=object_id,
            description=f'Восстановлен контент: {obj}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        Report.objects.filter(
            content_type=ct,
            object_id=object_id
        ).update(
            status='lifted',
            moderation_comment='Контент восстановлен',
            moderated_by=request.user,
            moderated_at=timezone.now()
        )

        messages.success(request, 'Контент восстановлен, жалоба закрыта')

    return redirect(request.META.get('HTTP_REFERER', 'moderation:panel'))