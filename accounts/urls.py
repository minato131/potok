from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit_view, name='profile_edit'),
    path('profile/<str:username>/', views.profile_view, name='profile_by_username'),
    path('follow/<int:user_id>/', views.follow_view, name='follow'),
    path('<str:username>/followers/', views.followers_list_view, name='followers'),
    path('<str:username>/following/', views.following_list_view, name='following'),
]