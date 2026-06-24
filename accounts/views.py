from django.utils import timezone
from datetime import timedelta
from communities.models import Community
from posts.models import Post, Like, Bookmark, Comment
from . import models
from .utils import generate_verification_code, send_verification_email, mask_email, send_welcome_email
from .forms import EmailVerificationForm, ResendCodeForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Notification, Friendship
from .models import Profile
import csv
import json
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.http import JsonResponse
from django.db.models import Q
from accounts.models import Friendship, Follow
from django.db.models import Case, When, Value, IntegerField

from io import StringIO, BytesIO
from django.http import HttpResponse
from django.core.mail import send_mail
from django.conf import settings
from django.contrib.sessions.models import Session
from django.utils import timezone
import random
from .forms import CustomUserCreationForm, CustomUserChangeForm, CustomPasswordChangeForm
from .models import User, Follow, Notification
from .utils import create_notification
from django.core.mail import send_mail
from django.conf import settings
import random
import string
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import random
import string
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate
from django.shortcuts import redirect, render
from django.contrib import messages
from .forms import ProfileEditForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


def register_view(request):
    """
    Регистрация нового пользователя с валидацией email
    """
    if request.user.is_authenticated:
        return redirect('posts:post_list')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # Дополнительная проверка email (на случай если валидатор пропустил)
            email = form.cleaned_data.get('email')

            # Проверка на временные домены (ещё раз на всякий случай)
            blocked_domains = ['tempmail.com', '10minutemail.com', 'mailinator.com', 'yopmail.com']
            domain = email.split('@')[-1].lower() if '@' in email else ''
            if domain in blocked_domains:
                form.add_error('email', 'Использование временной почты запрещено')
                return render(request, 'accounts/register.html', {'form': form})

            # Создаём пользователя
            user = form.save(commit=False)
            user.email_verified = False
            user.save()

            Profile.objects.get_or_create(user=user)

            # Генерируем и отправляем код
            code = generate_verification_code()
            user.email_verification_code = code
            user.email_verification_sent = timezone.now()
            user.save(update_fields=['email_verification_code', 'email_verification_sent'])

            # Отправляем email
            if send_verification_email(user, code):
                request.session['verification_email'] = user.email
                messages.success(request, 'Регистрация успешна! Проверьте почту для подтверждения.')
                return redirect('accounts:verify_email')
            else:
                # Если письмо не отправилось
                user.delete()
                messages.error(request, 'Ошибка отправки письма. Попробуйте позже.')
        else:
            # Выводим все ошибки формы
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    """
    Авторизация пользователя
    """
    if request.user.is_authenticated:
        return redirect('posts:post_list')  # <-- ИСПРАВЛЕНО

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f'Добро пожаловать, {user.username}!')
                return redirect('posts:post_list')  # <-- ИСПРАВЛЕНО
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """
    Выход из системы
    """
    logout(request)
    messages.info(request, 'Вы вышли из системы')
    return redirect('posts:post_list')  # <-- ИСПРАВЛЕНО


