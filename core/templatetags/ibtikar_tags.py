from django import template
from django.utils.translation import get_language
from core.ibtikar.schema import reference_projection
register = template.Library()

@register.simple_tag
def ibtikar_projection(req):
    form = req.ibtikar_form
    return reference_projection(form, get_language() or 'fr')
