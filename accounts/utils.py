from .models import Notification
from django.contrib.contenttypes.models import ContentType
import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone


def create_notification(recipient, sender, notification_type, title, message, link='', content_object=None):
    """
    Универсальная функция создания уведомлений
    """
    if recipient == sender:
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        sender=sender,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link
    )

    if content_object:
        from django.contrib.contenttypes.models import ContentType
        notification.content_type = ContentType.objects.get_for_model(content_object)
        notification.object_id = content_object.id
        notification.save()

    return notification


def generate_verification_code():
    """
    Генерирует 6-значный код подтверждения
    """
    return ''.join(random.choices(string.digits, k=6))


def send_verification_email(user, code):
    """
    Отправка кода подтверждения на email
    """
    try:
        # Контекст для шаблона
        context = {
            'user': user,
            'code': code,
            'site_name': 'Поток',
            'site_url': 'http://127.0.0.1:8000',  # Замени на реальный домен
            'expiry_minutes': 10,
        }

        # HTML версия письма
        html_content = render_to_string('emails/verification_code.html', context)

        # Текстовая версия
        text_content = strip_tags(html_content)

        # Отправляем письмо
        send_mail(
            subject=f'Код подтверждения - {code}',
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )

        # Обновляем время отправки
        user.email_verification_sent = timezone.now()
        user.save(update_fields=['email_verification_sent'])

        return True
    except Exception as e:
        print(f"Ошибка отправки email: {e}")
        return False


def send_welcome_email(user):
    """
    Отправляет приветственное письмо после подтверждения email
    """
    try:
        context = {
            'user': user,
            'site_name': 'Поток',
            'site_url': 'http://127.0.0.1:8000',
            'login_url': 'http://127.0.0.1:8000/accounts/login/',
        }

        html_content = render_to_string('emails/welcome_email.html', context)
        text_content = strip_tags(html_content)

        send_mail(
            subject=f'Добро пожаловать в {context["site_name"]}!',
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_content,
            fail_silently=False,
        )
        return True
    except Exception as e:
        print(f"Ошибка отправки приветствия: {e}")
        return False


def mask_email(email):
    """
    Маскирует email для отображения (показывает только первую букву и домен)
    """
    if not email:
        return email
    parts = email.split('@')
    if len(parts) != 2:
        return email
    name, domain = parts
    if len(name) <= 2:
        masked_name = name[0] + '*' * len(name[1:])
    else:
        masked_name = name[0] + '*' * (len(name) - 2) + name[-1]
    return f"{masked_name}@{domain}"