@login_required
def profile_view(request, username=None):
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    def can_view(user, target_user, content_type='profile'):
        if user == target_user:
            return True

        # Получаем настройку приватности из профиля
        if content_type == 'profile':
            setting = target_user.profile.who_can_see_profile
        elif content_type == 'photos':
            setting = target_user.profile.who_can_see_photos
        elif content_type == 'videos':
            setting = target_user.profile.who_can_see_videos
        elif content_type == 'music':
            setting = target_user.profile.who_can_see_music
        elif content_type == 'stats':  # НОВОЕ - для статистики
            setting = getattr(target_user.profile, 'who_can_see_stats', 'everyone')
        elif content_type == 'bookmarks':
            setting = 'only_me'
        else:
            setting = 'everyone'

        if setting == 'only_me':
            return False
        if setting == 'everyone':
            return True
        if setting == 'friends':
            # Проверяем, являются ли они друзьями
            return Friendship.objects.filter(
                Q(user=user, friend=target_user, status='accepted') |
                Q(user=target_user, friend=user, status='accepted')
            ).exists()

        return False

    # Проверка доступа к профилю
    if not can_view(request.user, profile_user, 'profile'):
        return render(request, 'accounts/private_profile.html', {
            'profile_user': profile_user,
        })

    # ========== ОСНОВНАЯ СТАТИСТИКА ==========
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count, Q
    from posts.models import Comment, Like

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Базовые метрики
    posts_count = profile_user.posts.filter(status='published', is_hidden=False).count()
    followers_count = Follow.objects.filter(following=profile_user).count()
    following_count = Follow.objects.filter(follower=profile_user).count()
    friend_ids = set(Friendship.objects.filter(user=request.user, status='accepted').values_list('friend_id',
                                                                                                 flat=True)) if request.user.is_authenticated else set()

    # ID постов пользователя
    user_post_ids = list(profile_user.posts.filter(status='published', is_hidden=False).values_list('id', flat=True))

    # Статистика по лайкам на постах пользователя
    total_likes_on_posts = Like.objects.filter(
        content_type='post',
        object_id__in=user_post_ids
    ).count()

    likes_this_week = Like.objects.filter(
        content_type='post',
        object_id__in=user_post_ids,
        created_at__gte=week_ago
    ).count()

    # Статистика по комментариям на постах пользователя
    total_comments_on_posts = Comment.objects.filter(
        post_id__in=user_post_ids,
        is_deleted=False,
        is_hidden=False
    ).count()

    comments_this_week = Comment.objects.filter(
        post_id__in=user_post_ids,
        is_deleted=False,
        is_hidden=False,
        created_at__gte=week_ago
    ).count()

    # Посты пользователя за период
    posts_this_week = profile_user.posts.filter(
        status='published',
        is_hidden=False,
        created_at__gte=week_ago
    ).count()

    posts_this_month = profile_user.posts.filter(
        status='published',
        is_hidden=False,
        created_at__gte=month_ago
    ).count()

    # Новые подписчики за неделю
    new_followers_this_week = Follow.objects.filter(
        following=profile_user,
        created_at__gte=week_ago
    ).count() if hasattr(Follow, 'created_at') else 0

    # Вовлечённость (лайки + комментарии на пост)
    engagement_rate = 0
    if posts_count > 0:
        engagement_rate = round(((total_likes_on_posts + total_comments_on_posts) / posts_count), 1)

    # Динамика по дням (для графика) - за последние 7 дней
    last_7_days = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)

        posts_count_day = profile_user.posts.filter(
            created_at__range=(day_start, day_end),
            status='published',
            is_hidden=False
        ).count()

        last_7_days.append({
            'date': day.strftime('%d.%m'),
            'posts': posts_count_day,
            'day_name': day.strftime('%a')
        })

    max_posts = max([d['posts'] for d in last_7_days]) if last_7_days and max(
        d['posts'] for d in last_7_days) > 0 else 1

    # Статистика для шаблона
    stats = {
        'total_posts': posts_count,
        'total_followers': followers_count,
        'total_following': following_count,
        'total_likes_on_posts': total_likes_on_posts,
        'total_comments_on_posts': total_comments_on_posts,
        'posts_this_week': posts_this_week,
        'posts_this_month': posts_this_month,
        'likes_this_week': likes_this_week,
        'comments_this_week': comments_this_week,
        'new_followers_this_week': new_followers_this_week,
        'engagement_rate': engagement_rate,
        'weekly_activity': last_7_days,
        'max_posts_in_week': max_posts,
        'join_date': profile_user.date_joined,
    }

    # ========== ОСТАЛЬНЫЕ ДАННЫЕ ==========
    user_posts = profile_user.posts.filter(status='published', is_hidden=False).order_by('-created_at')[:10]

    from posts.models import Comment, Like, Bookmark
    from communities.models import CommunityMembership, Community
    from media_storage.models import SavedPhoto, SavedVideo

    user_comments = Comment.objects.filter(author=profile_user, is_deleted=False).select_related('post').order_by(
        '-created_at')[:10]
    user_communities = CommunityMembership.objects.filter(user=profile_user, status='active').select_related(
        'community').order_by('-joined_at')[:10]

    # Закладки — только для владельца профиля
    user_bookmarks = []
    if request.user == profile_user:
        user_bookmarks = Bookmark.objects.filter(user=profile_user, post__is_hidden=False).select_related('post',
                                                                                                          'post__author',
                                                                                                          'post__author__profile').order_by(
            '-created_at')[:10]

    # Фото — с проверкой приватности
    if can_view(request.user, profile_user, 'photos'):
        user_photos = SavedPhoto.objects.filter(user=profile_user).select_related('post').order_by('-created_at')[:12]
    else:
        user_photos = []

    # Видео — с проверкой приватности
    if can_view(request.user, profile_user, 'videos'):
        user_videos = SavedVideo.objects.filter(user=profile_user).select_related('post').order_by('-created_at')[:12]
    else:
        user_videos = []

    # Музыка — с проверкой приватности
    from music_app.models import SavedTrack
    if can_view(request.user, profile_user, 'music'):
        user_tracks = SavedTrack.objects.filter(user=profile_user).order_by('-created_at')[:20]
    else:
        user_tracks = []

    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(follower=request.user, following=profile_user).exists()

    liked_post_ids = set()
    if request.user.is_authenticated:
        all_post_ids = set(user_post_ids)
        liked_post_ids = set(
            Like.objects.filter(user=request.user, content_type='post', object_id__in=all_post_ids).values_list(
                'object_id', flat=True))

    liked_post_ids_full = Like.objects.filter(user=profile_user, content_type='post').values_list('object_id',
                                                                                                  flat=True)
    liked_posts = Post.objects.filter(id__in=liked_post_ids_full, status='published', is_hidden=False).select_related(
        'author', 'author__profile').order_by('-created_at')[:10]

    friends_count = Friendship.objects.filter(user=profile_user, status='accepted').count()
    communities_count = Community.objects.filter(members=profile_user).count()

    context = {
        'profile_user': profile_user,
        'posts_count': posts_count,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'user_posts': user_posts,
        'liked_posts': liked_posts,
        'user_comments': user_comments,
        'user_communities': user_communities,
        'user_bookmarks': user_bookmarks,
        'user_photos': user_photos,
        'user_videos': user_videos,
        'friends_count': friends_count,
        'communities_count': communities_count,
        'liked_post_ids': liked_post_ids,
        'friend_ids': friend_ids,
        'user_tracks': user_tracks,
        'can_view_photos': can_view(request.user, profile_user, 'photos'),
        'can_view_videos': can_view(request.user, profile_user, 'videos'),
        'can_view_music': can_view(request.user, profile_user, 'music'),
        'can_view_stats': can_view(request.user, profile_user, 'stats'),
        'is_owner': request.user == profile_user,
        'stats': stats,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def privacy_settings(request):
    profile = request.user.profile

    if request.method == 'POST':
        # Основные настройки приватности
        profile.who_can_see_profile = request.POST.get('who_can_see_profile', 'everyone')
        profile.who_can_see_birthdate = request.POST.get('who_can_see_birthdate', 'friends')
        profile.who_can_see_photos = request.POST.get('who_can_see_photos', 'everyone')
        profile.who_can_see_videos = request.POST.get('who_can_see_videos', 'everyone')
        profile.who_can_see_music = request.POST.get('who_can_see_music', 'everyone')
        profile.who_can_see_communities = request.POST.get('who_can_see_communities', 'everyone')
        profile.who_can_see_friends = request.POST.get('who_can_see_friends', 'everyone')
        profile.who_can_see_stats = request.POST.get('who_can_see_stats', 'everyone')  # НОВОЕ
        profile.allow_messages = request.POST.get('allow_messages', 'everyone')
        profile.allow_comments = request.POST.get('allow_comments', 'everyone')

        # Исключения для сообщений
        if profile.allow_messages == 'friends_except':
            except_ids = request.POST.get('message_except', '')
            profile.message_except.clear()
            if except_ids:
                for uid in except_ids.split(','):
                    try:
                        u = User.objects.get(id=int(uid))
                        profile.message_except.add(u)
                    except:
                        pass
        else:
            profile.message_except.clear()

        profile.save()
        messages.success(request, 'Настройки приватности сохранены')
        return redirect('accounts:privacy_settings')

    # Для отображения формы
    message_except_list = profile.message_except.all() if profile.allow_messages == 'friends_except' else []
    all_friends = Friendship.objects.filter(
        user=request.user,
        status='accepted'
    ).select_related('friend', 'friend__profile')
    all_friends_list = [f.friend for f in all_friends]

    return render(request, 'accounts/privacy_settings.html', {
        'profile': profile,
        'message_except_list': message_except_list,
        'all_friends': all_friends_list,
    })

@login_required
def security_settings(request):
    """Безопасность: смена пароля, телефон, 2FA"""
    password_form = PasswordChangeForm(request.user)

    if request.method == 'POST':
        if 'change_password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, 'Пароль изменён')
                return redirect('accounts:security_settings')

        if 'add_phone' in request.POST:
            phone = request.POST.get('phone', '')
            request.user.profile.phone = phone
            request.user.profile.save()
            messages.success(request, 'Телефон добавлен')
            return redirect('accounts:security_settings')

    return render(request, 'accounts/security_settings.html', {
        'password_form': password_form,
        'profile': request.user.profile,
    })


@login_required
def notification_settings(request):
    """Настройки уведомлений"""
    if request.method == 'POST':
        profile = request.user.profile
        profile.notify_likes = request.POST.get('notify_likes') == 'on'
        profile.notify_comments = request.POST.get('notify_comments') == 'on'
        profile.notify_follows = request.POST.get('notify_follows') == 'on'
        profile.notify_messages = request.POST.get('notify_messages') == 'on'
        profile.notify_email = request.POST.get('notify_email') == 'on'
        profile.save()
        messages.success(request, 'Настройки уведомлений сохранены')
        return redirect('accounts:notification_settings')

    return render(request, 'accounts/notification_settings.html', {
        'profile': request.user.profile,
    })


@login_required
def blocked_users(request):
    """Чёрный список"""
    blocked = request.user.profile.blocked_users.all()

    if request.method == 'POST':
        if 'block_user' in request.POST:
            username = request.POST.get('username', '')
            user_to_block = User.objects.filter(username=username).first()
            if user_to_block and user_to_block != request.user:
                request.user.profile.blocked_users.add(user_to_block)
                messages.success(request, f'{username} заблокирован')
            else:
                messages.error(request, 'Пользователь не найден')
            return redirect('accounts:blocked_users')

        if 'unblock_user' in request.POST:
            user_id = request.POST.get('user_id')
            user_to_unblock = User.objects.filter(id=user_id).first()
            if user_to_unblock:
                request.user.profile.blocked_users.remove(user_to_unblock)
                messages.success(request, f'{user_to_unblock.username} разблокирован')
            return redirect('accounts:blocked_users')

    return render(request, 'accounts/blocked_users.html', {
        'blocked': blocked,
    })


@login_required
def sessions(request):
    """Активные сеансы с полной информацией"""
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    all_sessions = Session.objects.filter(expire_date__gte=timezone.now())
    user_sessions = []

    for session in all_sessions:
        data = session.get_decoded()
        if data.get('_auth_user_id') == str(request.user.id):
            ip = data.get('ip', '127.0.0.1')
            user_agent = data.get('user_agent', '')

            # Определяем устройство
            if 'Mobile' in user_agent or 'Android' in user_agent or 'iPhone' in user_agent:
                device = '📱 Телефон'
            elif 'iPad' in user_agent or 'Tablet' in user_agent:
                device = '📱 Планшет'
            else:
                device = '💻 Компьютер'

            # Определяем браузер
            if 'Edg' in user_agent:
                browser = 'Edge'
            elif 'Chrome' in user_agent and 'Safari' in user_agent:
                browser = 'Chrome'
            elif 'Firefox' in user_agent:
                browser = 'Firefox'
            elif 'Safari' in user_agent:
                browser = 'Safari'
            elif 'Opera' in user_agent or 'OPR' in user_agent:
                browser = 'Opera'
            else:
                browser = 'Неизвестный браузер'

            # Определяем ОС
            if 'Windows' in user_agent:
                os = 'Windows'
            elif 'Mac OS' in user_agent:
                os = 'macOS'
            elif 'Linux' in user_agent and 'Android' not in user_agent:
                os = 'Linux'
            elif 'Android' in user_agent:
                os = 'Android'
            elif 'iPhone' in user_agent or 'iPad' in user_agent:
                os = 'iOS'
            else:
                os = 'Неизвестная ОС'

            # Геолокация (кешируем в сессии)
            location = data.get('geo_location', '')
            if not location and ip and ip != '127.0.0.1':
                try:
                    import requests as req
                    geo = req.get(f'http://ip-api.com/json/{ip}?fields=city,country', timeout=2).json()
                    location = f"{geo.get('city', '')}, {geo.get('country', '')}"
                    # Сохраняем в сессию для будущих запросов
                    data['geo_location'] = location
                    session.session_data = data
                except:
                    location = 'Местоположение неизвестно'

            last_activity = data.get('last_activity', '')
            if last_activity:
                last_activity = timezone.datetime.fromisoformat(last_activity)
            else:
                last_activity = session.expire_date - timezone.timedelta(
                    seconds=settings.SESSION_COOKIE_AGE
                )

            user_sessions.append({
                'session_key': session.session_key,
                'ip': ip,
                'device': device,
                'browser': browser,
                'os': os,
                'location': location or 'Неизвестно',
                'last_activity': last_activity,
                'is_current': session.session_key == request.session.session_key,
            })

    if request.method == 'POST' and 'logout_session' in request.POST:
        session_key = request.POST.get('session_key')
        if session_key != request.session.session_key:
            Session.objects.filter(session_key=session_key).delete()
            messages.success(request, 'Сеанс завершён')
        return redirect('accounts:sessions')

    if request.method == 'POST' and 'logout_all' in request.POST:
        Session.objects.filter(expire_date__gte=timezone.now()).exclude(
            session_key=request.session.session_key
        ).delete()
        messages.success(request, 'Все сеансы кроме текущего завершены')
        return redirect('accounts:sessions')

    return render(request, 'accounts/sessions.html', {'sessions': user_sessions})


@login_required
def export_data(request):
    if request.method == 'POST':
        export_type = request.POST.get('type', 'json')

        # Собираем базовые данные
        from posts.models import Bookmark, Like
        from communities.models import Community
        from django.db.models import Count, Q

        posts_count = request.user.posts.filter(status='published', is_hidden=False).count()
        comments_count = Comment.objects.filter(author=request.user, is_deleted=False, is_hidden=False).count()
        followers_count = request.user.profile_followers.count()
        following_count = request.user.profile.following.count()
        friends_count = Friendship.objects.filter(user=request.user, status='accepted').count()
        bookmarks_count = Bookmark.objects.filter(user=request.user).count()
        likes_count = Like.objects.filter(user=request.user, content_type='post').count()
        communities_count = Community.objects.filter(members=request.user).count()

        if export_type == 'json':
            # Собираем полные данные
            full_data = {
                'exported_at': timezone.now().isoformat(),
                'profile': {
                    'username': request.user.username,
                    'email': request.user.email,
                    'first_name': request.user.first_name,
                    'last_name': request.user.last_name,
                    'full_name': request.user.get_full_name(),
                    'date_joined': request.user.date_joined.isoformat(),
                    'bio': request.user.profile.bio,
                    'location': request.user.profile.location,
                    'website': request.user.profile.website,
                    'phone': request.user.profile.phone,
                },
                'stats': {
                    'posts_count': posts_count,
                    'followers_count': followers_count,
                    'following_count': following_count,
                    'friends_count': friends_count,
                    'bookmarks_count': bookmarks_count,
                    'likes_count': likes_count,
                    'comments_count': comments_count,
                    'communities_count': communities_count,
                },
                'posts': list(request.user.posts.filter(status='published', is_hidden=False).values(
                    'id', 'title', 'content', 'created_at', 'updated_at', 'likes_count', 'views_count'
                )),
                'comments': list(Comment.objects.filter(author=request.user, is_deleted=False, is_hidden=False).values(
                    'id', 'content', 'created_at', 'post__title'
                )),
                'bookmarks': list(Bookmark.objects.filter(user=request.user, post__is_hidden=False).select_related('post').values(
                    'post__id', 'post__title', 'created_at'
                )),
                'liked_posts': list(Post.objects.filter(
                    id__in=Like.objects.filter(user=request.user, content_type='post').values_list('object_id', flat=True),
                    is_hidden=False
                ).values('id', 'title', 'created_at')),
                'communities': list(Community.objects.filter(members=request.user).values('id', 'name', 'slug')),
            }

            # Музыка
            try:
                from music_app.models import SavedTrack
                full_data['saved_tracks'] = list(SavedTrack.objects.filter(user=request.user).values(
                    'track_id', 'title', 'artist', 'created_at'
                ))
            except ImportError:
                full_data['saved_tracks'] = []

            response = HttpResponse(
                json.dumps(full_data, indent=2, ensure_ascii=False, default=str),
                content_type='application/json'
            )
            response['Content-Disposition'] = f'attachment; filename="potok_data_{request.user.username}_{timezone.now().strftime("%Y%m%d_%H%M")}.json"'
            return response

        elif export_type == 'pdf':
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.units import mm
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.enums import TA_CENTER, TA_LEFT
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                from django.conf import settings
                import os
                from io import BytesIO

                buffer = BytesIO()

                # Регистрируем шрифт
                font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('DejaVuSans', font_path))
                    pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', font_path))
                    font_name = 'DejaVuSans'
                    font_bold = 'DejaVuSans-Bold'
                else:
                    font_name = 'Helvetica'
                    font_bold = 'Helvetica-Bold'

                doc = SimpleDocTemplate(
                    buffer,
                    pagesize=A4,
                    rightMargin=15 * mm,
                    leftMargin=15 * mm,
                    topMargin=20 * mm,
                    bottomMargin=15 * mm
                )

                styles = getSampleStyleSheet()

                # Стили
                title_style = ParagraphStyle(
                    'CustomTitle', parent=styles['Normal'],
                    fontName=font_bold, fontSize=22,
                    textColor=colors.HexColor('#2563eb'),
                    alignment=TA_CENTER, spaceAfter=6
                )
                subtitle_style = ParagraphStyle(
                    'Subtitle', parent=styles['Normal'],
                    fontName=font_name, fontSize=12,
                    textColor=colors.HexColor('#6b7280'),
                    alignment=TA_CENTER, spaceAfter=15
                )
                heading_style = ParagraphStyle(
                    'CustomHeading', parent=styles['Normal'],
                    fontName=font_bold, fontSize=14,
                    textColor=colors.HexColor('#1f2937'),
                    spaceAfter=8, spaceBefore=12
                )
                meta_style = ParagraphStyle(
                    'MetaStyle', parent=styles['Normal'],
                    fontName=font_name, fontSize=9,
                    textColor=colors.HexColor('#4b5563'),
                    alignment=TA_CENTER, spaceAfter=4
                )
                normal_style = ParagraphStyle(
                    'CustomNormal', parent=styles['Normal'],
                    fontName=font_name, fontSize=9,
                    alignment=TA_LEFT
                )
                footer_style = ParagraphStyle(
                    'Footer', parent=styles['Normal'],
                    fontName=font_name, fontSize=8,
                    textColor=colors.HexColor('#9ca3af'),
                    alignment=TA_CENTER
                )

                elements = []

                # ========== ЗАГОЛОВОК ==========
                elements.append(Paragraph("Архив данных пользователя", title_style))
                elements.append(Paragraph(f"@{request.user.username}", subtitle_style))
                elements.append(Spacer(1, 8 * mm))

                # ========== МЕТАДАННЫЕ ==========
                now = timezone.now()
                elements.append(Paragraph(
                    f"<b>Пользователь:</b> {request.user.get_full_name() or request.user.username} ({request.user.email})",
                    meta_style
                ))
                elements.append(Paragraph(
                    f"<b>Дата экспорта:</b> {now.strftime('%d.%m.%Y %H:%M:%S')}",
                    meta_style
                ))
                elements.append(Spacer(1, 10 * mm))

                # ========== 1. ОСНОВНАЯ ИНФОРМАЦИЯ ==========
                elements.append(Paragraph("Основная информация", heading_style))

                profile_data = [
                    ['Поле', 'Значение'],
                    ['Имя пользователя', request.user.username],
                    ['Полное имя', request.user.get_full_name() or 'Не указано'],
                    ['Email', request.user.email],
                    ['Дата регистрации', request.user.date_joined.strftime('%d.%m.%Y %H:%M')],
                    ['Биография', request.user.profile.bio or 'Не указана'],
                    ['Местоположение', request.user.profile.location or 'Не указано'],
                    ['Веб-сайт', request.user.profile.website or 'Не указан'],
                    ['Телефон', request.user.profile.phone or 'Не указан'],
                ]

                profile_table = Table(profile_data, colWidths=[80 * mm, 100 * mm])
                profile_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#374151')),
                    ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                    ('FONTNAME', (0, 0), (1, 0), font_bold),
                    ('FONTSIZE', (0, 0), (1, 0), 10),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('FONTNAME', (0, 1), (-1, -1), font_name),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('PADDING', (0, 0), (-1, -1), 8),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ]))
                elements.append(profile_table)
                elements.append(Spacer(1, 10 * mm))

                # ========== 2. СТАТИСТИКА ==========
                elements.append(Paragraph("Статистика", heading_style))

                stats_data = [
                    ['Показатель', 'Значение'],
                    ['Постов', str(posts_count)],
                    ['Комментариев', str(comments_count)],
                    ['Подписчиков', str(followers_count)],
                    ['Подписок', str(following_count)],
                    ['Друзей', str(friends_count)],
                    ['Закладок', str(bookmarks_count)],
                    ['Лайков', str(likes_count)],
                    ['Сообществ', str(communities_count)],
                ]

                stats_table = Table(stats_data, colWidths=[80 * mm, 100 * mm])
                stats_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#2563eb')),
                    ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
                    ('FONTNAME', (0, 0), (1, 0), font_bold),
                    ('FONTSIZE', (0, 0), (1, 0), 10),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('FONTNAME', (0, 1), (-1, -1), font_name),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('PADDING', (0, 0), (-1, -1), 8),
                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ]))
                elements.append(stats_table)
                elements.append(Spacer(1, 10 * mm))

                # ========== 3. ПОСТЫ (первые 10) ==========
                posts = request.user.posts.filter(
                    status='published',
                    is_hidden=False
                ).order_by('-created_at')[:10]

                if posts:
                    elements.append(Paragraph(f"Последние посты ({posts.count()})", heading_style))
                    posts_data = [['#', 'Заголовок', 'Дата', 'Лайки', 'Комментарии']]

                    for i, post in enumerate(posts, 1):
                        comments_count_post = post.comments.filter(is_deleted=False, is_hidden=False).count()
                        posts_data.append([
                            str(i),
                            post.title[:80] + '...' if len(post.title) > 80 else post.title,
                            post.created_at.strftime('%d.%m.%Y'),
                            str(post.likes_count),
                            str(comments_count_post)
                        ])

                    posts_table = Table(posts_data, colWidths=[20 * mm, 80 * mm, 40 * mm, 30 * mm, 30 * mm])
                    posts_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), font_bold),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTNAME', (0, 1), (-1, -1), font_name),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('PADDING', (0, 0), (-1, -1), 6),
                        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                        ('ALIGN', (3, 0), (4, -1), 'CENTER'),
                    ]))
                    elements.append(posts_table)
                    elements.append(Spacer(1, 10 * mm))

                # ========== 4. КОММЕНТАРИИ (первые 10) ==========
                comments = Comment.objects.filter(
                    author=request.user,
                    is_deleted=False,
                    is_hidden=False
                ).select_related('post').order_by('-created_at')[:10]

                if comments:
                    elements.append(Paragraph(f"Последние комментарии ({comments.count()})", heading_style))
                    comments_data = [['#', 'Текст', 'Пост', 'Дата']]

                    for i, comment in enumerate(comments, 1):
                        comments_data.append([
                            str(i),
                            comment.content[:60] + '...' if len(comment.content) > 60 else comment.content,
                            comment.post.title[:40] + '...' if len(comment.post.title) > 40 else comment.post.title,
                            comment.created_at.strftime('%d.%m.%Y')
                        ])

                    comments_table = Table(comments_data, colWidths=[15 * mm, 70 * mm, 60 * mm, 35 * mm])
                    comments_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), font_bold),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTNAME', (0, 1), (-1, -1), font_name),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('PADDING', (0, 0), (-1, -1), 6),
                        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
                    ]))
                    elements.append(comments_table)
                    elements.append(Spacer(1, 10 * mm))

                # ========== 5. ЗАКЛАДКИ (первые 10) ==========
                from posts.models import Bookmark
                bookmarks = Bookmark.objects.filter(
                    user=request.user,
                    post__is_hidden=False
                ).select_related('post').order_by('-created_at')[:10]

                if bookmarks:
                    elements.append(Paragraph(f"Закладки ({bookmarks.count()})", heading_style))
                    bookmarks_data = [['#', 'Пост', 'Дата']]

                    for i, bm in enumerate(bookmarks, 1):
                        bookmarks_data.append([
                            str(i),
                            bm.post.title[:80] + '...' if len(bm.post.title) > 80 else bm.post.title,
                            bm.created_at.strftime('%d.%m.%Y')
                        ])

                    bookmarks_table = Table(bookmarks_data, colWidths=[15 * mm, 110 * mm, 40 * mm])
                    bookmarks_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), font_bold),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTNAME', (0, 1), (-1, -1), font_name),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('PADDING', (0, 0), (-1, -1), 6),
                        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ]))
                    elements.append(bookmarks_table)
                    elements.append(Spacer(1, 10 * mm))

                # ========== 6. СООБЩЕСТВА (первые 10) ==========
                from communities.models import Community
                communities = Community.objects.filter(members=request.user).order_by('-created_at')[:10]

                if communities:
                    elements.append(Paragraph(f"Сообщества ({communities.count()})", heading_style))
                    communities_data = [['#', 'Название', 'Участников', 'Дата']]

                    for i, community in enumerate(communities, 1):
                        communities_data.append([
                            str(i),
                            community.name[:60] + '...' if len(community.name) > 60 else community.name,
                            str(community.members.count()),
                            community.created_at.strftime('%d.%m.%Y')
                        ])

                    communities_table = Table(communities_data, colWidths=[15 * mm, 80 * mm, 40 * mm, 40 * mm])
                    communities_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), font_bold),
                        ('FONTSIZE', (0, 0), (-1, 0), 9),
                        ('FONTSIZE', (0, 1), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('FONTNAME', (0, 1), (-1, -1), font_name),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('PADDING', (0, 0), (-1, -1), 6),
                        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ]))
                    elements.append(communities_table)
                    elements.append(Spacer(1, 10 * mm))

                # ========== ПОДВАЛ ==========
                elements.append(Spacer(1, 10 * mm))
                elements.append(Paragraph(
                    "<i>Данные экспортированы из социальной сети «Поток»</i>",
                    footer_style
                ))
                elements.append(Paragraph(
                    f"Всего записей: {posts_count} постов, {comments_count} комментариев, {bookmarks_count} закладок",
                    footer_style
                ))

                # Собираем PDF
                doc.build(elements)
                buffer.seek(0)

                response = HttpResponse(buffer, content_type='application/pdf')
                response['Content-Disposition'] = (
                    f'attachment; filename="potok_data_{request.user.username}_'
                    f'{timezone.now().strftime("%Y%m%d_%H%M")}.pdf"'
                )
                return response

            except ImportError as e:
                messages.error(request, f'PDF-экспорт недоступен. Установите reportlab: pip install reportlab')
                return redirect('accounts:export_data')
            except Exception as e:
                messages.error(request, f'Ошибка при создании PDF: {str(e)}')
                return redirect('accounts:export_data')

    return render(request, 'accounts/export_data.html')


