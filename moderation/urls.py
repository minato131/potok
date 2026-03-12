from django.urls import path
from . import views

app_name = 'moderation'

urlpatterns = [
    path('', views.moderation_panel, name='panel'),
    path('reports/', views.report_list, name='report_list'),
    path('report/<int:report_id>/', views.report_detail, name='report_detail'),
    path('report/create/<str:content_type>/<int:object_id>/', views.create_report, name='create_report'),
    path('ban/<int:user_id>/', views.ban_user, name='ban_user'),
    path('ban/<int:ban_id>/lift/', views.lift_ban, name='lift_ban'),
    path('hide/<str:content_type>/<int:object_id>/', views.hide_content, name='hide_content'),
    path('user/<int:user_id>/', views.user_detail, name='user_detail'),
]