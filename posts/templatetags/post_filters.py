# posts/templatetags/post_filters.py
from django import template
from urllib.parse import urlparse

register = template.Library()

@register.filter(name='url_domain')
def url_domain(value):
    """Извлекает домен из URL"""
    if not value:
        return ''
    try:
        parsed = urlparse(value)
        domain = parsed.netloc or parsed.path.split('/')[0]
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except:
        return value


@register.filter(name='filename')
def filename(value):
    """Извлекает имя файла из пути"""
    import os
    if not value:
        return ''
    return os.path.basename(value)


@register.filter(name='truncate_chars')
def truncate_chars(value, max_length):
    """Обрезает строку до указанного количества символов"""
    if not value:
        return ''
    if len(value) <= max_length:
        return value
    return value[:max_length] + '...'

@register.filter
def get_item(dictionary, key):
    """Получить значение из словаря по ключу"""
    if dictionary is None:
        return ''
    # Поддержка как словарей, так и объектов с методом get
    if hasattr(dictionary, 'get'):
        return dictionary.get(key, '')
    # Если это объект формы, пытаемся получить значение поля
    if hasattr(dictionary, 'cleaned_data'):
        return dictionary.cleaned_data.get(key, '')
    return ''