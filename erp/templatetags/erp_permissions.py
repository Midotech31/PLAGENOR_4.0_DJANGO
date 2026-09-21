from django import template

from erp.models import Capability
from erp.permissions import grants, is_manager, is_team
from erp.services.links import request_scope

register = template.Library()


@register.simple_tag
def can_store_request(user, request):
    if request is None or not is_team(user):
        return False
    if not (is_manager(user) or grants(user, Capability.MANAGE_BIOBANK).exists()):
        return False
    return request_scope(user, write=True).filter(pk=request.pk).exists()


@register.simple_tag
def can_operate_request(user, request):
    return bool(request is not None and is_team(user) and not request.archived and
                request.status not in ('REJECTED', 'ARCHIVED') and
                request_scope(user, write=True).filter(pk=request.pk).exists())
