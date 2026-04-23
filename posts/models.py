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