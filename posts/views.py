import uuid
from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, OuterRef, Subquery
from django.test import tag
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from unicodedata import category
import json
from accounts.models import Notification
from communities.models import Community, CommunityPost
from .models import Post, Comment, Like, Category, Tag, Bookmark, PostView
from .forms import PostForm, CommentForm, PostSearchForm, TagForm, CategoryForm
from accounts.utils import create_notification
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from accounts.models import Profile
from django.utils.text import slugify
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

User = get_user_model()


def post_list(request):
    # Базовый queryset
    posts = Post.objects.select_related(
        'author',
        'author__profile',
        'category'
    ).prefetch_related(
        'tags',
        'comments'
    ).filter(status='published')

    # Фильтрация по ленте
    feed = request.GET.get('feed', 'all')

    if feed == 'following' and request.user.is_authenticated:
        try:
            # Получаем ID пользователей, на которых подписан текущий пользователь
            following_user_ids = request.user.profile.following.values_list('id', flat=True)

            # Получаем ID сообществ, в которых состоит пользователь
            following_communities = Community.objects.filter(members=request.user)

            # Получаем ID постов из сообществ
            community_post_ids = CommunityPost.objects.filter(
                community__in=following_communities
            ).values_list('post_id', flat=True)

            # Фильтруем: посты от подписанных пользователей ИЛИ посты из сообществ
            posts = posts.filter(
                Q(author_id__in=following_user_ids) |
                Q(id__in=community_post_ids)
            )
        except (AttributeError, Profile.DoesNotExist):
            # Если нет профиля - показываем пустую ленту
            posts = posts.none()

    elif feed == 'popular':
        # Используем существующее поле likes_count
        posts = posts.annotate(
            comment_count=Count('comments')
        ).order_by('-likes_count', '-comment_count', '-created_at')

    # Сортировка
    sort = request.GET.get('sort', 'new')
    if sort == 'top':
        from django.utils import timezone
        from datetime import timedelta
        day_ago = timezone.now() - timedelta(days=1)
        posts = posts.filter(created_at__gte=day_ago).order_by('-likes_count', '-created_at')
    elif sort == 'hot':
        posts = posts.annotate(
            comment_count=Count('comments')
        ).order_by('-comment_count', '-created_at')
    else:
        posts = posts.order_by('-created_at')

    # Фильтрация по категории
    category_slug = request.GET.get('category')
    category = None
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        posts = posts.filter(category=category)

    # Фильтрация по тегу
    tag_slug = request.GET.get('tag')
    tag = None
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        posts = posts.filter(tags=tag)

    # Пагинация
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)

    try:
        posts_page = paginator.page(page)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)

    # Популярные сообщества
    popular_communities = Community.objects.filter(
        status='active'
    ).order_by('-members_count')[:10]

    # Популярные теги
    popular_tags = Tag.objects.annotate(
        post_count=Count('posts')
    ).order_by('-post_count')[:10]

    context = {
        'posts': posts_page,
        'is_paginated': posts_page.has_other_pages(),
        'page_obj': posts_page,
        'category': category,
        'tag': tag,
        'popular_communities': popular_communities,
        'popular_tags': popular_tags,
    }

    return render(request, 'posts/feed.html', context)


def post_detail(request, pk):
    """
    Детальная страница поста
    """
    post = get_object_or_404(
        Post.objects.select_related('author', 'category'),
        pk=pk
    )

    # Если пост в черновике и не автор - 404
    if post.status != 'published' and post.author != request.user:
        return render(request, '404.html', status=404)

    # Увеличиваем просмотры (только для авторизованных или уникальных)
    if request.user.is_authenticated:
        # Проверяем, не смотрел ли пользователь этот пост в последний час
        recent_view = PostView.objects.filter(
            post=post,
            user=request.user,
            viewed_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()

        if not recent_view:
            PostView.objects.create(post=post, user=request.user)
            post.increment_views()
    elif not request.session.get(f'viewed_post_{pk}'):
        # Для неавторизованных используем сессию
        PostView.objects.create(post=post, ip_address=request.META.get('REMOTE_ADDR'))
        post.increment_views()
        request.session[f'viewed_post_{pk}'] = True

    # Комментарии
    comments = post.comments.filter(parent=None, is_deleted=False).prefetch_related('replies')

    # Форма комментария
    comment_form = CommentForm()

    # Проверка лайка от текущего пользователя
    user_like = None
    if request.user.is_authenticated:
        user_like = Like.objects.filter(
            user=request.user,
            content_type='post',
            object_id=post.id
        ).first()

    # Проверка, в избранном ли пост
    is_bookmarked = False
    if request.user.is_authenticated:
        is_bookmarked = Bookmark.objects.filter(
            user=request.user,
            post=post
        ).exists()

    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'user_like': user_like,
        'is_bookmarked': is_bookmarked,
    }
    return render(request, 'posts/post_detail.html', context)


