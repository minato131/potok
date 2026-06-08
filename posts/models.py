from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.text import slugify

User = get_user_model()


class Tag(models.Model):
    """
    Модель тегов для постов (из твоего проекта)
    """
    name = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Название',
        db_index=True
    )
    slug = models.SlugField(
        max_length=60,
        unique=True,
        verbose_name='URL-идентификатор',
        blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tags',
        verbose_name='Создатель'
    )

    class Meta:
        verbose_name = 'Тег'
        verbose_name_plural = 'Теги'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Category(models.Model):
    """
    Категории для группировки постов (из твоей логики)
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Название'
    )
    slug = models.SlugField(
        max_length=120,
        unique=True,
        verbose_name='URL-идентификатор',
        blank=True
    )
    description = models.TextField(
        max_length=500,
        blank=True,
        verbose_name='Описание'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Родительская категория'
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name='Порядок сортировки'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_categories',
        verbose_name='Создатель'
    )

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        ordering = ['order', 'name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} → {self.name}"
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Post(models.Model):
    """
    Модель поста (адаптация твоей модели Topic/Post из форума)
    """
    STATUS_CHOICES = [
        ('draft', 'Черновик'),
        ('published', 'Опубликован'),
        ('archived', 'В архиве'),
        ('deleted', 'Удален'),
    ]

    title = models.CharField(
        max_length=200,
        verbose_name='Заголовок',
        db_index=True
    )
    content = models.TextField(
        verbose_name='Содержание'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='posts',
        verbose_name='Автор'
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
        verbose_name='Категория'
    )
    tags = models.ManyToManyField(
        Tag,
        blank=True,
        related_name='posts',
        verbose_name='Теги'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='published',
        verbose_name='Статус',
        db_index=True
    )

    # Медиа-контент (как в твоем проекте)
    image = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Изображение'
    )
    video = models.FileField(
        upload_to='posts/videos/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Видео'
    )
    image2 = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Изображение 2'
    )
    image3 = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Изображение 3'
    )
    image4 = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Изображение 4'
    )
    image5 = models.ImageField(
        upload_to='posts/images/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Изображение 5'
    )

    video2 = models.FileField(
        upload_to='posts/videos/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name='Видео 2'
    )

    # Статистика
    views_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Просмотры'
    )
    likes_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Лайки'
    )
    comments_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Комментарии'
    )

    # Даты
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата публикации'
    )
    is_hidden = models.BooleanField(default=False, verbose_name='Скрыт модерацией')
    moderation_reason = models.TextField(blank=True, null=True, verbose_name='Причина блокировки модерацией')

    class Meta:
        verbose_name = 'Пост'
        verbose_name_plural = 'Посты'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'status']),
            models.Index(fields=['author', '-created_at']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Если статус меняется на published, устанавливаем дату публикации
        if self.status == 'published' and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def increment_views(self):
        """Увеличиваем счетчик просмотров"""
        self.views_count += 1
        self.save(update_fields=['views_count'])

    def delete(self, *args, **kwargs):
        # Удаляем все изображения
        for img in self.get_all_images():
            if img:
                img.delete(save=False)
        # Удаляем все видео
        for vid in self.get_all_videos():
            if vid:
                vid.delete(save=False)
        super().delete(*args, **kwargs)

    def get_clean_content(self):
        """Возвращает контент с правильными переносами строк"""
        if not self.content:
            return ''
        # Заменяем все варианты переносов строк на \n
        import re
        content = self.content
        # Убираем \u000D\u000A и \r\n
        content = content.replace('\\u000D\\u000A', '\n')
        content = content.replace('\\r\\n', '\n')
        content = content.replace('\r\n', '\n')
        content = content.replace('\r', '\n')
        return content

    def get_all_images(self):
        """Вернуть список всех изображений"""
        images = []
        if self.image:
            images.append(self.image)
        if hasattr(self, 'image2') and self.image2:
            images.append(self.image2)
        if hasattr(self, 'image3') and self.image3:
            images.append(self.image3)
        if hasattr(self, 'image4') and self.image4:
            images.append(self.image4)
        if hasattr(self, 'image5') and self.image5:
            images.append(self.image5)
        return images

    def get_all_videos(self):
        """Вернуть список всех видео"""
        videos = []
        if self.video:
            videos.append(self.video)
        if hasattr(self, 'video2') and self.video2:
            videos.append(self.video2)
        return videos

    def get_first_image(self):
        """Вернуть первое изображение для превью"""
        images = self.get_all_images()
        return images[0] if images else None


class Comment(models.Model):
    """
    Древовидные комментарии (твоя реализация из forum_wiki)
    """
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Автор'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name='Пост'
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
        verbose_name='Родительский комментарий'
    )
    content = models.TextField(
        max_length=2000,
        verbose_name='Содержание'
    )

    # Статистика
    likes_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Лайки'
    )

    # Модерация
    is_approved = models.BooleanField(
        default=True,
        verbose_name='Одобрен'
    )
    is_deleted = models.BooleanField(
        default=False,
        verbose_name='Удален'
    )
    is_hidden = models.BooleanField(default=False, verbose_name='Скрыт модерацией')

    # Даты
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
        db_index=True
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Дата обновления'
    )
    image = models.ImageField(upload_to='comments/images/%Y/%m/%d/', blank=True, null=True, verbose_name='Изображение')
    video = models.FileField(upload_to='comments/videos/%Y/%m/%d/', blank=True, null=True, verbose_name='Видео')

    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ['created_at']

    def __str__(self):
        return f"Комментарий от {self.author.username} к {self.post.title}"

    def get_depth(self):
        """Получаем глубину вложенности комментария"""
        depth = 0
        parent = self.parent
        while parent:
            depth += 1
            parent = parent.parent
        return depth


class Like(models.Model):
    """
    Система лайков (как в твоем проекте)
    """
    LIKE_TYPES = [
        ('like', 'Лайк'),
        ('dislike', 'Дизлайк'),
        ('love', '❤️'),
        ('laugh', '😂'),
        ('wow', '😮'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='likes',
        verbose_name='Пользователь'
    )
    content_type = models.CharField(
        max_length=20,
        choices=[('post', 'Пост'), ('comment', 'Комментарий')],
        verbose_name='Тип контента',
        db_index=True
    )
    object_id = models.PositiveIntegerField(
        verbose_name='ID объекта'
    )
    like_type = models.CharField(
        max_length=10,
        choices=LIKE_TYPES,
        default='like',
        verbose_name='Тип реакции'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата'
    )

    class Meta:
        verbose_name = 'Лайк'
        verbose_name_plural = 'Лайки'
        unique_together = ['user', 'content_type', 'object_id']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.content_type} {self.object_id}"


class PostView(models.Model):
    """
    Учет просмотров постов (аналитика)
    """
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='views',
        verbose_name='Пост'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='post_views',
        verbose_name='Пользователь'
    )
    ip_address = models.GenericIPAddressField(
        verbose_name='IP-адрес',
        null=True,
        blank=True
    )
    viewed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Время просмотра'
    )

    class Meta:
        verbose_name = 'Просмотр поста'
        verbose_name_plural = 'Просмотры постов'
        ordering = ['-viewed_at']


class Bookmark(models.Model):
    """
    Избранное (сохраненные посты)
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookmarks',
        verbose_name='Пользователь'
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='bookmarks',
        verbose_name='Пост'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата добавления'
    )
    notes = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Заметка'
    )

    class Meta:
        verbose_name = 'Закладка'
        verbose_name_plural = 'Закладки'
        unique_together = ['user', 'post']
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} → {self.post.title}"



