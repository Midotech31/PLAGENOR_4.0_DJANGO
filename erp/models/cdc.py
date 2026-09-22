from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import ImmutableRecord, Record


class CdcDossier(Record):
    class Family(models.TextChoices):
        REAGENTS = 'reagents', _('Réactifs et consommables')
        EQUIPMENT = 'equipment', _('Équipements scientifiques')
        WORKS = 'works', _('Aménagement et travaux')

    work = models.OneToOneField('erp.WorkItem', on_delete=models.PROTECT, related_name='cdc')
    family = models.CharField(_('Famille documentaire'), max_length=12, choices=Family.choices)
    reference = models.CharField(_('Référence du dossier'), max_length=90, unique=True)
    data = models.JSONField(default=dict, editable=False)
    revision_number = models.PositiveIntegerField(default=0, editable=False)

    def __str__(self):
        return self.reference


class CdcLot(Record):
    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='lots')
    position = models.PositiveSmallIntegerField()
    name = models.CharField(_('Intitulé du lot en français'), max_length=180)
    name_ar = models.CharField(_('Intitulé du lot en arabe'), max_length=240, blank=True)
    source_slot = models.PositiveSmallIntegerField(editable=False)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['dossier', 'position'], name='erp_cdc_lot_position')]

    def __str__(self):
        return self.name


class CdcItem(Record):
    lot = models.ForeignKey(CdcLot, on_delete=models.PROTECT, related_name='items')
    source_key = models.CharField(max_length=48, editable=False)
    position = models.PositiveSmallIntegerField()
    active = models.BooleanField(_('Retenir cet article'), default=True)
    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT, null=True, blank=True,
        related_name='cdc_items', verbose_name=_('Article du référentiel commun'))
    article_snapshot = models.JSONField(default=dict, blank=True, editable=False)
    designation = models.TextField(_('Désignation'))
    specifications = models.TextField(_('Spécifications techniques'), blank=True)
    unit_label = models.CharField(_('Unité documentaire'), max_length=100)
    purchase_unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_('Unité d’achat structurée'))
    base_factor = models.DecimalField(max_digits=24, decimal_places=9, null=True, blank=True, editable=False)
    packaging = models.TextField(_('Conditionnement'), blank=True)
    quantity = models.DecimalField(_('Quantité prévue'), max_digits=18, decimal_places=6, validators=[MinValueValidator(Decimal('0.000001'))])
    details = models.TextField(_('Précisions complémentaires'), blank=True)
    estimated_price = models.DecimalField(_('Prix unitaire estimé hors taxes'), max_digits=18, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(0)])
    tax_rate = models.DecimalField(_('Taux de taxe (%)'), max_digits=5, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    price_source = models.CharField(_('Source de l’estimation'), max_length=500, blank=True)
    currency = models.CharField(_('Devise'), max_length=3, default='DZD')

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['lot', 'source_key'], name='erp_cdc_item_source'),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='erp_cdc_item_quantity'),
            models.CheckConstraint(condition=Q(estimated_price__isnull=True) | Q(estimated_price__gte=0), name='erp_cdc_estimate_nonnegative'),
            models.CheckConstraint(condition=Q(tax_rate__isnull=True) | Q(tax_rate__gte=0, tax_rate__lte=100), name='erp_cdc_tax_range')]


class CdcRevision(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='revisions')
    number = models.PositiveIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    data = models.JSONField()
    estimates = models.JSONField(default=list)
    sha256 = models.CharField(max_length=64)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['dossier', 'number'], name='erp_cdc_revision_number')]


class CdcGeneration(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(CdcRevision, on_delete=models.PROTECT, related_name='generations')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    docx = models.BinaryField(editable=False)
    pdf = models.BinaryField(editable=False)
    docx_sha256 = models.CharField(max_length=64)
    pdf_sha256 = models.CharField(max_length=64)
    pages = models.PositiveIntegerField()
    checks = models.JSONField(default=dict)


class CdcApproval(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.OneToOneField(CdcDossier, on_delete=models.PROTECT, related_name='approval')
    generation = models.OneToOneField(CdcGeneration, on_delete=models.PROTECT, related_name='approval')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    statement = models.CharField(_('Justification de validation'), max_length=500)
    reviewed_pages = models.PositiveIntegerField()
