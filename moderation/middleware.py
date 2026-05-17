from django.shortcuts import redirect
from django.urls import resolve
from .models import Ban


class BanCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # URL-ы, доступные забаненному
            allowed_urls = [
                'banned_page', 'logout', 'create_unban_ticket',
                'login', 'register', 'verify_email', 'confirm_email',
                'password_reset', 'password_reset_done',
                'password_reset_confirm', 'password_reset_complete',
            ]

            current_url = resolve(request.path_info).url_name

            if current_url not in allowed_urls:
                active_ban = Ban.objects.filter(
                    user=request.user,
                    lifted_at__isnull=True
                ).first()

                # Проверяем временные баны — не истекли ли
                if active_ban and active_ban.ban_type == 'temporary':
                    from django.utils import timezone
                    if active_ban.expires_at and active_ban.expires_at < timezone.now():
                        active_ban.lifted_at = timezone.now()
                        active_ban.save()
                        return None  # Пропускаем, бан истёк

                if active_ban:
                    return redirect('moderation:banned_page')

        return self.get_response(request)