# messenger/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Message
from accounts.models import Notification
from django.contrib.auth import get_user_model

User = get_user_model()


def send_websocket_notification(user_id, notification_data, unread_count):
    """Отправка уведомления через WebSocket"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'notifications_{user_id}',
        {
            'type': 'send_notification',
            'notification': notification_data
        }
    )
    async_to_sync(channel_layer.group_send)(
        f'notifications_{user_id}',
        {
            'type': 'update_counter',
            'count': unread_count
        }
    )


def should_send_notification(user, notification_type):
    """Проверяет, нужно ли отправлять уведомление пользователю"""
    if not user or not user.is_authenticated:
        return False
    profile = user.profile
    return profile.notify_messages


# messenger/signals.py

# messenger/signals.py

# @receiver(post_save, sender=Message)
# def create_message_notification(sender, instance, created, **kwargs):
#     """Уведомление о новом сообщении"""
#     if created:
#         # Определяем отправителя (поле author)
#         sender_user = instance.author
#
#         # Определяем получателя (другой участник чата)
#         recipient = None
#         participants = instance.chat.participants.exclude(id=sender_user.id)
#         if participants.exists():
#             recipient = participants.first()
#
#         if not recipient:
#             return
#
#         # Проверяем настройки уведомлений получателя
#         if not should_send_notification(recipient, 'message'):
#             return
#
#         notification = Notification.create_notification(
#             recipient=recipient,
#             sender=sender_user,
#             notification_type='message',
#             title='Новое сообщение ✉️',
#             message=f'{sender_user.username}: {instance.content[:50]}',
#             link=f'/messenger/chat/{instance.chat.id}/'
#         )
#
#         if notification:
#             unread_count = Notification.objects.filter(
#                 recipient=recipient,
#                 is_read=False
#             ).count()
#
#             send_websocket_notification(
#                 recipient.id,
#                 {
#                     'id': notification.id,
#                     'title': notification.title,
#                     'message': notification.message,
#                     'created_at': notification.created_at.isoformat(),
#                     'notification_type': 'message',
#                     'link': notification.link
#                 },
#                 unread_count
#             )