from django.db import models
from django.contrib.auth import get_user_model
from posts.models import Post

User = get_user_model()


class SavedPhoto(models.Model):
    """Сохранённые фото отдельно от постов"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_photos')
    image = models.ImageField(upload_to='saved_photos/%Y/%m/%d/')
    post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name='saved_photos')
    created_at = models.DateTimeField(auto_now_add=True)
    original_url = models.URLField(max_length=500, blank=True, null=True)
    source_post_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Сохранённое фото'
        verbose_name_plural = 'Сохранённые фото'


class SavedVideo(models.Model):
    """Сохранённые видео отдельно от постов"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_videos')
    file = models.FileField(upload_to='saved_videos/%Y/%m/%d/')
    post = models.ForeignKey(Post, on_delete=models.SET_NULL, null=True, blank=True, related_name='saved_videos')
    created_at = models.DateTimeField(auto_now_add=True)
    original_url = models.URLField(max_length=500, blank=True, null=True)
    source_post_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Сохранённое видео'
        verbose_name_plural = 'Сохранённые видео'


class SavedMedia(models.Model):
    MEDIA_TYPES = [
        ('image', 'Изображение'),
        ('video', 'Видео'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_media')
    file = models.FileField(upload_to='saved_media/%Y/%m/%d/')
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    original_url = models.URLField(max_length=500)
    source_post_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.media_type} - {self.created_at}"