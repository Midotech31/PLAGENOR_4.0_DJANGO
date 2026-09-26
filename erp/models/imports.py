from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .common import Record


class ImportBatch(Record):
    class Kind(models.TextChoices):
        CATALOG='CATALOG',_('Catalogue des articles')
        INITIAL='INITIAL',_('Stock physique initial')
        RECEIPTS='RECEIPTS',_('Réceptions de stock')
        LOCATIONS='LOCATIONS',_('Emplacements')
        SAMPLES='SAMPLES',_('Échantillons')
        PRICES='PRICES',_('Observations de prix')
        PLAN='PLAN',_('Articles d’un plan annuel')
        TEMPERATURE='TEMPERATURE',_('Relevés de température')
    class Status(models.TextChoices):
        PREVIEW='PREVIEW',_('Aperçu à examiner')
        APPLIED='APPLIED',_('Import appliqué')
        CANCELLED='CANCELLED',_('Import abandonné')
    creation_key=models.UUIDField(unique=True,editable=False)
    creation_hash=models.CharField(max_length=64,editable=False)
    kind=models.CharField(_('Domaine d’import'),max_length=16,choices=Kind.choices)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='erp_imports')
    plan=models.ForeignKey('erp.ProcurementPlan',on_delete=models.PROTECT,null=True,blank=True,related_name='imports')
    filename=models.CharField(max_length=180)
    sha256=models.CharField(max_length=64)
    payload=models.JSONField(default=list)
    baselines=models.JSONField(default=list)
    report=models.JSONField(default=dict)
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.PREVIEW)
    expires_at=models.DateTimeField()
    applied_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    applied_at=models.DateTimeField(null=True,blank=True)
    reason=models.CharField(_('Justification de l’import'),max_length=500)

    class Meta:
        ordering=['-created_at']
        indexes=[models.Index(fields=['actor','status','created_at'])]


class InventorySourceRecord(Record):
    class Domain(models.TextChoices):
        EQUIPMENT='EQUIPMENT',_('Équipement')
        CHEMICAL='CHEMICAL',_('Produit chimique')
        CONSUMABLE='CONSUMABLE',_('Consommable')
        REAGENT='REAGENT',_('Réactif')

    class Status(models.TextChoices):
        IMPORTED='IMPORTED',_('Importé')
        ENRICHED='ENRICHED',_('Enrichi')
        NEEDS_REVIEW='NEEDS_REVIEW',_('À vérifier')
        SKIPPED_DUPLICATE='SKIPPED_DUPLICATE',_('Doublon source conservé')

    source_kind=models.CharField(max_length=16,choices=[('WORKBOOK',_('Classeur inventaire')),('ROOM_LIST',_('Fiche de salle'))])
    domain=models.CharField(max_length=16,choices=Domain.choices)
    source_file=models.CharField(max_length=255)
    source_sha256=models.CharField(max_length=64)
    source_sheet=models.CharField(max_length=180,blank=True)
    source_row=models.PositiveIntegerField()
    identity_key=models.CharField(max_length=64,db_index=True)
    raw_data=models.JSONField(default=dict)
    normalized_data=models.JSONField(default=dict)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.NEEDS_REVIEW)
    target_model=models.CharField(max_length=64,blank=True)
    target_id=models.UUIDField(null=True,blank=True)
    notes=models.TextField(blank=True)

    class Meta:
        ordering=['source_file','source_sheet','source_row','id']
        constraints=[
            models.UniqueConstraint(
                fields=['source_sha256','source_file','source_sheet','source_row','domain'],
                name='erp_inventory_source_identity',
            )
        ]
        indexes=[
            models.Index(fields=['domain','status']),
            models.Index(fields=['target_model','target_id']),
        ]
