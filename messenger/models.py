from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Chat(models.Model):
    """
    Модель чата (диалога или группового чата)
    """
    CHAT_TYPES = [
        ('private', 'Личный диалог'),
        ('group', 'Групповой чат'),
    ]

    name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Название чата'
    )
    chat_type = models.CharField(
        max_length=20,
        choices=CHAT_TYPES,
        default='private',
        verbose_name='Тип чата'
    )
    participants = models.ManyToManyField(
        User,
        through='ChatParticipant',
        related_name='chats',
        verbose_name='Участники'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    class Meta:
        verbose_name = 'Чат'
        verbose_name_plural = 'Чаты'
        ordering = ['-updated_at']

    def __str__(self):
        if self.chat_type == 'private':
            participants = self.participants.all()[:2]
            return f"Чат: {', '.join([p.username for p in participants])}"
        return self.name or f"Групповой чат #{self.id}"

    def get_last_message(self):
        """Получить последнее сообщение в чате"""
        return self.messages.order_by('-created_at').first()


class ChatParticipant(models.Model):
    """
    Модель участника чата (с дополнительными полями)
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )
    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        verbose_name='Чат'
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата присоединения'
    )
    last_read = models.DateTimeField(
        default=timezone.now,
        verbose_name='Последнее прочитанное'
    )
    is_admin = models.BooleanField(
        default=False,
        verbose_name='Администратор'
    )

    class Meta:
        verbose_name = 'Участник чата'
        verbose_name_plural = 'Участники чатов'
        unique_together = ['user', 'chat']

    def __str__(self):
        return f"{self.user.username} в чате {self.chat.id}"

    def unread_count(self):
        """Количество непрочитанных сообщений"""
        return self.chat.messages.filter(
            created_at__gt=self.last_read
        ).exclude(author=self.user).count()


class Message(models.Model):
    """
    Модель сообщения
    """
    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Чат'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Автор'
    )
    content = models.TextField(
        verbose_name='Содержание'
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='Прочитано'
    )
    is_edited = models.BooleanField(
        default=False,
        verbose_name='Отредактировано'
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удалено'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата отправки'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.author.username}: {self.content[:50]}"

    def mark_as_read(self):
        """Отметить сообщение как прочитанное"""
        self.is_read = True
        self.save(update_fields=['is_read'])