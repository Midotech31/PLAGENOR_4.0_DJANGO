from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord


class LocationType(CodedRecord):
    can_store = models.BooleanField(_('Stockage autorisé'), default=False)
    cold_storage = models.BooleanField(_('Stockage réfrigéré'), default=False)


class Location(CodedRecord):
    parent = models.ForeignKey('self', verbose_name=_('Emplacement parent'), on_delete=models.PROTECT,
                               null=True, blank=True, related_name='children')
    kind = models.ForeignKey(LocationType, verbose_name=_('Type d’emplacement'), on_delete=models.PROTECT)
    temperature_target = models.DecimalField(_('Température cible (°C)'), max_digits=7, decimal_places=2,
                                              null=True, blank=True)
    temperature_min = models.DecimalField(_('Température minimale (°C)'), max_digits=7, decimal_places=2,
                                           null=True, blank=True)
    temperature_max = models.DecimalField(_('Température maximale (°C)'), max_digits=7, decimal_places=2,
                                           null=True, blank=True)
    capacity = models.PositiveIntegerField(_('Capacité (positions)'), null=True, blank=True)
    grid_rows = models.PositiveSmallIntegerField(_('Lignes de la boîte'), null=True, blank=True)
    grid_columns = models.PositiveSmallIntegerField(_('Colonnes de la boîte'), null=True, blank=True)
    notes = models.TextField(_('Consignes et observations'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [
            models.CheckConstraint(condition=~Q(parent=F('pk')), name='erp_location_not_own_parent'),
            models.CheckConstraint(condition=Q(temperature_min__isnull=True) | Q(temperature_max__isnull=True)
                                   | Q(temperature_min__lte=F('temperature_max')), name='erp_location_temperature_order'),
            models.CheckConstraint(condition=Q(capacity__isnull=True) | Q(capacity__gt=0), name='erp_location_positive_capacity'),
            models.CheckConstraint(condition=Q(grid_rows__isnull=True, grid_columns__isnull=True)
                                   | Q(grid_rows__gt=0, grid_columns__gt=0, grid_rows__isnull=False, grid_columns__isnull=False),
                                   name='erp_location_grid_complete'),
        ]
        indexes = [models.Index(fields=['parent', 'active'])]


class LocationClosure(models.Model):
    ancestor = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='descendant_links')
    descendant = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='ancestor_links')
    depth = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ancestor', 'descendant'], name='erp_location_closure_unique'),
            models.CheckConstraint(condition=Q(depth=0, ancestor=F('descendant'))
                                   | (Q(depth__gt=0) & ~Q(ancestor=F('descendant'))), name='erp_closure_depth_matches'),
        ]
