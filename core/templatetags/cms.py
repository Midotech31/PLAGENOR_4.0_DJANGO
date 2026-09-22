import logging
from django import template
from django.conf import settings
from django.utils.translation import get_language

from core.models import PlatformContent

register = template.Library()
logger = logging.getLogger(__name__)

def clear_cms_cache():
    """Compatibility hook; CMS content is request-scoped, not worker-scoped."""
    return None


def _normalize_lang(code):
    if not code:
        return settings.LANGUAGE_CODE
    base = code.split('-', 1)[0].lower()
    available = {c for c, _ in settings.LANGUAGES}
    if base in available:
        return base
    return settings.LANGUAGE_CODE


def _rows(lang):
    fallback=_normalize_lang(settings.LANGUAGE_CODE)
    return {(key,row_lang):value for key,row_lang,value in PlatformContent.objects.filter(lang__in={lang,fallback}).values_list("key","lang","value")}

def _pick(rows,key,lang,default):
    value=rows.get((key,lang), "")
    if value:
        return value
    fallback=_normalize_lang(settings.LANGUAGE_CODE)
    if lang != fallback:
        value=rows.get((key,fallback), "")
        if value:
            return value
    return default

def cms(key, default=""):
    """Python-callable lookup that always observes committed DB state."""
    lang=_normalize_lang(get_language())
    try:
        return _pick(_rows(lang),key,lang,default)
    except Exception:
        logger.exception("CMS lookup failed for key=%s lang=%s",key,lang)
        return default

@register.simple_tag(takes_context=True, name="cms")
def cms_tag(context,key,default=""):
    """Render content with one preload per request and no cross-worker staleness."""
    lang=_normalize_lang(get_language())
    request=context.get("request") if hasattr(context,"get") else None
    try:
        if request is None:
            return cms(key,default)
        attr="_plagenor_cms_rows_"+lang
        rows=getattr(request,attr,None)
        if rows is None:
            rows=_rows(lang);setattr(request,attr,rows)
        return _pick(rows,key,lang,default)
    except Exception:
        logger.exception("CMS lookup failed for key=%s lang=%s",key,lang)
        return default
