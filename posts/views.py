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

from accounts.models import Notification
from communities.models import Community
from .models import Post, Comment, Like, Category, Tag, Bookmark, PostView
from .forms import PostForm, CommentForm, PostSearchForm, TagForm, CategoryForm
from accounts.utils import create_notification
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage


User = get_user_model()


# posts/views.py
def post_list(request):
    # Базовый queryset
    posts = Post.objects.select_related(
        'author', 'author__profile', 'community_post'
    ).prefetch_related(
        'tags', 'comments'
    ).filter(status='published')

    # Фильтрация по ленте
    feed = request.GET.get('feed', 'all')
    if feed == 'following' and request.user.is_authenticated:
        following_users = request.user.profile.following.all()
        following_communities = Community.objects.filter(members=request.user)
        posts = posts.filter(
            Q(author__in=following_users) |
            Q(community__in=following_communities)
        )
    elif feed == 'popular':
        posts = posts.annotate(
            popularity_score=Count('likes') + Count('comments') * 2
        ).order_by('-popularity_score', '-created_at')

    # Сортировка
    sort = request.GET.get('sort', 'new')
    if sort == 'top':
        from django.utils import timezone
        from datetime import timedelta
        day_ago = timezone.now() - timedelta(days=1)
        posts = posts.filter(created_at__gte=day_ago).order_by('-likes_count', '-created_at')
    elif sort == 'hot':
        posts = posts.order_by('-comments_count', '-created_at')
    else:
        posts = posts.order_by('-created_at')

    # Пагинация
    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)

    try:
        posts_page = paginator.page(page)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)

    # Популярные сообщества - используем count_members чтобы избежать конфликта
    popular_communities = Community.objects.annotate(
        count_members=Count('members')
    ).order_by('-count_members')[:10]

    # Популярные теги
    popular_tags = Tag.objects.annotate(
        count_posts=Count('posts')
    ).order_by('-count_posts')[:10]

    context = {
        'posts': posts_page,
        'is_paginated': posts_page.has_other_pages(),
        'page_obj': posts_page,
        'category': category if 'category' in locals() else None,
        'tag': tag if 'tag' in locals() else None,
        'popular_communities': popular_communities,
        'popular_tags': popular_tags,
    }

    return render(request, 'posts/post_list.html', context)


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
    """
    Создание нового поста
    """
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()  # Сохраняем ManyToMany поля (теги)
            messages.success(request, 'Пост успешно создан!')
            return redirect('posts:post_detail', pk=post.pk)
        else:
            # Если форма не валидна, показываем ошибки
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = PostForm()

    return render(request, 'posts/post_form.html', {
        'form': form,
        'title': 'Создать пост'
    })

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
    """
    Список всех категорий
    """
    categories = Category.objects.filter(parent=None).prefetch_related('children')
    return render(request, 'posts/category_list.html', {'categories': categories})


def category_detail(request, slug):
    """
    Детальная страница категории
    """
    category = get_object_or_404(Category, slug=slug)
    posts = Post.objects.filter(
        category=category,
        status='published'
    ).select_related('author').order_by('-created_at')[:10]

    return render(request, 'posts/category_detail.html', {
        'category': category,
        'posts': posts
    })


def search(request):
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'posts')

    context = {
        'query': query,
        'type': search_type,
    }

    if query:
        if search_type == 'posts':
            # Поиск по постам
            results = Post.objects.filter(
                Q(title__icontains=query) |
                Q(content__icontains=query)
            ).select_related('author', 'community').prefetch_related('tags', 'likes')

            context['posts_count'] = results.count()
            context['results'] = results[:50]

        elif search_type == 'communities':
            # Поиск по сообществам
            results = Community.objects.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            ).annotate(members_count=Count('members'))

            context['communities_count'] = results.count()
            context['results'] = results[:30]

        elif search_type == 'users':
            # Поиск по пользователям
            results = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).select_related('profile')

            context['users_count'] = results.count()
            context['results'] = results[:30]

        elif search_type == 'tags':
            # Поиск по тегам
            results = Tag.objects.filter(
                Q(name__icontains=query) |
                Q(description__icontains=query)
            ).annotate(posts_count=Count('posts'))

            context['tags_count'] = results.count()
            context['results'] = results[:50]

    # Пагинация
    page = request.GET.get('page', 1)
    # Добавь пагинацию здесь

    return render(request, 'posts/search.html', context)


