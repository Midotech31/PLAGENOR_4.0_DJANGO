import logging
import time

from django import template
from django.conf import settings
from django.utils.translation import get_language

from core.models import PlatformContent

register = template.Library()
logger = logging.getLogger(__name__)

# In-process cache: {(key, lang): (value, expires_at)}. Avoids a DB hit per
# {% cms %} call (a content page can reference dozens of keys). Entries carry a
# short TTL so edits self-heal across worker processes within ``_CACHE_TTL``,
# and ``clear_cms_cache()`` wipes the whole cache immediately after an admin
# save/delete (single-worker deploys see edits at once).
_content_cache = {}
_CACHE_TTL = 60  # seconds


def clear_cms_cache():
    """Drop every cached content value — call after any PlatformContent write."""
    _content_cache.clear()


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
    cached = _content_cache.get(cache_key)
    if cached is not None and cached[1] > time.monotonic():
        return cached[0] or default
    try:
        obj = PlatformContent.objects.filter(key=key, lang=lang).first()
        if obj is None and lang != settings.LANGUAGE_CODE:
            obj = PlatformContent.objects.filter(key=key, lang=settings.LANGUAGE_CODE).first()
        value = obj.value if (obj and obj.value) else ''
        _content_cache[cache_key] = (value, time.monotonic() + _CACHE_TTL)
        if value:
            return value
    except Exception:
        logger.exception("CMS lookup failed for key=%s lang=%s", key, lang)
    return default
