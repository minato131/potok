from django.urls import path
from . import views

app_name = 'posts'

urlpatterns = [
    # Главная страница
    path('', views.post_list, name='post_list'),

    # Поиск
    path('search/', views.search, name='search'),

    # Закладки
    path('bookmarks/', views.bookmarks_list, name='bookmarks'),
    path('bookmark/<int:post_pk>/toggle/', views.bookmark_toggle, name='bookmark_toggle'),
    path('bookmark/<int:bookmark_id>/remove/', views.bookmark_remove, name='bookmark_remove'),
    path('bookmarks/clear/', views.bookmarks_clear, name='bookmarks_clear'),

    # Категории
    path('categories/', views.category_list, name='category_list'),
    path('category/create/', views.category_create, name='category_create'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('category/<slug:slug>/edit/', views.category_edit, name='category_edit'),

    # Теги - ВАЖНО: create должен быть перед <slug:slug>
    path('tags/', views.tag_list, name='tag_list'),
    path('tags/create/', views.tag_create_ajax, name='tag_create_ajax'),  # ← AJAX создание
    path('tags/popular/', views.tag_popular, name='tag_popular'),  # ← популярные теги
    path('tag/create/', views.tag_create, name='tag_create'),  # ← обычная форма (если есть)
    path('tag/<slug:slug>/', views.tag_detail, name='tag_detail'),
    path('tag/<slug:slug>/edit/', views.tag_edit, name='tag_edit'),
    path('tag/<slug:slug>/delete/', views.tag_delete, name='tag_delete'),
    path('tags/search/', views.tag_search, name='tag_search'),

    # Посты
    path('post/create/', views.post_create, name='post_create'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/<int:pk>/delete/', views.post_delete, name='post_delete'),
    path('posts/<int:pk>/edit/', views.post_edit, name='post_edit'),

    # Комментарии и лайки
    path('post/<int:post_pk>/comment/', views.comment_create, name='comment_create'),
    path('like/toggle/', views.like_toggle, name='like_toggle'),
    path('comment/<int:comment_id>/edit/', views.comment_edit, name='comment_edit'),
    path('post/comment/<int:comment_id>/delete/', views.comment_delete, name='comment_delete_with_post'),

    # Избранное
    path('bookmark/<int:post_pk>/toggle/', views.bookmark_toggle, name='bookmark_toggle'),
    path('search/ajax/', views.search_ajax, name='search_ajax'),
    path('tag/<slug:slug>/', views.tag_detail, name='tag_detail'),
    path('tags/', views.tag_list, name='tag_list'),
    path('recommended/api/', views.recommended_posts_api, name='recommended_api'),
    # Модальное окно со списком лайкнувших
    path('post/<int:post_id>/likes/', views.post_likes_modal, name='post_likes_modal'),
    path('tag/<str:tag_name>/', views.tag_posts, name='tag_posts'),

    path('post/comment/<int:comment_id>/edit/', views.comment_edit, name='comment_edit_old'),
    path('poll/vote/', views.poll_vote, name='poll_vote'),
    path('poll/unvote/', views.poll_unvote, name='poll_unvote'),
    path('poll/<int:poll_id>/voters/', views.poll_voters, name='poll_voters'),
]