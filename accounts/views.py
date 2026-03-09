from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.contrib.auth.forms import AuthenticationForm
from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import User, Follow


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