from .models import Chat


def unread_messages(request):
    """
    Контекстный процессор для количества непрочитанных сообщений
    """
    if request.user.is_authenticated:
        total = 0
        for chat in request.user.chats.all():
            participant = chat.chatparticipant_set.filter(user=request.user).first()
            if participant:
                unread = chat.messages.filter(
                    created_at__gt=participant.last_read
                ).exclude(author=request.user).count()
                total += unread
        return {'unread_messages_count': total}
    return {'unread_messages_count': 0}