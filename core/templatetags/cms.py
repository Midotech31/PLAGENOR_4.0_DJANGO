from django import template
from core.models import PlatformContent

register = template.Library()

# Cache to avoid hitting DB for every tag
_content_cache = {}


@register.simple_tag
def cms(key, default=''):
    """Load editable content from PlatformContent. Usage: {% cms 'hero_title' 'PLAGENOR 4.0' %}"""
    if key in _content_cache:
        return _content_cache[key]
    try:
        obj = PlatformContent.objects.filter(key=key).first()
        if obj and obj.value:
            _content_cache[key] = obj.value
            return obj.value
    except Exception:
        pass
    return default
