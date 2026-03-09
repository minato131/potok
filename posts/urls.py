from django.urls import path
from . import views

app_name = 'posts'

urlpatterns = [
    # Существующие
    path('', views.post_list, name='post_list'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/create/', views.post_create, name='post_create'),
    path('post/<int:pk>/edit/', views.post_edit, name='post_edit'),
    path('post/<int:pk>/delete/', views.post_delete, name='post_delete'),
    path('post/<int:post_pk>/comment/', views.comment_create, name='comment_create'),
    path('like/toggle/', views.like_toggle, name='like_toggle'),
    path('bookmark/<int:post_pk>/toggle/', views.bookmark_toggle, name='bookmark_toggle'),
    path('bookmarks/', views.bookmarks_list, name='bookmarks'),

    # Новые
    path('categories/', views.category_list, name='category_list'),
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('tags/', views.tag_list, name='tag_list'),
    path('tag/<slug:slug>/', views.tag_detail, name='tag_detail'),
    path('search/', views.search, name='search'),
]