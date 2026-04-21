from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage  # ← добавь PageNotAnInteger, EmptyPage
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from accounts.utils import create_notification
from .models import Community, CommunityMembership, CommunityPost, CommunityJoinRequest
from .forms import CommunityForm, CommunityPostForm, CommunityJoinRequestForm
from posts.models import Post
from django.utils import timezone

from django.shortcuts import render
from django.db.models import Q, Count
from .models import Community


def community_list(request):
    # Базовый queryset - используем существующие поля без аннотации
    communities = Community.objects.filter(status='active')

    # Поиск
    search_query = request.GET.get('q', '')
    if search_query:
        communities = communities.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    # Фильтрация
    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'my' and request.user.is_authenticated:
        communities = communities.filter(members=request.user)
    elif filter_type == 'popular':
        communities = communities.order_by('-members_count')
    elif filter_type == 'new':
        communities = communities.order_by('-created_at')
    else:
        communities = communities.order_by('name')

    # Пагинация
    paginator = Paginator(communities, 12)
    page = request.GET.get('page', 1)

    try:
        communities_page = paginator.page(page)
    except PageNotAnInteger:
        communities_page = paginator.page(1)
    except EmptyPage:
        communities_page = paginator.page(paginator.num_pages)

    context = {
        'communities': communities_page,
        'search_query': search_query,
        'filter_type': filter_type,
        'is_paginated': communities_page.has_other_pages(),
        'page_obj': communities_page,
        'total_count': communities.count(),
    }

    return render(request, 'communities/community_list.html', context)


def community_detail(request, slug):
    """
    Детальная страница сообщества
    """
    community = get_object_or_404(
        Community.objects.select_related('creator'),
        slug=slug,
        status='active'
    )

    # Проверка доступа к закрытому сообществу
    if community.privacy != 'public':
        if not request.user.is_authenticated:
            messages.warning(request, 'Для просмотра этого сообщества необходимо войти')
            return redirect('accounts:login')

        membership = CommunityMembership.objects.filter(
            user=request.user,
            community=community,
            status='active'
        ).first()

        if not membership and community.privacy == 'hidden':
            messages.error(request, 'У вас нет доступа к этому сообществу')
            return redirect('communities:community_list')

    # Получаем посты сообщества
    posts = CommunityPost.objects.filter(
        community=community
    ).select_related(
        'post', 'post__author'
    ).prefetch_related(
        'post__tags'
    ).order_by('-is_pinned', '-post__created_at')

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Проверяем статус текущего пользователя
    user_membership = None
    pending_request = None
    if request.user.is_authenticated:
        user_membership = CommunityMembership.objects.filter(
            user=request.user,
            community=community
        ).first()

        if not user_membership and community.privacy == 'private':
            pending_request = CommunityJoinRequest.objects.filter(
                community=community,
                user=request.user,
                approved__isnull=True
            ).first()

    # Администраторы и модераторы
    admins = CommunityMembership.objects.filter(
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).select_related('user')

    context = {
        'community': community,
        'page_obj': page_obj,
        'user_membership': user_membership,
        'pending_request': pending_request,
        'admins': admins,
    }
    return render(request, 'communities/community_detail.html', context)


@login_required
def community_create(request):
    """
    Создание нового сообщества
    """
    if request.method == 'POST':
        form = CommunityForm(request.POST, request.FILES)
        if form.is_valid():
            community = form.save(commit=False)
            community.creator = request.user

            # Генерируем slug если он пустой
            if not community.slug:
                from django.utils.text import slugify
                community.slug = slugify(community.name)

            # Проверяем уникальность slug
            from django.db import IntegrityError
            try:
                community.save()
                form.save_m2m()
            except IntegrityError:
                # Если slug не уникален, добавляем случайное число
                import random
                community.slug = f"{slugify(community.name)}-{random.randint(1000, 9999)}"
                community.save()
                form.save_m2m()

            # Добавляем создателя как администратора
            CommunityMembership.objects.create(
                user=request.user,
                community=community,
                role='admin',
                status='active'
            )

            messages.success(request, f'Сообщество "{community.name}" успешно создано!')
            return redirect('communities:community_detail', slug=community.slug)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме')
    else:
        form = CommunityForm()

    return render(request, 'communities/community_form.html', {
        'form': form,
        'title': 'Создать сообщество'
    })


@login_required
def community_edit(request, slug):
    """
    Редактирование сообщества
    """
    community = get_object_or_404(Community, slug=slug)

    # Проверка прав (только создатель или админ)
    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).exists()

    if not membership and request.user != community.creator:
        messages.error(request, 'У вас нет прав на редактирование этого сообщества')
        return redirect('communities:community_detail', slug=community.slug)

    if request.method == 'POST':
        form = CommunityForm(request.POST, request.FILES, instance=community)
        if form.is_valid():
            community = form.save()
            messages.success(request, 'Сообщество успешно обновлено!')
            return redirect('communities:community_detail', slug=community.slug)
    else:
        form = CommunityForm(instance=community)

    return render(request, 'communities/community_form.html', {
        'form': form,
        'community': community,
        'title': f'Редактирование "{community.name}"'
    })


