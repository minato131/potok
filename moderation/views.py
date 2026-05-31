import json

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
from django.db.models import Count, Q
from datetime import timedelta
from .models import Report
from django.contrib.contenttypes.models import ContentType
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


# moderation/views.py - замени существующую moderation_panel

@login_required
@user_passes_test(is_moderator)
def moderation_panel(request):
    """Панель модератора площадки с полной статистикой"""
    today = timezone.now().date()
    week_ago = timezone.now() - timedelta(days=7)
    month_ago = timezone.now() - timedelta(days=30)

    # ===== ОСНОВНАЯ СТАТИСТИКА =====
    stats = {
        'pending_reports': Report.objects.filter(status='pending').count(),
        'approved_today': Report.objects.filter(
            status='approved',
            moderated_at__date=today
        ).count(),
        'rejected_today': Report.objects.filter(
            status='rejected',
            moderated_at__date=today
        ).count(),
        'new_reports_week': Report.objects.filter(
            created_at__gte=week_ago
        ).count(),
        'active_bans': Ban.objects.filter(lifted_at__isnull=True).count(),
        'total_users': User.objects.count(),
        'banned_users': Ban.objects.filter(lifted_at__isnull=True).values('user').distinct().count(),
        'reports_this_month': Report.objects.filter(created_at__gte=month_ago).count(),
        'resolved_this_month': Report.objects.filter(
            moderated_at__gte=month_ago,
            status__in=['approved', 'rejected']
        ).count(),
    }

    # ===== ТИПЫ ЖАЛОБ (для графика) =====
    report_types = Report.objects.values('report_type').annotate(
        count=Count('id')
    ).order_by('-count')

    # ===== ЕЖЕДНЕВНАЯ АКТИВНОСТЬ (для графика) =====
    daily_stats = []
    for i in range(6, -1, -1):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        daily_stats.append({
            'date': day.strftime('%d.%m'),
            'day_name': ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'][day.weekday()],
            'new': Report.objects.filter(created_at__range=(day_start, day_end)).count(),
            'resolved': Report.objects.filter(moderated_at__range=(day_start, day_end)).count(),
        })

    # ===== САМЫЕ АКТИВНЫЕ ЖАЛОБЩИКИ =====
    top_reporters = User.objects.filter(
        reports_made__isnull=False
    ).annotate(
        report_count=Count('reports_made')
    ).order_by('-report_count')[:5]

    # ===== САМЫЕ ЧАСТО ЖАЛУЮЩИЕСЯ ПОЛЬЗОВАТЕЛИ (на кого жалуются) =====
    from django.contrib.contenttypes.models import ContentType
    post_ct = ContentType.objects.get_for_model(Post)
    comment_ct = ContentType.objects.get_for_model(Comment)

    # Получаем ID пользователей, на которых жалуются
    reported_post_authors = Report.objects.filter(
        content_type=post_ct,
        status='approved'
    ).values_list('object_id', flat=True)

    reported_comment_authors = Report.objects.filter(
        content_type=comment_ct,
        status='approved'
    ).values_list('object_id', flat=True)

    # Это сложный запрос, упростим: покажем просто список жалоб по пользователям
    # (более точную статистику можно сделать отдельно)

    # ===== ПОСЛЕДНИЕ ЖАЛОБЫ =====
    pending_reports = Report.objects.filter(
        status='pending'
    ).select_related('reporter').order_by('-created_at')[:10]

    # Добавляем content_preview для каждого отчёта
    for report in pending_reports:
        if report.content_object:
            if hasattr(report.content_object, 'title'):
                report.content_preview = report.content_object.title[:50]
            elif hasattr(report.content_object, 'content'):
                report.content_preview = report.content_object.content[:50]
            else:
                report.content_preview = str(report.content_object)[:50]

    # ===== АКТИВНЫЕ БЛОКИРОВКИ =====
    active_bans = Ban.objects.filter(
        lifted_at__isnull=True
    ).select_related('user', 'banned_by').order_by('-created_at')[:10]

    # ===== НОВЫЕ ПОЛЬЗОВАТЕЛИ =====
    recent_users = User.objects.order_by('-date_joined')[:10]

    # ===== СТАТУСЫ ЖАЛОБ ДЛЯ КРУГОВОЙ ДИАГРАММЫ =====
    status_stats = {
        'pending': Report.objects.filter(status='pending').count(),
        'approved': Report.objects.filter(status='approved').count(),
        'rejected': Report.objects.filter(status='rejected').count(),
        'lifted': Report.objects.filter(status='lifted').count(),
    }

    # ===== КОНВЕРСИЯ ЖАЛОБ =====
    total_reports = Report.objects.count()
    if total_reports > 0:
        conversion_rate = round((stats['approved_today'] / total_reports) * 100, 1)
    else:
        conversion_rate = 0

    context = {
        'stats': stats,
        'status_stats': status_stats,
        'report_types': report_types,
        'daily_stats': daily_stats,
        'top_reporters': top_reporters,
        'pending_reports': pending_reports,
        'active_bans': active_bans,
        'recent_users': recent_users,
        'conversion_rate': conversion_rate,
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

    # Проверяем, нельзя заблокировать самого себя
    if user_to_ban == request.user:
        messages.error(request, 'Вы не можете заблокировать самого себя')
        return redirect('moderation:user_detail', user_id=user_id)

    # Проверяем, не заблокирован ли уже
    active_ban = Ban.objects.filter(user=user_to_ban, lifted_at__isnull=True).first()
    if active_ban:
        messages.warning(request, f'Пользователь уже заблокирован')
        return redirect('moderation:user_detail', user_id=user_id)

    if request.method == 'POST':
        print("POST данные:", request.POST)  # Отладка

        # Получаем данные из формы
        reason_type = request.POST.get('reason_type', 'other')
        duration = request.POST.get('duration', '7')
        reason_text = request.POST.get('reason', '')
        moderator_note = request.POST.get('note', '')
        delete_content = request.POST.get('delete_content') == '1'

        print(f"reason_type={reason_type}, duration={duration}, reason_text={reason_text}")  # Отладка

        if not reason_text:
            messages.error(request, 'Укажите причину блокировки')
            return redirect('moderation:ban_user', user_id=user_id)

        # Формируем полную причину с учётом типа
        reason_full = f"[{dict(Ban.BAN_TYPES).get(reason_type, 'Другое')}] {reason_text}"

        moderator_note = request.POST.get('note', '')

        # Вычисляем дату истечения
        expires_at = None
        if duration != 'permanent':
            try:
                days = int(duration)
                expires_at = timezone.now() + timedelta(days=days)
            except:
                expires_at = timezone.now() + timedelta(days=7)

        # Создаем блокировку
        ban = Ban.objects.create(
            user=user_to_ban,
            banned_by=request.user,
            ban_type='permanent' if duration == 'permanent' else 'temporary',
            reason=reason_full,
            moderator_note=moderator_note,
            expires_at=expires_at
        )

        print(f"Блокировка создана: ID={ban.id}")  # Отладка

        # Если нужно удалить контент пользователя
        if delete_content:
            # Скрываем все посты пользователя
            user_to_ban.posts.update(is_hidden=True)
            # Скрываем все комментарии пользователя
            from posts.models import Comment
            Comment.objects.filter(author=user_to_ban).update(is_hidden=True)

        # Логируем действие
        ModerationLog.objects.create(
            moderator=request.user,
            action='ban_user',
            description=f'Заблокирован пользователь {user_to_ban.username}: {reason_text}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # Отправляем уведомление пользователю
        from accounts.utils import create_notification
        expire_text = f"до {ban.expires_at.strftime('%d.%m.%Y')}" if ban.expires_at else "постоянная"
        create_notification(
            recipient=user_to_ban,
            sender=request.user,
            notification_type='moderation',
            title='🔒 Вы заблокированы',
            message=f'Ваш аккаунт был заблокирован модератором.\n'
                    f'Причина: {reason_text}\n'
                    f'Срок блокировки: {expire_text}\n\n'
                    f'Если вы считаете блокировку ошибочной, вы можете подать апелляцию.',
            link='/banned/'
        )

        messages.success(request, f'Пользователь {user_to_ban.username} заблокирован')
        return redirect('moderation:user_detail', user_id=user_id)

    # GET запрос - показываем форму
    active_bans = Ban.objects.filter(user=user_to_ban, lifted_at__isnull=True)

    return render(request, 'moderation/ban_user.html', {
        'user_to_ban': user_to_ban,
        'active_bans': active_bans,
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
    tickets = UnbanTicket.objects.filter(user=user).order_by('-created_at')

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
        'tickets': tickets,
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


# moderation/views.py - добавь импорт в начало файла
from accounts.utils import create_notification


# Затем замени существующие функции approve_report и reject_report:

@login_required
def approve_report(request, report_id):
    """Одобрить жалобу (контент будет скрыт)"""
    report = get_object_or_404(Report, id=report_id)

    # Получаем контент до одобрения
    content_obj = report.content_object

    # Проверяем, был ли контент ранее скрыт модерацией и потом восстановлен
    already_fixed = False
    if hasattr(content_obj, 'is_hidden') and not content_obj.is_hidden:
        # Проверяем, были ли ранее одобренные жалобы на этот контент

        ct = ContentType.objects.get_for_model(content_obj)
        previous_approved = Report.objects.filter(
            content_type=ct,
            object_id=content_obj.id,
            status='approved'
        ).exclude(id=report.id).exists()  # исключаем текущую жалобу

        # Если были одобренные жалобы, а сейчас контент видим - значит его отредактировали
        if previous_approved:
            already_fixed = True

    report.approve(request.user)

    # Скрываем контент, только если он ещё не был восстановлен
    if not already_fixed and content_obj and hasattr(content_obj, 'is_hidden'):
        content_obj.is_hidden = True
        content_obj.save()

        # ===== УВЕДОМЛЕНИЕ АВТОРУ КОНТЕНТА =====
        content_type = 'пост' if hasattr(content_obj, 'title') else 'комментарий'

        author = None
        if hasattr(content_obj, 'author'):
            author = content_obj.author
        elif hasattr(content_obj, 'user'):
            author = content_obj.user
        # В функции approve_report, в блоке уведомления автору контента
        if author and author != request.user:
            edit_link = None
            if hasattr(content_obj, 'title'):  # это пост
                edit_link = f'/post/{content_obj.id}/edit/'
            elif hasattr(content_obj, 'content'):  # это комментарий
                edit_link = f'/comment/{content_obj.id}/edit/'

            # Получаем текст причины жалобы
            report_type_display = report.get_report_type_display()
            report_description = report.description or 'Не указано'
            from accounts.utils import create_notification

            create_notification(
                recipient=author,
                sender=request.user,
                notification_type='moderation',
                title='⚠️ Ваш контент заблокирован',
                message=f'Ваш {content_type} был заблокирован модерацией.\n'
                        f'Причина: {report_type_display}.\n'
                        f'Описание: {report_description}\n\n'
                        f'Вы можете отредактировать контент в соответствии с правилами.',
                link=edit_link
            )
    elif already_fixed:
        # Если контент уже был восстановлен, обновляем статус жалобы на "снято"
        report.status = 'lifted'
        report.moderation_comment = 'Контент уже исправлен автором, жалоба снята'
        report.save()

        # Уведомляем автора жалобы
        from accounts.utils import create_notification
        create_notification(
            recipient=report.reporter,
            sender=request.user,
            notification_type='moderation',
            title='📋 Жалоба снята',
            message=f'Пользователь @{content_obj.author.username} уже отредактировал контент "{content_obj.title if hasattr(content_obj, "title") else "комментарий"}". Жалоба закрыта.',
            link=f'/post/{content_obj.id}/'
        )

    # Логируем действие
    from .models import ModerationLog
    ModerationLog.objects.create(
        moderator=request.user,
        action='approve_report',
        content_type=report.content_type,
        object_id=report.object_id,
        description=f'Одобрена жалоба #{report.id}: {report.get_report_type_display()} {"(контент уже восстановлен)" if already_fixed else ""}',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse(
            {'status': 'ok', 'message': 'Жалоба одобрена' + (" (контент уже восстановлен)" if already_fixed else "")})

    messages.success(request, 'Жалоба одобрена' + (" (контент уже восстановлен)" if already_fixed else ""))
    return redirect('moderation:report_list')


@login_required
def reject_report(request, report_id):
    """Отклонить жалобу"""
    report = get_object_or_404(Report, id=report_id)
    report.reject(request.user)

    # ===== УВЕДОМЛЕНИЕ АВТОРУ ЖАЛОБЫ (что жалоба отклонена) =====
    create_notification(
        recipient=report.reporter,
        sender=request.user,
        notification_type='moderation',
        title='📋 Результат рассмотрения жалобы',
        message=f'Ваша жалоба на контент была рассмотрена и отклонена.\n'
                f'Причина: {report.moderation_comment or "Нарушений не обнаружено"}\n\n'
                f'Спасибо за помощь в поддержании порядка на платформе.',
        link='/moderation/reports/'
    )

    # Логируем действие
    ModerationLog.objects.create(
        moderator=request.user,
        action='reject_report',
        content_type=report.content_type,
        object_id=report.object_id,
        description=f'Отклонена жалоба #{report.id}',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'message': 'Жалоба отклонена'})

    messages.success(request, 'Жалоба отклонена')
    return redirect('moderation:report_list')


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
def unban_tickets_list(request):
    """Список заявок на разбан"""
    status_filter = request.GET.get('status', 'pending')

    tickets = UnbanTicket.objects.select_related('user', 'ban', 'reviewed_by')

    if status_filter == 'pending':
        tickets = tickets.filter(status='pending')
    elif status_filter == 'approved':
        tickets = tickets.filter(status='approved')
    elif status_filter == 'rejected':
        tickets = tickets.filter(status='rejected')

    tickets = tickets.order_by('-created_at')

    # Статистика
    stats = {
        'pending': UnbanTicket.objects.filter(status='pending').count(),
        'approved': UnbanTicket.objects.filter(status='approved').count(),
        'rejected': UnbanTicket.objects.filter(status='rejected').count(),
        'total': UnbanTicket.objects.count(),
    }

    paginator = Paginator(tickets, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'moderation/unban_tickets.html', {
        'tickets': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'current_status': status_filter,
    })


@login_required
@user_passes_test(is_moderator)
def unhide_content(request, content_type, object_id):
    """
    Восстановление скрытого контента (снятие блокировки по жалобе)
    """
    try:
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get(model=content_type)
        obj = ct.get_object_for_this_type(id=object_id)
    except:
        messages.error(request, 'Объект не найден')
        return redirect('moderation:panel')

    if hasattr(obj, 'is_hidden'):
        obj.is_hidden = False
        obj.save()

        # Логируем действие
        ModerationLog.objects.create(
            moderator=request.user,
            action='unhide_content',
            content_type=ct,
            object_id=object_id,
            description=f'Восстановлен контент: {obj}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        # Обновляем связанные жалобы (переводим в статус 'lifted')
        Report.objects.filter(
            content_type=ct,
            object_id=object_id,
            status='approved'
        ).update(
            status='lifted',
            moderation_comment='Контент восстановлен',
            moderated_by=request.user,
            moderated_at=timezone.now()
        )

        # Уведомляем автора контента
        from accounts.utils import create_notification
        if hasattr(obj, 'author'):
            author = obj.author
            if author != request.user:
                content_type_name = 'пост' if hasattr(obj, 'title') else 'комментарий'
                create_notification(
                    recipient=author,
                    sender=request.user,
                    notification_type='moderation',
                    title='✅ Ваш контент восстановлен',
                    message=f'Ваш {content_type_name} был восстановлен модерацией после апелляции.\n'
                            f'Пожалуйста, соблюдайте правила платформы.',
                    link=f'/posts/{obj.id}/' if hasattr(obj, 'title') else None
                )

        messages.success(request, 'Контент восстановлен, жалоба закрыта')

    return redirect(request.META.get('HTTP_REFERER', 'moderation:panel'))


@login_required
@user_passes_test(is_moderator)
def approve_ticket(request, ticket_id):
    """Одобрить тикет на разбан (AJAX)"""
    if request.method == 'POST':
        ticket = get_object_or_404(UnbanTicket, id=ticket_id)

        try:
            data = json.loads(request.body)
            comment = data.get('comment', '')
        except:
            comment = request.POST.get('comment', '')

        ticket.approve(request.user, comment)

        return JsonResponse({'status': 'ok', 'message': 'Заявка одобрена'})

    return JsonResponse({'status': 'error', 'message': 'Метод не разрешен'}, status=405)


@login_required
@user_passes_test(is_moderator)
def reject_ticket(request, ticket_id):
    """Отклонить тикет на разбан (AJAX)"""
    if request.method == 'POST':
        ticket = get_object_or_404(UnbanTicket, id=ticket_id)

        try:
            data = json.loads(request.body)
            comment = data.get('comment', '')
        except:
            comment = request.POST.get('comment', '')

        ticket.reject(request.user, comment)

        return JsonResponse({'status': 'ok', 'message': 'Заявка отклонена'})

    return JsonResponse({'status': 'error', 'message': 'Метод не разрешен'}, status=405)