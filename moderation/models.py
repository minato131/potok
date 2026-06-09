from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

User = get_user_model()


class Report(models.Model):
    """
    Модель жалобы на контент
    """
    REPORT_TYPES = [
        ('spam', 'Спам'),
        ('abuse', 'Оскорбления'),
        ('illegal', 'Незаконный контент'),
        ('adult', 'Контент 18+'),
        ('violence', 'Насилие'),
        ('other', 'Другое'),
    ]

    STATUS_CHOICES = [
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
        ('lifted', 'Снято'),
    ]

    # Кто пожаловался
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='reports_made',
        verbose_name='Жалобщик'
    )

    # На что жалуются (Generic Foreign Key)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name='Тип контента'
    )
    object_id = models.PositiveIntegerField(
        verbose_name='ID объекта'
    )
    content_object = GenericForeignKey('content_type', 'object_id')

    # Детали жалобы
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPES,
        verbose_name='Тип жалобы'
    )
    description = models.TextField(
        max_length=1000,
        blank=True,
        verbose_name='Описание'
    )

    # Статус
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус',
        db_index=True
    )
    moderated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_reports',
        verbose_name='Модератор'
    )
    moderated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата модерации'
    )
    moderation_comment = models.TextField(
        max_length=500,
        blank=True,
        verbose_name='Комментарий модератора'
    )

    # Даты
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    CONTEXT_CHOICES = [
        ('platform', 'Платформа (вне сообществ)'),
        ('community', 'Внутри сообщества'),
    ]

    context = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default='platform',
        verbose_name='Контекст жалобы'
    )

    # Для жалоб внутри сообщества — ссылка на сообщество
    community = models.ForeignKey(
        'communities.Community',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports_on_content',
        verbose_name='Сообщество (если жалоба внутри)'
    )

    class Meta:
        verbose_name = 'Жалоба'
        verbose_name_plural = 'Жалобы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return f"Жалоба #{self.id} от {self.reporter.username}"

    def approve(self, moderator, comment=''):
        """Одобрить жалобу (контент будет скрыт)"""
        self.status = 'approved'
        self.moderated_by = moderator
        self.moderated_at = timezone.now()
        self.moderation_comment = comment
        self.save()

        # Здесь можно добавить логику скрытия контента
        content_obj = self.content_object
        if hasattr(content_obj, 'is_hidden'):
            content_obj.is_hidden = True
            content_obj.save()
        elif hasattr(content_obj, 'is_deleted'):
            content_obj.is_deleted = True
            content_obj.save()

    def reject(self, moderator, comment=''):
        """Отклонить жалобу"""
        self.status = 'rejected'
        self.moderated_by = moderator
        self.moderated_at = timezone.now()
        self.moderation_comment = comment
        self.save()


class Ban(models.Model):
    """
    Модель блокировки пользователя
    """
    BAN_TYPES = [
        ('temporary', 'Временная'),
        ('permanent', 'Постоянная'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bans',
        verbose_name='Пользователь'
    )
    banned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='bans_issued',
        verbose_name='Заблокировал'
    )
    ban_type = models.CharField(
        max_length=20,
        choices=BAN_TYPES,
        verbose_name='Тип блокировки'
    )
    reason = models.TextField(
        max_length=1000,
        verbose_name='Причина'
    )

    # Даты
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата блокировки'
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Истекает'
    )
    lifted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата снятия'
    )
    lifted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bans_lifted',
        verbose_name='Снял блокировку'
    )
    moderator_note = models.TextField(
        max_length=500,
        blank=True,
        verbose_name='Заметка для модераторов'
    )

    class Meta:
        verbose_name = 'Блокировка'
        verbose_name_plural = 'Блокировки'
        ordering = ['-created_at']

    def __str__(self):
        return f"Блокировка {self.user.username}"

    def is_active(self):
        """Проверяет, активна ли блокировка"""
        if self.lifted_at:
            return False
        if self.ban_type == 'permanent':
            return True
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True

    def lift(self, moderator):
        """Снять блокировку"""
        self.lifted_at = timezone.now()
        self.lifted_by = moderator
        self.save()


class ModerationLog(models.Model):
    """
    Логирование действий модераторов
    """
    ACTION_CHOICES = [
        ('approve_report', 'Одобрение жалобы'),
        ('reject_report', 'Отклонение жалобы'),
        ('ban_user', 'Блокировка пользователя'),
        ('lift_ban', 'Снятие блокировки'),
        ('hide_content', 'Скрытие контента'),
        ('delete_content', 'Удаление контента'),
        ('warn_user', 'Предупреждение'),
    ]

    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='moderation_actions',
        verbose_name='Модератор'
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name='Действие'
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True
    )
    description = models.TextField(
        verbose_name='Описание'
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP-адрес'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата'
    )

    class Meta:
        verbose_name = 'Лог модерации'
        verbose_name_plural = 'Логи модерации'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} от {self.created_at}"

