# accounts/context_processors.py
from .models import Notification


def notifications(request):
    """
    Контекстный процессор для количества непрочитанных уведомлений
    """
    context = {
        'is_authenticated': request.user.is_authenticated,
        'unread_notifications_count': 0,
        'notification_types': Notification.NOTIFICATION_TYPES,
    }

    if request.user.is_authenticated:
        context['unread_notifications_count'] = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

    return context