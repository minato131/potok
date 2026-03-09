from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Community, CommunityMembership, CommunityPost, CommunityJoinRequest
from .forms import CommunityForm, CommunityPostForm, CommunityJoinRequestForm
from posts.models import Post


def community_list(request):
    """
    Список всех сообществ
    """
    communities = Community.objects.filter(
        status='active'
    ).select_related('creator')

    # Убираем annotate, так как поле уже есть в модели
    # Или используем другое имя, если нужно пересчитать

    # Поиск
    query = request.GET.get('q')
    if query:
        communities = communities.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    # Фильтр по приватности
    privacy = request.GET.get('privacy')
    if privacy in ['public', 'private', 'hidden']:
        communities = communities.filter(privacy=privacy)

    # Сортировка
    sort = request.GET.get('sort', '-created_at')
    if sort in ['name', '-name', '-created_at', '-members_count']:
        communities = communities.order_by(sort)

    paginator = Paginator(communities, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'privacy': privacy,
        'sort': sort,
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
    if request.user.is_authenticated:
        user_membership = CommunityMembership.objects.filter(
            user=request.user,
            community=community
        ).first()

    # Проверяем заявку на вступление
    pending_request = None
    if request.user.is_authenticated and community.privacy == 'private':
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
    """
    Вступление в сообщество
    """
    community = get_object_or_404(Community, slug=slug)

    # Проверяем, не состоит ли уже
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

    # Для публичных сообществ - сразу добавляем
    if community.privacy == 'public':
        CommunityMembership.objects.create(
            user=request.user,
            community=community,
            status='active'
        )
        community.update_stats()
        messages.success(request, f'Вы вступили в сообщество "{community.name}"!')
        return redirect('communities:community_detail', slug=community.slug)

    # Для закрытых - создаем заявку
    elif community.privacy == 'private':
        # Проверяем, нет ли уже активной заявки
        existing_request = CommunityJoinRequest.objects.filter(
            community=community,
            user=request.user,
            approved__isnull=True
        ).first()

        if existing_request:
            messages.info(request, 'Ваша заявка уже рассматривается')
            return redirect('communities:community_detail', slug=community.slug)

        if request.method == 'POST':
            form = CommunityJoinRequestForm(request.POST)
            if form.is_valid():
                CommunityJoinRequest.objects.create(
                    community=community,
                    user=request.user,
                    message=form.cleaned_data['message']
                )
                messages.success(request, 'Заявка отправлена! Ожидайте решения модераторов.')
                return redirect('communities:community_detail', slug=community.slug)
        else:
            form = CommunityJoinRequestForm()

        return render(request, 'communities/join_request.html', {
            'form': form,
            'community': community
        })

    # Для скрытых - недоступно
    else:
        messages.error(request, 'Это сообщество закрыто для вступления')
        return redirect('communities:community_detail', slug=community.slug)


@login_required
def community_leave(request, slug):
    """
    Выход из сообщества
    """
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

    membership.delete()
    community.update_stats()
    messages.success(request, f'Вы покинули сообщество "{community.name}"')
    return redirect('communities:community_detail', slug=community.slug)


@login_required
def community_post_create(request, slug):
    """
    Создание поста в сообществе
    """
    community = get_object_or_404(Community, slug=slug)

    # Проверка, состоит ли пользователь в сообществе
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
        form = CommunityPostForm()

    return render(request, 'communities/community_post_form.html', {
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
    """
    Управление заявками на вступление
    """
    community = get_object_or_404(Community, slug=slug)

    # Проверка прав (только админы и модераторы)
    membership = CommunityMembership.objects.filter(
        user=request.user,
        community=community,
        role__in=['admin', 'moderator'],
        status='active'
    ).exists()

    if not membership and request.user != community.creator:
        messages.error(request, 'У вас нет прав на управление заявками')
        return redirect('communities:community_detail', slug=community.slug)

    pending_requests = CommunityJoinRequest.objects.filter(
        community=community,
        approved__isnull=True
    ).select_related('user').order_by('created_at')

    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')

        join_request = get_object_or_404(CommunityJoinRequest, id=request_id, community=community)

        if action == 'approve':
            if join_request.approve(request.user):
                messages.success(request, f'Заявка от {join_request.user.username} одобрена')
            else:
                messages.error(request, 'Не удалось одобрить заявку')
        elif action == 'reject':
            join_request.reject(request.user)
            messages.info(request, f'Заявка от {join_request.user.username} отклонена')

        return redirect('communities:community_manage_requests', slug=community.slug)

    context = {
        'community': community,
        'pending_requests': pending_requests,
    }
    return render(request, 'communities/community_requests.html', context)