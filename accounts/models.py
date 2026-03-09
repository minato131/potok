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
        # Запрещаем повторную подписку
        unique_together = ('follower', 'following')
        # Нельзя подписаться на самого себя (проверим на уровне приложения)

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