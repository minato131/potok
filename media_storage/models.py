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

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Сохранённое видео'
        verbose_name_plural = 'Сохранённые видео'