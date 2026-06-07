from django.urls import path
from . import views

app_name = 'media_storage'

urlpatterns = [
    path('photos/', views.photo_list, name='photo_list'),
    path('videos/', views.video_list, name='video_list'),
    path('save-from-post/', views.save_media_from_post, name='save_from_post'),
    path('photo/<int:photo_id>/delete/', views.photo_delete, name='photo_delete'),
    path('video/<int:video_id>/delete/', views.video_delete, name='video_delete'),
    path('photo/upload/', views.upload_photo, name='upload_photo'),
    path('video/upload/', views.upload_video, name='upload_video'),
    path('save-from-url/', views.save_media_from_url, name='save_from_url'),
    path('photos/delete-selected/', views.delete_selected_photos, name='delete_selected_photos'),
    path('videos/delete-selected/', views.delete_selected_videos, name='delete_selected_videos'),
]