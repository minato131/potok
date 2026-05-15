from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from accounts.utils import create_notification
from .models import Chat, Message, ChatParticipant, Reaction
from .forms import ChatCreateForm, GroupChatCreateForm
from django.contrib.auth import get_user_model

User = get_user_model()


@login_required
def messenger(request):
    """Главная страница мессенджера — всё в одном"""
    chats = Chat.objects.filter(participants=request.user)\
        .prefetch_related('participants', 'participants__profile')\
        .annotate(last_message_time=Max('messages__created_at'))\
        .order_by('-last_message_time', '-updated_at')

    total_unread = 0
    for chat in chats:
        chat.unread = chat.get_unread_count_for_user(request.user)
        total_unread += chat.unread

    return render(request, 'messenger/messenger.html', {
        'chats': chats,
        'total_unread': total_unread,
        'today': timezone.now().date(),
    })


@login_required
def api_chat_messages(request, chat_id):
    """API: получить сообщения чата (JSON)"""
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)

    messages_list = chat.messages.filter(is_deleted=False)\
        .select_related('author', 'author__profile')\
        .prefetch_related('reactions', 'reactions__user')\
        .order_by('-created_at')[:50]

    messages_list = sorted(messages_list, key=lambda m: m.created_at)

    participant = ChatParticipant.objects.get(user=request.user, chat=chat)

    # Отмечаем прочитанными
    unread = chat.messages.filter(
        created_at__gt=participant.last_read,
        is_read=False
    ).exclude(author=request.user)
    unread.update(is_read=True)
    participant.last_read = timezone.now()
    participant.save()

    other_user = None
    if chat.chat_type == 'private':
        other_user = chat.participants.exclude(id=request.user.id).first()

    messages_data = []
    for msg in messages_list:
        reactions = {}
        for r in msg.reactions.all():
            reactions[r.emoji] = reactions.get(r.emoji, 0) + 1

        messages_data.append({
            'id': msg.id,
            'content': msg.content,
            'author': msg.author.username,
            'author_name': msg.author.get_full_name() or msg.author.username,
            'author_avatar': msg.author.profile.avatar.url if msg.author.profile.avatar else None,
            'is_own': msg.author == request.user,
            'is_read': msg.is_read,
            'is_deleted': msg.is_deleted,
            'file_url': msg.file.url if msg.file else None,
            'file_type': msg.file_type,
            'created_at': msg.created_at.strftime('%H:%M'),
            'reactions': reactions,
        })

    return JsonResponse({
        'status': 'ok',
        'chat': {
            'id': chat.id,
            'type': chat.chat_type,
            'name': chat.name or (other_user.get_full_name() or other_user.username if other_user else ''),
            'other_user': {
                'username': other_user.username if other_user else None,
                'full_name': other_user.get_full_name() if other_user else None,
                'avatar': other_user.profile.avatar.url if other_user and other_user.profile.avatar else None,
                'is_online': other_user.profile.is_online if other_user else False,
            } if other_user else None,
            'participants_count': chat.participants.count(),
        },
        'messages': messages_data,
    })


