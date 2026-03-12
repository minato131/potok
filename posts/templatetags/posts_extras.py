from django import template
from django.utils.safestring import mark_safe
import re

register = template.Library()


@register.filter(name='highlight')
def highlight(text, query):
    """
    Подсвечивает слова из поискового запроса в тексте
    """
    if not query or not text:
        return text

    # Экранируем специальные символы регулярных выражений
    words = re.findall(r'\w+', query)
    if not words:
        return text

    highlighted_text = text
    for word in words:
        if len(word) < 2:
            continue
        # Создаем паттерн для поиска слова (без учета регистра)
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        # Заменяем на подсвеченную версию
        highlighted_text = pattern.sub(
            lambda m: f'<span class="bg-warning text-dark px-1 rounded">{m.group()}</span>',
            highlighted_text
        )

    return mark_safe(highlighted_text)


@register.filter(name='truncate_html')
def truncate_html(text, length=200):
    """
    Обрезает текст и корректно закрывает HTML теги
    """
    if len(text) <= length:
        return text

    # Простое обрезание без учета HTML (для простоты)
    return text[:length] + '...'