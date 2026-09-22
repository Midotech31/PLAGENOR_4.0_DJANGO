from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import Record


class InventoryCampaign(Record):
    work = models.OneToOneField('erp.WorkItem', on_delete=models.PROTECT, related_name='inventory')
    blind = models.BooleanField(_('Masquer le stock théorique pendant le comptage'), default=True)
    adjustment = models.OneToOneField('erp.StockMovement', on_delete=models.PROTECT,
        null=True, blank=True, editable=False, related_name='inventory_campaign')


class InventoryLine(Record):
    campaign = models.ForeignKey(InventoryCampaign, on_delete=models.PROTECT, related_name='lines')
    container = models.ForeignKey('erp.StockContainer', on_delete=models.PROTECT)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    theoretical_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    counted_quantity = models.DecimalField(_('Quantité physique comptée'), max_digits=18, decimal_places=6, null=True, blank=True)
    container_version = models.PositiveIntegerField()
    counted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    counted_at = models.DateTimeField(null=True, blank=True)
    needs_recount = models.BooleanField(default=False)
    note = models.CharField(_('Observation de comptage'), max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['campaign', 'container'], name='erp_inventory_container'),
            models.CheckConstraint(condition=Q(counted_quantity__isnull=True) | Q(counted_quantity__gte=0), name='erp_inventory_count_nonnegative')]
        ordering = ['container__code']
