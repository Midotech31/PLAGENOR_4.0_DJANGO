from django import template
from django.utils.translation import get_language
from core.ibtikar.schema import projection
register = template.Library()

@register.simple_tag
def ibtikar_projection(req):
    form = req.ibtikar_form
    return projection(form.schema, form.applicant, form.parameters, form.samples, form.staff, get_language() or 'fr')
