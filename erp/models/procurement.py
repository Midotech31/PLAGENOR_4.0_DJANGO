from decimal import Decimal
import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from .common import ImmutableRecord, Record


MAX_Q = Decimal('999999999999.999999')
MAX_PRICE = Decimal('9999999999999999.99')
MAX_FACTOR = Decimal('999999999999999.999999999')


class ProcurementPlan(Record):
    work = models.OneToOneField('erp.WorkItem', on_delete=models.PROTECT, related_name='procurement_plan')
    reference = models.CharField(_('Référence du plan'), max_length=90, unique=True)
    year = models.PositiveSmallIntegerField(_('Année du plan'))
    starts_on = models.DateField(_('Début de la période'))
    ends_on = models.DateField(_('Fin de la période'))
    revision_number = models.PositiveIntegerField(default=0, editable=False)
    approved_revision = models.OneToOneField('erp.ProcurementRevision', on_delete=models.PROTECT,
        null=True, blank=True, editable=False, related_name='approved_plan')
    cdc = models.OneToOneField('erp.CdcDossier', on_delete=models.PROTECT, null=True, blank=True,
        editable=False, related_name='procurement_plan')

    class Meta:
        ordering = ['-year','reference']
        constraints = [models.CheckConstraint(condition=Q(ends_on__gte=F('starts_on')),name='erp_procurement_plan_period')]

    def __str__(self):
        return self.reference


class ForecastObservation(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(ProcurementPlan, on_delete=models.PROTECT, related_name='forecasts')
    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT, related_name='forecasts')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    as_of = models.DateField()
    input_data = models.JSONField()
    result = models.JSONField()
    sha256 = models.CharField(max_length=64)


class ProcurementLine(Record):
    plan = models.ForeignKey(ProcurementPlan, on_delete=models.PROTECT, related_name='lines')
    article = models.ForeignKey('erp.Article', on_delete=models.PROTECT, verbose_name=_('Article du catalogue commun'))
    forecast = models.ForeignKey(ForecastObservation, on_delete=models.PROTECT, null=True, blank=True, editable=False)
    article_snapshot = models.JSONField(default=dict, editable=False)
    purchase_unit = models.ForeignKey('erp.Unit', on_delete=models.PROTECT)
    purchase_factor = models.DecimalField(max_digits=24,decimal_places=9,editable=False)
    proposed_quantity = models.DecimalField(max_digits=18,decimal_places=6,null=True,blank=True,editable=False)
    retained_quantity = models.DecimalField(_('Quantité retenue en unité d’achat'),max_digits=18,decimal_places=6,null=True,blank=True)
    included = models.BooleanField(_('Retenir cet article'),default=True)
    lot_name = models.CharField(_('Lot d’achat'),max_length=180)
    priority = models.CharField(_('Priorité'),max_length=10,choices=[('CRITICAL',_('Critique')),('HIGH',_('Haute')),('MEDIUM',_('Moyenne')),('LOW',_('Faible'))])
    estimated_price = models.DecimalField(_('Prix unitaire estimé hors taxes'),max_digits=18,decimal_places=2,null=True,blank=True)
    tax_rate = models.DecimalField(_('Taux de taxe (%)'),max_digits=5,decimal_places=2,null=True,blank=True)
    currency = models.CharField(_('Devise'),max_length=3,default='DZD')
    supplier = models.ForeignKey('erp.Party',on_delete=models.PROTECT,null=True,blank=True)
    price_source = models.CharField(_('Source du prix'),max_length=500,blank=True)
    decision_reason = models.CharField(_('Justification de la décision'),max_length=500,blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,editable=False)
    reviewed_at = models.DateTimeField(null=True,blank=True,editable=False)

    class Meta:
        ordering=['lot_name','article__code']
        constraints=[models.UniqueConstraint(fields=['plan','article'],name='erp_plan_unique_article'),
            models.CheckConstraint(condition=Q(retained_quantity__isnull=True)|Q(retained_quantity__gte=0,retained_quantity__lte=MAX_Q),name='erp_plan_retained_quantity'),
            models.CheckConstraint(condition=Q(tax_rate__isnull=True)|Q(tax_rate__gte=0,tax_rate__lte=100),name='erp_plan_tax_rate'),
            models.CheckConstraint(condition=Q(estimated_price__isnull=True)|Q(estimated_price__gte=0,estimated_price__lte=MAX_PRICE),name='erp_plan_estimated_price'),
            models.CheckConstraint(condition=Q(proposed_quantity__isnull=True)|Q(proposed_quantity__gte=0,proposed_quantity__lte=MAX_Q),name='erp_plan_proposed_quantity'),
            models.CheckConstraint(condition=Q(purchase_factor__gt=0,purchase_factor__lte=MAX_FACTOR),name='erp_plan_purchase_factor')]


