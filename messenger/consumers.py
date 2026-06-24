# messenger/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from .models import Message, Chat, ChatParticipant
from django.utils import timezone

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.chat_id = self.scope['url_route']['kwargs'].get('chat_id')

        if not self.user.is_authenticated or not self.chat_id:
            await self.close()
            return

        if not await self.is_participant():
            await self.close()
            return

        self.room_group_name = f'chat_{self.chat_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if msg_type == 'read_receipt':
            message_id = data.get('message_id')
            await self.mark_message_as_read(message_id)

    async def chat_message(self, event):
        """Отправка нового сообщения всем в чате"""
        await self.send(text_data=json.dumps({
            'type': 'new_message',
            'message': event['message']
        }))

    async def message_read(self, event):
        """Отправка обновления статуса прочтения"""
        await self.send(text_data=json.dumps({
            'type': 'message_read',
            'message_id': event['message_id'],
            'reader_id': event['reader_id']
        }))

    # ========== ДОБАВИТЬ ЭТОТ МЕТОД ==========
    async def message_edited(self, event):
        """Отправка обновления о редактировании сообщения"""
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'content': event['content'],
            'is_edited': True,
            'author': event.get('author'),
            'edited_at': event.get('edited_at'),
        }))

    @database_sync_to_async
    def is_participant(self):
        return ChatParticipant.objects.filter(
            chat_id=self.chat_id,
            user=self.user
        ).exists()

    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        try:
            message = Message.objects.get(id=message_id, chat_id=self.chat_id)
            if message.author != self.user and not message.is_read:
                message.is_read = True
                message.read_at = timezone.now()
                message.save()

                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'chat_{self.chat_id}',
                    {
                        'type': 'message_read',
                        'message_id': message.id,
                        'reader_id': self.user.id
                    }
                )
                return True
        except Message.DoesNotExist:
            pass
        return False