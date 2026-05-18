# accounts/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Notification


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
        else:
            self.group_name = f'notifications_{self.user.id}'

            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )

            await self.accept()

            # Отправляем текущий счетчик
            count = await self.get_unread_count()
            await self.send(text_data=json.dumps({
                'type': 'counter_update',
                'count': count
            }))

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'mark_as_read':
            notification_id = data.get('notification_id')
            await self.mark_notification_as_read(notification_id)
        elif action == 'mark_all_read':
            await self.mark_all_notifications_read()

    async def send_notification(self, event):
        """Отправка нового уведомления клиенту"""
        # Получаем актуальный счетчик
        count = await self.get_unread_count()

        await self.send(text_data=json.dumps({
            'type': 'new_notification',
            'notification': event['notification'],
            'unread_count': count
        }))

    async def update_counter(self, event):
        await self.send(text_data=json.dumps({
            'type': 'counter_update',
            'count': event['count']
        }))

    @database_sync_to_async
    def get_unread_count(self):
        return Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).count()

    @database_sync_to_async
    def mark_notification_as_read(self, notification_id):
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_all_notifications_read(self):
        Notification.objects.filter(
            recipient=self.user,
            is_read=False
        ).update(is_read=True)