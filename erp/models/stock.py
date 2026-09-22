from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, ImmutableRecord, Record


class StockLot(CodedRecord):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('En attente de contrôle')
        QUARANTINE = 'QUARANTINE', _('Quarantaine')
        AVAILABLE = 'AVAILABLE', _('Accepté / disponible')
        REJECTED = 'REJECTED', _('Rejeté')
        RECALLED = 'RECALLED', _('Rappelé')
        DESTROYED = 'DESTROYED', _('Détruit')

    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT, related_name='stock_lots')
    manufacturer_lot = models.CharField(_('Lot fabricant'), max_length=120, db_index=True)
    serial_number = models.CharField(_('Numéro de série'), max_length=120, blank=True)
    manufactured_on = models.DateField(_('Date de fabrication'), null=True, blank=True)
    expires_on = models.DateField(_('Péremption fabricant'), null=True, blank=True, db_index=True)
    status = models.CharField(_('État du lot'), max_length=12, choices=Status.choices, default=Status.PENDING)
    origin = models.CharField(_('Origine'), max_length=16, choices=[('PURCHASE', _('Achat')), ('PREPARATION', _('Préparation interne'))], default='PURCHASE')
    barcode = models.CharField(_('Code fabricant / GS1'), max_length=255, blank=True, db_index=True)
    specifications_snapshot = models.JSONField(default=dict, editable=False)

    class Meta(CodedRecord.Meta):
        constraints = [models.UniqueConstraint(fields=['article', 'manufacturer_lot', 'serial_number'], name='erp_lot_identity'),
            models.CheckConstraint(condition=Q(manufactured_on__isnull=True) | Q(expires_on__isnull=True) | Q(manufactured_on__lte=F('expires_on')), name='erp_lot_dates')]
        indexes = [models.Index(fields=['article', 'status', 'expires_on'])]


class StockContainer(CodedRecord):
    lot = models.ForeignKey(StockLot, on_delete=models.PROTECT, related_name='containers')
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='stock_containers')
    status = models.CharField(_('Contrôle du contenant'), max_length=12, choices=StockLot.Status.choices, default=StockLot.Status.PENDING)
    stability_days = models.PositiveIntegerField(null=True, blank=True, editable=False)
    quantity = models.DecimalField(_('Stock physique'), max_digits=18, decimal_places=6, default=0, editable=False)
    reserved = models.DecimalField(_('Stock réservé'), max_digits=18, decimal_places=6, default=0, editable=False)
    opened_on = models.DateField(_('Date d’ouverture'), null=True, blank=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    use_by = models.DateField(_('Date limite d’utilisation'), null=True, blank=True, editable=False, db_index=True)

    class Meta(CodedRecord.Meta):
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0, quantity__lte=Decimal('999999999999.999999'), reserved__gte=0) & Q(reserved__lte=F('quantity')), name='erp_container_balance')]
        indexes = [models.Index(fields=['location', 'lot'])]


class StockMovement(ImmutableRecord):
    class Kind(models.TextChoices):
        INITIAL = 'INITIAL', _('Stock initial')
        RECEIPT = 'RECEIPT', _('Réception')
        CONSUMPTION = 'CONSUMPTION', _('Consommation')
        TRANSFER = 'TRANSFER', _('Transfert')
        RESERVATION = 'RESERVATION', _('Réservation')
        RELEASE = 'RELEASE', _('Libération')
        RETURN = 'RETURN', _('Retour')
        CORRECTION = 'CORRECTION', _('Contre-passation')
        INVENTORY = 'INVENTORY', _('Ajustement d’inventaire')
        LOSS = 'LOSS', _('Perte')
        BREAKAGE = 'BREAKAGE', _('Casse')
        CONTAMINATION = 'CONTAMINATION', _('Contamination')
        EXPIRY = 'EXPIRY', _('Péremption')
        DESTRUCTION = 'DESTRUCTION', _('Destruction')
        EXIT = 'EXIT', _('Sortie définitive')
        PREPARATION = 'PREPARATION', _('Préparation interne')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField(unique=True)
    payload_hash = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.CharField(_('Motif'), max_length=500, blank=True)
    request = models.ForeignKey('core.Request', on_delete=models.PROTECT, null=True, blank=True, related_name='erp_stock_movements')
    reverses = models.OneToOneField('self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal')
    snapshot = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['kind', 'created_at']), models.Index(fields=['request', 'created_at'])]


