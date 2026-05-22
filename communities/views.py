import json

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage  # ← добавь PageNotAnInteger, EmptyPage
from django.db.models import Q, Count
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.models import Friendship
from accounts.utils import create_notification
from .models import Community, CommunityMembership, CommunityPost, CommunityJoinRequest, User
from .forms import CommunityForm, CommunityPostForm, CommunityJoinRequestForm
from posts.models import Post
from django.utils import timezone
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from posts.models import Comment, Like
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
    Детальная страница сообщества со статистикой
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
        community=community,
        post__is_hidden=False,
        post__status='published'
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

    community.update_stats()

    # ========== СТАТИСТИКА СООБЩЕСТВА ==========
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # ID постов сообщества (через CommunityPost)
    community_post_ids = list(CommunityPost.objects.filter(
        community=community,
        post__is_hidden=False,
        post__status='published'
    ).values_list('post_id', flat=True))

    # Лайкнутые посты текущего пользователя
    liked_post_ids = set()
    if request.user.is_authenticated:
        liked_post_ids = set(Like.objects.filter(
            user=request.user,
            content_type='post',
            object_id__in=community_post_ids
        ).values_list('object_id', flat=True))

    # Статистика по постам
    total_posts = len(community_post_ids)
    posts_this_week = Post.objects.filter(
        id__in=community_post_ids,
        created_at__gte=week_ago
    ).count()
    posts_this_month = Post.objects.filter(
        id__in=community_post_ids,
        created_at__gte=month_ago
    ).count()

    # Статистика по комментариям
    total_comments = Comment.objects.filter(
        post_id__in=community_post_ids,
        is_deleted=False,
        is_hidden=False
    ).count()

    comments_this_week = Comment.objects.filter(
        post_id__in=community_post_ids,
        is_deleted=False,
        is_hidden=False,
        created_at__gte=week_ago
    ).count()

    # Статистика по лайкам
    total_likes = Like.objects.filter(
        content_type='post',
        object_id__in=community_post_ids
    ).count()

    likes_this_week = Like.objects.filter(
        content_type='post',
        object_id__in=community_post_ids,
        created_at__gte=week_ago
    ).count()

    # Топ участников
    top_members = Post.objects.filter(
        id__in=community_post_ids
    ).values('author__username', 'author__id', 'author__profile__avatar').annotate(
        post_count=Count('id')
    ).order_by('-post_count')[:5]

    # Рост участников
    new_members_this_week = CommunityMembership.objects.filter(
        community=community,
        status='active',
        joined_at__gte=week_ago
    ).count()

    new_members_this_month = CommunityMembership.objects.filter(
        community=community,
        status='active',
        joined_at__gte=month_ago
    ).count()

    # Динамика по дням
    last_7_days = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        posts_count = Post.objects.filter(
            id__in=community_post_ids,
            created_at__range=(day_start, day_end)
        ).count()

        last_7_days.append({
            'date': day.strftime('%d.%m'),
            'posts': posts_count,
            'day_name': day.strftime('%a')
        })

    max_posts = max([d['posts'] for d in last_7_days]) if last_7_days and max(
        d['posts'] for d in last_7_days) > 0 else 1

    engagement_rate = 0
    if total_posts > 0:
        engagement_rate = round(((total_likes + total_comments) / total_posts), 1)

    stats = {
        'total_posts': total_posts,
        'posts_this_week': posts_this_week,
        'posts_this_month': posts_this_month,
        'total_comments': total_comments,
        'comments_this_week': comments_this_week,
        'total_likes': total_likes,
        'likes_this_week': likes_this_week,
        'total_members': community.members_count,
        'new_members_this_week': new_members_this_week,
        'new_members_this_month': new_members_this_month,
        'top_members': top_members,
        'weekly_activity': last_7_days,
        'engagement_rate': engagement_rate,
        'max_posts_in_week': max_posts,
    }

    context = {
        'community': community,
        'page_obj': page_obj,
        'user_membership': user_membership,
        'pending_request': pending_request,
        'admins': admins,
        'stats': stats,
        'liked_post_ids': liked_post_ids,  # <-- ДОБАВЛЕНО
    }
    return render(request, 'communities/community_detail.html', context)


