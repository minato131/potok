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


class SessionInfoMiddleware:
    """Сохраняет IP и User-Agent в сессию"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            session = request.session
            # Сохраняем данные только если изменились
            if session.get('ip') != self.get_client_ip(request):
                session['ip'] = self.get_client_ip(request)
                session['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:200]
                session['last_activity'] = timezone.now().isoformat()
                session.modified = True

        return response

    @staticmethod
    def get_client_ip(request):
        """Получить реальный IP пользователя"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '')
        return ip