# pages/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required


def user_guide(request):
    """Страница руководства пользователя"""
    return render(request, 'pages/user_guide.html')