@login_required
def community_create(request):
    """Создание нового сообщества"""
    if request.method == 'POST':
        form = CommunityForm(request.POST, request.FILES)
        if form.is_valid():
            community = form.save(commit=False)
            community.creator = request.user

            if not community.slug:
                from django.utils.text import slugify
                community.slug = slugify(community.name)

            from django.db import IntegrityError
            try:
                community.save()
            except IntegrityError:
                import random
                community.slug = f"{slugify(community.name)}-{random.randint(1000, 9999)}"
                community.save()

            # Добавляем создателя как администратора
            CommunityMembership.objects.create(
                user=request.user,
                community=community,
                role='admin',
                status='active'
            )

            community.update_stats()
            messages.success(request, f'Сообщество "{community.name}" создано!')
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
    community = get_object_or_404(Community, slug=slug)

    membership = CommunityMembership.objects.filter(
        user=request.user, community=community,
        role__in=['admin', 'moderator'], status='active'
    ).exists()

    if not membership and request.user != community.creator:
        messages.error(request, 'У вас нет прав на редактирование этого сообщества')
        return redirect('communities:community_detail', slug=community.slug)

    if request.method == 'POST':
        form = CommunityForm(request.POST, request.FILES, instance=community)
        if form.is_valid():
            community = form.save()
            community.update_stats()
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    membership = CommunityMembership.objects.filter(user=request.user, community=community).first()

    if membership:
        if membership.status == 'banned':
            return JsonResponse({'error': 'Заблокированы'}, status=403) if is_ajax else redirect(...)
        elif membership.status == 'active':
            return JsonResponse({'error': 'Уже участник'}, status=400) if is_ajax else redirect(...)

    # Публичное — сразу вступаем
    if community.privacy == 'public':
        CommunityMembership.objects.create(user=request.user, community=community, role='member', status='active')
        community.update_stats()
        if is_ajax: return JsonResponse({'joined': True})
        messages.success(request, 'Вы вступили!')
        return redirect('communities:community_detail', slug=community.slug)

    # Закрытое — заявка
    if request.method == 'POST':
        message = request.POST.get('message', '')
        CommunityJoinRequest.objects.filter(community=community, user=request.user, approved=False).delete()
        CommunityJoinRequest.objects.create(community=community, user=request.user, message=message)
        if is_ajax: return JsonResponse({'joined': False, 'message': 'Заявка отправлена'})
        messages.success(request, 'Заявка отправлена!')
        return redirect('communities:community_detail', slug=community.slug)

    community.update_stats()

    return render(request, 'communities/join_request_modal.html', {'community': community})


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

    community.update_stats()

    return render(request, 'communities/community_post_create.html', {
        'form': form,
        'community': community
    })


@login_required
def community_members(request, slug):
    community = get_object_or_404(Community, slug=slug)

    memberships = CommunityMembership.objects.filter(
        community=community, status='active'
    ).select_related('user', 'user__profile')

    all_members = [m.user for m in memberships]
    moderators = [m.user for m in memberships if m.role in ['admin', 'moderator'] and m.user != community.creator]

    pending_requests = CommunityJoinRequest.objects.filter(
        community=community, approved__isnull=True
    ).select_related('user', 'user__profile')

    context = {
        'community': community,
        'all_members': all_members,
        'total_members': len(all_members),
        'moderators': moderators,
        'pending_requests': pending_requests,
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


@login_required
def change_member_role(request, slug):
    community = get_object_or_404(Community, slug=slug)
    # Проверка что админ
    membership = CommunityMembership.objects.filter(
        user=request.user, community=community, role='admin', status='active'
    ).first()
    if not membership:
        return JsonResponse({'error': 'Нет прав'}, status=403)

    data = json.loads(request.body)
    user_id = data.get('user_id')
    role = data.get('role')

    member = CommunityMembership.objects.filter(community=community, user_id=user_id).first()
    if member and role in ['member', 'moderator']:
        member.role = role
        member.save()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'Ошибка'}, status=400)


@login_required
def ban_community_member(request, slug):
    community = get_object_or_404(Community, slug=slug)
    membership = CommunityMembership.objects.filter(
        user=request.user, community=community, role__in=['admin', 'moderator'], status='active'
    ).first()
    if not membership:
        return JsonResponse({'error': 'Нет прав'}, status=403)

    data = json.loads(request.body)
    user_id = data.get('user_id')

    member = CommunityMembership.objects.filter(community=community, user_id=user_id).first()
    if member and member.user != community.creator:
        member.status = 'banned'
        member.save()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'error': 'Ошибка'}, status=400)


@login_required
def unban_community_member(request, slug):
    # Аналогично ban_community_member, но status = 'active'
    ...

@login_required
def friends_search_api(request):
    """API поиска среди друзей (только accepted)"""
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return JsonResponse([], safe=False)

    friend_ids = Friendship.objects.filter(
        user=request.user,
        status='accepted'
    ).values_list('friend_id', flat=True)

    users = User.objects.filter(id__in=friend_ids).filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    )[:10]

    results = []
    for u in users:
        results.append({
            'id': u.id,
            'username': u.username,
            'full_name': u.get_full_name(),
            'avatar': u.profile.avatar.url if hasattr(u, 'profile') and u.profile.avatar else None,
        })
    return JsonResponse(results, safe=False)