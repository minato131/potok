from django.contrib import admin
from django.utils.html import format_html
from .models import Post, Comment, Like, Category, Tag, Bookmark, PostView


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'order', 'created_at']
    list_filter = ['parent']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['order']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'author', 'category', 'status',
        'views_count', 'likes_count', 'comments_count', 'created_at'
    ]
    list_filter = ['status', 'category', 'tags', 'created_at']
    search_fields = ['title', 'content', 'author__username']
    readonly_fields = ['views_count', 'likes_count', 'comments_count', 'created_at', 'updated_at']
    filter_horizontal = ['tags']
    list_editable = ['status']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Основное', {
            'fields': ('title', 'content', 'author', 'status')
        }),
        ('Классификация', {
            'fields': ('category', 'tags')
        }),
        ('Медиа', {
            'fields': ('image', 'video'),
            'classes': ('collapse',)
        }),
        ('Статистика', {
            'fields': ('views_count', 'likes_count', 'comments_count'),
            'classes': ('collapse',)
        }),
        ('Даты', {
            'fields': ('created_at', 'updated_at', 'published_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'post', 'short_content', 'likes_count', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'is_deleted', 'created_at']
    search_fields = ['content', 'author__username', 'post__title']
    list_editable = ['is_approved']

    def short_content(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content

    short_content.short_description = 'Содержание'


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ['user', 'content_type', 'object_id', 'like_type', 'created_at']
    list_filter = ['content_type', 'like_type', 'created_at']
    search_fields = ['user__username']


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ['user', 'post', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'post__title']


@admin.register(PostView)
class PostViewAdmin(admin.ModelAdmin):
    list_display = ['post', 'user', 'ip_address', 'viewed_at']
    list_filter = ['viewed_at']
    search_fields = ['post__title', 'user__username']