@login_required
def post_create(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.status = 'published'
            post.save()

            # Обрабатываем теги из скрытого поля tags_input
            tags_str = request.POST.get('tags', '') or request.POST.get('tags_input', '')
            if tags_str:
                tag_names = [t.strip().lower() for t in tags_str.split(',') if t.strip()]
                for tag_name in tag_names:
                    # Ищем или создаем тег
                    tag = Tag.objects.filter(name__iexact=tag_name).first()
                    if not tag:
                        slug = slugify(tag_name)
                        if not slug:
                            slug = f"tag-{uuid.uuid4().hex[:8]}"
                        # Проверяем уникальность slug
                        if Tag.objects.filter(slug=slug).exists():
                            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
                        tag = Tag.objects.create(name=tag_name, slug=slug)
                    post.tags.add(tag)

            messages.success(request, 'Пост успешно опубликован!')
            return redirect('posts:post_detail', pk=post.pk)
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PostForm()

    return render(request, 'posts/post_form.html', {'form': form})

@login_required
def post_edit(request, pk):
    """
    Редактирование поста
    """
    post = get_object_or_404(Post, pk=pk)

    # Проверка прав
    if post.author != request.user:
        messages.error(request, 'Вы не можете редактировать этот пост')
        return redirect('posts:post_detail', pk=post.pk)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save()
            messages.success(request, 'Пост успешно обновлен!')
            return redirect('posts:post_detail', pk=post.pk)
    else:
        form = PostForm(instance=post)

    return render(request, 'posts/post_form.html', {
        'form': form,
        'post': post,
        'title': 'Редактировать пост'
    })


@login_required
def post_delete(request, pk):
    """
    Удаление поста
    """
    post = get_object_or_404(Post, pk=pk)

    if post.author != request.user:
        messages.error(request, 'Вы не можете удалить этот пост')
        return redirect('posts:post_detail', pk=post.pk)

    if request.method == 'POST':
        post.delete()
        messages.success(request, 'Пост удален')
        return redirect('posts:post_list')

    return render(request, 'posts/post_confirm_delete.html', {'post': post})


@login_required
@require_POST
def comment_create(request, post_pk):
    post = get_object_or_404(Post, pk=post_pk)
    parent_id = request.POST.get('parent_id')

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post

        if parent_id:
            parent = get_object_or_404(Comment, pk=parent_id)
            comment.parent = parent

        comment.save()

        # Уведомление автору поста
        if post.author != request.user:
            create_notification(
                recipient=post.author,
                sender=request.user,
                notification_type='comment',
                title='Новый комментарий',
                message=f'@{request.user.username} прокомментировал ваш пост: "{comment.content[:50]}..."',
                link=f'/posts/post/{post.pk}/#comment-{comment.pk}',
                content_object=comment
            )

        # Уведомление автору родительского комментария (если это ответ)
        if parent_id and parent.author != request.user:
            create_notification(
                recipient=parent.author,
                sender=request.user,
                notification_type='comment',
                title='Ответ на комментарий',
                message=f'@{request.user.username} ответил на ваш комментарий: "{comment.content[:50]}..."',
                link=f'/posts/post/{post.pk}/#comment-{comment.pk}',
                content_object=comment
            )

        # Проверка на упоминания (@username)
        import re
        mentions = re.findall(r'@(\w+)', comment.content)
        for username in mentions:
            try:
                mentioned_user = User.objects.get(username=username)
                if mentioned_user != request.user and mentioned_user != post.author:
                    create_notification(
                        recipient=mentioned_user,
                        sender=request.user,
                        notification_type='mention',
                        title='Упоминание',
                        message=f'@{request.user.username} упомянул вас в комментарии',
                        link=f'/posts/post/{post.pk}/#comment-{comment.pk}',
                        content_object=comment
                    )
            except User.DoesNotExist:
                pass

        post.comments_count = post.comments.filter(is_deleted=False).count()
        post.save(update_fields=['comments_count'])

        messages.success(request, 'Комментарий добавлен')

    return redirect('posts:post_detail', pk=post_pk)


@login_required
@require_POST
def like_toggle(request):
    """
    Переключение лайка (AJAX)
    """
    try:
        content_type = request.POST.get('content_type')
        object_id = request.POST.get('object_id')
        like_type = request.POST.get('like_type', 'like')

        print(f"Получен запрос: content_type={content_type}, object_id={object_id}")  # Отладка

        if content_type not in ['post', 'comment']:
            return JsonResponse({'error': 'Invalid content type'}, status=400)

        # Проверяем существование объекта
        if content_type == 'post':
            obj = get_object_or_404(Post, pk=object_id)
        else:
            obj = get_object_or_404(Comment, pk=object_id)

        # Ищем существующий лайк
        like = Like.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id
        ).first()

        if like:
            # Если лайк уже есть - удаляем
            like.delete()
            action = 'removed'
        else:
            # Создаем новый лайк
            like = Like.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                like_type=like_type
            )
            action = 'added'

            # Уведомление автору поста
            if obj.author != request.user:
                from accounts.utils import create_notification
                create_notification(
                    recipient=obj.author,
                    sender=request.user,
                    notification_type='like',
                    title='Новый лайк',
                    message=f'@{request.user.username} оценил ваш пост',
                    link=f'/posts/post/{obj.pk}/'
                )

        # Обновляем счетчик
        likes_count = Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).count()

        if content_type == 'post':
            obj.likes_count = likes_count
        else:
            obj.likes_count = likes_count
        obj.save(update_fields=['likes_count'])

        return JsonResponse({
            'action': action,
            'likes_count': likes_count,
            'like_type': like_type
        })

    except Exception as e:
        print(f"Ошибка в like_toggle: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def bookmark_toggle(request, post_pk):
    """
    Добавление/удаление из избранного
    """
    post = get_object_or_404(Post, pk=post_pk)

    bookmark, created = Bookmark.objects.get_or_create(
        user=request.user,
        post=post
    )

    if not created:
        bookmark.delete()
        messages.info(request, 'Пост удален из избранного')
        action = 'removed'
    else:
        messages.success(request, 'Пост добавлен в избранное')
        action = 'added'

    # Если это AJAX запрос
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'action': action})

    return redirect('posts:post_detail', pk=post_pk)


