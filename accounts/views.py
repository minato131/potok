from django.utils import timezone
from datetime import timedelta
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
from .models import Notification

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
        ).select_related('post').order_by('-created_at')[:10]

    # Проверка подписки
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(
            follower=request.user,
            following=user
        ).exists()

    context = {
        'profile_user': user,
        'posts_count': posts_count,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'user_posts': user_posts,
        'user_comments': user_comments,
        'user_communities': user_communities,
        'user_bookmarks': user_bookmarks,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def profile_edit_view(request):
    if request.method == 'POST':
        # Для AJAX запроса с аватаром
        if request.FILES.get('avatar'):
            user = request.user
            user.avatar = request.FILES['avatar']
            user.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'avatar_url': user.avatar.url
                })

        # Обычная форма
        form = CustomUserChangeForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('accounts:profile')
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки')
    else:
        form = CustomUserChangeForm(instance=request.user)

    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def follow_view(request, user_id):
    """
    Подписка/отписка от пользователя (поддерживает AJAX)
    """
    user_to_follow = get_object_or_404(User, id=user_id)

    if request.user == user_to_follow:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Нельзя подписаться на себя'}, status=400)
        messages.error(request, 'Нельзя подписаться на самого себя')
        return redirect('accounts:profile_by_username', username=user_to_follow.username)

    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )

    if created:
        # Создаем уведомление
        from .utils import create_notification
        create_notification(
            recipient=user_to_follow,
            sender=request.user,
            notification_type='follow',
            title='Новый подписчик',
            message=f'@{request.user.username} подписался на вас',
            link=f'/accounts/profile/{request.user.username}/'
        )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Возвращаем ТОЛЬКО количество подписчиков пользователя, на которого подписались
            followers_count = Follow.objects.filter(following=user_to_follow).count()
            return JsonResponse({
                'action': 'followed',
                'followers_count': followers_count,  # Только это нужно для обновления
                'message': f'Вы подписались на {user_to_follow.username}'
            })
        messages.success(request, f'Вы подписались на {user_to_follow.username}')
    else:
        follow.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Возвращаем ТОЛЬКО количество подписчиков пользователя, от которого отписались
            followers_count = Follow.objects.filter(following=user_to_follow).count()
            return JsonResponse({
                'action': 'unfollowed',
                'followers_count': followers_count,  # Только это нужно для обновления
                'message': f'Вы отписались от {user_to_follow.username}'
            })
        messages.info(request, f'Вы отписались от {user_to_follow.username}')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    return redirect('accounts:profile_by_username', username=user_to_follow.username)


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