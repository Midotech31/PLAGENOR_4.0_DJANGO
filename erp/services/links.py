from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import Request
from erp.permissions import is_manager, is_team


def request_scope(user, *, write=False):
    qs = Request.objects.all()
    if not is_team(user):
        return qs.none()
    if is_manager(user):
        return qs
    condition = Q(assigned_to__user=user)
    if not write:
        condition |= Q(informed_members__user=user)
    return qs.filter(condition).distinct()


def require_request(user, request, *, write=True):
    if request is None:
        return
    if not request_scope(user, write=write).filter(pk=request.pk).exists():
        raise PermissionDenied
    if write and (request.status in ('REJECTED', 'ARCHIVED') or request.archived):
        raise ValidationError(_('Cette demande est rejetée ou archivée.'))



def lock_request(user, request, *, allow_closed=False):
    if request is None:
        return None
    request = Request.objects.select_for_update().get(pk=request.pk)
    if not request_scope(user, write=True).filter(pk=request.pk).exists():
        raise PermissionDenied
    if not allow_closed and (request.status in ('REJECTED', 'ARCHIVED') or request.archived):
        raise ValidationError(_('Cette demande est rejetée ou archivée.'))
    return request
