import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from django.views.decorators.http import require_POST

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
from .models import CommunityReport
User = get_user_model()


def is_moderator(user):
    """Проверка: модератор платформы ИЛИ модератор хотя бы одного сообщества"""
    if not user.is_authenticated:
        return False

    # Модератор платформы
    if user.is_staff or user.is_superuser or user.is_platform_moderator:
        return True

    # Модератор хотя бы одного сообщества
    if CommunityMembership.objects.filter(
            user=user,
            role__in=['admin', 'moderator'],
            status='active'
    ).exists():
        return True

    return False


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
    """Панель модератора площадки — видит все жалобы, с пометкой о сообществе"""
    today = timezone.now().date()
    week_ago = timezone.now() - timedelta(days=7)
    month_ago = timezone.now() - timedelta(days=30)

    user = request.user
    is_platform_mod = user.is_platform_moderator or user.is_superuser

    if is_platform_mod:
        # Модератор платформы: ВСЕ жалобы (и platform, и community)
        pending_reports = Report.objects.filter(
            status='pending'
        ).select_related('reporter', 'community').order_by('-created_at')[:20]
        pending_count = Report.objects.filter(status='pending').count()
    else:
        # Модератор сообщества: только жалобы в его сообществах
        moderator_communities = Community.objects.filter(
            communitymembership__user=user,
            communitymembership__role__in=['admin', 'moderator'],
            communitymembership__status='active'
        ).distinct()
        pending_reports = Report.objects.filter(
            status='pending',
            context='community',
            community__in=moderator_communities
        ).select_related('reporter', 'community').order_by('-created_at')[:20]
        pending_count = pending_reports.count()

    # Добавляем превью и пометку о сообществе
    for report in pending_reports:
        if report.content_object:
            if hasattr(report.content_object, 'title'):
                report.content_preview = report.content_object.title[:50]
            elif hasattr(report.content_object, 'content'):
                report.content_preview = report.content_object.content[:50]
            else:
                report.content_preview = str(report.content_object)[:50]
        # Пометка о сообществе для модератора платформы
        if is_platform_mod and report.context == 'community' and report.community:
            report.community_note = f" Из сообщества: {report.community.name}"
        else:
            report.community_note = None

    # ===== ОСТАЛЬНАЯ СТАТИСТИКА =====
    stats = {
        'pending_reports': pending_count,
        'pending_community_reports': CommunityReport.objects.filter(status='pending').count(),
        'approved_today': Report.objects.filter(status='approved', moderated_at__date=today).count(),
        'rejected_today': Report.objects.filter(status='rejected', moderated_at__date=today).count(),
        'new_reports_week': Report.objects.filter(created_at__gte=week_ago).count(),
        'active_bans': Ban.objects.filter(lifted_at__isnull=True).count(),
        'total_users': User.objects.count(),
        'banned_users': Ban.objects.filter(lifted_at__isnull=True).values('user').distinct().count(),
        'reports_this_month': Report.objects.filter(created_at__gte=month_ago).count(),
        'resolved_this_month': Report.objects.filter(moderated_at__gte=month_ago,
                                                     status__in=['approved', 'rejected']).count(),
        'resolved_today': Report.objects.filter(moderated_at__date=today, status__in=['approved', 'rejected']).count(),
    }

    # ===== ТИПЫ ЖАЛОБ (для графика) =====
    report_types = Report.objects.values('report_type').annotate(count=Count('id')).order_by('-count')

    # ===== ЕЖЕДНЕВНАЯ АКТИВНОСТЬ =====
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
    top_reporters = User.objects.filter(reports_made__isnull=False).annotate(
        report_count=Count('reports_made')).order_by('-report_count')[:5]

    # ===== ПОСЛЕДНИЕ ЖАЛОБЫ НА СООБЩЕСТВА =====
    pending_community_reports = CommunityReport.objects.filter(status='pending').select_related('community',
                                                                                                'reporter').order_by(
        '-created_at')[:5]

    # ===== АКТИВНЫЕ БЛОКИРОВКИ =====
    active_bans = Ban.objects.filter(lifted_at__isnull=True).select_related('user', 'banned_by').order_by(
        '-created_at')[:10]

    # ===== НОВЫЕ ПОЛЬЗОВАТЕЛИ =====
    recent_users = User.objects.order_by('-date_joined')[:10]

    # ===== СТАТУСЫ ЖАЛОБ =====
    status_stats = {
        'pending': Report.objects.filter(status='pending').count(),
        'approved': Report.objects.filter(status='approved').count(),
        'rejected': Report.objects.filter(status='rejected').count(),
        'lifted': Report.objects.filter(status='lifted').count(),
    }

    # ===== КОНВЕРСИЯ =====
    total_reports = Report.objects.count()
    conversion_rate = round((stats['approved_today'] / total_reports) * 100, 1) if total_reports > 0 else 0

    context = {
        'stats': stats,
        'status_stats': status_stats,
        'report_types': report_types,
        'daily_stats': daily_stats,
        'top_reporters': top_reporters,
        'pending_reports': pending_reports,
        'pending_community_reports': pending_community_reports,
        'active_bans': active_bans,
        'recent_users': recent_users,
        'conversion_rate': conversion_rate,
        'is_platform_moderator': is_platform_mod,  # <-- ДЛЯ ШАБЛОНА
    }
    return render(request, 'moderation/moderation_panel.html', context)


