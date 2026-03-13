from django.contrib import admin
from .models import Chat, ChatParticipant, Message


class ChatParticipantInline(admin.TabularInline):
    model = ChatParticipant
    extra = 1
    raw_id_fields = ['user']
    verbose_name = 'Участник'
    verbose_name_plural = 'Участники'


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'chat_type', 'created_at', 'updated_at']
    list_filter = ['chat_type', 'created_at']
    search_fields = ['name']
    inlines = [ChatParticipantInline]  # Вместо filter_horizontal используем inlines
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'chat_type')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ChatParticipant)
class ChatParticipantAdmin(admin.ModelAdmin):
    list_display = ['user', 'chat', 'joined_at', 'last_read', 'is_admin']
    list_filter = ['is_admin', 'joined_at']
    search_fields = ['user__username', 'chat__name']
    raw_id_fields = ['user', 'chat']
    readonly_fields = ['joined_at']

    fieldsets = (
        ('Основная информация', {
            'fields': ('user', 'chat', 'is_admin')
        }),
        ('Даты', {
            'fields': ('joined_at', 'last_read'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['author', 'chat', 'short_content', 'is_read', 'is_edited', 'created_at']
    list_filter = ['is_read', 'is_edited', 'is_deleted', 'created_at']
    search_fields = ['content', 'author__username']
    raw_id_fields = ['author', 'chat']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основная информация', {
            'fields': ('author', 'chat', 'content')
        }),
        ('Статус', {
            'fields': ('is_read', 'is_edited', 'is_deleted')
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def short_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content

    short_content.short_description = 'Сообщение'