class Poll(models.Model):
    """Опрос в посте"""
    post = models.OneToOneField(
        Post,
        on_delete=models.CASCADE,
        related_name='poll',
        verbose_name='Пост'
    )
    question = models.CharField(
        max_length=500,
        verbose_name='Вопрос опроса'
    )
    is_anonymous = models.BooleanField(
        default=False,
        verbose_name='Анонимное голосование'
    )
    allow_multiple = models.BooleanField(
        default=False,
        verbose_name='Можно выбрать несколько вариантов'
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания'
    )

    class Meta:
        verbose_name = 'Опрос'
        verbose_name_plural = 'Опросы'

    def __str__(self):
        return f"Опрос в посте {self.post.id}: {self.question[:50]}"

    def total_votes(self):
        """Общее количество голосов"""
        return PollVote.objects.filter(option__poll=self).count()

    def can_vote(self, user):
        """Может ли пользователь голосовать"""
        if not user.is_authenticated:
            return False
        if self.allow_multiple:
            return True
        # Проверяем, голосовал ли пользователь
        return not PollVote.objects.filter(option__poll=self, user=user).exists()

    def get_user_votes(self, user):
        """Получить варианты, за которые проголосовал пользователь"""
        if not user.is_authenticated:
            return []
        return PollVote.objects.filter(
            option__poll=self,
            user=user
        ).values_list('option_id', flat=True)

    def get_results(self):
        total = self.total_votes()
        results = []
        for option in self.options.all():
            votes = option.votes.count()
            percentage = round((votes / total) * 100, 1) if total > 0 else 0
            results.append({
                'id': option.id,
                'text': option.text,
                'votes': votes,
                'percentage': percentage
            })
        return results, total

    def user_voted(self, user):
        return PollVote.objects.filter(option__poll=self, user=user).exists()


class PollOption(models.Model):
    """Вариант ответа в опросе"""
    poll = models.ForeignKey(
        Poll,
        on_delete=models.CASCADE,
        related_name='options'
    )
    text = models.CharField(
        max_length=200,
        verbose_name='Текст варианта'
    )

    class Meta:
        verbose_name = 'Вариант опроса'
        verbose_name_plural = 'Варианты опросов'
        ordering = ['id']

    def __str__(self):
        return self.text[:50]

    def votes_count(self):
        return self.votes.count()

    def votes_percentage(self):
        total = self.poll.total_votes()
        if total == 0:
            return 0
        return round((self.votes_count() / total) * 100, 1)


class PollVote(models.Model):
    """Голос пользователя"""
    option = models.ForeignKey(
        PollOption,
        on_delete=models.CASCADE,
        related_name='votes'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='poll_votes'
    )
    voted_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = 'Голос'
        verbose_name_plural = 'Голоса'
        unique_together = ['option', 'user']

    def __str__(self):
        return f"{self.user.username} → {self.option.text[:30]}"