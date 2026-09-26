from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, Record


class PlanningResource(CodedRecord):
    class Kind(models.TextChoices):
        EQUIPMENT = 'EQUIPMENT', _('Équipement')
        ROOM = 'ROOM', _('Salle')
        OTHER = 'OTHER', _('Autre ressource')

    kind = models.CharField(_('Type de ressource'), max_length=12, choices=Kind.choices)
    location = models.ForeignKey('erp.Location', on_delete=models.PROTECT, null=True, blank=True)
    serial_number = models.CharField(_('Numéro de série'), max_length=120, blank=True)
    model_name = models.CharField(_('Modèle'), max_length=255, blank=True)
    manufacturer_reference = models.CharField(_('Référence fabricant'), max_length=120, blank=True)
    inventory_status = models.CharField(
        _('État inventaire'), max_length=18,
        choices=[
            ('UNVERIFIED', _('À vérifier')),
            ('IN_SERVICE', _('En service')),
            ('MAINTENANCE', _('Maintenance')),
            ('OUT_OF_SERVICE', _('Hors service')),
            ('DECOMMISSIONED', _('Réformé')),
        ],
        default='IN_SERVICE',
    )
    source_snapshot = models.JSONField(default=dict, editable=False)
    instructions = models.TextField(_('Consignes de réservation'), blank=True)

    class Meta(CodedRecord.Meta):
        constraints = [models.UniqueConstraint(fields=['location'], condition=Q(kind='ROOM', location__isnull=False),
            name='erp_one_planning_room')]


class ActivitySchedule(Record):
    work = models.OneToOneField('erp.WorkItem', on_delete=models.PROTECT, related_name='schedule')
    starts_at = models.DateTimeField(_('Début prévu'))
    ends_at = models.DateTimeField(_('Fin prévue'))
    resources = models.ManyToManyField(PlanningResource, blank=True, related_name='schedules')
    request = models.ForeignKey('core.Request', on_delete=models.PROTECT, null=True, blank=True, related_name='planned_activities')
    run = models.OneToOneField('erp.AnalysisRun', on_delete=models.PROTECT, null=True, blank=True, related_name='schedule')
    resource_check_note = models.TextField(_('Vérification des ressources'), blank=True)
    resources_checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    resources_checked_at = models.DateTimeField(null=True, blank=True)
    creation_key = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    creation_hash = models.CharField(max_length=64, blank=True, editable=False)
    actual_started_at = models.DateTimeField(null=True, blank=True, editable=False)
    actual_finished_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['starts_at', 'work__title']
        indexes = [models.Index(fields=['starts_at', 'ends_at'])]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F('starts_at')), name='erp_activity_positive_interval')]


class ActivityDependency(Record):
    work = models.ForeignKey('erp.WorkItem', on_delete=models.PROTECT, related_name='prerequisites')
    prerequisite = models.ForeignKey('erp.WorkItem', on_delete=models.PROTECT, related_name='successors')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['work', 'prerequisite'], name='erp_unique_activity_dependency'),
            models.CheckConstraint(condition=~Q(work=F('prerequisite')), name='erp_dependency_not_self')]


class AvailabilityBlock(Record):
    resource = models.ForeignKey(PlanningResource, on_delete=models.PROTECT, null=True, blank=True, related_name='unavailability')
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='planning_unavailability')
    starts_at = models.DateTimeField(_('Début d’indisponibilité'))
    ends_at = models.DateTimeField(_('Fin d’indisponibilité'))
    reason = models.CharField(_('Motif'), max_length=500)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        ordering = ['starts_at']
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F('starts_at')), name='erp_unavailability_interval'),
            models.CheckConstraint(condition=(Q(resource__isnull=False, member__isnull=True) |
                Q(resource__isnull=True, member__isnull=False)), name='erp_unavailability_one_target')]
        indexes = [models.Index(fields=['starts_at', 'ends_at', 'active'])]
