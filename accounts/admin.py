from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import User, Follow, Notification


class CustomUserAdmin(UserAdmin):
    """
    Кастомная админка для пользователей
    """
    list_display = [
        'username',
        'email',
        'first_name',
        'last_name',
        'email_verified',
        'is_staff',
        'is_active',
        'date_joined'
    ]
    list_filter = ['email_verified', 'is_staff', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    fieldsets = UserAdmin.fieldsets + (
        ('Дополнительная информация', {
            'fields': (
                'avatar',
                'bio',
                'birth_date',
                'email_verified',
                'email_verification_code',
                'email_verification_sent',
                'last_activity',
                'private_profile',
                'hide_email',
                'message_privacy',
                'telegram',
                'vk',
                'github',
                'email_likes',
                'email_comments',
                'email_follows',
                'email_messages'
            )
        }),
    )

    readonly_fields = ['last_activity', 'email_verification_sent', 'date_joined', 'last_login']

    def avatar_preview(self, obj):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.avatar.url)
        return "Нет аватара"

    avatar_preview.short_description = 'Аватар'


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """
    Админка для подписок
    """
    list_display = ['follower', 'following', 'created_at']
    list_filter = ['created_at']
    search_fields = ['follower__username', 'following__username']
    raw_id_fields = ['follower', 'following']
    date_hierarchy = 'created_at'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """
    Админка для уведомлений
    """
    list_display = ['recipient', 'sender', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['recipient__username', 'sender__username', 'title']
    raw_id_fields = ['recipient', 'sender']
    date_hierarchy = 'created_at'


# Регистрируем модель User
admin.site.register(User, CustomUserAdmin)