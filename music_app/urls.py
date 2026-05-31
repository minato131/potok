from django.urls import path
from . import views

app_name = 'music'

urlpatterns = [
    path('', views.music_player, name='player'),
    path('search/', views.search_music, name='search'),
    path('save/', views.save_track, name='save'),
    path('remove/', views.remove_track, name='remove'),
    path('audio-url/', views.get_audio_url, name='audio_url'),
    path('wave/', views.my_wave, name='wave'),
    path('lyrics/', views.get_lyrics, name='lyrics'),
    path('playlist/create/', views.playlist_create, name='playlist_create'),
    path('playlist/delete/', views.playlist_delete, name='playlist_delete'),
    path('playlist/add/', views.playlist_add_track, name='playlist_add'),
    path('playlist/tracks/', views.playlist_tracks, name='playlist_tracks'),
    path('playlist/list/', views.playlist_list, name='playlist_list'),
    path('playlist/remove-track/', views.playlist_remove_track, name='playlist_remove_track'),
    path('check-saved/', views.check_saved_track, name='check_saved'),
]