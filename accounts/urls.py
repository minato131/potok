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
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('profile/<str:username>/', views.profile_view, name='profile_by_username'),

    # Подписки
    path('follow/<int:user_id>/', views.follow_view, name='follow'),
    path('<str:username>/followers/', views.followers_list_view, name='followers'),
    path('<str:username>/following/', views.following_list_view, name='following'),

    # Друзья и сообщества
    path('friends/', views.friends_list, name='friends_list'),
    path('friends/<str:username>/', views.friends_list, name='friends_list'),
    path('friend/requests/', views.friend_requests_list, name='friend_requests'),
    path('friend/status/<int:user_id>/', views.get_friend_status, name='get_friend_status'),
    path('friend/send/<int:user_id>/', views.send_friend_request, name='send_friend_request'),
    path('friend/accept/<int:request_id>/', views.accept_friend_request, name='accept_friend_request'),
    path('friend/reject/<int:request_id>/', views.reject_friend_request, name='reject_friend_request'),
    path('friend/cancel/<int:request_id>/', views.cancel_friend_request, name='cancel_friend_request'),
    path('friend/remove/<int:user_id>/', views.remove_friend, name='remove_friend'),
    path('<str:username>/communities/', views.community_list, name='community_list'),
    path('friend/cancel-by-user/<int:user_id>/', views.cancel_friend_request_by_user, name='cancel_friend_request_by_user'),

    # Пользователи
    path('users/', views.user_list_view, name='user_list'),
    path('users/search/', views.user_search_api, name='user_search_api'),
    path('group-participants/search/', views.group_participants_search_api, name='group_participants_search_api'),

    # Смена пароля
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        form_class=CustomPasswordChangeForm,
        success_url='/accounts/profile/'
    ), name='password_change'),

    # Сброс пароля
    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='accounts/password_reset.html',
             email_template_name='accounts/password_reset_email.html',
             subject_template_name='accounts/password_reset_subject.txt',
             html_email_template_name='accounts/password_reset_email.html',
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

    # Уведомления - ИСПРАВЛЕННЫЕ МАРШРУТЫ
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/<int:notification_id>/mark-read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/mark-all-read/', views.notification_mark_all_read, name='notification_mark_all_read'),
    path('notifications/unread-count/', views.get_unread_count, name='unread_count'),
    path('notifications/ajax/', views.notifications_ajax, name='notifications_ajax'),

    # Настройки уведомлений
    path('settings/notifications/', views.notification_settings, name='notification_settings'),

    # Подтверждение email
    path('verify-email/', views.verify_email, name='verify_email'),
    path('confirm-email/', views.confirm_email, name='confirm_email'),
    path('resend-code/', views.resend_code, name='resend_code'),

    # Настройки
    path('privacy/', views.privacy_settings, name='privacy_settings'),
    path('security/', views.security_settings, name='security_settings'),
    path('blocked/', views.blocked_users, name='blocked_users'),
    path('sessions/', views.sessions, name='sessions'),
    path('export/', views.export_data, name='export_data'),

    # Юридические страницы
    path('terms/', views.terms_view, name='terms'),
    path('privacy-policy/', views.privacy_view, name='privacy'),
]