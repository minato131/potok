from django.urls import path
from . import views

app_name = 'messenger'

urlpatterns = [
    path('', views.messenger, name='messenger'),
    path('api/chat/<int:chat_id>/', views.api_chat_messages, name='api_chat_messages'),
    path('api/search/<int:chat_id>/', views.api_search_messages, name='api_search_messages'),
    path('chat/<int:chat_id>/send/', views.send_message, name='send_message'),
    path('chat/<int:chat_id>/settings/', views.chat_settings, name='chat_settings'),
    path('chat/<int:chat_id>/info/', views.api_chat_info, name='api_chat_info'),
    path('create/private/', views.create_private_chat, name='create_private_chat'),
    path('create/group/', views.create_group_chat, name='create_group_chat'),
    path('message/<int:message_id>/edit/', views.edit_message, name='edit_message'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('message/<int:message_id>/reaction/', views.toggle_reaction, name='toggle_reaction'),
    path('create-or-get-chat/', views.create_or_get_chat, name='create_or_get_chat'),
    path('search-users/', views.search_users_for_chat, name='search_users_for_chat'),
    path('api/user/<int:user_id>/', views.api_user_profile, name='api_user_profile'),
    path('api/group/<int:chat_id>/', views.api_group_info, name='api_group_info'),
    path('api/chat/<int:chat_id>/media/', views.api_chat_media, name='api_chat_media'),
    path('message/<int:message_id>/read/', views.mark_message_read, name='mark_message_read'),
    path('message/<int:message_id>/status/', views.message_status, name='message_status'),
    path('forward/<int:post_id>/', views.forward_post_to_pm, name='forward_post_to_pm'),
    path('forward-multiple/', views.forward_multiple_messages, name='forward_multiple_messages'),
    path('delete-multiple/', views.delete_multiple_messages, name='delete_multiple'),
    path('api/chats-list/', views.api_chats_list, name='api_chats_list'),
    path('api/friends/', views.api_friends_list, name='api_friends_list'),
]