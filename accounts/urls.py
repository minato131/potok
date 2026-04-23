# accounts/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import CustomPasswordChangeForm

app_name = 'accounts'

urlpatterns = [
    # Регистрация и вход
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Профиль
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/<str:username>/', views.profile_view, name='profile_by_username'),

    # Подписки
    path('follow/<int:user_id>/', views.follow_view, name='follow'),
    path('<str:username>/followers/', views.followers_list_view, name='followers'),
    path('<str:username>/following/', views.following_list_view, name='following'),

    # Пользователи
    path('users/', views.user_list_view, name='user_list'),

    # Смена пароля (для авторизованных)
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        form_class=CustomPasswordChangeForm,
        success_url='/accounts/profile/'
    ), name='password_change'),

    # Сброс пароля (для неавторизованных - "Забыли пароль?")
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='accounts/password_reset.html',
             email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             html_email_template_name='accounts/password_reset_email.html',  # ← добавь эту строку
             success_url='/accounts/password-reset/done/'
         ),
         name='password_reset'),

    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='accounts/password_reset_done.html'
         ),
         name='password_reset_done'),

    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='accounts/password_reset_confirm.html',
             success_url='/accounts/password-reset-complete/'
         ),
         name='password_reset_confirm'),

    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='accounts/password_reset_complete.html'
         ),
         name='password_reset_complete'),

    # Уведомления
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/ajax/', views.notifications_ajax, name='notifications_ajax'),
    path('notifications/<int:notification_id>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/read-all/', views.notification_mark_all_read, name='notification_mark_all_read'),

    # Подтверждение email
    path('verify-email/', views.verify_email, name='verify_email'),
    path('confirm-email/', views.confirm_email, name='confirm_email'),
    path('resend-code/', views.resend_code, name='resend_code'),

    # Юридические страницы
    path('terms/', views.terms_view, name='terms'),
    path('privacy/', views.privacy_view, name='privacy'),
    path('profile/delete/', views.delete_account, name='delete_account'),
]