class ProcurementRequirementLink(ImmutableRecord):
    """Immutable trace between a real analytical shortage and procurement."""
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    line=models.ForeignKey(ProcurementLine,on_delete=models.PROTECT,related_name='requirement_links')
    requirement=models.ForeignKey('erp.RunRequirement',on_delete=models.PROTECT,related_name='procurement_links')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    shortage_quantity=models.DecimalField(max_digits=18,decimal_places=6)
    purchase_quantity=models.DecimalField(max_digits=18,decimal_places=6)
    reason=models.CharField(max_length=500)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['line','requirement'],name='erp_plan_requirement_unique'),
            models.CheckConstraint(condition=Q(shortage_quantity__gt=0,shortage_quantity__lte=MAX_Q),name='erp_plan_requirement_shortage'),
            models.CheckConstraint(condition=Q(purchase_quantity__gt=0,purchase_quantity__lte=MAX_Q),name='erp_plan_requirement_purchase')]


class ProcurementRevision(ImmutableRecord):
    id = models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    plan=models.ForeignKey(ProcurementPlan,on_delete=models.PROTECT,related_name='revisions')
    number=models.PositiveIntegerField()
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    data=models.JSONField()
    sha256=models.CharField(max_length=64)
    reason=models.CharField(max_length=500,blank=True)

    class Meta:
        ordering=['-number']
        constraints=[models.UniqueConstraint(fields=['plan','number'],name='erp_plan_revision_number')]


class PurchaseOrder(Record):
    class Status(models.TextChoices):
        DRAFT='DRAFT',_('Brouillon')
        CONFIRMED='CONFIRMED',_('Commande confirmée')
        PARTIAL='PARTIAL',_('Réception partielle')
        RECEIVED='RECEIVED',_('Réception complète')
        CANCELLED='CANCELLED',_('Solde annulé')
    plan=models.ForeignKey(ProcurementPlan,on_delete=models.PROTECT,related_name='orders')
    reference=models.CharField(_('Référence commande / marché'),max_length=120,unique=True)
    supplier=models.ForeignKey('erp.Party',on_delete=models.PROTECT,verbose_name=_('Fournisseur'))
    ordered_on=models.DateField(_('Date de commande'))
    expected_on=models.DateField(_('Livraison confirmée pour le'))
    status=models.CharField(max_length=12,choices=Status.choices,default=Status.DRAFT)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,related_name='+')
    confirmed_by=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True,blank=True,related_name='+')
    confirmed_at=models.DateTimeField(null=True,blank=True)
    notes=models.TextField(_('Observations'),blank=True)

    class Meta:
        ordering=['-ordered_on','reference']
        constraints=[models.CheckConstraint(condition=Q(expected_on__gte=F('ordered_on')),name='erp_order_delivery_dates')]

    def __str__(self):
        return self.reference


