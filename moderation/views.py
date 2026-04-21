from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.http import JsonResponse
from accounts.utils import create_notification
from .models import Report, Ban, ModerationLog
from .forms import ReportForm, BanForm, ModerationActionForm
from posts.models import Post, Comment
from communities.models import Community, CommunityPost
from django.contrib.auth import get_user_model

User = get_user_model()


def is_moderator(user):
    """Проверка, является ли пользователь модератором"""
    return user.is_authenticated and (
                user.is_staff or user.is_superuser or user.groups.filter(name='Moderators').exists())


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
    """
    Панель модератора
    """
    # Статистика
    stats = {
        'pending_reports': Report.objects.filter(status='pending').count(),
        'active_bans': Ban.objects.filter(lifted_at__isnull=True).count(),
        'reports_today': Report.objects.filter(created_at__date=timezone.now().date()).count(),
    }

    # Ожидающие жалобы
    pending_reports = Report.objects.filter(
        status='pending'
    ).select_related(
        'reporter', 'moderated_by'
    ).prefetch_related(
        'content_object'
    ).order_by('created_at')[:20]

    # Активные блокировки
    active_bans = Ban.objects.filter(
        lifted_at__isnull=True
    ).select_related(
        'user', 'banned_by'
    ).order_by('-created_at')[:20]

    # Последние действия модераторов
    recent_actions = ModerationLog.objects.select_related(
        'moderator'
    ).order_by('-created_at')[:30]

    context = {
        'stats': stats,
        'pending_reports': pending_reports,
        'active_bans': active_bans,
        'recent_actions': recent_actions,
    }
    return render(request, 'moderation/moderation_panel.html', context)


@login_required
@user_passes_test(is_moderator)
def report_list(request):
    """
    Список всех жалоб
    """
    reports = Report.objects.select_related(
        'reporter', 'moderated_by'
    ).prefetch_related(
        'content_object'
    ).order_by('-created_at')

    # Фильтры
    status = request.GET.get('status')
    if status:
        reports = reports.filter(status=status)

    report_type = request.GET.get('type')
    if report_type:
        reports = reports.filter(report_type=report_type)

    # Поиск
    query = request.GET.get('q')
    if query:
        reports = reports.filter(
            Q(reporter__username__icontains=query) |
            Q(description__icontains=query)
        )

    paginator = Paginator(reports, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'moderation/report_list.html', {
        'page_obj': page_obj,
        'status': status,
        'report_type': report_type,
        'query': query,
    })


@login_required
@user_passes_test(is_moderator)
def report_detail(request, report_id):
    report = get_object_or_404(Report.objects.select_related('reporter'), id=report_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')

        if action == 'approve':
            report.approve(request.user, comment)

            # Уведомление пользователю, который подал жалобу
            create_notification(
                recipient=report.reporter,
                sender=request.user,
                notification_type='report',
                title='Жалоба рассмотрена',
                message=f'Ваша жалоба одобрена. {comment}',
                link=f'/moderation/report/{report.id}/'
            )

            # Уведомление автору контента (если есть)
            if report.content_object and hasattr(report.content_object, 'author'):
                create_notification(
                    recipient=report.content_object.author,
                    sender=request.user,
                    notification_type='report',
                    title='Жалоба на ваш контент',
                    message=f'На ваш контент поступила жалоба, и она была одобрена. {comment}',
                    link='#'
                )

            messages.success(request, 'Жалоба одобрена, контент скрыт')
        elif action == 'reject':
            report.reject(request.user, comment)

            # Уведомление пользователю, который подал жалобу
            create_notification(
                recipient=report.reporter,
                sender=request.user,
                notification_type='report',
                title='Жалоба рассмотрена',
                message=f'Ваша жалоба отклонена. {comment}',
                link=f'/moderation/report/{report.id}/'
            )

            messages.success(request, 'Жалоба отклонена')

        ModerationLog.objects.create(
            moderator=request.user,
            action='approve_report' if action == 'approve' else 'reject_report',
            content_type=report.content_type,
            object_id=report.object_id,
            description=f'{action} жалоба #{report.id}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return redirect('moderation:report_list')

    return render(request, 'moderation/report_detail.html', {'report': report})


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
    """
    Детальная информация о пользователе для модератора
    """
    user = get_object_or_404(User, id=user_id)

    # Статистика пользователя
    stats = {
        'posts': user.posts.count(),
        'comments': Comment.objects.filter(author=user).count(),
        'communities': user.communities.count(),
        'reports_made': Report.objects.filter(reporter=user).count(),
        'reports_received': Report.objects.filter(
            object_id=user_id,
            content_type=ContentType.objects.get_for_model(User)
        ).count(),
    }

    # Активные блокировки
    active_bans = Ban.objects.filter(user=user, lifted_at__isnull=True)

    # Жалобы на пользователя
    reports = Report.objects.filter(
        object_id=user_id,
        content_type=ContentType.objects.get_for_model(User)
    ).select_related('reporter').order_by('-created_at')[:10]

    context = {
        'target_user': user,
        'stats': stats,
        'active_bans': active_bans,
        'reports': reports,
    }
    return render(request, 'moderation/user_detail.html', context)