class StockEntry(ImmutableRecord):
    movement = models.ForeignKey(StockMovement, on_delete=models.PROTECT, related_name='entries')
    container = models.ForeignKey(StockContainer, on_delete=models.PROTECT, related_name='entries')
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT)
    quantity_delta = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    reserved_delta = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    snapshot = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=['container', 'created_at']), models.Index(fields=['location', 'created_at'])]
        constraints = [models.CheckConstraint(condition=~Q(quantity_delta=0, reserved_delta=0), name='erp_entry_nonzero')]


class StockReceipt(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name='receipt')
    container = models.ForeignKey(StockContainer, on_delete=models.PROTECT)
    supplier = models.ForeignKey('erp.Party', on_delete=models.PROTECT, null=True, blank=True)
    order_reference = models.CharField(_('Commande / marché'), max_length=120, blank=True)
    ordered_on = models.DateField(_('Date de commande'), null=True, blank=True)
    received_on = models.DateField(_('Date de réception'))
    ordered_quantity = models.DecimalField(_('Quantité commandée (unité de gestion)'), max_digits=18, decimal_places=6, null=True, blank=True)
    received_quantity = models.DecimalField(max_digits=18, decimal_places=6)
    condition = models.CharField(_('État à la réception'), max_length=255)
    cold_chain_ok = models.BooleanField(_('Chaîne du froid respectée'), null=True, blank=True)
    control_notes = models.TextField(_('Contrôle de réception'), blank=True)
    unit_price = models.DecimalField(_('Prix unitaire (unité de gestion)'), max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(_('Devise'), max_length=3, default='DZD')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(received_quantity__gt=0), name='erp_receipt_quantity'),
            models.CheckConstraint(condition=Q(ordered_quantity__isnull=True) | Q(ordered_quantity__gt=0), name='erp_receipt_order_quantity'),
            models.CheckConstraint(condition=Q(unit_price__isnull=True) | Q(unit_price__gte=0), name='erp_receipt_price')]
        ordering = ['-received_on', '-created_at']


class StockReservation(Record):
    container = models.ForeignKey(StockContainer, on_delete=models.PROTECT, related_name='reservations')
    request = models.ForeignKey('core.Request', on_delete=models.PROTECT, null=True, blank=True, related_name='erp_reservations')
    reference = models.CharField(_('Run / projet / justification'), max_length=255)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT)
    remaining = models.DecimalField(max_digits=18, decimal_places=6)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(remaining__gte=0), name='erp_reservation_nonnegative')]


class InternalPreparation(ImmutableRecord):
    output_lot = models.OneToOneField(StockLot, on_delete=models.PROTECT, related_name='preparation')
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT)
    protocol_reference = models.CharField(_('Protocole / SOP'), max_length=255)
    prepared_on = models.DateField(_('Date de préparation'))
    concentration = models.CharField(_('Concentration documentée'), max_length=120, blank=True)
    concentration_value = models.DecimalField(_('Valeur de concentration'),max_digits=18,decimal_places=6,null=True,blank=True)
    concentration_unit = models.ForeignKey('erp.Unit',on_delete=models.PROTECT,null=True,blank=True,related_name='+',verbose_name=_('Unité de concentration'))
    sources = models.JSONField(default=list)


    class Meta:
        constraints=[models.CheckConstraint(condition=Q(concentration_value__isnull=True,concentration_unit__isnull=True)|
            Q(concentration_value__gte=0,concentration_value__lte=Decimal('999999999999.999999'),concentration_value__isnull=False,concentration_unit__isnull=False),name='erp_preparation_concentration_pair')]
