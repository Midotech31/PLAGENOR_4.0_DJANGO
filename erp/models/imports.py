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
