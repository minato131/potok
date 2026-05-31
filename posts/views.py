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
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseRedirect
from .models import Post, Tag, Comment
import json
from accounts.models import Friendship
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
from django.db.models import Case, When, Value, IntegerField

from django.db.models import Count, Q, Value, Case, When, IntegerField, F
from django.db.models.functions import Coalesce
from datetime import timedelta
User = get_user_model()


def post_list(request):
    posts = Post.objects.select_related(
        'author', 'author__profile', 'category'
    ).prefetch_related(
        'tags', 'comments'
    ).filter(status='published', is_hidden=False)

    feed = request.GET.get('feed', 'all')
    sort = request.GET.get('sort', 'new')
    period = request.GET.get('period', 'week')

    if feed == 'following' and request.user.is_authenticated:
        friend_ids = list(Friendship.objects.filter(user=request.user).values_list('friend_id', flat=True))
        following_ids = list(request.user.profile.following.exclude(id__in=friend_ids).values_list('id', flat=True))
        community_ids = list(Community.objects.filter(members=request.user).values_list('id', flat=True))
        community_post_ids = list(CommunityPost.objects.filter(community_id__in=community_ids).values_list('post_id', flat=True))

        posts = posts.filter(
            Q(author_id__in=friend_ids) |
            Q(id__in=community_post_ids) |
            Q(author_id__in=following_ids)
        ).annotate(
            priority=Case(
                When(author_id__in=friend_ids, then=Value(0)),
                When(id__in=community_post_ids, then=Value(1)),
                default=Value(2),
                output_field=IntegerField()
            )
        ).order_by('priority', '-created_at')

    elif feed == 'popular':
        if period == 'day':
            date_from = timezone.now() - timedelta(days=1)
        elif period == 'month':
            date_from = timezone.now() - timedelta(days=30)
        elif period == 'year':
            date_from = timezone.now() - timedelta(days=365)
        else:
            date_from = timezone.now() - timedelta(days=7)
        posts = posts.filter(created_at__gte=date_from).order_by('-likes_count', '-created_at')



    elif feed == 'recommended' and request.user.is_authenticated:

        posts = get_recommended_posts(request)

    else:
        if sort == 'top':
            # Лучшие = много лайков + много просмотров
            posts = posts.annotate(
                score=F('likes_count') * 2 + F('views_count') + F('comments_count') * 2
            ).order_by('-score', '-created_at')
        elif sort == 'hot':
            # Обсуждаемые = много комментариев
            posts = posts.annotate(
                comment_count=Count('comments')
            ).order_by('-comment_count', '-created_at')

    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    try:
        posts_page = paginator.page(page)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)

    liked_post_ids = set()
    bookmarked_post_ids = set()
    if request.user.is_authenticated:
        post_ids = [p.id for p in posts_page]
        liked_post_ids = set(Like.objects.filter(user=request.user, content_type='post', object_id__in=post_ids).values_list('object_id', flat=True))
        bookmarked_post_ids = set(Bookmark.objects.filter(user=request.user, post_id__in=post_ids).values_list('post_id', flat=True))

    friend_ids = set()
    if request.user.is_authenticated:
        friend_ids = set(Friendship.objects.filter(user=request.user).values_list('friend_id', flat=True))

    context = {
        'posts': posts_page,
        'is_paginated': posts_page.has_other_pages(),
        'page_obj': posts_page,
        'liked_post_ids': liked_post_ids,
        'bookmarked_post_ids': bookmarked_post_ids,
        'current_feed': feed,
        'current_sort': sort,
        'current_period': period,
        'friend_ids': friend_ids,
    }
    return render(request, 'posts/post_list.html', context)

