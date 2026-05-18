# accounts/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, Follow, Friendship
from django.contrib.auth import get_user_model

User = get_user_model()


# ========== WebSocket отправка ==========
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


def send_counter_update(user_id):
    """Отправка только обновления счетчика"""
    from .models import Notification
    channel_layer = get_channel_layer()
    unread_count = Notification.objects.filter(
        recipient_id=user_id,
        is_read=False
    ).count()
    async_to_sync(channel_layer.group_send)(
        f'notifications_{user_id}',
        {
            'type': 'update_counter',
            'count': unread_count
        }
    )


# ========== Уведомления о подписках (Follow) ==========
@receiver(post_save, sender=Follow)
def create_follow_notification(sender, instance, created, **kwargs):
    """Уведомление о новой подписке"""
    if created and instance.follower != instance.following:
        # Проверяем настройки уведомлений получателя
        recipient_profile = instance.following.profile
        if not recipient_profile.notify_follows:
            return

        notification = Notification.create_notification(
            recipient=instance.following,
            sender=instance.follower,
            notification_type='follow',
            title='Новый подписчик 👥',
            message=f'{instance.follower.username} подписался на вас',
            link=f'/accounts/profile/{instance.follower.username}/'
        )

        if notification:
            unread_count = Notification.objects.filter(
                recipient=instance.following,
                is_read=False
            ).count()

            send_websocket_notification(
                instance.following.id,
                {
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'created_at': notification.created_at.isoformat(),
                    'notification_type': 'follow',
                    'link': notification.link
                },
                unread_count
            )


# ========== Уведомления о дружбе (Friendship) ==========
@receiver(post_save, sender=Friendship)
def create_friendship_notification(sender, instance, created, **kwargs):
    """Уведомление о новом друге"""
    if created:
        notification = Notification.create_notification(
            recipient=instance.friend,
            sender=instance.user,
            notification_type='follow',
            title='Новый друг 🤝',
            message=f'{instance.user.username} добавил вас в друзья',
            link=f'/accounts/profile/{instance.user.username}/'
        )

        if notification:
            unread_count = Notification.objects.filter(
                recipient=instance.friend,
                is_read=False
            ).count()

            send_websocket_notification(
                instance.friend.id,
                {
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'created_at': notification.created_at.isoformat(),
                    'notification_type': 'follow',
                    'link': notification.link
                },
                unread_count
            )


# ========== Уведомления при отметке прочитанных ==========
@receiver(post_save, sender=Notification)
def notification_marked_read(sender, instance, **kwargs):
    """Когда уведомление помечено как прочитанное - обновляем счетчик"""
    if instance.is_read:
        send_counter_update(instance.recipient.id)


# ========== Уведомления при удалении ==========
@receiver(post_delete, sender=Notification)
def notification_deleted(sender, instance, **kwargs):
    """При удалении уведомления обновляем счетчик"""
    send_counter_update(instance.recipient.id)


# ========== Функция для проверки настроек уведомлений ==========
def should_send_notification(user, notification_type):
    """Проверяет, нужно ли отправлять уведомление пользователю"""
    if not user or not user.is_authenticated:
        return False

    profile = user.profile
    if notification_type == 'like':
        return profile.notify_likes
    elif notification_type == 'comment':
        return profile.notify_comments
    elif notification_type == 'follow':
        return profile.notify_follows
    elif notification_type == 'message':
        return profile.notify_messages
    return True