from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord, ImmutableRecord, Record


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
    archived_at = models.DateTimeField(null=True, blank=True, editable=False)
    archived_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        editable=False, related_name='+')
    archive_reason = models.CharField(max_length=500, blank=True, editable=False)

    def __str__(self):
        return self.reference


class CdcLot(Record):
    active = models.BooleanField(_('Lot retenu'), default=True)
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


class CdcWorkbookPreview(Record):
    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='workbook_imports')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    base_version = models.PositiveIntegerField()
    filename = models.CharField(max_length=180)
    payload = models.JSONField()
    import_prices = models.BooleanField(default=False)
    reason = models.CharField(max_length=500)
    expires_at = models.DateTimeField()
    applied_revision = models.ForeignKey(CdcRevision, on_delete=models.PROTECT, null=True, blank=True)



class CdcRequirement(Record):
    class Kind(models.TextChoices):
        MANDATORY = 'MANDATORY', _('Obligatoire')
        MINIMUM = 'MINIMUM', _('Minimum')
        PREFERRED = 'PREFERRED', _('Souhaitable')
        SCORED = 'SCORED', _('Notée')
        INFORMATIONAL = 'INFORMATIONAL', _('Informative')
        ELIMINATORY = 'ELIMINATORY', _('Éliminatoire')

    item = models.ForeignKey(CdcItem, on_delete=models.PROTECT, related_name='requirements')
    position = models.PositiveSmallIntegerField(default=1)
    kind = models.CharField(_('Nature de l’exigence'), max_length=16, choices=Kind.choices)
    statement = models.TextField(_('Exigence'))
    evidence = models.TextField(_('Preuve exigée'), blank=True)
    verification_method = models.TextField(_('Méthode de vérification / réception'), blank=True)
    justification = models.TextField(_('Justification'), blank=True)
    active = models.BooleanField(_('Retenir cette exigence'), default=True)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['item', 'position'], name='erp_cdc_requirement_position')]


class CdcCriterion(Record):
    class Method(models.TextChoices):
        PROPORTIONAL = 'PROPORTIONAL', _('Proportionnelle')
        BINARY = 'BINARY', _('Binaire')
        INVERSE_PRICE = 'INVERSE_PRICE', _('Prix inverse')

    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='criteria')
    lot = models.ForeignKey(CdcLot, on_delete=models.PROTECT, null=True, blank=True, related_name='criteria')
    code = models.CharField(_('Code'), max_length=40)
    title = models.CharField(_('Critère'), max_length=255)
    method = models.CharField(_('Méthode'), max_length=16, choices=Method.choices, default=Method.PROPORTIONAL)
    weight = models.DecimalField(_('Pondération (points)'), max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal('0')), MaxValueValidator(Decimal('100'))])
    threshold = models.DecimalField(_('Seuil éventuel'), max_digits=8, decimal_places=2,
        null=True, blank=True)
    eliminatory = models.BooleanField(_('Critère éliminatoire'), default=False)
    evidence = models.TextField(_('Justificatif / preuve attendue'), blank=True)
    position = models.PositiveSmallIntegerField(default=1)
    active = models.BooleanField(_('Retenir ce critère'), default=True)

    class Meta:
        ordering = ['lot_id', 'position', 'id']
        constraints = [models.UniqueConstraint(fields=['dossier', 'code'], name='erp_cdc_criterion_code'),
            models.CheckConstraint(condition=Q(weight__gte=0, weight__lte=100), name='erp_cdc_criterion_weight')]


class CdcClause(CodedRecord):
    title = models.CharField(_('Intitulé de la clause'), max_length=255)
    active_revision = models.OneToOneField('erp.CdcClauseRevision', on_delete=models.PROTECT,
        null=True, blank=True, related_name='active_for')

    def __str__(self):
        return self.title


class CdcClauseRevision(ImmutableRecord):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', _('Brouillon')
        ACTIVE = 'ACTIVE', _('Validée / active')
        RETIRED = 'RETIRED', _('Retirée')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clause = models.ForeignKey(CdcClause, on_delete=models.PROTECT, related_name='revisions')
    number = models.PositiveIntegerField()
    text_fr = models.TextField(_('Texte français'))
    text_en = models.TextField(_('Texte anglais'), blank=True)
    text_ar = models.TextField(_('Texte arabe'), blank=True)
    source_reference = models.CharField(_('Source / référence'), max_length=500)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sha256 = models.CharField(max_length=64)

    class Meta:
        ordering = ['-number']
        constraints = [models.UniqueConstraint(fields=['clause', 'number'], name='erp_cdc_clause_revision_number')]


class CdcClauseSelection(Record):
    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='clause_selections')
    revision = models.ForeignKey(CdcClauseRevision, on_delete=models.PROTECT, related_name='selections')
    position = models.PositiveSmallIntegerField(default=1)
    mandatory = models.BooleanField(_('Clause obligatoire pour ce dossier'), default=False)
    note = models.CharField(_('Note interne'), max_length=500, blank=True)
    active = models.BooleanField(_('Retenir cette clause'), default=True)

    class Meta:
        ordering = ['position', 'id']
        constraints = [models.UniqueConstraint(fields=['dossier', 'revision'], name='erp_cdc_clause_selection_unique')]


class CdcReviewDecision(ImmutableRecord):
    class Stage(models.TextChoices):
        TECHNICAL = 'TECHNICAL', _('Revue technique')
        ADMIN_LEGAL = 'ADMIN_LEGAL', _('Revue administrative et juridique')
        FINANCIAL = 'FINANCIAL', _('Revue financière')

    class Outcome(models.TextChoices):
        APPROVED = 'APPROVED', _('Approuvée')
        CHANGES = 'CHANGES', _('Corrections demandées')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(CdcDossier, on_delete=models.PROTECT, related_name='review_decisions')
    revision = models.ForeignKey(CdcRevision, on_delete=models.PROTECT, related_name='review_decisions')
    stage = models.CharField(max_length=16, choices=Stage.choices)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    comment = models.CharField(_('Compte rendu'), max_length=1000)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [models.UniqueConstraint(fields=['revision', 'stage'], name='erp_cdc_review_stage_unique')]
