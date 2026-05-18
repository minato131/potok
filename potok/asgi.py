# potok/asgi.py
import os
from django.core.asgi import get_asgi_application

# Сначала настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'potok.settings')

# Получаем Django ASGI приложение
django_asgi_app = get_asgi_application()

# Теперь импортируем channels (после настройки Django)
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from accounts.consumers import NotificationConsumer

# Создаём основное приложение
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/notifications/", NotificationConsumer.as_asgi()),
        ])
    ),
})