@login_required
def delete_account(request):
    """Удаление аккаунта с подтверждением по коду"""
    if request.method == 'POST':
        step = request.POST.get('step', '1')

        if step == '1':
            # Генерируем код и отправляем на почту
            code = str(random.randint(100000, 999999))
            request.session['delete_code'] = code
            request.session['delete_code_time'] = timezone.now().isoformat()

            try:
                send_mail(
                    'Подтверждение удаления аккаунта Поток',
                    f'Код для удаления аккаунта: {code}\n\n'
                    f'Если вы не запрашивали удаление — проигнорируйте это письмо.',
                    settings.DEFAULT_FROM_EMAIL,
                    [request.user.email],
                    fail_silently=False,
                )
                messages.info(request, f'Код подтверждения отправлен на {request.user.email}')
            except Exception as e:
                # Если почта не работает — показываем код на странице
                messages.info(request, f'Код подтверждения: {code} (отправка на почту недоступна)')

            return render(request, 'accounts/delete_account.html', {'step': '2'})

        elif step == '2':
            entered_code = request.POST.get('code', '')
            stored_code = request.session.get('delete_code', '')
            code_time = request.session.get('delete_code_time', '')

            # Проверяем что код не истёк (10 минут)
            if code_time:
                code_time = timezone.datetime.fromisoformat(code_time)
                if timezone.now() - code_time > timezone.timedelta(minutes=10):
                    messages.error(request, 'Код истёк. Запросите новый')
                    return redirect('accounts:delete_account')

            if entered_code == stored_code:
                # Показываем финальное подтверждение
                return render(request, 'accounts/delete_account.html', {'step': '3'})
            else:
                messages.error(request, 'Неверный код')
                return render(request, 'accounts/delete_account.html', {'step': '2'})

        elif step == '3':
            password = request.POST.get('password', '')
            if request.user.check_password(password):
                user = request.user
                # Очищаем сессию
                request.session.flush()
                user.delete()
                messages.success(request, 'Аккаунт удалён')
                return redirect('posts:post_list')
            else:
                messages.error(request, 'Неверный пароль')
                return render(request, 'accounts/delete_account.html', {'step': '3'})

    return render(request, 'accounts/delete_account.html', {'step': '1'})


