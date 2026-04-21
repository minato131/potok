# potok/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('communities/', include('communities.urls', namespace='communities')),
    path('messenger/', include('messenger.urls', namespace='messenger')),
    path('moderation/', include('moderation.urls', namespace='moderation')),
    path('', include('posts.urls', namespace='posts')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)