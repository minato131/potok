from django.urls import path
from . import views

app_name = 'posts'

urlpatterns = [
    # Главная страница
    path('', views.post_list, name='feed'),

    # Поиск
    path('search/', views.search, name='search'),

    # Закладки
    path('bookmarks/', views.bookmarks_list, name='bookmarks'),

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
    path('post/<int:pk>/edit/', views.post_edit, name='post_edit'),
    path('post/<int:pk>/delete/', views.post_delete, name='post_delete'),

    # Комментарии и лайки
    path('post/<int:post_pk>/comment/', views.comment_create, name='comment_create'),
    path('like/toggle/', views.like_toggle, name='like_toggle'),

    # Избранное
    path('bookmark/<int:post_pk>/toggle/', views.bookmark_toggle, name='bookmark_toggle'),
    path('search/ajax/', views.search_ajax, name='search_ajax'),


    path('test/', views.test_view, name='test_view'),
]