@login_required
@require_POST
def send_message(request, chat_id):
    """Отправка сообщения"""
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)

    content = request.POST.get('content', '').strip()
    uploaded_file = request.FILES.get('file')

    if not content and not uploaded_file:
        return JsonResponse({'status': 'error', 'message': 'Пустое сообщение'}, status=400)

    # Защита от дублирования
    if not uploaded_file:
        last = chat.messages.filter(author=request.user).order_by('-created_at').first()
        if last and (timezone.now() - last.created_at).seconds < 2 and last.content == content:
            return JsonResponse({'status': 'duplicate'})

    # Тип файла
    file_type = None
    if uploaded_file:
        mime = uploaded_file.content_type
        if mime.startswith('image/'):
            file_type = 'image'
        elif mime.startswith('video/'):
            file_type = 'video'
        elif mime.startswith('audio/'):
            file_type = 'voice'
        else:
            file_type = 'document'

    message = Message.objects.create(
        chat=chat,
        author=request.user,
        content=content,
        file=uploaded_file,
        file_type=file_type
    )

    # Уведомления
    for p in ChatParticipant.objects.filter(chat=chat).exclude(user=request.user):
        title = 'Новое сообщение' if chat.chat_type == 'private' else f'Новое в {chat.name}'
        create_notification(
            recipient=p.user,
            sender=request.user,
            notification_type='message',
            title=title,
            message=f'@{request.user.username}: {content[:50] or "Файл"}',
            link=f'/messenger/chat/{chat.id}/'
        )

    chat.save()

    return JsonResponse({
        'status': 'ok',
        'message_id': message.id,
        'content': message.content,
        'file_url': message.file.url if message.file else None,
        'file_type': message.file_type,
        'created_at': message.created_at.strftime('%H:%M'),
        'author': message.author.username,
    })


@login_required
def create_private_chat(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        initial_message = request.POST.get('message', '').strip()

        if not user_id:
            return JsonResponse({'error': 'Пользователь не указан'}, status=400)

        try:
            other_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse({'error': 'Пользователь не найден'}, status=404)

        if other_user == request.user:
            return JsonResponse({'error': 'Нельзя создать чат с собой'}, status=400)

        existing = Chat.objects.filter(chat_type='private', participants=request.user) \
            .filter(participants=other_user).distinct().first()

        chat = existing or Chat.objects.create(chat_type='private')
        if not existing:
            ChatParticipant.objects.create(user=request.user, chat=chat)
            ChatParticipant.objects.create(user=other_user, chat=chat)

        if initial_message:
            Message.objects.create(chat=chat, author=request.user, content=initial_message)

        return JsonResponse({'status': 'ok', 'chat_id': chat.id})

    # GET — показываем страницу
    return render(request, 'messenger/create_private_chat.html')


@login_required
def create_group_chat(request):
    """Создание группового чата"""
    if request.method == 'POST':
        form = GroupChatCreateForm(request.POST, user=request.user)
        if form.is_valid():
            chat = Chat.objects.create(chat_type='group', name=form.cleaned_data['name'])
            ChatParticipant.objects.create(user=request.user, chat=chat, is_admin=True)
            for u in form.cleaned_data['participants']:
                ChatParticipant.objects.create(user=u, chat=chat)
            if form.cleaned_data['initial_message']:
                Message.objects.create(chat=chat, author=request.user, content=form.cleaned_data['initial_message'])
            return redirect('messenger:messenger')
    else:
        form = GroupChatCreateForm(user=request.user)
    return render(request, 'messenger/create_group_chat.html', {'form': form})


@login_required
def edit_message(request, message_id):
    """Редактирование сообщения"""
    msg = get_object_or_404(Message, id=message_id, author=request.user)
    if request.method == 'POST':
        new_content = request.POST.get('content', '').strip()
        if new_content:
            msg.content = new_content
            msg.is_edited = True
            msg.save()
            return JsonResponse({'status': 'ok'})
        return JsonResponse({'status': 'error'}, status=400)
    return render(request, 'messenger/edit_message.html', {'message': msg})


@login_required
@require_POST
def delete_message(request, message_id):
    """Удаление сообщения"""
    msg = get_object_or_404(Message, id=message_id, author=request.user)
    msg.is_deleted = True
    msg.save()
    return JsonResponse({'status': 'ok'})


@login_required
def chat_settings(request, chat_id):
    """Настройки чата"""
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)
    participant = ChatParticipant.objects.get(user=request.user, chat=chat)

    if chat.chat_type == 'private':
        return redirect('messenger:messenger')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'rename' and participant.is_admin:
            name = request.POST.get('name', '').strip()
            if name:
                chat.name = name
                chat.save()
        elif action == 'leave':
            participant.delete()
            return redirect('messenger:messenger')
        return redirect('messenger:chat_settings', chat_id=chat_id)

    return render(request, 'messenger/chat_settings.html', {
        'chat': chat,
        'participants': ChatParticipant.objects.filter(chat=chat).select_related('user'),
        'is_admin': participant.is_admin,
    })


