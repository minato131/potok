from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class SavedTrack(models.Model):
    """Сохранённый трек из Яндекс Музыки"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_tracks')
    track_id = models.CharField(max_length=50, verbose_name='ID трека в Яндексе')
    title = models.CharField(max_length=255, verbose_name='Название')
    artist = models.CharField(max_length=255, verbose_name='Исполнитель')
    album = models.CharField(max_length=255, blank=True, verbose_name='Альбом')
    cover_url = models.URLField(max_length=500, blank=True, verbose_name='Обложка')
    duration = models.PositiveIntegerField(default=0, verbose_name='Длительность (сек)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлен')

    class Meta:
        unique_together = ['user', 'track_id']
        ordering = ['-created_at']
        verbose_name = 'Сохранённый трек'
        verbose_name_plural = 'Сохранённые треки'

    def __str__(self):
        return f'{self.title} — {self.artist}'

class Playlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='playlists')
    name = models.CharField(max_length=200)
    cover = models.ImageField(upload_to='playlist_covers/%Y/%m/%d/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'name']
        ordering = ['-created_at']
    def __str__(self):
        return f'{self.name} ({self.user.username})'


class PlaylistTrack(models.Model):
    playlist = models.ForeignKey(Playlist, on_delete=models.CASCADE, related_name='tracks')
    track_id = models.CharField(max_length=50)
    title = models.CharField(max_length=255)
    artist = models.CharField(max_length=255)
    cover_url = models.URLField(max_length=500, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['playlist', 'track_id']
        ordering = ['added_at']