@login_required
def bookmarks_list(request):
    """
    Список избранных постов пользователя
    """
    bookmarks = Bookmark.objects.filter(
        user=request.user
    ).select_related('post', 'post__author').order_by('-created_at')

    paginator = Paginator(bookmarks, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'posts/bookmarks.html', {'page_obj': page_obj})


def category_list(request):
    """Список всех категорий"""
    categories = Category.objects.all()
    return render(request, 'posts/category_list.html', {'categories': categories})


def category_detail(request, slug):
    """Детальная страница категории с постами"""
    category = get_object_or_404(Category, slug=slug)
    posts = category.posts.filter(status='published').order_by('-created_at')
    return render(request, 'posts/category_detail.html', {
        'category': category,
        'posts': posts,
    })


def search(request):
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'posts')
    sort = request.GET.get('sort', 'relevance')
    date_filter = request.GET.get('date', 'all')
    community_filter = request.GET.get('community', '')
    category_filter = request.GET.get('category', '')

    context = {
        'query': query,
        'type': search_type,
        'sort': sort,
        'date_filter': date_filter,
        'community_filter': community_filter,
        'category_filter': category_filter,
        'communities': Community.objects.filter(status='active')[:20],
        'categories': Category.objects.all()[:20],
    }

    results = []
    total_count = 0

    if query:
        if search_type == 'posts':
            results = Post.objects.filter(
                Q(title__icontains=query) | Q(content__icontains=query),
                status='published'
            ).select_related('author', 'community').prefetch_related('tags')

            # Фильтр по дате
            if date_filter == 'day':
                from django.utils import timezone
                from datetime import timedelta
                day_ago = timezone.now() - timedelta(days=1)
                results = results.filter(created_at__gte=day_ago)
            elif date_filter == 'week':
                from django.utils import timezone
                from datetime import timedelta
                week_ago = timezone.now() - timedelta(days=7)
                results = results.filter(created_at__gte=week_ago)
            elif date_filter == 'month':
                from django.utils import timezone
                from datetime import timedelta
                month_ago = timezone.now() - timedelta(days=30)
                results = results.filter(created_at__gte=month_ago)

            # Фильтр по сообществу
            if community_filter:
                results = results.filter(community__slug=community_filter)

            # Фильтр по категории
            if category_filter:
                results = results.filter(category__slug=category_filter)

            # Сортировка
            if sort == 'new':
                results = results.order_by('-created_at')
            elif sort == 'top':
                results = results.order_by('-likes_count', '-created_at')
            elif sort == 'comments':
                results = results.annotate(comment_count=Count('comments')).order_by('-comment_count', '-created_at')
            else:
                results = results.order_by('-created_at')

            total_count = results.count()
            context['posts_count'] = total_count

        elif search_type == 'communities':
            results = Community.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                status='active'
            ).annotate(members_count=Count('members'))

            if sort == 'popular':
                results = results.order_by('-members_count')
            elif sort == 'new':
                results = results.order_by('-created_at')
            else:
                results = results.order_by('name')

            total_count = results.count()
            context['communities_count'] = total_count

        elif search_type == 'users':
            results = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).select_related('profile')

            if sort == 'followers':
                results = results.annotate(followers_count=Count('profile__followers')).order_by('-followers_count')
            elif sort == 'new':
                results = results.order_by('-date_joined')
            else:
                results = results.order_by('username')

            total_count = results.count()
            context['users_count'] = total_count

        elif search_type == 'tags':
            results = Tag.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            ).annotate(posts_count=Count('posts'))

            if sort == 'popular':
                results = results.order_by('-posts_count')
            else:
                results = results.order_by('name')

            total_count = results.count()
            context['tags_count'] = total_count

        # Пагинация
        paginator = Paginator(results, 20)
        page = request.GET.get('page', 1)
        try:
            results_page = paginator.page(page)
        except:
            results_page = paginator.page(1)

        context['results'] = results_page
        context['is_paginated'] = results_page.has_other_pages()
        context['page_obj'] = results_page

    return render(request, 'posts/search.html', context)


