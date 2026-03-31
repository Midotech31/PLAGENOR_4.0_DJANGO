import logging

from django import template
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError

from core.models import PlatformContent

register = template.Library()
logger = logging.getLogger('plagenor.cms')

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
    except (DatabaseError, ObjectDoesNotExist) as e:
        logger.warning(
            f"Failed to load CMS content for key '{key}': {str(e)}",
            extra={'cms_key': key},
            exc_info=True
        )
    return default