@login_required
@user_passes_test(is_moderator)
def report_list(request):
    """Список жалоб — модератор платформы видит все, с пометкой о сообществе"""
    user = request.user
    is_platform_mod = user.is_platform_moderator or user.is_superuser

    if is_platform_mod:
        # Модератор платформы: ВСЕ жалобы
        base_reports = Report.objects.all()
    else:
        # Модератор сообщества: только жалобы в его сообществах
        moderator_communities = Community.objects.filter(
            communitymembership__user=user,
            communitymembership__role__in=['admin', 'moderator'],
            communitymembership__status='active'
        ).distinct()
        base_reports = Report.objects.filter(
            context='community',
            community__in=moderator_communities
        )

    # Счётчики
    total_count = base_reports.count()
    pending_count = base_reports.filter(status='pending').count()
    approved_count = base_reports.filter(status='approved').count()
    rejected_count = base_reports.filter(status='rejected').count()
    lifted_count = base_reports.filter(status='lifted').count()

    # Фильтрация
    reports = base_reports.select_related('reporter', 'moderated_by', 'community')
    status = request.GET.get('status', 'all')
    if status == 'pending':
        reports = reports.filter(status='pending')
    elif status == 'approved':
        reports = reports.filter(status='approved')
    elif status == 'rejected':
        reports = reports.filter(status='rejected')
    elif status == 'lifted':
        reports = reports.filter(status='lifted')

    # Тип жалобы
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

    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Добавляем превью и пометку
    for report in page_obj:
        if report.content_object:
            if hasattr(report.content_object, 'title'):
                report.content_preview = report.content_object.title[:50]
            elif hasattr(report.content_object, 'content'):
                report.content_preview = report.content_object.content[:50]
            else:
                report.content_preview = str(report.content_object)[:50]
        if is_platform_mod and report.context == 'community' and report.community:
            report.community_note = f" Из сообщества: {report.community.name}"
        else:
            report.community_note = None

    context = {
        'reports': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'current_status': status,
        'current_type': report_type or 'all',
        'current_sort': sort,
        'total_count': total_count,
        'pending_count': pending_count,
        'resolved_count': approved_count,
        'dismissed_count': rejected_count,
        'lifted_count': lifted_count,
        'is_platform_moderator': is_platform_mod,
    }
    return render(request, 'moderation/report_list.html', context)


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
    community = get_object_or_404(Community, slug=slug)

    # Проверка прав — только админ или модератор сообщества
    membership = CommunityMembership.objects.filter(
        user=request.user, community=community,
        role__in=['admin', 'moderator'], status='active'
    ).first()
    if not membership:
        messages.error(request, 'Нет доступа')
        return redirect('communities:community_detail', slug=slug)

    # Жалобы ТОЛЬКО на контент ЭТОГО сообщества
    post_ct = ContentType.objects.get_for_model(Post)
    community_post_ids = CommunityPost.objects.filter(community=community).values_list('post_id', flat=True)

    # Жалобы, где context='community' И community=текущее сообщество
    pending_reports = Report.objects.filter(
        context='community',
        community=community,
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
        post_id = request.POST.get('post_id')
        comment_id = request.POST.get('comment_id')
        reason = request.POST.get('reason', '')
        report_type = request.POST.get('report_type', 'other')

        if not post_id and not comment_id:
            return JsonResponse({'status': 'error', 'message': 'Контент не указан'})

        # Жалоба на комментарий
        if comment_id:
            try:
                comment = Comment.objects.get(id=comment_id)
            except Comment.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Комментарий не найден'})

            content_type = ContentType.objects.get_for_model(Comment)
            obj_id = comment.id

            # Определяем, находится ли комментарий в сообществе
            community = None
            context = 'platform'

            # Проверяем, есть ли пост комментария в сообществе
            community_post = CommunityPost.objects.filter(post=comment.post).first()
            if community_post:
                community = community_post.community
                context = 'community'

            existing = Report.objects.filter(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                status='pending'
            ).first()

            if existing:
                return JsonResponse(
                    {'status': 'duplicate', 'message': '⚠️ Вы уже отправляли жалобу на этот комментарий.'})

            Report.objects.create(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                context=context,
                community=community
            )

            return JsonResponse({'status': 'ok', 'message': '✅ Жалоба отправлена.'})

        # Жалоба на пост
        if post_id:
            try:
                post = Post.objects.get(id=post_id)
            except Post.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Пост не найден'})

            content_type = ContentType.objects.get_for_model(Post)
            obj_id = post.id

            # Определяем, находится ли пост в сообществе
            community = None
            context = 'platform'

            community_post = CommunityPost.objects.filter(post=post).first()
            if community_post:
                community = community_post.community
                context = 'community'

            existing = Report.objects.filter(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                status='pending'
            ).first()

            if existing:
                return JsonResponse({'status': 'duplicate', 'message': '⚠️ Вы уже отправляли жалобу на этот пост.'})

            Report.objects.create(
                reporter=request.user,
                content_type=content_type,
                object_id=obj_id,
                report_type=report_type,
                description=reason,
                context=context,
                community=community
            )

            return JsonResponse({'status': 'ok', 'message': '✅ Жалоба отправлена.'})

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


@login_required
def report_community(request):
    """Создание жалобы на сообщество"""
    if request.method == 'POST':
        community_slug = request.POST.get('community_slug')
        reason = request.POST.get('reason')
        description = request.POST.get('description')

        if not community_slug or not reason or not description:
            messages.error(request, 'Заполните все поля')
            return redirect(request.META.get('HTTP_REFERER', 'communities:community_list'))

        community = get_object_or_404(Community, slug=community_slug)

        # Нельзя жаловаться на своё сообщество
        if community.creator == request.user:
            messages.error(request, 'Вы не можете жаловаться на своё сообщество')
            return redirect('communities:community_detail', slug=community.slug)

        # Проверяем, не жаловался ли уже пользователь
        existing = CommunityReport.objects.filter(
            community=community,
            reporter=request.user,
            status='pending'
        ).exists()

        if existing:
            messages.warning(request, 'Вы уже отправили жалобу на это сообщество, она ожидает рассмотрения')
            return redirect('communities:community_detail', slug=community.slug)

        # Создаём жалобу
        report = CommunityReport.objects.create(
            community=community,
            reporter=request.user,
            reason=reason,
            description=description,
            status='pending'
        )

        # Уведомляем модераторов платформы
        from accounts.models import User as CustomUser
        moderators = CustomUser.objects.filter(is_platform_moderator=True)
        for mod in moderators:
            create_notification(
                recipient=mod,
                sender=request.user,
                notification_type='moderation',
                title='Новая жалоба на сообщество',
                message=f'Поступила жалоба на сообщество "{community.name}" от @{request.user.username}',
                link=f'/moderation/community-report/{report.id}/'
            )

        messages.success(request, 'Жалоба отправлена. Модераторы рассмотрят её в ближайшее время.')
        return redirect('communities:community_detail', slug=community.slug)

    return redirect('communities:community_list')

@login_required
@user_passes_test(is_moderator)
def community_reports_list(request):
    """Список жалоб на сообщества (только для модераторов платформы)"""
    reports = CommunityReport.objects.select_related('community', 'reporter', 'moderated_by').all()

    status = request.GET.get('status', 'pending')
    if status != 'all':
        reports = reports.filter(status=status)

    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    stats = {
        'pending': CommunityReport.objects.filter(status='pending').count(),
        'approved': CommunityReport.objects.filter(status='restricted').count(),
        'rejected': CommunityReport.objects.filter(status='rejected').count(),
        'warning': CommunityReport.objects.filter(status='warning_issued').count(),
        'total': CommunityReport.objects.count(),
    }

    return render(request, 'moderation/community_reports_list.html', {
        'reports': page_obj,
        'page_obj': page_obj,
        'stats': stats,
        'current_status': status,
    })


@login_required
@user_passes_test(is_moderator)
def community_report_detail(request, report_id):
    """Детальный просмотр жалобы на сообщество"""
    report = get_object_or_404(CommunityReport, id=report_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '').strip()
        creator_message = request.POST.get('creator_message', '').strip()

        if action == 'approve':
            report.approve(request.user, comment)
            messages.success(request, f'Сообщество "{report.community.name}" ограничено')

        elif action == 'reject':
            report.reject(request.user, comment)
            messages.success(request, 'Жалоба отклонена')

        elif action == 'warn':
            report.warn_creator(request.user, comment)
            messages.success(request, 'Предупреждение отправлено создателю')

        elif action == 'write_creator':
            if not creator_message:
                messages.error(request, 'Введите сообщение для создателя')
                return redirect('moderation:community_report_detail', report_id=report.id)

            # 1. Отправляем уведомление
            from accounts.utils import create_notification
            create_notification(
                recipient=report.community.creator,
                sender=request.user,
                notification_type='moderation',
                title='Сообщение от модерации',
                message=f'По поводу вашего сообщества "{report.community.name}":\n\n{creator_message}',
                link=f'/communities/{report.community.slug}/edit/'
            )

            # 2. Отправляем личное сообщение через мессенджер
            try:
                from messenger.models import Chat, ChatParticipant, Message

                # Находим или создаём чат между модератором и создателем
                # Ищем существующий приватный чат между этими двумя пользователями
                chat = Chat.objects.filter(
                    chat_type='private',
                    participants=request.user
                ).filter(
                    participants=report.community.creator
                ).distinct().first()

                if not chat:
                    # Создаём новый приватный чат
                    chat = Chat.objects.create(
                        chat_type='private',
                        name=''  # Для приватных чатов имя не нужно
                    )
                    # Добавляем участников через ChatParticipant
                    ChatParticipant.objects.create(user=request.user, chat=chat, last_read=timezone.now())
                    ChatParticipant.objects.create(user=report.community.creator, chat=chat, last_read=timezone.now())

                # Создаём сообщение
                message_text = f"**Сообщение от модерации**\n\n{creator_message}\n\n---\n*Это сообщение отправлено в связи с жалобой на сообщество \"{report.community.name}\"*"

                Message.objects.create(
                    chat=chat,
                    author=request.user,
                    content=message_text
                )

                messages.success(request, 'Сообщение отправлено создателю в ЛС')

            except ImportError as e:
                messages.warning(request, f'Мессенджер не настроен: {e}')
            except Exception as e:
                messages.warning(request, f'Сообщение не отправлено, но уведомление доставлено: {str(e)}')

        return redirect('moderation:community_reports_list')

    return render(request, 'moderation/community_report_detail.html', {
        'report': report,
    })


def is_platform_moderator(user):
    """Модератор платформы (видит жалобы, может блокировать пользователей)"""
    return user.is_authenticated and (
        user.is_platform_moderator or
        user.is_platform_admin or
        user.is_superuser
    )

def is_platform_admin(user):
    """Администратор платформы (полный доступ)"""
    return user.is_authenticated and (
        user.is_platform_admin or
        user.is_superuser
    )

def is_community_moderator(user, community):
    """Модератор сообщества (жалобы внутри сообщества)"""
    if not user.is_authenticated:
        return False
    membership = CommunityMembership.objects.filter(
        user=user,
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).first()
    return membership is not None

def is_community_admin(user, community):
    """Администратор сообщества (создатель или admin)"""
    if not user.is_authenticated:
        return False
    if user == community.creator:
        return True
    membership = CommunityMembership.objects.filter(
        user=user,
        community=community,
        role='admin',
        status='active'
    ).first()
    return membership is not None


@login_required
@user_passes_test(is_platform_moderator)
def platform_moderator_dashboard(request):
    """Дашборд модератора/администратора платформы"""
    from django.utils import timezone
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    # Статистика для модератора
    context = {
        'pending_reports_count': Report.objects.filter(status='pending').count(),
        'pending_community_reports_count': CommunityReport.objects.filter(status='pending').count(),
        'active_bans_count': Ban.objects.filter(lifted_at__isnull=True).count(),
        'today_reports': Report.objects.filter(created_at__range=(today_start, today_end)).count(),
        'is_platform_admin': is_platform_admin(request.user),  # Для отображения админ-ссылок
    }
    return render(request, 'moderation/platform_moderator_dashboard.html', context)


@login_required
@user_passes_test(is_moderator)
@require_POST
def hide_all_user_posts(request, user_id):
    """Скрыть все посты пользователя"""
    user = get_object_or_404(User, id=user_id)
    count = Post.objects.filter(author=user, is_hidden=False).update(is_hidden=True)

    ModerationLog.objects.create(
        moderator=request.user,
        action='hide_user_posts',
        description=f'Скрыты все посты пользователя {user.username} (кол-во: {count})',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({'status': 'ok', 'message': f'Скрыто постов: {count}'})


@login_required
@user_passes_test(is_moderator)
@require_POST
def hide_all_user_comments(request, user_id):
    """Скрыть все комментарии пользователя"""
    user = get_object_or_404(User, id=user_id)
    count = Comment.objects.filter(author=user, is_hidden=False).update(is_hidden=True)

    ModerationLog.objects.create(
        moderator=request.user,
        action='hide_user_comments',
        description=f'Скрыты все комментарии пользователя {user.username} (кол-во: {count})',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({'status': 'ok', 'message': f'Скрыто комментариев: {count}'})


@login_required
@user_passes_test(is_moderator)
@require_POST
def unhide_all_user_posts(request, user_id):
    """Показать все посты пользователя"""
    user = get_object_or_404(User, id=user_id)
    count = Post.objects.filter(author=user, is_hidden=True).update(is_hidden=False)

    # Обновляем статус жалоб
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(Post)
    post_ids = Post.objects.filter(author=user).values_list('id', flat=True)
    Report.objects.filter(content_type=ct, object_id__in=post_ids, status='approved').update(
        status='lifted',
        moderation_comment='Контент восстановлен модератором',
        moderated_by=request.user,
        moderated_at=timezone.now()
    )

    ModerationLog.objects.create(
        moderator=request.user,
        action='unhide_user_posts',
        description=f'Восстановлены все посты пользователя {user.username} (кол-во: {count})',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({'status': 'ok', 'message': f'Восстановлено постов: {count}'})


@login_required
@user_passes_test(is_moderator)
@require_POST
def unhide_all_user_comments(request, user_id):
    """Показать все комментарии пользователя"""
    user = get_object_or_404(User, id=user_id)
    count = Comment.objects.filter(author=user, is_hidden=True).update(is_hidden=False)

    # Обновляем статус жалоб
    from django.contrib.contenttypes.models import ContentType
    ct = ContentType.objects.get_for_model(Comment)
    comment_ids = Comment.objects.filter(author=user).values_list('id', flat=True)
    Report.objects.filter(content_type=ct, object_id__in=comment_ids, status='approved').update(
        status='lifted',
        moderation_comment='Контент восстановлен модератором',
        moderated_by=request.user,
        moderated_at=timezone.now()
    )

    ModerationLog.objects.create(
        moderator=request.user,
        action='unhide_user_comments',
        description=f'Восстановлены все комментарии пользователя {user.username} (кол-во: {count})',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({'status': 'ok', 'message': f'Восстановлено комментариев: {count}'})