@login_required
def category_create(request):
    """Создание новой категории (только для персонала)"""
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для создания категорий')
        return redirect('posts:category_list')

    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Категория "{category.name}" успешно создана')
            return redirect('posts:category_detail', slug=category.slug)
    else:
        form = CategoryForm()

    return render(request, 'posts/category_form.html', {'form': form, 'title': 'Создание категории'})


@login_required
def category_edit(request, slug):
    """Редактирование категории (только для персонала)"""
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для редактирования категорий')
        return redirect('posts:category_detail', slug=slug)

    category = get_object_or_404(Category, slug=slug)

    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Категория "{category.name}" успешно обновлена')
            return redirect('posts:category_detail', slug=category.slug)
    else:
        form = CategoryForm(instance=category)

    return render(request, 'posts/category_form.html', {
        'form': form,
        'category': category,
        'title': f'Редактирование "{category.name}"'
    })


def tag_list(request):
    """Список всех тегов"""
    tags = Tag.objects.annotate(posts_count=Count('posts')).order_by('-posts_count')
    return render(request, 'posts/tag_list.html', {'tags': tags})


def tag_detail(request, slug):
    """Детальная страница тега с постами"""
    tag = get_object_or_404(Tag, slug=slug)
    posts = tag.posts.filter(status='published').order_by('-created_at')
    is_following = False
    if request.user.is_authenticated:
        is_following = request.user.followed_tags.filter(id=tag.id).exists()
    return render(request, 'posts/tag_detail.html', {
        'tag': tag,
        'posts': posts,
        'is_following': is_following,
    })


@login_required
def tag_create(request):
    """Создание нового тега (доступно всем авторизованным пользователям)"""
    if request.method == 'POST':
        form = TagForm(request.POST)
        if form.is_valid():
            tag = form.save()
            messages.success(request, f'Тег "#{tag.name}" успешно создан')
            return redirect('posts:tag_detail', slug=tag.slug)
    else:
        form = TagForm()

    return render(request, 'posts/tag_form.html', {'form': form, 'title': 'Создание тега'})


@login_required
def tag_edit(request, slug):
    """Редактирование тега (только для персонала или создателя)"""
    tag = get_object_or_404(Tag, slug=slug)

    if not request.user.is_staff and request.user != tag.creator:
        messages.error(request, 'У вас нет прав для редактирования этого тега')
        return redirect('posts:tag_detail', slug=slug)

    if request.method == 'POST':
        form = TagForm(request.POST, instance=tag)
        if form.is_valid():
            tag = form.save()
            messages.success(request, f'Тег "#{tag.name}" успешно обновлен')
            return redirect('posts:tag_detail', slug=tag.slug)
    else:
        form = TagForm(instance=tag)

    return render(request, 'posts/tag_form.html', {
        'form': form,
        'tag': tag,
        'title': f'Редактирование тега "#{tag.name}"'
    })


