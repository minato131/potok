# posts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Like, Comment, Post
from accounts.models import Notification
from django.contrib.auth import get_user_model
import re

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
    if notification_type == 'like':
        return profile.notify_likes
    elif notification_type == 'comment':
        return profile.notify_comments
    return True


# ========== Уведомления о лайках ==========
@receiver(post_save, sender=Like)
def create_like_notification(sender, instance, created, **kwargs):
    """Уведомление о лайке поста"""
    if not created:
        return

    # Определяем объект (пост или комментарий) по content_type
    if instance.content_type == 'post':
        try:
            post = Post.objects.get(id=instance.object_id)
            author = post.author
            obj_link = f'/post/{post.id}/'
            obj_title = post.title[:50]
        except Post.DoesNotExist:
            return
    elif instance.content_type == 'comment':
        try:
            comment = Comment.objects.get(id=instance.object_id)
            author = comment.post.author  # Автор поста, к которому относится комментарий
            obj_link = f'/post/{comment.post.id}/'
            obj_title = comment.content[:50]
        except Comment.DoesNotExist:
            return
    else:
        return

    # Не отправляем уведомление если лайк от автора
    if instance.user == author:
        return

    # Проверяем настройки уведомлений автора
    if not should_send_notification(author, 'like'):
        return

    notification = Notification.create_notification(
        recipient=author,
        sender=instance.user,
        notification_type='like',
        title='Новый лайк ❤️',
        message=f'{instance.user.username} лайкнул ваш {instance.content_type} "{obj_title}"',
        link=obj_link
    )

    if notification:
        unread_count = Notification.objects.filter(
            recipient=author,
            is_read=False
        ).count()

        send_websocket_notification(
            author.id,
            {
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'created_at': notification.created_at.isoformat(),
                'notification_type': 'like',
                'link': notification.link
            },
            unread_count
        )


# ========== Уведомления о комментариях ==========
@receiver(post_save, sender=Comment)
def create_comment_notification(sender, instance, created, **kwargs):
    """Уведомление о комментарии к посту"""
    if created and instance.author != instance.post.author:
        if not should_send_notification(instance.post.author, 'comment'):
            return

        notification = Notification.create_notification(
            recipient=instance.post.author,
            sender=instance.author,
            notification_type='comment',
            title='Новый комментарий 💬',
            message=f'{instance.author.username} прокомментировал: "{instance.content[:50]}"',
            link=f'/post/{instance.post.id}/'
        )

        if notification:
            unread_count = Notification.objects.filter(
                recipient=instance.post.author,
                is_read=False
            ).count()

            send_websocket_notification(
                instance.post.author.id,
                {
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'created_at': notification.created_at.isoformat(),
                    'notification_type': 'comment',
                    'link': notification.link
                },
                unread_count
            )


# ========== Уведомления об упоминаниях в комментариях ==========
@receiver(post_save, sender=Comment)
def create_mention_notification(sender, instance, created, **kwargs):
    """Уведомление об упоминании @username в комментарии"""
    if created:
        mentions = re.findall(r'@(\w+)', instance.content)

        for username in mentions:
            try:
                mentioned_user = User.objects.get(username=username)
                if mentioned_user != instance.author:
                    notification = Notification.create_notification(
                        recipient=mentioned_user,
                        sender=instance.author,
                        notification_type='mention',
                        title='Вас упомянули @',
                        message=f'{instance.author.username} упомянул вас в комментарии: "{instance.content[:50]}"',
                        link=f'/post/{instance.post.id}/'
                    )

                    if notification:
                        unread_count = Notification.objects.filter(
                            recipient=mentioned_user,
                            is_read=False
                        ).count()

                        send_websocket_notification(
                            mentioned_user.id,
                            {
                                'id': notification.id,
                                'title': notification.title,
                                'message': notification.message,
                                'created_at': notification.created_at.isoformat(),
                                'notification_type': 'mention',
                                'link': notification.link
                            },
                            unread_count
                        )
            except User.DoesNotExist:
                pass