class UnbanTicket(models.Model):
    """
    Тикет на разбан — заявка от заблокированного пользователя
    """
    STATUS_CHOICES = [
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрен'),
        ('rejected', 'Отклонён'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='unban_tickets',
        verbose_name='Пользователь'
    )
    ban = models.ForeignKey(
        Ban,
        on_delete=models.CASCADE,
        related_name='unban_tickets',
        verbose_name='Блокировка',
        null=True,
        blank=True
    )
    message = models.TextField(
        max_length=1000,
        verbose_name='Сообщение'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_tickets',
        verbose_name='Рассмотрел'
    )
    review_comment = models.TextField(
        max_length=500,
        blank=True,
        verbose_name='Комментарий модератора'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Тикет на разбан'
        verbose_name_plural = 'Тикеты на разбан'
        ordering = ['-created_at']

    def __str__(self):
        return f"Тикет #{self.id} от {self.user.username}"

    def approve(self, moderator, comment=''):
        self.status = 'approved'
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.review_comment = comment
        self.save()
        if self.ban:
            self.ban.lift(moderator)

    def reject(self, moderator, comment=''):
        self.status = 'rejected'
        self.reviewed_by = moderator
        self.reviewed_at = timezone.now()
        self.review_comment = comment
        self.save()


class CommunityReport(models.Model):
    """
    Жалоба на сообщество
    """
    REASON_CHOICES = [
        ('rules_violation', 'Нарушение правил платформы'),
        ('spam', 'Спам / реклама'),
        ('nsfw', 'NSFW / 18+ контент'),
        ('hate_speech', 'Разжигание ненависти'),
        ('illegal', 'Противоправные действия'),
        ('fake', 'Фейковое / мошенническое сообщество'),
        ('other', 'Другое'),
    ]

    STATUS_CHOICES = [
        ('pending', 'На рассмотрении'),
        ('approved', 'Жалоба одобрена'),
        ('rejected', 'Жалоба отклонена'),
        ('warning_issued', 'Выдано предупреждение'),
        ('restricted', 'Сообщество ограничено'),
    ]

    community = models.ForeignKey(
        'communities.Community',
        on_delete=models.CASCADE,
        related_name='reports',
        verbose_name='Сообщество'
    )
    reporter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='community_reports_made',
        verbose_name='Кто пожаловался'
    )
    reason = models.CharField(
        max_length=50,
        choices=REASON_CHOICES,
        verbose_name='Причина'
    )
    description = models.TextField(
        verbose_name='Описание',
        help_text='Подробно опишите, что нарушено'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_community_reports'
    )
    moderator_comment = models.TextField(
        blank=True,
        verbose_name='Комментарий модератора (виден создателю)'
    )

    class Meta:
        verbose_name = 'Жалоба на сообщество'
        verbose_name_plural = 'Жалобы на сообщества'
        ordering = ['-created_at']

    def __str__(self):
        return f'Жалоба на {self.community.name} от {self.reporter.username}'

    def approve(self, moderator, comment=''):
        """Одобрить жалобу — ограничить сообщество"""
        self.status = 'restricted'
        self.moderated_at = timezone.now()
        self.moderated_by = moderator
        self.moderator_comment = comment
        self.save()

        # Ограничиваем сообщество
        self.community.status = 'restricted'
        self.community.save()

        # Уведомляем создателя
        from accounts.utils import create_notification
        create_notification(
            recipient=self.community.creator,
            sender=moderator,
            notification_type='moderation',
            title='⚠️ Ваше сообщество ограничено',
            message=f'Сообщество "{self.community.name}" ограничено из-за жалобы.\n'
                    f'Причина: {self.get_reason_display()}\n'
                    f'Комментарий: {comment or "Свяжитесь с модерацией"}',
            link=f'/communities/{self.community.slug}/'
        )

    def reject(self, moderator, comment=''):
        """Отклонить жалобу"""
        self.status = 'rejected'
        self.moderated_at = timezone.now()
        self.moderated_by = moderator
        self.moderator_comment = comment
        self.save()

        from accounts.utils import create_notification
        create_notification(
            recipient=self.reporter,
            sender=moderator,
            notification_type='moderation',
            title='📋 Жалоба на сообщество отклонена',
            message=f'Ваша жалоба на "{self.community.name}" отклонена.\n'
                    f'Причина: {comment or "Нарушений не обнаружено"}',
            link=f'/communities/{self.community.slug}/'
        )

    def warn_creator(self, moderator, comment=''):
        from django.utils import timezone

        self.status = 'warning_issued'
        self.moderated_at = timezone.now()
        self.moderated_by = moderator
        self.moderator_comment = comment
        self.save()

        # Увеличиваем счётчик предупреждений сообщества
        self.community.warning_count += 1
        self.community.save()

        # Если 3 предупреждения — автоматически ограничить
        if self.community.warning_count >= 3:
            self.community.status = 'restricted'
            self.community.restricted_at = timezone.now()
            self.community.save()

            self.status = 'restricted'
            self.save()

            warning_message = f"Сообщество \"{self.community.name}\" АВТОМАТИЧЕСКИ ОГРАНИЧЕНО из-за 3 предупреждений."
        else:
            warning_message = f"Предупреждение {self.community.warning_count}/3 для сообщества \"{self.community.name}\""

        # Уведомление создателю
        from accounts.utils import create_notification
        create_notification(
            recipient=self.community.creator,
            sender=moderator,
            notification_type='moderation',
            title='⚠️ Предупреждение сообществу',
            message=f'{warning_message}\nПричина: {self.get_reason_display()}\nКомментарий: {comment}\n\nИсправьте нарушения.',
            link=f'/communities/{self.community.slug}/edit/'
        )