@login_required
def profile_edit_view(request):
    profile = request.user.profile

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES,
                               instance=profile, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('accounts:profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме.')
    else:
        form = ProfileEditForm(instance=profile, user=request.user)

    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
@require_POST
def follow_view(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        return JsonResponse({'status': 'error', 'message': 'Нельзя подписаться на самого себя'}, status=400)

    current_profile = request.user.profile

    if current_profile.following.filter(id=target_user.id).exists():
        current_profile.following.remove(target_user)
        status = 'unfollowed'
    else:
        current_profile.following.add(target_user)
        status = 'followed'

        # ========== УВЕДОМЛЕНИЕ О ПОДПИСКЕ ==========
        from accounts.utils import create_notification
        create_notification(
            recipient=target_user,
            sender=request.user,
            notification_type='follow',
            title='👤 Новый подписчик',
            message=f'{request.user.username} подписался на вас',
            link=f'/accounts/profile/{request.user.username}/'
        )

    follower_count = target_user.profile_followers.count()

    return JsonResponse({
        'status': status,
        'followers_count': follower_count,
    })
@login_required
def followers_list_view(request, username):
    """
    Список подписчиков пользователя
    """
    user = get_object_or_404(User, username=username)
    followers = Follow.objects.filter(
        following=user
    ).select_related('follower').order_by('-created_at')  # Добавил сортировку

    paginator = Paginator(followers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/followers_list.html', {
        'page_obj': page_obj,
        'profile_user': user,
        'title': 'Подписчики'
    })


