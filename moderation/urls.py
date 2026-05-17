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
    path('community/<slug:slug>/', views.community_moderation_panel, name='community_moderation'),
    path('report/<int:report_id>/approve/', views.approve_report, name='approve_report'),
    path('report/<int:report_id>/reject/', views.reject_report, name='reject_report'),
    path('banned/', views.banned_page, name='banned_page'),
    path('unban-ticket/', views.create_unban_ticket, name='create_unban_ticket'),
    path('report/', views.submit_report, name='submit_report'),
    path('unhide/<str:content_type>/<int:object_id>/', views.unhide_content, name='unhide_content'),
]