@login_required
def category_create(request):
    """
    Создание новой категории (доступно всем авторизованным)
    """
    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()
            messages.success(request, f'Категория "{category.name}" создана')
            return redirect('posts:category_detail', slug=category.slug)
    else:
        form = CategoryForm(user=request.user)

    return render(request, 'posts/category_form.html', {'form': form})


@login_required
def category_edit(request, slug):
    """
    Редактирование категории (только создатель или админ)
    """
    category = get_object_or_404(Category, slug=slug)

    # Проверяем права
    if category.created_by != request.user and not request.user.is_staff:
        messages.error(request, 'У вас нет прав для редактирования этой категории')
        return redirect('posts:category_detail', slug=category.slug)

    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category, user=request.user)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Категория "{category.name}" обновлена')
            return redirect('posts:category_detail', slug=category.slug)
    else:
        form = CategoryForm(instance=category, user=request.user)

    return render(request, 'posts/category_form.html', {'form': form, 'category': category})


def tag_list(request):
    """
    Список всех тегов с количеством постов
    """
    # Получаем все теги с подсчетом количества постов
    tags = Tag.objects.annotate(
        posts_count=Count('posts', filter=Q(posts__status='published'))
    ).order_by('-posts_count', 'name')

    # Поиск по тегам
    query = request.GET.get('q')
    if query:
        tags = tags.filter(name__icontains=query)

    # Пагинация
    paginator = Paginator(tags, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Для AJAX запросов
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        data = [{
            'id': tag.id,
            'name': tag.name,
            'slug': tag.slug,
            'posts_count': tag.posts_count
        } for tag in tags[:10]]
        return JsonResponse({'tags': data})

    # Статистика
    total_tags = Tag.objects.count()
    tags_with_posts = tags.filter(posts_count__gt=0).count()

    context = {
        'page_obj': page_obj,
        'query': query,
        'total_tags': total_tags,
        'tags_with_posts': tags_with_posts,
    }
    return render(request, 'posts/tag_list.html', context)


def tag_detail(request, slug):
    """
    Детальная страница тега
    """
    tag = get_object_or_404(Tag, slug=slug)
    posts = Post.objects.filter(
        tags=tag,
        status='published'
    ).select_related('author').prefetch_related('tags').order_by('-created_at')

    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Похожие теги
    similar_tags = Tag.objects.filter(
        posts__in=posts[:20]
    ).exclude(id=tag.id).annotate(
        common_count=Count('posts')
    ).order_by('-common_count')[:10]

    context = {
        'tag': tag,
        'page_obj': page_obj,
        'posts_count': posts.count(),
        'similar_tags': similar_tags,
    }
    return render(request, 'posts/tag_detail.html', context)


@login_required
def tag_create(request):
    """
    Создание нового тега (доступно всем авторизованным)
    """
    if request.method == 'POST':
        form = TagForm(request.POST, user=request.user)
        if form.is_valid():
            tag = form.save(commit=False)
            tag.created_by = request.user
            tag.save()
            messages.success(request, f'Тег "{tag.name}" успешно создан')
            return redirect('posts:tag_detail', slug=tag.slug)
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме')
    else:
        form = TagForm(user=request.user)

    return render(request, 'posts/tag_form.html', {'form': form, 'is_create': True})


@login_required
def tag_edit(request, slug):
    """
    Редактирование тега (только создатель или админ)
    """
    tag = get_object_or_404(Tag, slug=slug)

    # Проверяем права
    if tag.created_by != request.user and not request.user.is_staff:
        messages.error(request, 'У вас нет прав для редактирования этого тега')
        return redirect('posts:tag_detail', slug=tag.slug)

    if request.method == 'POST':
        form = TagForm(request.POST, instance=tag, user=request.user)
        if form.is_valid():
            tag = form.save()
            messages.success(request, f'Тег "{tag.name}" обновлен')
            return redirect('posts:tag_detail', slug=tag.slug)
    else:
        form = TagForm(instance=tag, user=request.user)

    return render(request, 'posts/tag_form.html', {'form': form, 'tag': tag})


@login_required
def tag_delete(request, slug):
    """
    Удаление тега (только создатель или админ)
    """
    tag = get_object_or_404(Tag, slug=slug)

    # Проверяем права
    if tag.created_by != request.user and not request.user.is_staff:
        messages.error(request, 'У вас нет прав для удаления этого тега')
        return redirect('posts:tag_detail', slug=tag.slug)

    if request.method == 'POST':
        name = tag.name
        tag.delete()
        messages.success(request, f'Тег "{name}" удален')
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