@login_required
def following_list_view(request, username):
    user = get_object_or_404(User, username=username)
    profile = user.profile

    following = profile.following.all().order_by('username')

    paginator = Paginator(following, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/following_list.html', {
        'following': page_obj,
        'page_obj': page_obj,
        'profile_user': user,
        'following_count': following.count(),
        'followers_count': user.profile_followers.count(),
        'title': 'Подписки',
    })

@login_required
def user_list_view(request):
    """
    Список всех пользователей
    """
    users = User.objects.all().annotate(
        posts_count=Count('posts')
    ).order_by('-date_joined')

    # Поиск
    query = request.GET.get('q')
    if query:
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    paginator = Paginator(users, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/user_list.html', {
        'page_obj': page_obj,
        'query': query
    })


@login_required
def notifications_list(request):
    """
    Список уведомлений пользователя
    """
    notifications = request.user.notifications.all()

    # Фильтры
    filter_type = request.GET.get('type')
    if filter_type:
        notifications = notifications.filter(notification_type=filter_type)

    # Пагинация
    paginator = Paginator(notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Отмечаем как прочитанные при просмотре
    if request.GET.get('mark_read') == 'true':
        unread = notifications.filter(is_read=False)
        unread.update(is_read=True)

    return render(request, 'accounts/notifications.html', {
        'page_obj': page_obj,
        'filter_type': filter_type
    })


@login_required
def notifications_ajax(request):
    """
    AJAX-запрос для получения последних уведомлений
    """
    notifications = request.user.notifications.filter(is_read=False).order_by('-created_at')[:10]

    data = {
        'count': request.user.notifications.filter(is_read=False).count(),
        'notifications': []
    }

    for notif in notifications:
        data['notifications'].append({
            'id': notif.id,
            'title': notif.title,
            'message': notif.message[:50] + '...' if len(notif.message) > 50 else notif.message,
            'link': notif.link or '#',
            'created_at': notif.created_at.strftime('%d.%m.%Y %H:%M'),
            'type': notif.notification_type,
        })

    return JsonResponse(data)


@login_required
@require_POST
def notification_mark_read(request, notification_id):
    """Отметить уведомление как прочитанное"""
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.mark_as_read()

    # Получаем актуальное количество непрочитанных
    unread_count = request.user.notifications.filter(is_read=False).count()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'unread_count': unread_count})

    return redirect(request.META.get('HTTP_REFERER', 'accounts:notifications'))


