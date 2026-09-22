import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .common import CodedRecord,ImmutableRecord,Record


class ResourceDocument(ImmutableRecord):
    class Kind(models.TextChoices):
        SDS='SDS',_('Fiche de données de sécurité')
        CERTIFICATE='CERTIFICATE',_('Certificat / contrôle')
        PROTOCOL='PROTOCOL',_('Protocole / SOP')
        EVIDENCE='EVIDENCE',_('Justificatif / preuve')
        OTHER='OTHER',_('Autre document')
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    article=models.ForeignKey('erp.Article',on_delete=models.PROTECT,null=True,blank=True,related_name='resource_documents')
    receipt=models.ForeignKey('erp.StockReceipt',on_delete=models.PROTECT,null=True,blank=True,related_name='resource_documents')
    work=models.ForeignKey('erp.WorkItem',on_delete=models.PROTECT,null=True,blank=True,related_name='resource_documents')
    sample=models.ForeignKey('erp.BiologicalSample',on_delete=models.PROTECT,null=True,blank=True,related_name='resource_documents')
    order=models.ForeignKey('erp.PurchaseOrder',on_delete=models.PROTECT,null=True,blank=True,related_name='resource_documents')
    kind=models.CharField(_('Type de document'),max_length=12,choices=Kind.choices)
    title=models.CharField(_('Intitulé du document'),max_length=200)
    financial=models.BooleanField(_('Contient des informations financières restreintes'),default=False)
    original_name=models.CharField(max_length=180)
    extension=models.CharField(max_length=6)
    content=models.BinaryField(editable=False)
    sha256=models.CharField(max_length=64,editable=False)
    size=models.PositiveIntegerField(editable=False)
    documented_on=models.DateField(_('Date du document'),null=True,blank=True)
    source=models.CharField(_('Origine / référence documentaire'),max_length=500)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    supersedes=models.OneToOneField('self',on_delete=models.PROTECT,null=True,blank=True,related_name='replacement')

    class Meta:
        ordering=['-created_at']
        constraints=[models.CheckConstraint(condition=(
            Q(article__isnull=False,receipt__isnull=True,work__isnull=True,sample__isnull=True,order__isnull=True)|
            Q(article__isnull=True,receipt__isnull=False,work__isnull=True,sample__isnull=True,order__isnull=True)|
            Q(article__isnull=True,receipt__isnull=True,work__isnull=False,sample__isnull=True,order__isnull=True)|
            Q(article__isnull=True,receipt__isnull=True,work__isnull=True,sample__isnull=False,order__isnull=True)|
            Q(article__isnull=True,receipt__isnull=True,work__isnull=True,sample__isnull=True,order__isnull=False)),name='erp_resource_document_target')]


class HazardTag(CodedRecord):
    ghs_code=models.CharField(_('Pictogramme indiqué sur la FDS'),max_length=5,blank=True,
        choices=[('','—')]+[('GHS%02d'%number,'GHS%02d'%number) for number in range(1,10)])
    description=models.TextField(_('Description documentée'),blank=True)


class ChemicalProfile(Record):
    article=models.OneToOneField('erp.Article',on_delete=models.PROTECT,related_name='chemical_profile')
    tags=models.ManyToManyField(HazardTag,blank=True,related_name='chemical_profiles')
    classification=models.TextField(_('Classification et mentions relevées dans la FDS'))
    signal_word=models.CharField(_('Mention d’avertissement documentée'),max_length=8,blank=True,
        choices=[('','—'),('DANGER',_('Danger')),('WARNING',_('Attention'))])
    handling=models.TextField(_('Précautions et restrictions documentées'),blank=True)
    source_reference=models.CharField(_('FDS / source officielle et version'),max_length=500)
    source_document=models.ForeignKey(ResourceDocument,on_delete=models.PROTECT,null=True,blank=True,related_name='chemical_profiles')
    reviewed_on=models.DateField(_('Date de vérification de la source'))
    reviewed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)


class StorageSafetyRule(Record):
    class Mode(models.TextChoices):
        PROHIBITED='PROHIBITED',_('Danger interdit dans cet emplacement')
        INCOMPATIBLE='INCOMPATIBLE',_('Deux groupes ne peuvent pas être stockés ensemble')
    location=models.ForeignKey('erp.Location',on_delete=models.PROTECT,related_name='safety_rules')
    mode=models.CharField(_('Type de règle'),max_length=16,choices=Mode.choices)
    first_tag=models.ForeignKey(HazardTag,on_delete=models.PROTECT,related_name='+',verbose_name=_('Premier groupe de danger'))
    second_tag=models.ForeignKey(HazardTag,on_delete=models.PROTECT,null=True,blank=True,related_name='+',verbose_name=_('Groupe incompatible'))
    blocking=models.BooleanField(_('Bloquer une réception ou un transfert incompatible'),default=True)
    active=models.BooleanField(_('Règle active'),default=True)
    reference=models.CharField(_('Justification / source de la règle'),max_length=500)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)

    class Meta:
        constraints=[models.CheckConstraint(condition=Q(mode='PROHIBITED',second_tag__isnull=True)|Q(mode='INCOMPATIBLE',second_tag__isnull=False),name='erp_storage_rule_pair')]
