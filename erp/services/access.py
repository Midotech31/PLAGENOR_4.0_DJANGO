from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from erp.models import AccessGrant, Capability
from erp.permissions import TEAM_ROLES, require_manager
from .common import assign, audit, check_version, snapshot


@transaction.atomic
def save_grant(user, values, *, pk=None, expected=None):
    require_manager(user)
    obj = AccessGrant.objects.select_for_update().get(pk=pk) if pk else AccessGrant(granted_by=user)
    before = snapshot(obj) if pk else {}
    if pk:
        check_version(obj, expected)
    assign(obj, values)
    obj.granted_by = user
    if not obj.user.is_active or obj.user.role not in TEAM_ROLES:
        raise ValidationError(_('Seul un membre actif de l’équipe peut recevoir une délégation ERP.'))
    if obj.capability in (Capability.VIEW_STORAGE, Capability.EDIT_STORAGE, Capability.VIEW_BIOBANK, Capability.MANAGE_BIOBANK):
        if obj.category_id:
            raise ValidationError(_('Une permission de stockage est limitée par emplacement, pas par catégorie.'))
    elif obj.capability in (Capability.VIEW_CATALOG, Capability.EDIT_CATALOG, Capability.VIEW_COST, Capability.EDIT_COST, Capability.VIEW_PLANNING, Capability.EDIT_PLANNING) and obj.location_id:
        raise ValidationError(_('Une permission de catalogue ou de coût est limitée par catégorie.'))
    obj.full_clean()
    if pk:
        obj.version += 1
    obj.save()
    audit(user, obj, 'updated' if pk else 'created', before)
    return obj
