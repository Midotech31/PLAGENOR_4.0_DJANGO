from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, ImmutableRecord, Record


class StoragePosition(CodedRecord):
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='positions')
    row = models.PositiveSmallIntegerField(_('Ligne'))
    column = models.PositiveSmallIntegerField(_('Colonne'))

    class Meta(CodedRecord.Meta):
        ordering = ['row', 'column']
        constraints = [models.UniqueConstraint(fields=['location', 'row', 'column'], name='erp_storage_grid_position'),
                       models.CheckConstraint(condition=Q(row__gt=0, column__gt=0), name='erp_storage_grid_positive')]


class PositionReservation(Record):
    position = models.ForeignKey(StoragePosition, on_delete=models.PROTECT, related_name='reservations')
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    until = models.DateTimeField(_('Réservée jusqu’au'))
    reason = models.CharField(_('Motif'), max_length=500)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['position'], condition=Q(active=True), name='erp_active_position_reservation')]


class BiologicalSample(CodedRecord):
    class Status(models.TextChoices):
        STORED = 'STORED', _('Stocké')
        OUT = 'OUT', _('Sorti du stockage')
        QUARANTINE = 'QUARANTINE', _('Quarantaine')
        EXHAUSTED = 'EXHAUSTED', _('Épuisé')
        SHIPPED = 'SHIPPED', _('Expédié')
        DESTROYED = 'DESTROYED', _('Détruit')

    origin_request = models.ForeignKey('core.Request', on_delete=models.PROTECT,
        null=True, blank=True, related_name='erp_samples')
    source_kind = models.CharField(max_length=16, choices=[('IBTIKAR', 'IBTIKAR'),
        ('LEGACY', _('Demande PLAGENOR')), ('MANUAL', _('Réception documentée')), ('ALIQUOT', _('Aliquot'))])
    source_key = models.CharField(max_length=100, blank=True)
    source_fingerprint = models.CharField(max_length=64, blank=True, editable=False)
    source_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='aliquots')
    root_sample = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True,
        editable=False, related_name='descendant_samples')
    sample_type = models.CharField(_('Type d’échantillon'), max_length=160, blank=True)
    matrix = models.CharField(_('Matrice'), max_length=160, blank=True)
    received_on = models.DateField(_('Date de réception'))
    collected_on = models.DateField(_('Date de prélèvement'), null=True, blank=True)
    concentration_value = models.DecimalField(_('Concentration'), max_digits=18, decimal_places=6, null=True, blank=True)
    concentration_unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_('Unité de concentration'), related_name='+')
    unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT, related_name='+', verbose_name=_('Unité de gestion'))
    initial_quantity = models.DecimalField(_('Quantité initiale'), max_digits=18, decimal_places=6, editable=False)
    remaining_quantity = models.DecimalField(_('Quantité restante'), max_digits=18, decimal_places=6, editable=False)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='biological_samples')
    position = models.OneToOneField(StoragePosition, on_delete=models.PROTECT, null=True, blank=True, related_name='occupant')
    status = models.CharField(_('État de l’échantillon'), max_length=12, choices=Status.choices, default=Status.STORED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    temperature_min = models.DecimalField(_('Température minimale de conservation (°C)'), max_digits=7, decimal_places=2, null=True, blank=True)
    temperature_max = models.DecimalField(_('Température maximale de conservation (°C)'), max_digits=7, decimal_places=2, null=True, blank=True)
    preservation = models.CharField(_('Conditions de conservation documentées'), max_length=500, blank=True)
    freeze_thaw_limit = models.PositiveIntegerField(_('Seuil de cycles selon le protocole'), null=True, blank=True)
    freeze_thaw_cycles = models.PositiveIntegerField(default=0, editable=False)
    checked_out_at = models.DateTimeField(null=True, blank=True, editable=False)
    thawed_during_checkout = models.BooleanField(default=False, editable=False)
    out_of_storage_seconds = models.PositiveBigIntegerField(default=0, editable=False)
    notes = models.TextField(_('Observations'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [
            models.UniqueConstraint(fields=['origin_request', 'source_kind', 'source_key'],
                condition=Q(origin_request__isnull=False), name='erp_sample_request_source_unique'),
            models.CheckConstraint(condition=Q(initial_quantity__gt=0, initial_quantity__lte=Decimal('999999999999.999999'),
                remaining_quantity__gte=0) & Q(remaining_quantity__lte=F('initial_quantity')), name='erp_sample_quantity_bounds'),
            models.CheckConstraint(condition=Q(collected_on__isnull=True) | Q(collected_on__lte=F('received_on')), name='erp_sample_collection_date'),
            models.CheckConstraint(condition=Q(temperature_min__isnull=True) | Q(temperature_max__isnull=True) | Q(temperature_min__lte=F('temperature_max')), name='erp_sample_temperature_range'),
            models.CheckConstraint(condition=Q(concentration_value__isnull=True, concentration_unit__isnull=True) |
                Q(concentration_value__gte=0, concentration_value__isnull=False, concentration_unit__isnull=False), name='erp_sample_concentration_pair'),
            models.CheckConstraint(condition=~Q(parent=F('pk')), name='erp_sample_not_own_parent'),
        ]
        indexes = [models.Index(fields=['location', 'status']), models.Index(fields=['origin_request', 'source_kind']),
                   models.Index(fields=['root_sample', 'status'])]

    @property
    def shared_metadata(self):
        return self.root_sample if self.root_sample_id else self


class SampleEvent(ImmutableRecord):
    class Kind(models.TextChoices):
        RECEIPT = 'RECEIPT', _('Réception')
        ALIQUOT = 'ALIQUOT', _('Aliquotage')
        TRANSFER = 'TRANSFER', _('Transfert')
        CHECK_OUT = 'CHECK_OUT', _('Sortie du stockage')
        RETURN = 'RETURN', _('Retour au stockage')
        CONSUMPTION = 'CONSUMPTION', _('Consommation analytique')
        ANALYSIS = 'ANALYSIS', _('Analyse sans quantité biologique consommée')
        QUARANTINE = 'QUARANTINE', _('Mise en quarantaine')
        RELEASE = 'RELEASE', _('Libération après contrôle')
        SHIPMENT = 'SHIPMENT', _('Expédition')
        DESTRUCTION = 'DESTRUCTION', _('Destruction')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField(unique=True)
    payload_hash = models.CharField(max_length=64)
    sample = models.ForeignKey(BiologicalSample, on_delete=models.PROTECT, related_name='events')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    from_location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    to_location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    from_position = models.ForeignKey(StoragePosition, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    to_position = models.ForeignKey(StoragePosition, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    quantity_delta = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    request = models.ForeignKey('core.Request', on_delete=models.PROTECT, null=True, blank=True, related_name='erp_sample_events')
    reason = models.CharField(_('Motif'), max_length=500)
    data = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [models.Index(fields=['sample', 'created_at']), models.Index(fields=['request', 'kind'])]


class StorageIncident(Record):
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='incidents')
    kind = models.CharField(_('Type d’incident'), max_length=16, choices=[('FAILURE', _('Panne')),
        ('TEMPERATURE', _('Excursion de température')), ('MAINTENANCE', _('Maintenance')), ('DEFROST', _('Dégivrage'))])
    started_at = models.DateTimeField(_('Début de l’incident'))
    resolved_at = models.DateTimeField(_('Fin de l’incident'), null=True, blank=True)
    description = models.TextField(_('Description et impact observé'))
    corrective_action = models.TextField(_('Action corrective'), blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    work = models.OneToOneField('erp.WorkItem', on_delete=models.PROTECT, null=True, blank=True, related_name='incident')

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(resolved_at__isnull=True) | Q(resolved_at__gte=F('started_at')), name='erp_incident_chronology')]
        ordering = ['-started_at']


class TemperatureReading(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='temperature_readings')
    measured_at = models.DateTimeField(_('Date et heure du relevé'))
    value = models.DecimalField(_('Température mesurée (°C)'), max_digits=7, decimal_places=2)
    minimum_snapshot = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    maximum_snapshot = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    out_of_range = models.BooleanField(default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.CharField(max_length=16, choices=[('MANUAL', _('Relevé manuel')), ('IMPORT', _('Import contrôlé'))])
    comment = models.CharField(_('Observation'), max_length=500, blank=True)
    incident = models.ForeignKey(StorageIncident, on_delete=models.PROTECT, null=True, blank=True, related_name='readings')

    class Meta:
        ordering = ['-measured_at', '-id']
        indexes = [models.Index(fields=['location', 'measured_at'])]


class StorageTransfer(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField(unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='+')
    destination = models.ForeignKey('erp.Location', on_delete=models.PROTECT, related_name='+')
    mapping = models.JSONField(default=list)
    payload_hash = models.CharField(max_length=64)
    reason = models.CharField(_('Motif du transfert collectif'), max_length=500)
    incident = models.ForeignKey(StorageIncident, on_delete=models.PROTECT, null=True, blank=True, related_name='transfers')
