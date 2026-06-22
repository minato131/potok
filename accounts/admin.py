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
        'is_platform_moderator',
        'email_verified',
        'is_staff',
        'is_active',
        'date_joined'
    ]
    list_filter = ['is_platform_moderator', 'email_verified', 'is_staff', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    fieldsets = UserAdmin.fieldsets + (
        ('Права модерации', {
            'fields': (
                'is_platform_moderator',
            )
        }),
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

    # ========== ЗАЩИТА ОТ САМОУДАЛЕНИЯ ==========

    def delete_view(self, request, object_id, extra_context=None):
        """
        Переопределяем метод удаления: запрещаем удалять самого себя
        """
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)

        # Если текущий пользователь пытается удалить себя
        if obj == request.user:
            messages.error(request, "❌ Вы не можете удалить себя, поскольку вы администратор")
            return redirect('admin:accounts_user_changelist')

        # Иначе разрешаем стандартное удаление
        return super().delete_view(request, object_id, extra_context)

    def delete_queryset(self, request, queryset):
        """
        Защита от массового удаления через выделение и удаление
        """
        # Убираем текущего пользователя из списка на удаление
        if request.user in queryset:
            queryset = queryset.exclude(pk=request.user.pk)
            messages.warning(request, "⚠️ Вы были исключены из массового удаления, так как нельзя удалить себя")

        # Если после исключения остались объекты — удаляем их
        if queryset.exists():
            super().delete_queryset(request, queryset)
        else:
            messages.info(request, "Нет пользователей для удаления")


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