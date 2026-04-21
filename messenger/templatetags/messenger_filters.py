# messenger/templatetags/messenger_filters.py
from django import template
import os

register = template.Library()


@register.filter(name='filename')
def filename(value):
    """
    Извлекает имя файла из пути.
    Например: /path/to/file.pdf -> file.pdf
    """
    if not value:
        return ''
    return os.path.basename(value)


@register.filter(name='filesizeformat')
def filesizeformat_custom(value):
    """
    Форматирует размер файла в читаемый вид.
    """
    if not value:
        return '0 B'

    try:
        size = int(value)
    except (TypeError, ValueError):
        return value

    if size < 1024:
        return f'{size} B'
    elif size < 1024 * 1024:
        return f'{size / 1024:.1f} KB'
    elif size < 1024 * 1024 * 1024:
        return f'{size / (1024 * 1024):.1f} MB'
    else:
        return f'{size / (1024 * 1024 * 1024):.1f} GB'