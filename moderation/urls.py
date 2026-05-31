from django.urls import path
from . import views

app_name = 'moderation'

urlpatterns = [
    path('', views.moderation_panel, name='panel'),
    path('reports/', views.report_list, name='report_list'),
    path('report/<int:report_id>/', views.report_detail, name='report_detail'),
    path('report/create/<str:content_type>/<int:object_id>/', views.create_report, name='create_report'),
    path('report/<int:report_id>/approve/', views.approve_report, name='approve_report'),
    path('report/<int:report_id>/reject/', views.reject_report, name='reject_report'),
    path('report/', views.submit_report, name='submit_report'),

    # Пользователи
    path('user/<int:user_id>/', views.user_detail, name='user_detail'),
    path('ban/<int:user_id>/', views.ban_user, name='ban_user'),
    path('ban/<int:ban_id>/lift/', views.lift_ban, name='lift_ban'),

    # Тикеты на разбан (только AJAX обработка, без отдельных страниц)
    path('unban-tickets/<int:ticket_id>/approve/', views.approve_ticket, name='approve_ticket'),
    path('unban-tickets/<int:ticket_id>/reject/', views.reject_ticket, name='reject_ticket'),

    # Скрытие/восстановление контента
    path('hide/<str:content_type>/<int:object_id>/', views.hide_content, name='hide_content'),
    path('unhide/<str:content_type>/<int:object_id>/', views.unhide_content, name='unhide_content'),

    # Сообщества
    path('community/<slug:slug>/', views.community_moderation_panel, name='community_moderation'),

    # Страница бана для пользователя
    path('banned/', views.banned_page, name='banned_page'),
    path('unban-ticket/', views.create_unban_ticket, name='create_unban_ticket'),
]