@login_required
def community_join(request, slug):
    community = get_object_or_404(Community, slug=slug)

    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community
    ).first()

    if membership:
        if membership.status == 'banned':
            messages.error(request, 'Вы заблокированы в этом сообществе')
        elif membership.status == 'active':
            messages.info(request, 'Вы уже состоите в этом сообществе')
        return redirect('communities:community_detail', slug=community.slug)

    # Для публичных сообществ
    if community.privacy == 'public':
        membership = CommunityMembership.objects.create(
            user=request.user,
            community=community,
            role='member',
            status='active'
        )

        # Обновляем статистику
        community.update_stats()

        # Уведомление админам
        admins = CommunityMembership.objects.filter(
            community=community,
            role__in=['admin', 'moderator'],
            status='active'
        ).select_related('user')

        from accounts.utils import create_notification
        for admin in admins:
            create_notification(
                recipient=admin.user,
                sender=request.user,
                notification_type='community',
                title='Новый участник',
                message=f'@{request.user.username} присоединился к сообществу "{community.name}"',
                link=f'/communities/{community.slug}/'
            )

        messages.success(request, f'Вы вступили в сообщество "{community.name}"!')
        return redirect('communities:community_detail', slug=community.slug)

    # Для закрытых - заявка
    elif community.privacy in ['private', 'hidden']:
        # Проверяем, не был ли пользователь забанен
        banned = CommunityMembership.objects.filter(
            user=request.user,
            community=community,
            status='banned'
        ).exists()

        if banned:
            messages.error(request, 'Вы заблокированы в этом сообществе')
            return redirect('communities:community_detail', slug=community.slug)

        # Проверяем, нет ли уже активной заявки
        existing_request = CommunityJoinRequest.objects.filter(
            community=community,
            user=request.user,
            approved__isnull=True
        ).first()

        if existing_request:
            messages.info(request, 'Ваша заявка уже рассматривается')
            return redirect('communities:community_detail', slug=community.slug)

        # Удаляем старые отклоненные заявки
        CommunityJoinRequest.objects.filter(
            community=community,
            user=request.user,
            approved=False
        ).delete()

        if request.method == 'POST':
            message = request.POST.get('message', '')

            join_request = CommunityJoinRequest.objects.create(
                community=community,
                user=request.user,
                message=message
            )

            # Уведомление админам о новой заявке
            admins = CommunityMembership.objects.filter(
                community=community,
                role__in=['admin', 'moderator'],
                status='active'
            ).select_related('user')

            from accounts.utils import create_notification
            for admin in admins:
                create_notification(
                    recipient=admin.user,
                    sender=request.user,
                    notification_type='community_request',
                    title='Новая заявка',
                    message=f'@{request.user.username} хочет вступить в "{community.name}"',
                    link=f'/communities/{community.slug}/requests/'
                )

            messages.success(request, 'Заявка отправлена! Ожидайте решения модераторов.')
            return redirect('communities:community_detail', slug=community.slug)

        # Если GET запрос - показываем модальное окно с формой
        return render(request, 'communities/join_request_modal.html', {
            'community': community
        })


@login_required
def community_leave(request, slug):
    community = get_object_or_404(Community, slug=slug)

    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community,
        status='active'
    ).first()

    if not membership:
        messages.error(request, 'Вы не состоите в этом сообществе')
        return redirect('communities:community_detail', slug=community.slug)

    # Нельзя выйти, если ты единственный администратор
    if membership.role == 'admin':
        admin_count = CommunityMembership.objects.filter(
            community=community,
            role='admin',
            status='active'
        ).count()

        if admin_count <= 1:
            messages.error(request, 'Вы единственный администратор. Назначьте другого администратора перед выходом.')
            return redirect('communities:community_detail', slug=community.slug)

    # Удаляем членство
    membership.delete()

    # Удаляем все старые заявки этого пользователя (чтобы можно было подать новую)
    CommunityJoinRequest.objects.filter(
        community=community,
        user=request.user
    ).delete()

    # Обновляем статистику
    community.update_stats()

    messages.success(request, f'Вы покинули сообщество "{community.name}"')
    return redirect('communities:community_detail', slug=community.slug)


@login_required
def community_post_create(request, slug):
    community = get_object_or_404(Community, slug=slug)

    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community,
        status='active'
    ).first()

    if not membership:
        messages.error(request, 'Вы должны состоять в сообществе, чтобы создавать посты')
        return redirect('communities:community_detail', slug=community.slug)

    if request.method == 'POST':
        form = CommunityPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(community, request.user)
            community.update_stats()
            messages.success(request, 'Пост успешно опубликован в сообществе!')
            return redirect('posts:post_detail', pk=post.pk)
        else:
            # Выводим ошибки формы для отладки
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            print("Ошибки формы:", form.errors)  # Отладка
    else:
        form = CommunityPostForm()

    return render(request, 'communities/community_post_create.html', {
        'form': form,
        'community': community
    })