@login_required
@require_POST
def create_or_get_chat(request):
    """Создать или получить чат с пользователем"""
    import json
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный формат'}, status=400)

    if not username:
        return JsonResponse({'error': 'Имя не указано'}, status=400)

    try:
        other = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Пользователь не найден'}, status=404)

    if other == request.user:
        return JsonResponse({'error': 'Нельзя с собой'}, status=400)

    existing = Chat.objects.filter(chat_type='private', participants=request.user)\
        .filter(participants=other).distinct().first()

    if existing:
        return JsonResponse({'chat_id': existing.id, 'status': 'existing'})

    chat = Chat.objects.create(chat_type='private')
    ChatParticipant.objects.create(user=request.user, chat=chat)
    ChatParticipant.objects.create(user=other, chat=chat)
    return JsonResponse({'chat_id': chat.id, 'status': 'created'})


@login_required
@require_POST
def toggle_reaction(request, message_id):
    """Добавить/удалить реакцию"""
    import json
    try:
        data = json.loads(request.body)
        emoji = data.get('emoji', '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error'}, status=400)

    if not emoji:
        return JsonResponse({'status': 'error'}, status=400)

    message = get_object_or_404(Message.objects.select_related('chat'), id=message_id)

    if not message.chat.participants.filter(id=request.user.id).exists():
        return JsonResponse({'status': 'error'}, status=403)

    existing = Reaction.objects.filter(message=message, user=request.user, emoji=emoji).first()

    if existing:
        existing.delete()
    else:
        Reaction.objects.filter(message=message, user=request.user).delete()
        Reaction.objects.create(message=message, user=request.user, emoji=emoji)

    reactions_count = {}
    for e in Reaction.EMOJI_CHOICES:
        count = message.reactions.filter(emoji=e[0]).count()
        if count > 0:
            reactions_count[e[0]] = count

    return JsonResponse({'status': 'ok', 'reactions': reactions_count})



# Добавьте в messenger/views.py

@login_required
def api_chat_info(request, chat_id):
    """API: информация о чате (для меню трёх точек)"""
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)

    other_user = None
    if chat.chat_type == 'private':
        other_user = chat.participants.exclude(id=request.user.id).first()

    return JsonResponse({
        'status': 'ok',
        'id': chat.id,
        'type': chat.chat_type,
        'name': chat.name or (other_user.get_full_name() or other_user.username if other_user else ''),
        'other_user': {
            'id': other_user.id if other_user else None,
            'username': other_user.username if other_user else None,
            'full_name': other_user.get_full_name() if other_user else None,
            'avatar': other_user.profile.avatar.url if other_user and other_user.profile.avatar else None,
            'is_online': other_user.profile.is_online if other_user else False,
        } if other_user else None,
        'participants_count': chat.participants.count(),
    })


@login_required
def api_search_messages(request, chat_id):
    """API: поиск по сообщениям чата"""
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)
    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({'status': 'error', 'message': 'Слишком короткий запрос'}, status=400)

    messages_list = chat.messages.filter(
        is_deleted=False,
        content__icontains=query
    ).select_related('author', 'author__profile').order_by('-created_at')[:20]

    results = []
    for msg in messages_list:
        results.append({
            'id': msg.id,
            'content': msg.content,
            'author': msg.author.username,
            'author_name': msg.author.get_full_name() or msg.author.username,
            'created_at': msg.created_at.strftime('%d.%m.%Y %H:%M'),
        })

    return JsonResponse({
        'status': 'ok',
        'query': query,
        'count': len(results),
        'results': results,
    })