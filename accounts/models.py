from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Кастомная модель пользователя, расширяющая стандартную AbstractUser
    """
    # Дополнительные поля
    avatar = models.ImageField(
        upload_to='avatars/',
        verbose_name='Аватар',
        blank=True,
        null=True,
        help_text='Загрузите изображение для аватара'
    )
    birth_date = models.DateField(
        verbose_name='Дата рождения',
        blank=True,
        null=True,
        help_text='Укажите дату рождения'
    )
    bio = models.TextField(
        max_length=500,
        verbose_name='О себе',
        blank=True,
        help_text='Расскажите немного о себе'
    )

    # Для статистики
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата регистрации'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    email_verified = models.BooleanField(
        default=False,
        verbose_name='Email подтвержден'
    )
    private_profile = models.BooleanField(
        default=False,
        verbose_name='Закрытый профиль'
    )
    hide_email = models.BooleanField(
        default=True,
        verbose_name='Скрыть email'
    )
    message_privacy = models.CharField(
        max_length=20,
        choices=[
            ('everyone', 'Все'),
            ('followers', 'Только подписчики'),
            ('none', 'Никто'),
        ],
        default='everyone',
        verbose_name='Кто может писать'
    )

    # Социальные сети
    telegram = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Telegram'
    )
    vk = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='VK'
    )
    github = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='GitHub'
    )

    # Настройки уведомлений
    email_likes = models.BooleanField(
        default=True,
        verbose_name='Уведомления о лайках'
    )
    email_comments = models.BooleanField(
        default=True,
        verbose_name='Уведомления о комментариях'
    )
    email_follows = models.BooleanField(
        default=True,
        verbose_name='Уведомления о подписчиках'
    )
    email_messages = models.BooleanField(
        default=True,
        verbose_name='Уведомления о сообщениях'
    )
    last_activity = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Последняя активность'
    )

    @property
    def is_online(self):
        """Проверяет, был ли пользователь активен в последние 5 минут"""
        if not self.last_activity:
            return False
        from django.utils import timezone
        return (timezone.now() - self.last_activity).seconds < 300

    def __str__(self):
        return self.username

    def get_full_name(self):
        """Возвращает полное имя или username, если имя не указано"""
        full_name = super().get_full_name()
        return full_name if full_name else self.username

    def get_avatar_url(self):
        """Возвращает URL аватара или путь к дефолтному изображению"""
        if self.avatar and hasattr(self.avatar, 'url'):
            return self.avatar.url
        return '/static/images/default-avatar.png'

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['-date_joined']


class Follow(models.Model):
    """
    Модель для подписок (связи между пользователями)
    """
    follower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='following',  # те, на кого подписан пользователь
        verbose_name='Подписчик'
    )
    following = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='followers',  # те, кто подписан на пользователя
        verbose_name='Подписка'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата подписки'
    )

    class Meta:
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'
        unique_together = ('follower', 'following')

    def __str__(self):
        return f"{self.follower.username} подписан на {self.following.username}"

    def clean(self):
        """Валидация: нельзя подписаться на самого себя"""
        from django.core.exceptions import ValidationError
        if self.follower == self.following:
            raise ValidationError('Нельзя подписаться на самого себя')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Notification(models.Model):
    """
    Модель уведомлений пользователя
    """
    NOTIFICATION_TYPES = [
        ('like', 'Лайк'),
        ('comment', 'Комментарий'),
        ('follow', 'Подписка'),
        ('mention', 'Упоминание'),
        ('message', 'Сообщение'),
        ('community_invite', 'Приглашение в сообщество'),
        ('community_request', 'Заявка в сообщество'),
        ('report', 'Жалоба рассмотрена'),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='Получатель'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
        null=True,
        blank=True,
        verbose_name='Отправитель'
    )
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        verbose_name='Тип уведомления'
    )
    title = models.CharField(
        max_length=200,
        verbose_name='Заголовок'
    )
    message = models.TextField(
        verbose_name='Текст уведомления'
    )
    link = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Ссылка'
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='Прочитано'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['recipient', 'is_read']),
        ]

    def __str__(self):
        return f"{self.recipient.username}: {self.title}"

    def mark_as_read(self):
        self.is_read = True
        self.save(update_fields=['is_read'])