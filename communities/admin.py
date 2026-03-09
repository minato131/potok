from django.contrib import admin
from django.utils.html import format_html
from .models import Community, CommunityMembership, CommunityPost, CommunityInvite, CommunityJoinRequest


class CommunityMembershipInline(admin.TabularInline):
    model = CommunityMembership
    extra = 1
    raw_id_fields = ['user']


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'creator', 'privacy', 'status',
        'members_count', 'posts_count', 'created_at'
    ]
    list_filter = ['privacy', 'status', 'created_at']
    search_fields = ['name', 'description', 'creator__username']
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ['admins', 'categories', 'tags']
    readonly_fields = ['members_count', 'posts_count', 'created_at', 'updated_at']
    inlines = [CommunityMembershipInline]

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'slug', 'description', 'creator')
        }),
        ('Медиа', {
            'fields': ('avatar', 'cover'),
            'classes': ('collapse',)
        }),
        ('Настройки', {
            'fields': ('privacy', 'status')
        }),
        ('Управление', {
            'fields': ('admins',)
        }),
        ('Классификация', {
            'fields': ('categories', 'tags'),
            'classes': ('collapse',)
        }),
        ('Статистика', {
            'fields': ('members_count', 'posts_count'),
            'classes': ('collapse',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('creator')


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'community', 'role', 'status', 'joined_at']
    list_filter = ['role', 'status', 'joined_at']
    search_fields = ['user__username', 'community__name']
    raw_id_fields = ['user', 'community']


@admin.register(CommunityPost)
class CommunityPostAdmin(admin.ModelAdmin):
    list_display = ['post_title', 'community', 'is_pinned', 'is_announcement']
    list_filter = ['is_pinned', 'is_announcement']
    search_fields = ['post__title', 'community__name']
    raw_id_fields = ['post', 'community']

    def post_title(self, obj):
        return obj.post.title

    post_title.short_description = 'Пост'


@admin.register(CommunityInvite)
class CommunityInviteAdmin(admin.ModelAdmin):
    list_display = ['community', 'inviter', 'invitee', 'created_at', 'accepted_at']
    list_filter = ['created_at', 'accepted_at']
    search_fields = ['community__name', 'inviter__username', 'invitee__username']


@admin.register(CommunityJoinRequest)
class CommunityJoinRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'community', 'created_at', 'approved', 'processed_at']
    list_filter = ['approved', 'created_at']
    search_fields = ['user__username', 'community__name']
    raw_id_fields = ['user', 'community', 'processed_by']