from django.urls import path
from . import views

app_name = 'communities'

urlpatterns = [
    # Список сообществ
    path('', views.community_list, name='community_list'),

    # Создание сообщества
    path('create/', views.community_create, name='community_create'),

    # Детальная страница сообщества
    path('<slug:slug>/', views.community_detail, name='community_detail'),

    # Редактирование сообщества
    path('<slug:slug>/edit/', views.community_edit, name='community_edit'),

    # Вступление/выход
    path('<slug:slug>/join/', views.community_join, name='community_join'),
    path('<slug:slug>/leave/', views.community_leave, name='community_leave'),

    # Посты в сообществе
    path('<slug:slug>/post/create/', views.community_post_create, name='community_post_create'),

    # Участники
    path('<slug:slug>/members/', views.community_members, name='community_members'),

    # Управление заявками (для закрытых сообществ)
    path('<slug:slug>/requests/', views.community_manage_requests, name='community_manage_requests'),

    path('<slug:slug>/cancel-request/', views.cancel_join_request, name='cancel_join_request'),
]