@login_required
@require_POST
def notification_mark_all_read(request):
    """Отметить все уведомления как прочитанные"""
    request.user.notifications.filter(is_read=False).update(is_read=True)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok', 'unread_count': 0})

    return redirect('accounts:notifications')


@login_required
def get_unread_count(request):
    """Возвращает количество непрочитанных уведомлений"""
    count = request.user.notifications.filter(is_read=False).count()
    return JsonResponse({'count': count})


def send_verification_email(user, code):
    """
    Отправка письма с кодом подтверждения
    """
    try:
        # Создаем HTML-версию письма
        html_content = render_to_string('emails/verification_code.html', {
            'user': user,
            'code': code,
            'site_name': 'Поток',
            'site_url': 'http://127.0.0.1:8000'  # Замени на реальный домен
        })

        # Текстовая версия (на случай если HTML не поддерживается)
        text_content = strip_tags(html_content)

        # Отправляем письмо
        email = EmailMultiAlternatives(
            subject=f'Код подтверждения - {code}',
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        return True
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        return False


def verify_email(request):
    """
    Страница подтверждения email
    """
    # Проверяем, есть ли email в сессии
    email = request.session.get('verification_email')
    if not email:
        messages.error(request, 'Сессия истекла. Пожалуйста, войдите снова.')
        return redirect('accounts:login')

    try:
        user = User.objects.get(email=email, email_verified=False)
    except User.DoesNotExist:
        messages.error(request, 'Пользователь не найден или уже подтвержден.')
        return redirect('accounts:login')

    # Проверяем, не истек ли код (10 минут)
    if user.email_verification_sent:
        time_diff = timezone.now() - user.email_verification_sent
        if time_diff > timedelta(minutes=10):  # теперь timedelta определен
            # Код истек
            user.email_verification_code = None
            user.save(update_fields=['email_verification_code'])
            messages.warning(request, 'Код истек. Запросите новый.')
            return redirect('accounts:resend_code')

    if request.method == 'POST':
        form = EmailVerificationForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']

            if code == user.email_verification_code:
                # Код верный - подтверждаем email
                user.email_verified = True
                user.email_verification_code = None
                user.save(update_fields=['email_verified', 'email_verification_code'])

                # Отправляем приветственное письмо
                from .utils import send_welcome_email
                send_welcome_email(user)

                # Автоматически логиним пользователя
                login(request, user)

                # Очищаем сессию
                if 'verification_email' in request.session:
                    del request.session['verification_email']

                messages.success(request, 'Email успешно подтвержден! Добро пожаловать!')
                return redirect('posts:post_list')
            else:
                messages.error(request, 'Неверный код подтверждения')
    else:
        form = EmailVerificationForm()

    # Маскируем email для отображения
    masked_email = mask_email(email)

    return render(request, 'accounts/verify_email.html', {
        'form': form,
        'email': masked_email,
        'full_email': email,
    })


def resend_code(request):
    """
    Повторная отправка кода подтверждения
    """
    if request.method == 'POST':
        email = request.POST.get('email')

        if not email:
            messages.error(request, 'Email не указан')
            return redirect('accounts:resend_code')

        try:
            # Используем существующее поле email_verified
            user = User.objects.get(email=email, email_verified=False)

            # Генерируем новый код
            code = generate_verification_code()
            user.email_verification_code = code
            user.email_verification_sent = timezone.now()
            user.save(update_fields=['email_verification_code', 'email_verification_sent'])

            # Отправляем новый код
            if send_verification_email(user, code):
                request.session['verification_email'] = email
                messages.success(request, 'Новый код отправлен на вашу почту')
                return redirect('accounts:verify_email')
            else:
                messages.error(request, 'Ошибка отправки письма')
        except User.DoesNotExist:
            messages.error(request, 'Пользователь с таким email не найден или уже подтвержден')

    return render(request, 'accounts/resend_code.html')

@login_required
def confirm_email(request):
    """
    Подтверждение email по коду
    """
    if request.method == 'POST':
        code = request.POST.get('code')
        saved_data = request.session.get('verification_code')

        if not saved_data:
            return JsonResponse({
                'status': 'error',
                'message': 'Код не найден. Запросите новый код.'
            }, status=400)

        # Проверяем время (код действителен 10 минут)
        import time
        current_time = time.time()
        if current_time - saved_data['created_at'] > 600:  # 10 минут
            del request.session['verification_code']
            return JsonResponse({
                'status': 'error',
                'message': 'Код истек. Запросите новый код.'
            }, status=400)

        if code == saved_data['code'] and saved_data['email'] == request.user.email:
            request.user.email_verified = True
            request.user.save()

            # Очищаем сессию
            del request.session['verification_code']

            return JsonResponse({
                'status': 'success',
                'message': 'Email успешно подтвержден'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Неверный код подтверждения'
            }, status=400)

    return JsonResponse({'status': 'error', 'message': 'Метод не поддерживается'}, status=405)



def terms_view(request):
    """Страница условий использования"""
    return render(request, 'accounts/terms.html')


def privacy_view(request):
    """Страница политики конфиденциальности"""
    return render(request, 'accounts/privacy.html')



def community_list(request, username):
    """Список сообществ пользователя"""
    profile_user = get_object_or_404(User.objects.select_related('profile'), username=username)
    communities = Community.objects.filter(members=profile_user)

    query = request.GET.get('q', '')
    if query:
        communities = communities.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )

    paginator = Paginator(communities, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'accounts/community_list.html', {
        'profile_user': profile_user,
        'communities': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'total_count': communities.count(),
    })


