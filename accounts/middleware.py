from django.utils import timezone


class LastActivityMiddleware:
    """
    Middleware для обновления времени последней активности пользователя
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Обновляем время последней активности
            request.user.last_activity = timezone.now()
            request.user.save(update_fields=['last_activity'])
        response = self.get_response(request)
        return response