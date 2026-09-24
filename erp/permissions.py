from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .models import AccessGrant, Capability, LocationClosure, WorkItem


ADMIN_ROLES = ('SUPER_ADMIN', 'PLATFORM_ADMIN')
TEAM_ROLES = (*ADMIN_ROLES, 'MEMBER', 'FINANCE')
READ_INCLUDES = {
    Capability.VIEW_CATALOG: (Capability.VIEW_CATALOG, Capability.EDIT_CATALOG),
    Capability.VIEW_STORAGE: (Capability.VIEW_STORAGE, Capability.EDIT_STORAGE),
    Capability.VIEW_COST: (Capability.VIEW_COST, Capability.EDIT_COST),
    Capability.VIEW_STOCK: (Capability.VIEW_STOCK, Capability.RECEIVE_STOCK, Capability.CONSUME_STOCK,
                            Capability.TRANSFER_STOCK, Capability.RESERVE_STOCK, Capability.CONTROL_STOCK, Capability.INVENTORY),
    Capability.VIEW_BIOBANK: (Capability.VIEW_BIOBANK, Capability.MANAGE_BIOBANK),
    Capability.VIEW_PLANNING: (Capability.VIEW_PLANNING, Capability.EDIT_PLANNING),
}


def is_manager(user):
    return bool(user.is_authenticated and user.is_active and user.role in ADMIN_ROLES)


def is_team(user):
    return bool(user.is_authenticated and user.is_active and user.role in TEAM_ROLES)


def grants(user, capability):
    return AccessGrant.objects.filter(user=user, active=True,
        capability__in=READ_INCLUDES.get(capability, (capability,)))


def has_access(user):
    return is_team(user) and (is_manager(user) or AccessGrant.objects.filter(user=user, active=True).exists()
        or WorkItem.objects.filter(assignee=user).exclude(status=WorkItem.Status.CANCELLED).exists())


def permitted(user, capability, *, location=None, category=None):
    if not is_team(user):
        return False
    if is_manager(user):
        return True
    candidates = grants(user, capability)
    category_filter = Q(category__isnull=True)
    if category is not None:
        category_filter |= Q(category_id=category.pk)
    candidates = candidates.filter(category_filter)
    location_filter = Q(location__isnull=True)
    if location is not None:
        ancestors = LocationClosure.objects.filter(descendant=location).values('ancestor_id')
        location_filter |= Q(location_id__in=ancestors)
    return candidates.filter(location_filter).exists()


def require(user, capability, **scope):
    if not permitted(user, capability, **scope):
        raise PermissionDenied


def require_manager(user):
    if not is_manager(user):
        raise PermissionDenied


def catalog_scope(queryset, user, capability=Capability.VIEW_CATALOG, field='category_id'):
    if not is_team(user):
        return queryset.none()
    if is_manager(user):
        return queryset
    allowed = grants(user, capability).filter(location__isnull=True)
    if allowed.filter(category__isnull=True).exists():
        return queryset
    return queryset.filter(**{field + '__in': allowed.values('category_id')})


def storage_scope(queryset, user, capability=Capability.VIEW_STORAGE):
    if not is_team(user):
        return queryset.none()
    if is_manager(user):
        return queryset
    allowed = grants(user, capability).filter(category__isnull=True)
    if allowed.filter(location__isnull=True).exists():
        return queryset
    descendants = LocationClosure.objects.filter(ancestor_id__in=allowed.values('location_id')).values('descendant_id')
    return queryset.filter(pk__in=descendants)


def operational_scope(queryset, user, capability=Capability.VIEW_STOCK, *, category_field='lot__article__category_id', location_field='location_id'):
    if not is_team(user):
        return queryset.none()
    if is_manager(user):
        return queryset
    condition = Q(pk__in=[])
    for grant in grants(user, capability):
        scope = Q()
        if grant.category_id:
            scope &= Q(**{category_field: grant.category_id})
        if grant.location_id:
            descendants = LocationClosure.objects.filter(ancestor_id=grant.location_id).values('descendant_id')
            scope &= Q(**{location_field + '__in': descendants})
        if not scope:
            return queryset
        condition |= scope
    return queryset.filter(condition)
