from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .common import ImmutableRecord, Record


class WorkItem(Record):
    class Kind(models.TextChoices):
        INVENTORY = 'INVENTORY', _('Inventaire physique')
        CDC = 'CDC', _('Cahier des charges')
        RECEIPT = 'RECEIPT', _('Contrôle de réception')
        TEMPERATURE = 'TEMPERATURE', _('Relevé de température')
        PLAN = 'PLAN', _('Plan d’approvisionnement')
        CONTROL = 'CONTROL', _('Contrôle opérationnel')
        ANALYSIS = 'ANALYSIS', _('Activité analytique')
        MAINTENANCE = 'MAINTENANCE', _('Maintenance')
        QUALITY = 'QUALITY', _('Contrôle qualité')
        TRAINING = 'TRAINING', _('Formation')
        MEETING = 'MEETING', _('Réunion')
        OTHER = 'OTHER', _('Autre activité')

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Brouillon')
        ASSIGNED = 'ASSIGNED', _('Affecté')
        IN_PROGRESS = 'IN_PROGRESS', _('En cours')
        SUBMITTED = 'SUBMITTED', _('Soumis à validation')
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', _('Corrections demandées')
        APPROVED = 'APPROVED', _('Validé')
        CANCELLED = 'CANCELLED', _('Annulé')

    class Priority(models.TextChoices):
        LOW = 'LOW', _('Faible')
        NORMAL = 'NORMAL', _('Normale')
        HIGH = 'HIGH', _('Haute')
        URGENT = 'URGENT', _('Urgente')

    kind = models.CharField(_('Type de tâche'), max_length=16, choices=Kind.choices)
    title = models.CharField(_('Intitulé'), max_length=255)
    instructions = models.TextField(_('Consignes'), blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('Membre responsable'),
        on_delete=models.PROTECT, null=True, blank=True, related_name='erp_work_items')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    due_on = models.DateField(_('Échéance'), null=True, blank=True)
    priority = models.CharField(_('Priorité'), max_length=8, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(_('Statut'), max_length=20, choices=Status.choices, default=Status.DRAFT)
    location = models.ForeignKey('erp.Location', verbose_name=_('Périmètre de stockage'),
        on_delete=models.PROTECT, null=True, blank=True)
    category = models.ForeignKey('erp.Category', verbose_name=_('Catégorie'),
        on_delete=models.PROTECT, null=True, blank=True)
    allow_costs = models.BooleanField(_('Autoriser les estimations de ce dossier'), default=False)
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, editable=False, related_name='+')
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ['due_on', '-created_at', 'id']
        indexes = [models.Index(fields=['assignee', 'status', 'due_on'])]

    def __str__(self):
        return self.title


class WorkComment(ImmutableRecord):
    work = models.ForeignKey(WorkItem, on_delete=models.PROTECT, related_name='comments')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField(_('Compte rendu / justification'))

    class Meta:
        ordering = ['id']
