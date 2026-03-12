from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .forms import CustomPasswordChangeForm

app_name = 'accounts'

urlpatterns = [
    # Существующие
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/<str:username>/', views.profile_view, name='profile_by_username'),
    path('follow/<int:user_id>/', views.follow_view, name='follow'),
    path('<str:username>/followers/', views.followers_list_view, name='followers'),
    path('<str:username>/following/', views.following_list_view, name='following'),
    path('users/', views.user_list_view, name='user_list'),

    # Смена пароля
    path('password-change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        form_class=CustomPasswordChangeForm,
        success_url='/accounts/profile/'
    ), name='password_change'),

    # Новые URL-ы для уведомлений
    path('notifications/', views.notifications_list, name='notifications'),
    path('notifications/ajax/', views.notifications_ajax, name='notifications_ajax'),
    path('notifications/<int:notification_id>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/read-all/', views.notification_mark_all_read, name='notification_mark_all_read'),
    path('verify-email/', views.verify_email, name='verify_email'),
    path('confirm-email/', views.confirm_email, name='confirm_email'),
]