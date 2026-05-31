from django import template

register = template.Library()

@register.filter
def duration_format(seconds):
    if not seconds:
        return "0:00"
    try:
        seconds = int(float(seconds))
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"
    except (ValueError, TypeError):
        return "0:00"