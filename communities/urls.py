from django.urls import path
from . import views

app_name = 'communities'

urlpatterns = [
    # Список сообществ
    path('', views.community_list, name='community_list'),
    path('my/', views.my_communities, name='my_communities'),

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

    # API для заявок
    path('requests/<int:request_id>/approve/', views.approve_join_request, name='approve_join_request'),
    path('requests/<int:request_id>/reject/', views.reject_join_request, name='reject_join_request'),

    # Отмена заявки
    path('<slug:slug>/cancel-request/', views.cancel_join_request, name='cancel_join_request'),

    # Управление ролями
    path('<slug:slug>/change-role/', views.change_member_role, name='change_member_role'),

    # Модераторы - ВАЖНО: добавить оба маршрута
    path('<slug:slug>/add-moderator/', views.add_moderator, name='add_moderator'),
    path('<slug:slug>/remove-moderator/<int:user_id>/', views.remove_moderator, name='remove_moderator'),

    # Блокировка/разблокировка
    path('<slug:slug>/ban-member/', views.ban_community_member, name='ban_community_member'),
    path('<slug:slug>/unban-member/', views.unban_community_member, name='unban_community_member'),

    # Поиск друзей API
    path('friends/search/', views.friends_search_api, name='friends_search_api'),
    path('<slug:slug>/delete/', views.community_delete, name='community_delete'),
]