@login_required
def tag_delete(request, slug):
    """Удаление тега (только для персонала)"""
    if not request.user.is_staff:
        messages.error(request, 'У вас нет прав для удаления тегов')
        return redirect('posts:tag_detail', slug=slug)

    tag = get_object_or_404(Tag, slug=slug)

    if request.method == 'POST':
        tag_name = tag.name
        tag.delete()
        messages.success(request, f'Тег "#{tag_name}" успешно удален')
        return redirect('posts:tag_list')

    return render(request, 'posts/tag_confirm_delete.html', {'tag': tag})


def search_ajax(request):
    """AJAX поиск для мгновенных результатов"""
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'posts')

    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    if search_type == 'users':
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:10]

        for user in users:
            results.append({
                'id': user.id,
                'username': user.username,
                'full_name': user.get_full_name() or user.username,
                'avatar': user.profile.avatar.url if user.profile.avatar else None,
                'url': f'/accounts/profile/{user.username}/'
            })

    elif search_type == 'communities':
        communities = Community.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )[:10]

        for community in communities:
            results.append({
                'id': community.id,
                'name': community.name,
                'description': community.description[:100],
                'avatar': community.avatar.url if community.avatar else None,
                'url': f'/communities/{community.slug}/'
            })

    return JsonResponse({'results': results})


@login_required
@require_POST
def tag_create_ajax(request):
    """Создание тега через AJAX"""
    name = request.POST.get('name', '').strip()

    if not name:
        return JsonResponse({'success': False, 'error': 'Введите название тега'}, status=400)

    if len(name) < 2:
        return JsonResponse({'success': False, 'error': 'Название тега должно быть не менее 2 символов'}, status=400)

    if len(name) > 50:
        return JsonResponse({'success': False, 'error': 'Название тега должно быть не более 50 символов'}, status=400)

    # Проверяем, существует ли уже такой тег
    existing_tag = Tag.objects.filter(name__iexact=name).first()
    if existing_tag:
        return JsonResponse({
            'success': True,
            'tag': {
                'id': existing_tag.id,
                'name': existing_tag.name,
                'slug': existing_tag.slug if existing_tag.slug else '',
            },
            'message': 'Тег уже существует'
        })

    # Генерируем slug (транслитерация или UUID если не получается)
    slug = slugify(name)
    if not slug:
        # Если slugify не смог (например, только кириллица), используем UUID
        slug = f"tag-{uuid.uuid4().hex[:8]}"

    # Проверяем уникальность slug
    original_slug = slug
    counter = 1
    while Tag.objects.filter(slug=slug).exists():
        slug = f"{original_slug}-{counter}"
        counter += 1

    # Создаем тег
    tag = Tag.objects.create(
        name=name,
        slug=slug
    )

    return JsonResponse({
        'success': True,
        'tag': {
            'id': tag.id,
            'name': tag.name,
            'slug': tag.slug,
        },
        'message': f'Тег "#{tag.name}" успешно создан'
    })


def tag_popular(request):
    """Возвращает популярные теги для подсказок"""
    tags = Tag.objects.annotate(
        posts_count=Count('posts')
    ).order_by('-posts_count')[:10]

    return JsonResponse({
        'tags': [
            {
                'id': tag.id,
                'name': tag.name,
                'slug': tag.slug,
                'posts_count': tag.posts_count,
            }
            for tag in tags
        ]
    })

@login_required
def post_preview(request):
    """Предпросмотр Markdown"""
    import markdown
    try:
        data = json.loads(request.body)
        content = data.get('content', '')
        html = markdown.markdown(content, extensions=['fenced_code', 'tables', 'nl2br'])
        return JsonResponse({'html': html})
    except Exception as e:
        return JsonResponse({'html': '<p>Ошибка предпросмотра</p>'})


def tag_search(request):
    """Поиск тегов для автодополнения"""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'tags': []})

    tags = Tag.objects.filter(
        name__icontains=query
    ).annotate(
        posts_count=Count('posts')
    ).order_by('-posts_count')[:8]

    return JsonResponse({
        'tags': [
            {
                'id': tag.id,
                'name': tag.name,
                'slug': tag.slug,
                'posts_count': tag.posts_count,
            }
            for tag in tags
        ]
    })


def test_view(request):
    """Временная страница для теста нового дизайна"""
    posts = Post.objects.filter(status='published').order_by('-created_at')[:10]
    return render(request, 'posts/feed.html', {
        'posts': posts,
        'page_obj': None,
        'is_paginated': False,
        'popular_communities': Community.objects.all()[:5],
        'popular_tags': Tag.objects.all()[:10],
    })