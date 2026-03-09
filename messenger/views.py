from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Max
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Chat, Message, ChatParticipant
from .forms import MessageForm, ChatCreateForm, GroupChatCreateForm
from django.contrib.auth import get_user_model

User = get_user_model()


@login_required
def chat_list(request):
    """
    Список чатов пользователя
    """
    # Получаем все чаты пользователя
    chats = Chat.objects.filter(
        participants=request.user
    ).annotate(
        last_message_time=Max('messages__created_at')
    ).order_by('-last_message_time', '-updated_at')

    # Считаем непрочитанные сообщения для каждого чата
    for chat in chats:
        participant = ChatParticipant.objects.filter(
            user=request.user,
            chat=chat
        ).first()
        if participant:
            chat.unread = Message.objects.filter(
                chat=chat,
                created_at__gt=participant.last_read
            ).exclude(author=request.user).count()
        else:
            chat.unread = 0

    return render(request, 'messenger/chat_list.html', {'chats': chats})


@login_required
def chat_detail(request, chat_id):
    """
    Детальная страница чата
    """
    chat = get_object_or_404(
        Chat.objects.prefetch_related('participants'),
        id=chat_id,
        participants=request.user
    )

    # Получаем участника для обновления last_read
    participant = ChatParticipant.objects.get(user=request.user, chat=chat)

    # Получаем сообщения
    messages_list = chat.messages.filter(is_deleted=False).select_related('author')

    # Пагинация сообщений (загружаем по 50)
    paginator = Paginator(messages_list, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Отмечаем непрочитанные сообщения как прочитанные
    if page_obj.number == paginator.num_pages:  # Если это последняя страница
        unread_messages = messages_list.filter(
            created_at__gt=participant.last_read
        ).exclude(author=request.user)
        unread_messages.update(is_read=True)
        participant.last_read = timezone.now()
        participant.save()

    # Форма отправки сообщения
    form = MessageForm()

    # Информация о чате
    if chat.chat_type == 'private':
        other_user = chat.participants.exclude(id=request.user.id).first()
    else:
        other_user = None

    context = {
        'chat': chat,
        'other_user': other_user,
        'page_obj': page_obj,
        'form': form,
        'participant': participant,
    }
    return render(request, 'messenger/chat_detail.html', context)


@login_required
@require_POST
def send_message(request, chat_id):
    """
    Отправка сообщения в чат
    """
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)

    form = MessageForm(request.POST)
    if form.is_valid():
        message = form.save(commit=False)
        message.chat = chat
        message.author = request.user
        message.save()

        # Обновляем время чата
        chat.save()  # updated_at обновится автоматически

        # Если это AJAX запрос
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'ok',
                'message_id': message.id,
                'content': message.content,
                'created_at': message.created_at.strftime('%d.%m.%Y %H:%M'),
                'author': message.author.username,
            })

        messages.success(request, 'Сообщение отправлено')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
        messages.error(request, 'Ошибка при отправке сообщения')

    return redirect('messenger:chat_detail', chat_id=chat_id)


@login_required
def create_private_chat(request):
    """
    Создание личного диалога
    """
    if request.method == 'POST':
        form = ChatCreateForm(request.POST, user=request.user)
        if form.is_valid():
            other_user = form.cleaned_data['participant']
            initial_message = form.cleaned_data['initial_message']

            # Проверяем, существует ли уже диалог
            existing_chat = Chat.objects.filter(
                chat_type='private',
                participants=request.user
            ).filter(participants=other_user).distinct().first()

            if existing_chat:
                chat = existing_chat
            else:
                # Создаем новый чат
                chat = Chat.objects.create(chat_type='private')
                ChatParticipant.objects.create(user=request.user, chat=chat)
                ChatParticipant.objects.create(user=other_user, chat=chat)

            # Отправляем первое сообщение
            if initial_message:
                Message.objects.create(
                    chat=chat,
                    author=request.user,
                    content=initial_message
                )

            messages.success(request, f'Чат с {other_user.username} создан')
            return redirect('messenger:chat_detail', chat_id=chat.id)
    else:
        form = ChatCreateForm(user=request.user)

    return render(request, 'messenger/create_chat.html', {'form': form})


