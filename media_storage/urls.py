from django.urls import path
from . import views

app_name = 'media_storage'

urlpatterns = [
    path('photos/', views.photo_list, name='photo_list'),
    path('videos/', views.video_list, name='video_list'),
    path('photo/save/', views.save_photo, name='save_photo'),
    path('video/save/', views.save_video, name='save_video'),
    path('photo/<int:photo_id>/delete/', views.photo_delete, name='photo_delete'),
    path('video/<int:video_id>/delete/', views.video_delete, name='video_delete'),
]