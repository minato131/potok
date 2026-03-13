from django.contrib import admin
from .models import Report, Ban, ModerationLog


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ['id', 'reporter', 'content_type', 'object_id', 'report_type', 'status', 'created_at']
    list_filter = ['report_type', 'status', 'created_at']
    search_fields = ['reporter__username', 'description']
    raw_id_fields = ['reporter', 'moderated_by']
    readonly_fields = ['created_at', 'moderated_at']
    date_hierarchy = 'created_at'


@admin.register(Ban)
class BanAdmin(admin.ModelAdmin):
    list_display = ['user', 'banned_by', 'ban_type', 'created_at', 'expires_at', 'is_active']
    list_filter = ['ban_type', 'created_at']
    search_fields = ['user__username', 'banned_by__username', 'reason']
    raw_id_fields = ['user', 'banned_by', 'lifted_by']
    date_hierarchy = 'created_at'

    def is_active(self, obj):
        return obj.is_active()

    is_active.boolean = True
    is_active.short_description = 'Активна'


@admin.register(ModerationLog)
class ModerationLogAdmin(admin.ModelAdmin):
    list_display = ['moderator', 'action', 'description', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['moderator__username', 'description']
    raw_id_fields = ['moderator']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at']