def post_detail(request, pk):
    post = get_object_or_404(
        Post.objects.select_related('author', 'category'),
        pk=pk,
        is_hidden=False
    )

    if post.status != 'published' and post.author != request.user:
        return render(request, '404.html', status=404)

    if request.user.is_authenticated:
        recent_view = PostView.objects.filter(
            post=post, user=request.user,
            viewed_at__gte=timezone.now() - timedelta(hours=1)
        ).exists()
        if not recent_view:
            PostView.objects.create(post=post, user=request.user)
            post.increment_views()
    elif not request.session.get(f'viewed_post_{pk}'):
        PostView.objects.create(post=post, ip_address=request.META.get('REMOTE_ADDR'))
        post.increment_views()
        request.session[f'viewed_post_{pk}'] = True

    comments = post.comments.filter(parent=None, is_deleted=False, is_hidden=False).prefetch_related('replies')
    comment_form = CommentForm()

    user_like = None
    if request.user.is_authenticated:
        user_like = Like.objects.filter(user=request.user, content_type='post', object_id=post.id).first()

    is_bookmarked = False
    if request.user.is_authenticated:
        is_bookmarked = Bookmark.objects.filter(user=request.user, post=post).exists()

    is_subscribed = False
    if request.user.is_authenticated:
        is_subscribed = request.user.profile.following.filter(id=post.author.id).exists()

    liked_comment_ids = set()
    if request.user.is_authenticated:
        comment_ids = list(comments.values_list('id', flat=True))
        liked_comment_ids = set(Like.objects.filter(
            user=request.user, content_type='comment', object_id__in=comment_ids
        ).values_list('object_id', flat=True))

    friend_ids = set()
    if request.user.is_authenticated:
        friend_ids = set(Friendship.objects.filter(user=request.user).values_list('friend_id', flat=True))

    context = {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'user_like': user_like,
        'is_bookmarked': is_bookmarked,
        'is_subscribed': is_subscribed,
        'liked_comment_ids': liked_comment_ids,
        'friend_ids': friend_ids,
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


# posts/views.py - в функции post_edit
@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)

    # Проверка прав
    if not (post.author == request.user or request.user.is_staff or request.user.is_platform_moderator):
        messages.error(request, 'Вы не можете редактировать этот пост')
        return redirect('posts:post_detail', pk=post.pk)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            was_hidden = post.is_hidden

            # Если пост был скрыт модерацией и автор его редактирует - снимаем блокировку
            if was_hidden and request.user == post.author:
                post.is_hidden = False

                # ========== ОБНОВЛЯЕМ СТАТУС ВСЕХ ЖАЛОБ НА ЭТОТ ПОСТ ==========
                from moderation.models import Report
                from django.contrib.contenttypes.models import ContentType
                from accounts.utils import create_notification

                post_ct = ContentType.objects.get_for_model(Post)

                # Обновляем ВСЕ жалобы на этот пост (не только approved)
                # pending тоже переносим в снятые, потому что контент уже исправлен
                reports = Report.objects.filter(
                    content_type=post_ct,
                    object_id=post.id
                ).exclude(status='rejected')  # отклонённые не трогаем

                for report in reports:
                    old_status = report.status
                    report.status = 'lifted'
                    report.moderation_comment = 'Контент исправлен автором, жалоба снята'
                    report.save()

                    # Уведомляем автора жалобы, если она была approved или pending
                    if old_status in ['approved', 'pending']:
                        create_notification(
                            recipient=report.reporter,
                            sender=post.author,
                            notification_type='moderation',
                            title='📋 Жалоба снята',
                            message=f'Пользователь @{post.author.username} отредактировал пост "{post.title}", на который вы жаловались. Жалоба закрыта.',
                            link=f'/post/{post.id}/'
                        )

                # Уведомляем модераторов (только по approved)
                for report in reports.filter(status='approved'):
                    if report.moderated_by:
                        create_notification(
                            recipient=report.moderated_by,
                            sender=post.author,
                            notification_type='moderation',
                            title='📝 Контент исправлен',
                            message=f'Пользователь {post.author.username} отредактировал пост "{post.title}", который был скрыт модерацией. Пост восстановлен.',
                            link=f'/post/{post.id}/'
                        )

            post.save()
            form.save_m2m()
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

    form = CommentForm(request.POST, request.FILES)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post

        # Обработка загруженных файлов
        if request.FILES.get('image'):
            comment.image = request.FILES['image']
        if request.FILES.get('video'):
            comment.video = request.FILES['video']

        if parent_id:
            parent = get_object_or_404(Comment, pk=parent_id)
            comment.parent = parent

        comment.save()

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

        # Если AJAX — вернуть JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'comment_id': comment.id})

        messages.success(request, 'Комментарий добавлен')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            errors = {k: v[0] for k, v in form.errors.items()}
            return JsonResponse({'success': False, 'errors': errors}, status=400)

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

        print(f"Получен запрос: content_type={content_type}, object_id={object_id}")

        if content_type not in ['post', 'comment']:
            return JsonResponse({'error': 'Invalid content type'}, status=400)

        # Получаем объект
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
            Like.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                like_type=like_type
            )
            action = 'added'

        # Считаем лайки
        likes_count = Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).count()

        # Обновляем счетчик в объекте
        obj.likes_count = likes_count
        obj.save(update_fields=['likes_count'])

        return JsonResponse({
            'action': action,
            'likes_count': likes_count,
            'status': 'ok'
        })

    except Exception as e:
        print(f"Ошибка в like_toggle: {e}")
        import traceback
        traceback.print_exc()
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
        user=request.user,
        post__is_hidden=False
    ).select_related('post', 'post__author', 'post__author__profile')

    # Сортировка
    sort = request.GET.get('sort', 'new')
    if sort == 'old':
        bookmarks = bookmarks.order_by('created_at')
    else:
        bookmarks = bookmarks.order_by('-created_at')



    # Пагинация
    paginator = Paginator(bookmarks, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'posts/bookmarks.html', {
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    })


