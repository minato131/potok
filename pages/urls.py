# pages/urls.py
from django.urls import path
from . import views

app_name = 'pages'

urlpatterns = [
    path('guide/', views.user_guide, name='user_guide'),
]