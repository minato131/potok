# messenger/urls.py
from django.urls import path
from . import views

app_name = 'messenger'

urlpatterns = [
    path('', views.chat_list, name='chat_list'),
    path('chat/<int:chat_id>/', views.chat_detail, name='chat_detail'),
    path('chat/<int:chat_id>/send/', views.send_message, name='send_message'),
    path('chat/<int:chat_id>/settings/', views.chat_settings, name='chat_settings'),
    path('create/private/', views.create_private_chat, name='create_private_chat'),
    path('create/group/', views.create_group_chat, name='create_group_chat'),  # ← должно быть так
    path('message/<int:message_id>/edit/', views.edit_message, name='edit_message'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete_message'),
]