@login_required
@require_POST
def bookmark_remove(request, bookmark_id):
    """
    Удаление одной закладки
    """
    bookmark = get_object_or_404(Bookmark, id=bookmark_id, user=request.user)
    bookmark.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def bookmarks_clear(request):
    """
    Очистка всех закладок пользователя
    """
    Bookmark.objects.filter(user=request.user).delete()
    return JsonResponse({'success': True})


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
                status='published',
                is_hidden=False
            ).select_related('author').prefetch_related('tags')

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
                results = results.filter(community_post__community__slug=community_filter)

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
            )

            if sort == 'popular':
                results = results.order_by('-members_count')
            elif sort == 'new':
                results = results.order_by('-created_at')
            else:
                results = results.order_by('name')

            total_count = results.count()
            context['communities_count'] = total_count
            # Показывать теги рядом с результатами постов
            tag_results = Tag.objects.filter(name__icontains=query)[:10]
            context['tag_results'] = tag_results

        elif search_type == 'users':
            results = User.objects.filter(
                Q(username__icontains=query) |
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).select_related('profile')

            if sort == 'followers':
                results = results.annotate(followers_count=Count('profile_followers')).order_by('-followers_count')
            elif sort == 'new':
                results = results.order_by('-date_joined')
            else:
                results = results.order_by('username')

            total_count = results.count()
            context['users_count'] = total_count


        elif search_type == 'tags':
            results = Tag.objects.filter(
                Q(name__icontains=query)
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


def tag_posts(request, tag_name):
    """Страница постов по тегу"""
    from django.core.paginator import Paginator
    from .models import Post, Tag

    try:
        tag = Tag.objects.get(name__iexact=tag_name)
    except Tag.DoesNotExist:
        messages.error(request, f'Тег "{tag_name}" не найден')
        return HttpResponseRedirect(reverse('posts:post_list'))

    posts = Post.objects.filter(
        tags=tag,
        status='published',
        is_hidden=False
    ).select_related('author').prefetch_related('tags').order_by('-created_at')

    paginator = Paginator(posts, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'tag': tag,
        'page_obj': page_obj,
        'posts': page_obj,
    }

    return render(request, 'posts/tag_posts.html', context)


def tag_list(request):
    tags = Tag.objects.annotate(posts_count=Count('posts')).filter(posts_count__gt=0)
    popular_tags = tags.order_by('-posts_count')[:10]

    context = {
        'tags': tags,
        'popular_tags': popular_tags,
    }
    return render(request, 'posts/tag_list.html', context)


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    posts = Post.objects.filter(tags=tag, status='published', is_hidden=False).select_related('author',
                                                                                              'author__profile').order_by(
        '-created_at')

    paginator = Paginator(posts, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'posts/tag_detail.html', {
        'tag': tag,
        'posts': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'page_obj': page_obj,
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
    search_type = request.GET.get('type', 'all')

    if len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    # Ищем пользователей
    if search_type in ['all', 'users']:
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )[:10]

        for user in users:
            avatar_url = ''
            if hasattr(user, 'profile') and user.profile.avatar:
                avatar_url = user.profile.avatar.url
            results.append({
                'id': user.id,
                'name': user.get_full_name() or user.username,
                'full_name': user.get_full_name() or user.username,
                'username': user.username,
                'avatar': avatar_url,
                'url': f'/accounts/profile/{user.username}/',
                'type': 'user',
                'type_display': 'Пользователь',
            })

    # Ищем сообщества
    if search_type in ['all', 'communities']:
        communities = Community.objects.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )[:10]

        for community in communities:
            results.append({
                'id': community.id,
                'name': community.name,
                'avatar': community.avatar.url if community.avatar else '',
                'url': f'/communities/{community.slug}/',
                'type': 'community',
                'type_display': 'Сообщество',
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


def get_recommended_posts(request, limit=20):
    """
    Упрощённая рекомендательная система
    """
    user = request.user

    # ID постов, которые пользователь уже лайкнул
    liked_post_ids = list(Like.objects.filter(user=user, content_type='post').values_list('object_id', flat=True))

    # ID просмотренных постов
    viewed_post_ids = list(PostView.objects.filter(user=user).values_list('post_id', flat=True).distinct())

    print(f"DEBUG: liked count = {len(liked_post_ids)}")
    print(f"DEBUG: viewed count = {len(viewed_post_ids)}")

    # Если есть лайки - получаем теги и категории из лайкнутых постов
    if liked_post_ids:
        # Теги из лайкнутых постов
        user_tags = Tag.objects.filter(posts__id__in=liked_post_ids).distinct()
        print(f"DEBUG: tags found = {user_tags.count()}")

        # Категории из лайкнутых постов
        user_categories = Category.objects.filter(posts__id__in=liked_post_ids).distinct()
        print(f"DEBUG: categories found = {user_categories.count()}")

        # Рекомендации по тегам и категориям
        recommendations = Post.objects.filter(
            status='published',
            is_hidden=False
        ).exclude(
            author=user
        ).exclude(
            id__in=liked_post_ids
        )

        # Добавляем фильтр по тегам или категориям
        if user_tags.exists() or user_categories.exists():
            recommendations = recommendations.filter(
                Q(tags__in=user_tags) | Q(category__in=user_categories)
            ).distinct()
            print(f"DEBUG: recommendations after tags/cats = {recommendations.count()}")

        # Исключаем просмотренные
        if viewed_post_ids:
            recommendations = recommendations.exclude(id__in=viewed_post_ids)
            print(f"DEBUG: after excluding viewed = {recommendations.count()}")

        # Сортируем
        recommendations = recommendations.order_by('-likes_count', '-created_at')

        if recommendations.exists():
            return recommendations[:limit]

    # Если нет рекомендаций - показываем популярные посты, которые пользователь не видел
    fallback_posts = Post.objects.filter(
        status='published',
        is_hidden=False
    ).exclude(
        author=user
    ).exclude(
        id__in=liked_post_ids
    )

    if viewed_post_ids:
        fallback_posts = fallback_posts.exclude(id__in=viewed_post_ids)

    print(f"DEBUG: fallback posts count = {fallback_posts.count()}")

    return fallback_posts.order_by('-likes_count', '-created_at')[:limit]


@login_required
def recommended_posts_api(request):
    """API для получения рекомендаций через AJAX (для бесконечной прокрутки)"""
    page = int(request.GET.get('page', 1))
    per_page = 10

    recommendations = get_recommended_posts(request, limit=per_page * page)

    # Пагинация
    start = (page - 1) * per_page
    end = start + per_page
    page_posts = recommendations[start:end]

    # Формируем HTML для новых постов
    from django.template.loader import render_to_string
    html = render_to_string('posts/_post_items.html', {
        'posts': page_posts,
        'liked_post_ids': set(),
        'bookmarked_post_ids': set(),
    }, request=request)

    return JsonResponse({
        'html': html,
        'has_more': len(recommendations) > end,
        'next_page': page + 1 if len(recommendations) > end else None
    })


def post_likes_modal(request, post_id):
    """Возвращает JSON со списком лайкнувших"""
    from django.http import JsonResponse
    from django.contrib.auth import get_user_model

    User = get_user_model()
    post = get_object_or_404(Post, id=post_id)

    # Получаем пользователей, которые лайкнули пост
    likes = Like.objects.filter(
        content_type='post',
        object_id=post.id
    ).select_related('user', 'user__profile').order_by('-created_at')

    # Формируем список пользователей
    users_list = []
    for like in likes:
        user = like.user
        users_list.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'avatar': user.profile.avatar.url if user.profile.avatar else None,
            'profile_url': f'/accounts/profile/{user.username}/'
        })

    return JsonResponse({
        'users': users_list,
        'total': len(users_list)
    })


@login_required
def comment_edit(request, comment_id):
    """Редактирование комментария"""
    from posts.models import Comment
    from django.shortcuts import get_object_or_404, redirect
    from django.contrib import messages

    comment = get_object_or_404(Comment, id=comment_id)
    post = comment.post

    # Проверка прав
    if not (comment.author == request.user or request.user.is_staff or request.user.is_platform_moderator):
        messages.error(request, 'Вы не можете редактировать этот комментарий')
        return redirect('posts:post_detail', pk=post.id)

    # Получаем информацию о блокировке
    moderation_info = None
    if comment.is_hidden:
        from moderation.models import Report
        from django.contrib.contenttypes.models import ContentType
        ct = ContentType.objects.get_for_model(Comment)
        reports = Report.objects.filter(
            content_type=ct,
            object_id=comment.id,
            status='approved'
        ).select_related('moderated_by')
        if reports.exists():
            report = reports.first()
            moderation_info = {
                'reason': report.get_report_type_display(),
                'comment': report.moderation_comment,
                'moderator': report.moderated_by,
                'date': report.moderated_at,
            }

    if request.method == 'POST':
        content = request.POST.get('content', '')
        if content.strip():
            was_hidden = comment.is_hidden
            comment.content = content

            # Если комментарий был скрыт модерацией и автор его редактирует - снимаем блокировку
            if was_hidden and request.user == comment.author:
                comment.is_hidden = False

                # Обновляем статус жалоб
                from moderation.models import Report
                from django.contrib.contenttypes.models import ContentType
                from accounts.utils import create_notification

                ct = ContentType.objects.get_for_model(Comment)
                reports = Report.objects.filter(
                    content_type=ct,
                    object_id=comment.id
                ).exclude(status='rejected')

                for report in reports:
                    report.status = 'lifted'
                    report.moderation_comment = 'Комментарий исправлен автором, жалоба снята'
                    report.save()

                    # Уведомляем автора жалобы
                    if report.reporter != request.user:
                        create_notification(
                            recipient=report.reporter,
                            sender=comment.author,
                            notification_type='moderation',
                            title='📋 Жалоба снята',
                            message=f'Пользователь @{comment.author.username} отредактировал комментарий, на который вы жаловались. Жалоба закрыта.',
                            link=f'/post/{post.id}/#comment-{comment.id}'
                        )

            comment.save()
            messages.success(request, 'Комментарий обновлён')
        else:
            messages.error(request, 'Комментарий не может быть пустым')

        return redirect('posts:post_detail', pk=post.id)

    return render(request, 'posts/comment_edit.html', {
        'comment': comment,
        'post': post,
        'moderation_info': moderation_info,
    })


@login_required
def comment_delete(request, comment_id):
    """Удаление комментария (для автора, модератора, админа)"""
    comment = get_object_or_404(Comment, id=comment_id)
    post_id = comment.post.id

    # Проверка прав
    if not (request.user == comment.author or request.user.is_staff or request.user.is_platform_moderator):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'У вас нет прав'}, status=403)
        messages.error(request, 'У вас нет прав на удаление этого комментария')
        return redirect('posts:post_detail', pk=post_id)

    comment.delete()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok'})

    messages.success(request, 'Комментарий удалён')
    return redirect('posts:post_detail', pk=post_id)