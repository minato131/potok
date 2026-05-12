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
]