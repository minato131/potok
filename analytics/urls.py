from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('data/', views.data, name='data'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
    path('export/json/', views.export_analytics_json, name='export_json'),
]