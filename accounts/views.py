from datetime import timezone

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.contrib.auth.forms import AuthenticationForm
from django.http import JsonResponse
from django.views.decorators.http import require_POST

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
        return redirect('posts:post_list')  # <-- ИСПРАВЛЕНО

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно!')
            return redirect('posts:post_list')  # <-- ИСПРАВЛЕНО
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
    Если username не указан - показываем профиль текущего пользователя
    """
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user

    # Получаем статистику
    posts_count = user.posts.count()  # <-- ИСПРАВЛЕНО: было post_set, стало posts (related_name в модели)
    followers_count = Follow.objects.filter(following=user).count()
    following_count = Follow.objects.filter(follower=user).count()

    # Проверяем, подписан ли текущий пользователь на просматриваемого
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(
            follower=request.user,
            following=user
        ).exists()

    # Получаем посты пользователя
    user_posts = user.posts.filter(status='published').order_by('-created_at')[:10]  # <-- ИСПРАВЛЕНО

    context = {
        'profile_user': user,
        'posts_count': posts_count,
        'followers_count': followers_count,
        'following_count': following_count,
        'is_following': is_following,
        'user_posts': user_posts,  # <-- ДОБАВЛЕНО для отображения в профиле
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def profile_edit_view(request):
    """
    Редактирование профиля текущего пользователя
    """
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('accounts:profile')  # <-- ИСПРАВЛЕНО
        else:
            messages.error(request, 'Пожалуйста, исправьте ошибки')
    else:
        form = CustomUserChangeForm(instance=request.user)

    return render(request, 'accounts/profile_edit.html', {'form': form})


@login_required
def follow_view(request, user_id):
    """
    Подписка/отписка от пользователя
    """
    user_to_follow = get_object_or_404(User, id=user_id)

    # Нельзя подписаться на самого себя
    if request.user == user_to_follow:
        messages.error(request, 'Нельзя подписаться на самого себя')
        return redirect('accounts:profile_by_username', username=user_to_follow.username)

    # Проверяем, есть ли уже подписка
    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )

    if created:
        messages.success(request, f'Вы подписались на {user_to_follow.username}')
    else:
        follow.delete()
        messages.info(request, f'Вы отписались от {user_to_follow.username}')

    return redirect('accounts:profile_by_username', username=user_to_follow.username)


@login_required
def followers_list_view(request, username):
    """
    Список подписчиков пользователя
    """
    user = get_object_or_404(User, username=username)
    followers = Follow.objects.filter(following=user).select_related('follower')

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
    following = Follow.objects.filter(follower=user).select_related('following')

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
    notifications = request.user.notifications.filter(is_read=False)[:5]

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


@login_required
def verify_email(request):
    """
    Отправка кода подтверждения на email
    """
    if request.method == 'POST':
        email = request.POST.get('email')

        # Проверяем, что email принадлежит пользователю
        if email != request.user.email:
            return JsonResponse({
                'status': 'error',
                'message': 'Email не совпадает с вашим текущим email'
            }, status=400)

        # Генерируем код подтверждения
        verification_code = ''.join(random.choices(string.digits, k=6))

        # Сохраняем код в сессии с временной меткой
        request.session['verification_code'] = {
            'code': verification_code,
            'email': email,
            'created_at': timezone.now().timestamp()
        }

        # Отправляем код на почту
        if send_verification_email(request.user, verification_code):
            return JsonResponse({
                'status': 'success',
                'message': 'Код отправлен. Проверьте почту.'
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Ошибка при отправке письма. Попробуйте позже.'
            }, status=500)

    return JsonResponse({'status': 'error', 'message': 'Метод не поддерживается'}, status=405)


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