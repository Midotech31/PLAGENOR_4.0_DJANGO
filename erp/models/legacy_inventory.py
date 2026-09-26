from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .common import Record


class LegacyInventoryRecord(Record):
    class Kind(models.TextChoices):
        EQUIPMENT = 'EQUIPMENT', _('Équipement')
        CHEMICAL = 'CHEMICAL', _('Produit chimique')
        CONSUMABLE = 'CONSUMABLE', _('Consommable')
        REAGENT = 'REAGENT', _('Réactif')

    class Resolution(models.TextChoices):
        IMPORTED = 'IMPORTED', _('Importé')
        REUSED = 'REUSED', _('Rattaché à un existant')
        REVIEW = 'REVIEW', _('À vérifier')
        SKIPPED = 'SKIPPED', _('Non importé')

    class ReviewStatus(models.TextChoices):
        OPEN = 'OPEN', _('À traiter')
        CONFIRMED = 'CONFIRMED', _('Source vérifiée / donnée confirmée')
        CORRECTED = 'CORRECTED', _('Correction reportée dans PLAGENOR')
        NOT_APPLICABLE = 'NOT_APPLICABLE', _('Non applicable / ne pas importer')

    source_key = models.CharField(_('Clé source'), max_length=180, unique=True)
    source_file = models.CharField(_('Fichier source'), max_length=255)
    source_section = models.CharField(_('Feuille / section source'), max_length=120, blank=True)
    source_row = models.CharField(_('Ligne source'), max_length=64, blank=True)
    kind = models.CharField(_('Nature'), max_length=16, choices=Kind.choices)
    fingerprint = models.CharField(_('Empreinte des données source'), max_length=64)
    raw_data = models.JSONField(_('Données source originales'), default=dict)
    resolution = models.CharField(_('Résolution'), max_length=12, choices=Resolution.choices)
    entity_type = models.CharField(_('Type d’objet PLAGENOR'), max_length=64, blank=True)
    entity_id = models.UUIDField(_('Objet PLAGENOR'), null=True, blank=True)
    note = models.TextField(_('Observation de migration'), blank=True)
    review_status = models.CharField(
        _('État de la revue humaine'), max_length=16, choices=ReviewStatus.choices,
        default=ReviewStatus.OPEN,
    )
    review_note = models.TextField(_('Conclusion de la revue humaine'), blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='+', verbose_name=_('Revu par'),
    )
    reviewed_at = models.DateTimeField(_('Date de revue'), null=True, blank=True)

    class Meta:
        ordering = ['source_file', 'source_section', 'source_row', 'source_key']
        indexes = [
            models.Index(fields=['kind', 'resolution']),
            models.Index(fields=['entity_type', 'entity_id']),
            models.Index(fields=['resolution', 'review_status'], name='erp_legacyi_resolut_ef54f1_idx'),
        ]