@login_required
def community_members(request, slug):
    """
    Список участников сообщества
    """
    community = get_object_or_404(Community, slug=slug)

    members = CommunityMembership.objects.filter(
        community=community,
        status='active'
    ).select_related('user').order_by('-role', 'joined_at')

    # Фильтр по роли
    role = request.GET.get('role')
    if role in ['admin', 'moderator', 'member']:
        members = members.filter(role=role)

    paginator = Paginator(members, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Проверка прав текущего пользователя
    user_membership = None
    if request.user.is_authenticated:
        user_membership = CommunityMembership.objects.filter(
            user=request.user,
            community=community
        ).first()

    context = {
        'community': community,
        'page_obj': page_obj,
        'user_membership': user_membership,
        'current_role': role,
    }
    return render(request, 'communities/community_members.html', context)


@login_required
def community_manage_requests(request, slug):
    community = get_object_or_404(Community, slug=slug)

    # Проверка прав
    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).exists()

    if not membership and request.user != community.creator:
        messages.error(request, 'У вас нет прав на управление заявками')
        return redirect('communities:community_detail', slug=community.slug)

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')

        join_request = get_object_or_404(CommunityJoinRequest, id=request_id, community=community)

        if action == 'approve':
            # Проверяем, не было ли уже членство
            existing_membership = CommunityMembership.objects.filter(
                user=join_request.user,
                community=community
            ).first()

            if existing_membership:
                if existing_membership.status == 'banned':
                    messages.error(request, f'Пользователь {join_request.user.username} заблокирован в этом сообществе')
                else:
                    messages.info(request, f'Пользователь {join_request.user.username} уже является участником')
                join_request.approved = False
                join_request.processed_at = timezone.now()
                join_request.processed_by = request.user
                join_request.save()
            else:
                # Создаем членство
                CommunityMembership.objects.create(
                    user=join_request.user,
                    community=community,
                    role='member',
                    status='active'
                )
                join_request.approved = True
                join_request.processed_at = timezone.now()
                join_request.processed_by = request.user
                join_request.save()

                # Обновляем статистику
                community.update_stats()

                # Уведомление пользователю
                from accounts.utils import create_notification
                create_notification(
                    recipient=join_request.user,
                    sender=request.user,
                    notification_type='community',
                    title='Заявка одобрена',
                    message=f'Ваша заявка на вступление в сообщество "{community.name}" одобрена',
                    link=f'/communities/{community.slug}/'
                )

                messages.success(request, f'Заявка от {join_request.user.username} одобрена')

        elif action == 'reject':
            # Отклоняем заявку
            join_request.approved = False
            join_request.processed_at = timezone.now()
            join_request.processed_by = request.user
            join_request.save()

            # Уведомление пользователю об отклонении
            from accounts.utils import create_notification
            create_notification(
                recipient=join_request.user,
                sender=request.user,
                notification_type='community',
                title='Заявка отклонена',
                message=f'Ваша заявка на вступление в сообщество "{community.name}" отклонена',
                link=f'/communities/{community.slug}/'
            )

            messages.info(request, f'Заявка от {join_request.user.username} отклонена')

        return redirect('communities:community_manage_requests', slug=community.slug)

    # Получаем все ожидающие заявки
    pending_requests = CommunityJoinRequest.objects.filter(
        community=community,
        approved__isnull=True
    ).select_related('user').order_by('created_at')

    return render(request, 'communities/community_manage_requests.html', {
        'community': community,
        'pending_requests': pending_requests
    })


@login_required
def cancel_join_request(request, slug):
    """
    Отмена отправленной заявки на вступление
    """
    community = get_object_or_404(Community, slug=slug)

    # Ищем активную заявку пользователя
    join_request = CommunityJoinRequest.objects.filter(
        community=community,
        user=request.user,
        approved__isnull=True
    ).first()

    if not join_request:
        messages.error(request, 'Активная заявка не найдена')
        return redirect('communities:community_detail', slug=community.slug)

    # Удаляем заявку
    join_request.delete()

    # Уведомление админам (опционально)
    admins = CommunityMembership.objects.filter(
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).select_related('user')

    from accounts.utils import create_notification
    for admin in admins:
        create_notification(
            recipient=admin.user,
            sender=request.user,
            notification_type='community',
            title='Заявка отменена',
            message=f'@{request.user.username} отменил свою заявку на вступление в "{community.name}"',
            link=f'/communities/{community.slug}/requests/'
        )

    messages.success(request, 'Заявка успешно отменена')
    return redirect('communities:community_detail', slug=community.slug)