from django import template
from erp.permissions import has_access

register = template.Library()


@register.simple_tag
def erp_available(user):
    return has_access(user)


@register.filter
def erp_value(value):
    from django.utils.translation import gettext as _
    if isinstance(value, bool):
        return _('Oui') if value else _('Non')
    if value is None or value == '':
        return _('Non renseigné')
    return str(value)