class PurchaseOrderLine(Record):
    order=models.ForeignKey(PurchaseOrder,on_delete=models.PROTECT,related_name='lines')
    plan_line=models.ForeignKey(ProcurementLine,on_delete=models.PROTECT,related_name='orders')
    article_snapshot=models.JSONField(default=dict,editable=False)
    unit=models.ForeignKey('erp.Unit',on_delete=models.PROTECT)
    factor=models.DecimalField(max_digits=24,decimal_places=9,editable=False)
    quantity=models.DecimalField(_('Quantité commandée'),max_digits=18,decimal_places=6)
    unit_price=models.DecimalField(_('Prix unitaire commandé HT'),max_digits=18,decimal_places=2)
    tax_rate=models.DecimalField(_('Taux de taxe (%)'),max_digits=5,decimal_places=2)
    currency=models.CharField(max_length=3,default='DZD')
    variance_reason=models.CharField(_('Justification de l’écart au plan'),max_length=500,blank=True)

    class Meta:
        constraints=[models.UniqueConstraint(fields=['order','plan_line'],name='erp_order_plan_line_unique'),
            models.CheckConstraint(condition=Q(quantity__gt=0,quantity__lte=MAX_Q),name='erp_order_positive_quantity'),
            models.CheckConstraint(condition=Q(unit_price__gte=0,unit_price__lte=MAX_PRICE),name='erp_order_nonnegative_price'),
            models.CheckConstraint(condition=Q(tax_rate__gte=0,tax_rate__lte=100),name='erp_order_tax_rate'),
            models.CheckConstraint(condition=Q(factor__gt=0,factor__lte=MAX_FACTOR),name='erp_order_factor')]


class PurchaseReceiptLink(ImmutableRecord):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    line=models.ForeignKey(PurchaseOrderLine,on_delete=models.PROTECT,related_name='deliveries')
    receipt=models.OneToOneField('erp.StockReceipt',on_delete=models.PROTECT,related_name='purchase_delivery')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    purchase_quantity=models.DecimalField(max_digits=18,decimal_places=6)
    actual_unit_price=models.DecimalField(max_digits=18,decimal_places=2)
    expected_delivery_snapshot=models.DateField()
    variance_reason=models.CharField(max_length=500,blank=True)


    class Meta:
        constraints=[models.CheckConstraint(condition=Q(purchase_quantity__gt=0,purchase_quantity__lte=MAX_Q),name='erp_purchase_receipt_quantity'),
            models.CheckConstraint(condition=Q(actual_unit_price__gte=0,actual_unit_price__lte=MAX_PRICE),name='erp_purchase_receipt_price')]


class ProcurementCdcItemLink(ImmutableRecord):
    """Immutable trace from a structured CDC need to the canonical procurement line."""
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    line=models.ForeignKey(ProcurementLine,on_delete=models.PROTECT,related_name='cdc_item_links')
    item=models.ForeignKey('erp.CdcItem',on_delete=models.PROTECT,related_name='procurement_links')
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    required_quantity=models.DecimalField(max_digits=18,decimal_places=6)
    stock_covered_quantity=models.DecimalField(max_digits=18,decimal_places=6,default=0)
    shortage_quantity=models.DecimalField(max_digits=18,decimal_places=6)
    reason=models.CharField(max_length=500)

    class Meta:
        constraints=[
            models.UniqueConstraint(fields=['line','item'],name='erp_plan_cdc_item_unique'),
            models.CheckConstraint(condition=Q(required_quantity__gt=0,required_quantity__lte=MAX_Q),name='erp_plan_cdc_required'),
            models.CheckConstraint(condition=Q(stock_covered_quantity__gte=0,stock_covered_quantity__lte=MAX_Q),name='erp_plan_cdc_covered'),
            models.CheckConstraint(condition=Q(shortage_quantity__gt=0,shortage_quantity__lte=MAX_Q),name='erp_plan_cdc_shortage'),
            models.CheckConstraint(condition=Q(required_quantity=F('stock_covered_quantity')+F('shortage_quantity')),name='erp_plan_cdc_balance'),
        ]
