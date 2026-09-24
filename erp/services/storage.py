from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from erp.models import Capability, Location, LocationClosure
from erp.permissions import require
from .common import assign, audit, check_version, lock_tree, snapshot


@transaction.atomic
def save_location(user, values, *, pk=None, expected=None):
    lock_tree('locations')
    obj = Location.objects.select_for_update().get(pk=pk) if pk else Location()
    before = snapshot(obj) if pk else {}
    if pk:
        require(user, Capability.EDIT_STORAGE, location=obj)
        check_version(obj, expected)
    assign(obj, values)
    parent_changed = not pk or before['parent'] != (str(obj.parent_id) if obj.parent_id else None)
    if parent_changed:
        require(user, Capability.EDIT_STORAGE, location=obj.parent)
    if obj.parent and not obj.parent.active:
        raise ValidationError(_('L’emplacement parent doit être actif.'))
    if not obj.kind.active:
        raise ValidationError(_('Le type d’emplacement doit être actif.'))
    descendants = dict(LocationClosure.objects.filter(ancestor=obj).values_list('descendant_id', 'depth')) if pk else {obj.pk: 0}
    if obj.parent_id in descendants:
        raise ValidationError(_('Une hiérarchie ne peut pas contenir de cycle.'))
    if pk and not obj.active and obj.children.filter(active=True).exists():
        raise ValidationError(_('Désactivez d’abord les emplacements enfants.'))
    if obj.temperature_target is not None and (
        (obj.temperature_min is not None and obj.temperature_target < obj.temperature_min)
        or (obj.temperature_max is not None and obj.temperature_target > obj.temperature_max)
    ):
        raise ValidationError(_('La température cible doit appartenir à la plage autorisée.'))
    if obj.grid_rows is not None and obj.grid_columns is not None:
        size = obj.grid_rows * obj.grid_columns
        if obj.capacity is not None and obj.capacity != size:
            raise ValidationError(_('La capacité doit correspondre au nombre de positions de la grille.'))
        obj.capacity = size
    from erp.models import BiologicalSample, StockContainer, StoragePosition
    if pk:
        positions = StoragePosition.objects.filter(location=obj)
        if positions.exists() and (obj.grid_rows is None or obj.grid_columns is None or
            positions.filter(Q(row__gt=obj.grid_rows) | Q(column__gt=obj.grid_columns)).exists()):
            raise ValidationError(_('La modification supprimerait des positions existantes. Conservez la grille historique.'))
        if not obj.active or not obj.kind.can_store:
            if BiologicalSample.objects.filter(location_id__in=LocationClosure.objects.filter(ancestor=obj).values('descendant_id')).exclude(status__in=['DESTROYED', 'SHIPPED', 'EXHAUSTED']).exists() or StockContainer.objects.filter(location_id__in=LocationClosure.objects.filter(ancestor=obj).values('descendant_id'), quantity__gt=0).exists():
                raise ValidationError(_('Déplacez le contenu physique avant de désactiver cet emplacement ou son stockage.'))
    obj.full_clean()
    if pk:
        obj.version += 1
    obj.save()
    if not pk:
        LocationClosure.objects.create(ancestor=obj, descendant=obj, depth=0)
    if parent_changed:
        LocationClosure.objects.filter(descendant_id__in=descendants).exclude(ancestor_id__in=descendants).delete()
        ancestors = list(LocationClosure.objects.filter(descendant_id=obj.parent_id).values_list('ancestor_id', 'depth'))
        LocationClosure.objects.bulk_create([
            LocationClosure(ancestor_id=ancestor_id, descendant_id=descendant_id, depth=above + below + 1)
            for ancestor_id, above in ancestors for descendant_id, below in descendants.items()
        ])
    if obj.active and obj.kind.can_store and obj.grid_rows and obj.grid_columns:
        from .biobank import build_positions
        build_positions(user, obj.pk, expected=obj.version)
    audit(user, obj, 'updated' if pk else 'created', before)
    return obj