@login_required
def user_search_api(request):
    """API поиска пользователей для чата"""
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return JsonResponse([], safe=False)

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).exclude(
        id=request.user.id
    ).select_related('profile')[:10]

    results = []
    for user in users:
        results.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'avatar': user.profile.avatar.url if user.profile.avatar else '',
            # Убираем поле url, чтобы не было ссылки!
        })

    return JsonResponse(results, safe=False)


@login_required
def get_friend_status(request, user_id):
    """Получить статус дружбы с пользователем"""
    target = get_object_or_404(User, id=user_id)

    if target == request.user:
        return JsonResponse({'status': 'self'})

    # Проверяем, есть ли принятая дружба
    if Friendship.objects.filter(
            user=request.user, friend=target, status='accepted'
    ).exists():
        return JsonResponse({'status': 'friends'})

    # Проверяем, отправлял ли текущий пользователь заявку
    if Friendship.objects.filter(
            user=request.user, friend=target, status='pending'
    ).exists():
        return JsonResponse({'status': 'pending_sent'})

    # Проверяем, есть ли входящая заявка
    if Friendship.objects.filter(
            user=target, friend=request.user, status='pending'
    ).exists():
        return JsonResponse({'status': 'pending_received'})

    return JsonResponse({'status': 'none'})


@login_required
@require_POST
def send_friend_request(request, user_id):
    target = get_object_or_404(User, id=user_id)

    if target == request.user:
        return JsonResponse({'status': 'error', 'message': 'Нельзя добавить себя'})

    # Проверяем существующую запись (включая rejected)
    existing = Friendship.objects.filter(
        user=request.user, friend=target
    ).first()

    if existing:
        if existing.status == 'accepted':
            return JsonResponse({'status': 'error', 'message': 'Вы уже друзья'})
        elif existing.status == 'pending':
            return JsonResponse({'status': 'error', 'message': 'Заявка уже отправлена'})
        elif existing.status == 'rejected':
            # Если заявка была отклонена, обновляем её, а не создаём новую
            existing.status = 'pending'
            existing.created_at = timezone.now()
            existing.save()

            # Создаём уведомление
            from accounts.utils import create_notification
            create_notification(
                recipient=target,
                sender=request.user,
                notification_type='friend',
                title='Заявка в друзья 👥',
                message=f'{request.user.username} хочет добавить вас в друзья',
                link='/accounts/friend/requests/'
            )

            return JsonResponse({'status': 'pending_sent', 'message': 'Заявка отправлена'})

    # Проверяем входящую заявку
    incoming = Friendship.objects.filter(
        user=target, friend=request.user, status='pending'
    ).first()

    if incoming:
        incoming.accept()
        return JsonResponse({'status': 'accepted', 'message': 'Вы теперь друзья'})

    # Создаём новую заявку
    Friendship.objects.create(
        user=request.user,
        friend=target,
        status='pending'
    )

    # Создаём уведомление
    from accounts.utils import create_notification
    create_notification(
        recipient=target,
        sender=request.user,
        notification_type='friend',
        title='Заявка в друзья 👥',
        message=f'{request.user.username} хочет добавить вас в друзья',
        link='/accounts/friend/requests/'
    )

    return JsonResponse({'status': 'pending_sent', 'message': 'Заявка отправлена'})


@login_required
@require_POST
def accept_friend_request(request, request_id):
    friendship = get_object_or_404(
        Friendship,
        id=request_id,
        friend=request.user,
        status='pending'
    )

    friendship.accept()

    create_notification(
        recipient=friendship.user,
        sender=request.user,
        notification_type='friend_accept',
        title='Заявка принята 🎉',
        message=f'{request.user.username} принял вашу заявку в друзья',
        link=f'/accounts/profile/{request.user.username}/'
    )

    return JsonResponse({'status': 'accepted', 'message': 'Заявка принята'})


