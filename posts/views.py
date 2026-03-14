from datetime import timedelta

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, F, OuterRef, Subquery
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from accounts.models import Notification
from communities.models import Community
from .models import Post, Comment, Like, Category, Tag, Bookmark, PostView
from .forms import PostForm, CommentForm, PostSearchForm, TagForm, CategoryForm
from accounts.utils import create_notification

User = get_user_model()


def post_list(request):
    """
    Список постов (главная лента)
    """
    # Базовый queryset
    posts = Post.objects.filter(status='published').select_related(
        'author', 'category'
    ).prefetch_related('tags')

    # Поиск и фильтрация
    search_form = PostSearchForm(request.GET or None)

    if search_form.is_valid():
        query = search_form.cleaned_data.get('query')
        category = search_form.cleaned_data.get('category')
        tag = search_form.cleaned_data.get('tag')
        author = search_form.cleaned_data.get('author')
        date_from = search_form.cleaned_data.get('date_from')
        date_to = search_form.cleaned_data.get('date_to')
        ordering = search_form.cleaned_data.get('ordering')

        if query:
            posts = posts.filter(
                Q(title__icontains=query) |
                Q(content__icontains=query)
            )
        if category:
            posts = posts.filter(category=category)
        if tag:
            posts = posts.filter(tags=tag)
        if author:
            posts = posts.filter(author__username__icontains=author)
        if date_from:
            posts = posts.filter(created_at__date__gte=date_from)
        if date_to:
            posts = posts.filter(created_at__date__lte=date_to)

        # Сортировка
        if ordering:
            posts = posts.order_by(ordering)
        else:
            posts = posts.order_by('-created_at')
    else:
        # Если форма не валидна, сортируем по умолчанию
        posts = posts.order_by('-created_at')

    # Пагинация
    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Получаем популярные теги для сайдбара
    popular_tags = Tag.objects.annotate(
        posts_count=Count('posts')
    ).filter(posts_count__gt=0).order_by('-posts_count')[:15]

    # Категории для навигации
    categories = Category.objects.filter(parent=None)[:5]

    # Общее количество пользователей
    total_users = User.objects.count()

    # Онлайн пользователи (активные за последние 5 минут)
    online_users = User.objects.filter(
        last_activity__gte=timezone.now() - timedelta(minutes=5)
    )[:10]

    # Рекомендуемые сообщества
    recommended_communities = Community.objects.filter(
        status='active'
    ).order_by('-members_count')[:5]

    # Топ постов недели
    week_ago = timezone.now() - timedelta(days=7)
    top_posts = Post.objects.filter(
        status='published',
        created_at__gte=week_ago
    ).order_by('-views_count', '-comments_count')[:5]

    # Проверяем лайки для каждого поста (если пользователь авторизован)
    if request.user.is_authenticated:
        liked_posts = Like.objects.filter(
            user=request.user,
            content_type='post'
        ).values_list('object_id', flat=True)

        bookmarked_posts = Bookmark.objects.filter(
            user=request.user
        ).values_list('post_id', flat=True)
    else:
        liked_posts = []
        bookmarked_posts = []

    # Добавляем информацию о лайках и закладках к каждому посту
    for post in page_obj:
        post.user_like = post.pk in liked_posts
        post.is_bookmarked = post.pk in bookmarked_posts

    # Добавляем в контекст
    context = {
        'page_obj': page_obj,
        'search_form': search_form,
        'popular_tags': popular_tags,
        'categories': categories,
        'total_users': total_users,
        'online_users': online_users,
        'recommended_communities': recommended_communities,
        'top_posts': top_posts,
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
    """
    Глобальный поиск
    """
    query = request.GET.get('q', '')
    search_type = request.GET.get('type', 'all')

    posts = []
    comments = []
    users = []
    total_results = 0

    if query:
        if search_type in ['all', 'posts']:
            posts = Post.objects.filter(
                Q(title__icontains=query) | Q(content__icontains=query),
                status='published'
            ).select_related('author').order_by('-created_at')
            total_results += posts.count()

        if search_type in ['all', 'comments']:
            comments = Comment.objects.filter(
                content__icontains=query,
                is_deleted=False
            ).select_related('author', 'post').order_by('-created_at')
            total_results += comments.count()

        if search_type in ['all', 'users']:
            users = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            )
            total_results += users.count()

    context = {
        'query': query,
        'search_type': search_type,
        'posts': posts[:10] if posts else [],
        'comments': comments[:10] if comments else [],
        'users': users[:10] if users else [],
        'total_results': total_results,
    }
    return render(request, 'posts/search_results.html', context)


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