@login_required
def create_group_chat(request):
    """
    Создание группового чата
    """
    if request.method == 'POST':
        form = GroupChatCreateForm(request.POST, user=request.user)
        if form.is_valid():
            name = form.cleaned_data['name']
            participants = form.cleaned_data['participants']
            initial_message = form.cleaned_data['initial_message']

            # Создаем групповой чат
            chat = Chat.objects.create(
                chat_type='group',
                name=name
            )

            # Добавляем создателя как администратора
            ChatParticipant.objects.create(
                user=request.user,
                chat=chat,
                is_admin=True
            )

            # Добавляем остальных участников
            for user in participants:
                ChatParticipant.objects.create(user=user, chat=chat)

            # Отправляем приветственное сообщение
            if initial_message:
                Message.objects.create(
                    chat=chat,
                    author=request.user,
                    content=initial_message
                )

            messages.success(request, f'Групповой чат "{name}" создан')
            return redirect('messenger:chat_detail', chat_id=chat.id)
    else:
        form = GroupChatCreateForm(user=request.user)

    return render(request, 'messenger/create_group_chat.html', {'form': form})


@login_required
def edit_message(request, message_id):
    """
    Редактирование сообщения
    """
    message = get_object_or_404(Message, id=message_id, author=request.user)

    if request.method == 'POST':
        new_content = request.POST.get('content')
        if new_content and new_content.strip():
            message.content = new_content.strip()
            message.is_edited = True
            message.save()
            messages.success(request, 'Сообщение отредактировано')
        else:
            messages.error(request, 'Сообщение не может быть пустым')

        return redirect('messenger:chat_detail', chat_id=message.chat.id)

    return render(request, 'messenger/edit_message.html', {'message': message})


@login_required
@require_POST
def delete_message(request, message_id):
    """
    Удаление сообщения
    """
    message = get_object_or_404(Message, id=message_id, author=request.user)
    chat_id = message.chat.id
    message.is_deleted = True
    message.content = '[Сообщение удалено]'
    message.save()

    messages.success(request, 'Сообщение удалено')
    return redirect('messenger:chat_detail', chat_id=chat_id)


@login_required
def chat_settings(request, chat_id):
    """
    Настройки чата (для групповых чатов)
    """
    chat = get_object_or_404(Chat, id=chat_id, participants=request.user)

    # Проверяем, является ли пользователь администратором
    participant = ChatParticipant.objects.get(user=request.user, chat=chat)
    is_admin = participant.is_admin

    if chat.chat_type == 'private':
        messages.warning(request, 'У личных чатов нет дополнительных настроек')
        return redirect('messenger:chat_detail', chat_id=chat_id)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'rename' and is_admin:
            new_name = request.POST.get('name')
            if new_name:
                chat.name = new_name
                chat.save()
                messages.success(request, 'Название чата изменено')

        elif action == 'add_participant' and is_admin:
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id)
                ChatParticipant.objects.get_or_create(user=user, chat=chat)
                messages.success(request, f'{user.username} добавлен в чат')
            except User.DoesNotExist:
                messages.error(request, 'Пользователь не найден')

        elif action == 'remove_participant':
            user_id = request.POST.get('user_id')
            try:
                user = User.objects.get(id=user_id)
                if user != request.user:
                    ChatParticipant.objects.filter(user=user, chat=chat).delete()
                    messages.success(request, f'{user.username} удален из чата')
                else:
                    messages.error(request, 'Нельзя удалить себя')
            except User.DoesNotExist:
                messages.error(request, 'Пользователь не найден')

        elif action == 'leave':
            participant.delete()
            messages.info(request, 'Вы покинули чат')
            return redirect('messenger:chat_list')

        return redirect('messenger:chat_settings', chat_id=chat_id)

    participants = ChatParticipant.objects.filter(chat=chat).select_related('user')

    context = {
        'chat': chat,
        'participants': participants,
        'is_admin': is_admin,
        'other_users': User.objects.exclude(
            id__in=participants.values_list('user_id', flat=True)
        )[:20],
    }
    return render(request, 'messenger/chat_settings.html', context)