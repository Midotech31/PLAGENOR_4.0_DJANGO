from django import template
from django.conf import settings
from django.utils.translation import get_language

from core.models import PlatformContent

register = template.Library()

_content_cache = {}


def _normalize_lang(code):
    if not code:
        return settings.LANGUAGE_CODE
    base = code.split('-', 1)[0].lower()
    available = {c for c, _ in settings.LANGUAGES}
    if base in available:
        return base
    return settings.LANGUAGE_CODE


@register.simple_tag
def cms(key, default=''):
    """Load editable content from PlatformContent for the active language.

    Usage: {% cms 'hero_title' 'PLAGENOR 4.0' %}

    Falls back to the project's default LANGUAGE_CODE entry if the active
    language has no row, then to the provided default string.
    """
    lang = _normalize_lang(get_language())
    cache_key = (key, lang)
    if cache_key in _content_cache:
        return _content_cache[cache_key]
    try:
        obj = PlatformContent.objects.filter(key=key, lang=lang).first()
        if obj is None and lang != settings.LANGUAGE_CODE:
            obj = PlatformContent.objects.filter(key=key, lang=settings.LANGUAGE_CODE).first()
        if obj and obj.value:
            _content_cache[cache_key] = obj.value
            return obj.value
    except Exception:
        pass
    return default