@login_required
@require_POST
def reject_friend_request(request, request_id):
    friendship = get_object_or_404(
        Friendship,
        id=request_id,
        friend=request.user,
        status='pending'
    )

    friendship.reject()

    create_notification(
        recipient=friendship.user,
        sender=request.user,
        notification_type='friend_reject',
        title='Заявка отклонена',
        message=f'{request.user.username} отклонил вашу заявку в друзья',
        link='/'
    )

    return JsonResponse({'status': 'rejected', 'message': 'Заявка отклонена'})


@login_required
@require_POST
def cancel_friend_request(request, request_id):
    """Отменить отправленную заявку"""
    friendship = get_object_or_404(
        Friendship,
        id=request_id,
        user=request.user,
        status='pending'
    )

    friendship.cancel()
    return JsonResponse({'status': 'cancelled', 'message': 'Заявка отменена'})


@login_required
@require_POST
def remove_friend(request, user_id):
    """Удалить из друзей"""
    target = get_object_or_404(User, id=user_id)

    # Удаляем обе записи
    Friendship.objects.filter(
        user=request.user, friend=target, status='accepted'
    ).delete()
    Friendship.objects.filter(
        user=target, friend=request.user, status='accepted'
    ).delete()

    return JsonResponse({'status': 'removed', 'message': 'Пользователь удалён из друзей'})


@login_required
def friend_requests_list(request):
    """Список входящих заявок в друзья"""
    incoming_requests = Friendship.objects.filter(
        friend=request.user,
        status='pending'
    ).select_related('user', 'user__profile').order_by('-created_at')

    outgoing_requests = Friendship.objects.filter(
        user=request.user,
        status='pending'
    ).select_related('friend', 'friend__profile').order_by('-created_at')

    return render(request, 'accounts/friend_requests.html', {
        'incoming_requests': incoming_requests,
        'outgoing_requests': outgoing_requests,
    })


@login_required
def friends_list(request, username=None):
    if username:
        profile_user = get_object_or_404(User, username=username)
    else:
        profile_user = request.user

    # Друзья — где статус accepted, И пользователь является либо user, либо friend
    friendships = Friendship.objects.filter(
        status='accepted'
    ).filter(
        Q(user=profile_user) | Q(friend=profile_user)
    ).select_related('user', 'friend', 'user__profile', 'friend__profile').order_by('-created_at')

    # Преобразуем в список уникальных друзей
    friends_set = set()
    friends_list = []
    for f in friendships:
        if f.user == profile_user:
            friend = f.friend
        else:
            friend = f.user

        if friend.id not in friends_set:
            friends_set.add(friend.id)
            friends_list.append(friend)

    # Поиск
    query = request.GET.get('q')
    if query:
        friends_list = [f for f in friends_list if
                        query.lower() in f.username.lower() or query.lower() in f.get_full_name().lower()]

    # Пагинация
    paginator = Paginator(friends_list, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    pending_count = Friendship.objects.filter(
        friend=request.user,
        status='pending'
    ).count()

    return render(request, 'accounts/friends_list.html', {
        'profile_user': profile_user,
        'friendships': page_obj,  # теперь это список уникальных друзей
        'page_obj': page_obj,
        'total_count': len(friends_list),
        'pending_count': pending_count,
        'query': query,
        'is_paginated': page_obj.has_other_pages(),
    })

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


@login_required
@require_POST
def cancel_friend_request_by_user(request, user_id):
    """Отменить отправленную заявку по ID пользователя"""
    target = get_object_or_404(User, id=user_id)

    friendship = Friendship.objects.filter(
        user=request.user,
        friend=target,
        status='pending'
    ).first()

    if not friendship:
        return JsonResponse({'status': 'error', 'message': 'Заявка не найдена'})

    friendship.cancel()
    return JsonResponse({'status': 'cancelled', 'message': 'Заявка отменена'})


def can_view_content(request, profile_user, content_type='profile'):
    """
    Проверяет, может ли текущий пользователь видеть контент
    content_type: 'profile', 'photos', 'videos', 'music', 'friends'
    """
    if request.user == profile_user:
        return True

    # Если профиль публичный
    if content_type == 'profile':
        setting = profile_user.profile.who_can_see_profile
    elif content_type == 'photos':
        setting = profile_user.profile.who_can_see_photos
    elif content_type == 'videos':
        setting = profile_user.profile.who_can_see_videos
    elif content_type == 'music':
        setting = profile_user.profile.who_can_see_music
    else:
        setting = 'everyone'

    if setting == 'everyone':
        return True

    if setting == 'friends':
        # Проверяем, являются ли они друзьями
        return Friendship.objects.filter(
            user=request.user, friend=profile_user, status='accepted'
        ).exists() or Friendship.objects.filter(
            user=profile_user, friend=request.user, status='accepted'
        ).exists()

    return False


@login_required
def group_participants_search_api(request):
    """API поиска пользователей для добавления в групповой чат (без ссылок)"""
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return JsonResponse([], safe=False)

    users = User.objects.filter(
        Q(username__icontains=query) |
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query)
    ).exclude(
        id=request.user.id
    ).select_related('profile')[:10]

    results = []
    for user in users:
        results.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'avatar': user.profile.avatar.url if user.profile.avatar else '',
        })

    return JsonResponse(results, safe=False)


def api_search_users(request):
    """API для поиска пользователей (только друзья и подписчики)"""
    query = request.GET.get('q', '').strip()
    filter_type = request.GET.get('filter', 'all')  # all, friends, followers

    if not request.user.is_authenticated:
        return JsonResponse([], safe=False)

    # Базовый QuerySet — только друзья и подписчики
    # Получаем ID друзей
    friends_ids = list(Friendship.objects.filter(
        user=request.user,
        status='accepted'
    ).values_list('friend_id', flat=True))

    # Получаем ID подписчиков (кто подписан на текущего пользователя)
    followers_ids = list(Follow.objects.filter(
        following=request.user
    ).values_list('follower_id', flat=True))

    # Объединяем: друзья + подписчики
    allowed_ids = set(friends_ids) | set(followers_ids)

    # Если нужны только друзья
    if filter_type == 'friends':
        allowed_ids = set(friends_ids)
    elif filter_type == 'followers':
        allowed_ids = set(followers_ids)
    # else 'all' — друзья + подписчики

    # Если нет никого для отображения
    if not allowed_ids:
        return JsonResponse([], safe=False)

    users = User.objects.filter(id__in=allowed_ids).select_related('profile')

    # Поиск по тексту
    if len(query) >= 2:
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    # Сортируем: сначала друзья, потом подписчики
    users = users.annotate(
        is_friend=Case(
            When(id__in=friends_ids, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-is_friend', 'username')[:20]

    results = []
    for user in users:
        results.append({
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name() or user.username,
            'avatar': user.profile.avatar.url if hasattr(user, 'profile') and user.profile.avatar else None,
            'is_friend': user.id in friends_ids,
            'is_follower': user.id in followers_ids,
        })

    return JsonResponse(results, safe=False)