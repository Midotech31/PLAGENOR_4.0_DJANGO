from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, ImmutableRecord, Record


class ConsumptionProfile(CodedRecord):
    service = models.ForeignKey('core.Service', on_delete=models.PROTECT, related_name='consumption_profiles')
    reference_samples = models.PositiveIntegerField(_('Nombre d’échantillons de référence'), default=1)
    protocol_reference = models.CharField(_('Protocole / SOP'), max_length=255)
    notes = models.TextField(_('Précisions opérationnelles'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [models.CheckConstraint(condition=Q(reference_samples__gt=0), name='erp_recipe_reference_samples')]


class ConsumptionRule(Record):
    class Basis(models.TextChoices):
        PROPORTIONAL = 'PROPORTIONAL', _('Proportionnel au nombre d’échantillons')
        BATCH = 'BATCH', _('Par série complète ou partielle')

    profile = models.ForeignKey(ConsumptionProfile, on_delete=models.PROTECT, related_name='rules')
    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT, related_name='consumption_rules')
    quantity = models.DecimalField(_('Quantité standard'), max_digits=18, decimal_places=6)
    unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT)
    basis = models.CharField(_('Mode de calcul'), max_length=16, choices=Basis.choices)

    class Meta:
        ordering = ['article__code', 'basis']
        constraints = [models.UniqueConstraint(fields=['profile', 'article', 'basis'], name='erp_recipe_article_basis'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='erp_recipe_quantity')]


class AnalysisRun(CodedRecord):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', _('Planifié')
        RESERVED = 'RESERVED', _('Stock réservé')
        COMPLETED = 'COMPLETED', _('Consommations confirmées')
        CANCELLED = 'CANCELLED', _('Annulé')

    request = models.ForeignKey('core.Request', on_delete=models.PROTECT, related_name='erp_runs')
    profile = models.ForeignKey(ConsumptionProfile, on_delete=models.PROTECT)
    profile_snapshot = models.JSONField(default=dict, editable=False)
    sample_count = models.PositiveIntegerField(_('Nombre d’échantillons'))
    planned_on = models.DateField(_('Date prévue'))
    incremental_demand = models.BooleanField(_('Activité supplémentaire non comprise dans le rythme habituel'), default=False)
    committed = models.BooleanField(_('Activité prévue confirmée par l’administration'), default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta(CodedRecord.Meta):
        indexes = [models.Index(fields=['planned_on', 'status']), models.Index(fields=['request', 'status'])]
        constraints = [models.CheckConstraint(condition=Q(sample_count__gt=0), name='erp_run_sample_count')]


class RunRequirement(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AnalysisRun, on_delete=models.PROTECT, related_name='requirements')
    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT)
    article_snapshot = models.JSONField(default=dict)
    calculation = models.JSONField(default=list)

    class Meta:
        ordering = ['article__code']
        constraints = [models.UniqueConstraint(fields=['run', 'article'], name='erp_run_article_requirement'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='erp_run_requirement_positive')]


class RunInput(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AnalysisRun, on_delete=models.PROTECT, related_name='inputs')
    sample = models.ForeignKey('erp.BiologicalSample', on_delete=models.PROTECT, null=True, blank=True, related_name='analysis_inputs')
    source_key = models.CharField(max_length=100)
    source_fingerprint = models.CharField(max_length=64, blank=True)
    label = models.CharField(max_length=180)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run', 'source_key'], name='erp_run_source_unique'),
            models.UniqueConstraint(fields=['run', 'sample'], condition=Q(sample__isnull=False), name='erp_run_sample_unique')]


class RunOperation(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key = models.UUIDField(unique=True)
    run = models.ForeignKey(AnalysisRun, on_delete=models.PROTECT, related_name='operations')
    kind = models.CharField(max_length=12, choices=[('RESERVE', _('Réserver')), ('CONFIRM', _('Confirmer les consommations')),
        ('CANCEL', _('Annuler')), ('COMMIT', _('Confirmer l’activité prévue'))])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payload_hash = models.CharField(max_length=64)
    data = models.JSONField(default=dict)


class RunAllocation(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requirement = models.ForeignKey(RunRequirement, on_delete=models.PROTECT, related_name='allocations')
    reservation = models.OneToOneField('erp.StockReservation', on_delete=models.PROTECT, related_name='run_allocation')
    operation = models.ForeignKey(RunOperation, on_delete=models.PROTECT, related_name='allocations')
    quantity = models.DecimalField(max_digits=18, decimal_places=6)


class RunConsumption(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AnalysisRun, on_delete=models.PROTECT, related_name='consumptions')
    requirement = models.ForeignKey(RunRequirement, on_delete=models.PROTECT, related_name='consumptions')
    container = models.ForeignKey('erp.StockContainer', on_delete=models.PROTECT, related_name='analytical_consumptions')
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    movement = models.OneToOneField('erp.StockMovement', on_delete=models.PROTECT, related_name='analytical_consumption')
    operation = models.ForeignKey(RunOperation, on_delete=models.PROTECT, related_name='consumptions')


class RunBiologyEvent(ImmutableRecord):
    input = models.OneToOneField(RunInput, on_delete=models.PROTECT, related_name='biology_event')
    event = models.OneToOneField('erp.SampleEvent', on_delete=models.PROTECT, related_name='run_link')
    operation = models.ForeignKey(RunOperation, on_delete=models.PROTECT)
