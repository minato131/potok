from .models import Notification


def notifications(request):
    """
    Контекстный процессор для количества непрочитанных уведомлений
    """
    if request.user.is_authenticated:
        return {
            'unread_notifications_count': Notification.objects.filter(
                recipient=request.user,
                is_read=False
            ).count(),
            'notification_types': Notification.NOTIFICATION_TYPES,
        }
    return {
        'unread_notifications_count': 0,
        'notification_types': Notification.NOTIFICATION_TYPES,
    }