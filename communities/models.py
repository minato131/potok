from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify
from django.core.exceptions import ValidationError

User = get_user_model()


class Community(models.Model):
    """
    Модель сообщества (группы) - аналог wiki-разделов из твоего проекта
    """
    STATUS_CHOICES = [
        ('active', 'Активно'),
        ('closed', 'Закрыто'),
        ('deleted', 'Удалено'),
    ]

    PRIVACY_CHOICES = [
        ('public', 'Публичное'),
        ('private', 'Закрытое (требуется одобрение)'),
        ('hidden', 'Скрытое (не отображается в списках)'),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Название',
        db_index=True
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        verbose_name='URL-идентификатор',
        blank=True
    )
    description = models.TextField(
        max_length=2000,
        verbose_name='Описание',
        blank=True
    )
    avatar = models.ImageField(
        upload_to='communities/avatars/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Аватар'
    )
    cover = models.ImageField(
        upload_to='communities/covers/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Обложка'
    )

    # Создатель и администраторы
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_communities',
        verbose_name='Создатель'
    )
    admins = models.ManyToManyField(
        User,
        related_name='admin_communities',
        blank=True,
        verbose_name='Администраторы'
    )

    # Участники
    members = models.ManyToManyField(
        User,
        through='CommunityMembership',
        related_name='communities',
        verbose_name='Участники'
    )

    # Настройки
    privacy = models.CharField(
        max_length=20,
        choices=PRIVACY_CHOICES,
        default='public',
        verbose_name='Приватность'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Статус'
    )

    # Тематика (категории и теги из posts)
    categories = models.ManyToManyField(
        'posts.Category',
        related_name='communities',
        blank=True,
        verbose_name='Категории'
    )
    tags = models.ManyToManyField(
        'posts.Tag',
        related_name='communities',
        blank=True,
        verbose_name='Теги'
    )

    # Статистика
    members_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Участников'
    )
    posts_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Постов'
    )

    # Даты
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )

    class Meta:
        verbose_name = 'Сообщество'
        verbose_name_plural = 'Сообщества'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['-created_at', 'status']),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def update_stats(self):
        """Обновление статистики сообщества"""
        from .models import CommunityMembership, CommunityPost

        # Подсчет участников (активных)
        self.members_count = CommunityMembership.objects.filter(
            community=self,
            status='active'
        ).count()

        # Подсчет постов в сообществе
        self.posts_count = CommunityPost.objects.filter(
            community=self
        ).count()

        # Сохраняем изменения
        self.save(update_fields=['members_count', 'posts_count'])
        print(f"Stats updated: members={self.members_count}, posts={self.posts_count}")  # для отладки


class CommunityMembership(models.Model):
    """
    Модель членства в сообществе (с ролями и статусами)
    """
    ROLE_CHOICES = [
        ('member', 'Участник'),
        ('moderator', 'Модератор'),
        ('admin', 'Администратор'),
    ]

    STATUS_CHOICES = [
        ('active', 'Активен'),
        ('banned', 'Заблокирован'),
        ('pending', 'Ожидает подтверждения'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        verbose_name='Сообщество'
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='member',
        verbose_name='Роль'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        verbose_name='Статус'
    )
    joined_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата вступления'
    )

    class Meta:
        verbose_name = 'Участник сообщества'
        verbose_name_plural = 'Участники сообществ'
        unique_together = ['user', 'community']
        indexes = [
            models.Index(fields=['community', 'role']),
            models.Index(fields=['community', 'status']),
        ]

    def __str__(self):
        return f"{self.user.username} в {self.community.name}"


class CommunityPost(models.Model):
    """
    Модель поста в сообществе (расширение обычного поста)
    """
    post = models.OneToOneField(
        'posts.Post',
        on_delete=models.CASCADE,
        related_name='community_post',
        verbose_name='Пост'
    )
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='posts',
        verbose_name='Сообщество'
    )
    is_pinned = models.BooleanField(
        default=False,
        verbose_name='Закреплен'
    )
    is_announcement = models.BooleanField(
        default=False,
        verbose_name='Объявление'
    )

    class Meta:
        verbose_name = 'Пост сообщества'
        verbose_name_plural = 'Посты сообществ'
        ordering = ['-is_pinned', '-post__created_at']
        indexes = [
            models.Index(fields=['community', '-is_pinned']),
        ]

    def __str__(self):
        return f"{self.post.title} в {self.community.name}"


class CommunityInvite(models.Model):
    """
    Модель приглашений в сообщество
    """
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='invites',
        verbose_name='Сообщество'
    )
    inviter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_invites',
        verbose_name='Пригласил'
    )
    invitee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_invites',
        verbose_name='Приглашенный'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата приглашения'
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата принятия'
    )

    class Meta:
        verbose_name = 'Приглашение'
        verbose_name_plural = 'Приглашения'
        unique_together = ['community', 'invitee']

    def __str__(self):
        return f"{self.inviter.username} пригласил {self.invitee.username} в {self.community.name}"

    def accept(self):
        """Принять приглашение"""
        membership, created = CommunityMembership.objects.get_or_create(
            user=self.invitee,
            community=self.community,
            defaults={'status': 'active'}
        )
        if created:
            self.accepted_at = timezone.now()
            self.save()
            return True
        return False


class CommunityJoinRequest(models.Model):
    """
    Модель заявок на вступление в закрытые сообщества
    """
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='join_requests',
        verbose_name='Сообщество'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_requests',
        verbose_name='Пользователь'
    )
    message = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='Сообщение'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата заявки'
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата обработки'
    )
    approved = models.BooleanField(
        null=True,
        verbose_name='Одобрено'
    )
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='processed_requests',
        verbose_name='Обработал'
    )

    class Meta:
        verbose_name = 'Заявка на вступление'
        verbose_name_plural = 'Заявки на вступление'
        unique_together = ['community', 'user']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} хочет вступить в {self.community.name}"

    def approve(self, moderator):
        """Одобрить заявку"""
        membership, created = CommunityMembership.objects.get_or_create(
            user=self.user,
            community=self.community,
            defaults={'status': 'active'}
        )
        if created:
            self.approved = True
            self.processed_at = timezone.now()
            self.processed_by = moderator
            self.save()
            return True
        return False

    def reject(self, moderator):
        """Отклонить заявку"""
        self.approved = False
        self.processed_at = timezone.now()
        self.processed_by = moderator
        self.save()