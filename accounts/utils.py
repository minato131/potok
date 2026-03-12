from .models import Notification
from django.contrib.contenttypes.models import ContentType


def create_notification(recipient, sender, notification_type, title, message, content_object=None, link=''):
    """
    Хелпер для создания уведомлений
    """
    if recipient == sender:
        return None  # Не уведомляем самого себя

    notification = Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link
    )

    if content_object:
        notification.content_type = ContentType.objects.get_for_model(content_object)
        notification.object_id = content_object.id
        notification.save()

    return notification