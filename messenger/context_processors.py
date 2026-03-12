from .models import Chat


def unread_messages(request):
    """
    Контекстный процессор для количества непрочитанных сообщений
    """
    if request.user.is_authenticated:
        return {
            'unread_messages_count': Chat.get_unread_count_for_user(request.user)
        }
    return {'unread_messages_count': 0}