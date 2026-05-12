from django.utils import timezone
from datetime import timedelta

from communities.models import Community
from posts.models import Post, Like, Bookmark, Comment
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

logger = logging.getLogger(__name__)


def register_view(request):
    """
    Регистрация нового пользователя
    """
    if request.user.is_authenticated:
        return redirect('posts:post_list')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # Создаем пользователя
            user = form.save(commit=False)
            user.email_verified = False
            user.save()

            Profile.objects.get_or_create(user=user)

            # Генерируем и отправляем код
            code = generate_verification_code()
            user.email_verification_code = code
            user.email_verification_sent = timezone.now()  # теперь работает
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
            messages.error(request, 'Пожалуйста, исправьте ошибки в форме')
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
    """
    Просмотр профиля пользователя
    """
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user

    # Статистика
    posts_count = user.posts.filter(status='published').count()
    followers_count = Follow.objects.filter(following=user).count()
    following_count = Follow.objects.filter(follower=user).count()

    # Посты пользователя
    user_posts = user.posts.filter(status='published').order_by('-created_at')[:10]

    # Комментарии пользователя
    from posts.models import Comment
    user_comments = Comment.objects.filter(
        author=user,
        is_deleted=False
    ).select_related('post').order_by('-created_at')[:10]

    # Сообщества пользователя
    from communities.models import CommunityMembership
    user_communities = CommunityMembership.objects.filter(
        user=user,
        status='active'
    ).select_related('community').order_by('-joined_at')[:10]

    # Закладки пользователя (только для своего профиля)
    user_bookmarks = []
    if request.user == user:
        from posts.models import Bookmark
        user_bookmarks = Bookmark.objects.filter(
            user=user
        ).select_related('post', 'post__author', 'post__author__profile').order_by('-created_at')[:10]

    # Проверка подписки
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(
            follower=request.user,
            following=user
        ).exists()

    # Лайки
    liked_post_ids = set()
    if request.user.is_authenticated:
        from posts.models import Like
        post_ids = [p.id for p in user_posts]
        liked_post_ids = set(Like.objects.filter(
            user=request.user, content_type='post', object_id__in=post_ids
        ).values_list('object_id', flat=True))

    # Понравившиеся посты
    from posts.models import Like
    liked_post_ids_full = Like.objects.filter(
        user=user, content_type='post'
    ).values_list('object_id', flat=True)
    liked_posts = Post.objects.filter(
        id__in=liked_post_ids_full, status='published'
    ).select_related('author', 'author__profile').order_by('-created_at')[:10]

    # Друзья и сообщества
    from accounts.models import Friendship
    from communities.models import Community

    friends_count = Friendship.objects.filter(user=user).count()
    communities_count = Community.objects.filter(members=user).count()

    context = {
        'profile_user': user,
        'posts_count': posts_count,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'user_posts': user_posts,
        'liked_posts': liked_posts,
        'user_comments': user_comments,
        'user_communities': user_communities,
        'user_bookmarks': user_bookmarks,
        'friends_count': friends_count,
        'communities_count': communities_count,
        'liked_post_ids': liked_post_ids,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def privacy_settings(request):
    """Настройки приватности"""
    if request.method == 'POST':
        profile = request.user.profile
        profile.is_private = request.POST.get('is_private') == 'on'
        profile.show_email = request.POST.get('show_email') == 'on'
        profile.allow_messages = request.POST.get('allow_messages', 'everyone')
        profile.allow_comments = request.POST.get('allow_comments', 'everyone')
        profile.save()
        messages.success(request, 'Настройки приватности сохранены')
        return redirect('accounts:privacy_settings')

    return render(request, 'accounts/privacy_settings.html', {
        'profile': request.user.profile,
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

        # Собираем ВСЕ данные
        posts = list(request.user.posts.filter(status='published').values('title', 'content', 'created_at'))
        posts_count = len(posts)
        comments = list(Comment.objects.filter(author=request.user).values('content', 'created_at', 'post__title'))

        data = {
            'username': request.user.username,
            'email': request.user.email,
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'date_joined': request.user.date_joined.isoformat(),
            'posts_count': posts_count,
            'posts': posts,
            'comments_count': len(comments),
            'comments': comments,
        }

        if export_type == 'json':
            # Собираем полные данные
            from posts.models import Bookmark, Like
            from communities.models import Community
            from accounts.models import Friendship

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
                    'followers_count': request.user.profile_followers.count(),
                    'following_count': request.user.profile.following.count(),
                    'friends_count': Friendship.objects.filter(user=request.user).count(),
                    'bookmarks_count': Bookmark.objects.filter(user=request.user).count(),
                    'likes_count': Like.objects.filter(user=request.user, content_type='post').count(),
                    'comments_count': len(comments),
                },
                'posts': list(request.user.posts.filter(status='published').values(
                    'id', 'title', 'content', 'created_at', 'updated_at', 'likes_count', 'views_count'
                )),
                'comments': list(Comment.objects.filter(author=request.user).values(
                    'id', 'content', 'created_at', 'post__title'
                )),
                'bookmarks': list(Bookmark.objects.filter(user=request.user).select_related('post').values(
                    'post__id', 'post__title', 'created_at'
                )),
                'liked_posts': list(Post.objects.filter(
                    id__in=Like.objects.filter(user=request.user, content_type='post').values_list('object_id',
                                                                                                   flat=True)
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
            response['Content-Disposition'] = f'attachment; filename="potok_data_{request.user.username}.json"'
            return response

        elif export_type == 'pdf':
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.pdfgen import canvas
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                from django.conf import settings
                import os

                buffer = BytesIO()
                p = canvas.Canvas(buffer, pagesize=A4)

                font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'DejaVuSans.ttf')
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('DejaVu', font_path))
                    font_name = 'DejaVu'
                else:
                    font_name = 'Helvetica'

                y = 820

                # Заголовок
                p.setFont(font_name, 20)
                p.drawString(50, y, "Архив данных • Поток")
                y -= 30
                p.setFont(font_name, 16)
                p.drawString(50, y, f"Пользователь: @{request.user.username}")
                y -= 30

                # Основная информация
                p.setFont(font_name, 14)
                p.drawString(50, y, "Основная информация")
                y -= 22
                p.setFont(font_name, 11)
                info_lines = [
                    f"Имя: {request.user.get_full_name() or 'Не указано'}",
                    f"Email: {request.user.email}",
                    f"Дата регистрации: {request.user.date_joined.strftime('%d.%m.%Y')}",
                    f"Биография: {request.user.profile.bio or 'Не указана'}",
                    f"Местоположение: {request.user.profile.location or 'Не указано'}",
                    f"Веб-сайт: {request.user.profile.website or 'Не указан'}",
                    f"Телефон: {request.user.profile.phone or 'Не указан'}",
                ]
                for line in info_lines:
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 11)
                    p.drawString(60, y, line)
                    y -= 18
                y -= 10

                # Статистика
                p.setFont(font_name, 14)
                p.drawString(50, y, "Статистика")
                y -= 22
                p.setFont(font_name, 11)
                stats = [
                    f"Постов: {posts_count}",
                    f"Подписчиков: {request.user.profile_followers.count()}",
                    f"Подписок: {request.user.profile.following.count()}",
                    f"Друзей: {Friendship.objects.filter(user=request.user).count()}",
                ]
                for s in stats:
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 11)
                    p.drawString(60, y, s)
                    y -= 18
                y -= 10

                # Посты
                p.setFont(font_name, 14)
                p.drawString(50, y, f"Посты ({len(posts)})")
                y -= 22
                p.setFont(font_name, 11)
                for i, post in enumerate(posts, 1):
                    if y < 80:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 11)
                    p.setFont(font_name, 12)
                    p.drawString(60, y, f"{i}. {post['title'][:90]}")
                    y -= 18
                    p.setFont(font_name, 10)
                    content = post['content'][:200].replace('\n', ' ')
                    p.drawString(70, y, f"{content}")
                    y -= 16
                    p.drawString(70, y, f"Опубликовано: {str(post['created_at'])[:19]}")
                    y -= 22
                y -= 10

                # Комментарии
                p.setFont(font_name, 14)
                p.drawString(50, y, f"Комментарии ({len(comments)})")
                y -= 22
                p.setFont(font_name, 10)
                for i, comment in enumerate(comments[:30], 1):
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 10)
                    p.drawString(60, y, f"{i}. [{str(comment['created_at'])[:19]}] {comment['content'][:150]}")
                    y -= 16
                y -= 10

                # Закладки
                from posts.models import Bookmark
                bookmarks = Bookmark.objects.filter(user=request.user).select_related('post')[:20]
                p.setFont(font_name, 14)
                p.drawString(50, y, f"Закладки ({bookmarks.count()})")
                y -= 22
                p.setFont(font_name, 10)
                for i, bm in enumerate(bookmarks, 1):
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 10)
                    p.drawString(60, y, f"{i}. {bm.post.title[:90]} — {str(bm.created_at)[:19]}")
                    y -= 16
                y -= 10

                # Лайки
                from posts.models import Like
                liked_ids = Like.objects.filter(
                    user=request.user, content_type='post'
                ).values_list('object_id', flat=True)[:20]
                liked_posts = Post.objects.filter(id__in=liked_ids)
                liked_count = Like.objects.filter(user=request.user, content_type='post').count()
                p.setFont(font_name, 14)
                p.drawString(50, y, f"Понравившиеся посты ({liked_count})")
                y -= 22
                p.setFont(font_name, 10)
                for i, post in enumerate(liked_posts, 1):
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 10)
                    p.drawString(60, y, f"{i}. {post.title[:90]}")
                    y -= 16
                y -= 10

                # Сообщества
                from communities.models import Community
                communities = Community.objects.filter(members=request.user)[:20]
                p.setFont(font_name, 14)
                p.drawString(50, y, f"Сообщества ({communities.count()})")
                y -= 22
                p.setFont(font_name, 10)
                for i, c in enumerate(communities, 1):
                    if y < 60:
                        p.showPage()
                        y = 820
                        p.setFont(font_name, 10)
                    p.drawString(60, y, f"{i}. c/{c.name}")
                    y -= 16
                y -= 10

                # Музыка
                try:
                    from music_app.models import SavedTrack
                    tracks = SavedTrack.objects.filter(user=request.user)[:20]
                    if tracks.exists():
                        p.setFont(font_name, 14)
                        p.drawString(50, y, f"Сохранённые треки ({tracks.count()})")
                        y -= 22
                        p.setFont(font_name, 10)
                        for i, t in enumerate(tracks, 1):
                            if y < 60:
                                p.showPage()
                                y = 820
                                p.setFont(font_name, 10)
                            p.drawString(60, y, f"{i}. {t.title} — {t.artist}")
                            y -= 16
                except ImportError:
                    pass

                # Футер
                y -= 10
                p.setFont(font_name, 8)
                p.drawString(50, 30, f"Экспортировано: {timezone.now().strftime('%d.%m.%Y %H:%M')} • Поток")

                p.save()
                buffer.seek(0)
                response = HttpResponse(buffer, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="potok_data_{request.user.username}.pdf"'
                return response

            except ImportError:
                messages.error(request, 'PDF-экспорт недоступен. pip install reportlab')
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
    """Подписка/отписка от пользователя"""
    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        return JsonResponse({
            'status': 'error',
            'message': 'Нельзя подписаться на самого себя'
        }, status=400)

    # Получаем или создаем профиль текущего пользователя
    current_profile, _ = Profile.objects.get_or_create(user=request.user)

    # Получаем или создаем профиль целевого пользователя
    target_profile, _ = Profile.objects.get_or_create(user=target_user)

    if current_profile.following.filter(id=target_user.id).exists():
        current_profile.following.remove(target_user)
        status = 'unfollowed'
        message = 'Вы отписались'
    else:
        current_profile.following.add(target_user)
        status = 'followed'
        message = 'Вы подписались'

        # Создаем уведомление
        try:
            from accounts.utils import create_notification
            create_notification(
                recipient=target_user,
                sender=request.user,
                notification_type='follow',
                title='Новый подписчик',
                message=f'@{request.user.username} подписался на вас',
                link=f'/accounts/profile/{request.user.username}/'
            )
        except (ImportError, AttributeError):
            pass

    return JsonResponse({
        'status': status,
        'message': message,
        'user_id': user_id,
        'followers_count': target_profile.followers.count()
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
    """
    Список подписок пользователя
    """
    user = get_object_or_404(User, username=username)
    following = Follow.objects.filter(
        follower=user
    ).select_related('following').order_by('-created_at')  # Добавил сортировку

    paginator = Paginator(following, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'accounts/following_list.html', {
        'page_obj': page_obj,
        'profile_user': user,
        'title': 'Подписки'
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
    """
    Отметить уведомление как прочитанное
    """
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.mark_as_read()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok'})

    return redirect(request.META.get('HTTP_REFERER', 'accounts:notifications'))


@login_required
@require_POST
def notification_mark_all_read(request):
    """
    Отметить все уведомления как прочитанные
    """
    request.user.notifications.filter(is_read=False).update(is_read=True)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'ok'})

    return redirect('accounts:notifications')


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


@login_required
@require_POST
def toggle_friend(request, user_id):
    target = get_object_or_404(User, id=user_id)
    if target == request.user:
        return JsonResponse({'error': 'Нельзя добавить себя'}, status=400)

    friendship = Friendship.objects.filter(user=request.user, friend=target).first()
    if friendship:
        friendship.delete()
        return JsonResponse({'action': 'removed'})
    else:
        Friendship.objects.create(user=request.user, friend=target)
        return JsonResponse({'action': 'added'})


def friend_list(request, username):
    """Список друзей пользователя"""
    profile_user = get_object_or_404(User.objects.select_related('profile'), username=username)
    friendships = Friendship.objects.filter(user=profile_user).select_related('friend', 'friend__profile')

    query = request.GET.get('q', '')
    if query:
        friendships = friendships.filter(
            Q(friend__username__icontains=query) |
            Q(friend__first_name__icontains=query) |
            Q(friend__last_name__icontains=query)
        )

    paginator = Paginator(friendships, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'accounts/friend_list.html', {
        'profile_user': profile_user,
        'friendships': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'query': query,
        'total_count': friendships.count(),
    })


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