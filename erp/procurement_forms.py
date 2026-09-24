from datetime import date
from decimal import Decimal
import uuid

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import VersionedForm
from .models import Article, CdcDossier, Party, ProcurementLine, PurchaseOrderLine
from .permissions import TEAM_ROLES, Capability, permitted
from .services.work import work_allowed
from .stock_forms import location_choices
from .work_forms import OperationForm, WorkForm


class PlanCreateForm(WorkForm):
    reference=forms.CharField(label=_('Référence du plan'),max_length=90)
    year=forms.IntegerField(label=_('Année du plan'))

    class Meta(WorkForm.Meta):
        fields=['title','assignee','due_on','instructions','location','category','allow_costs']

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        year=timezone.localdate().year
        self.fields['year'].min_value=year
        self.fields['year'].max_value=year+2
        self.fields['year'].initial=year+1


class PlanArticleForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    article=forms.ModelChoiceField(label=_('Article du catalogue commun'),queryset=Article.objects.filter(active=True))
    lot_name=forms.CharField(label=_('Lot d’achat'),max_length=180)

    def __init__(self,*args,plan,**kwargs):
        super().__init__(*args,**kwargs)
        if plan.work.category_id:
            self.fields['article'].queryset=self.fields['article'].queryset.filter(category_id=plan.work.category_id)


class PlanDecisionForm(VersionedForm):
    class Meta:
        model=ProcurementLine
        fields=['retained_quantity','included','lot_name','priority','estimated_price','tax_rate','currency',
            'supplier','price_source','decision_reason']

    def __init__(self,*args,plan,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['expected_version'].initial=plan.version
        self.fields['supplier'].queryset=Party.objects.filter(active=True,is_supplier=True)
        self.fields['decision_reason'].required=True
        if not work_allowed(self.user,plan.work,costs=True):
            for name in ('estimated_price','tax_rate','currency','supplier','price_source'):
                del self.fields[name]


class PlanActionForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reason=forms.CharField(label=_('Justification / compte rendu'),max_length=500,widget=forms.Textarea)


class CdcFromPlanForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reference=forms.RegexField(label=_('Référence du cahier des charges'),regex=r'^[0-9]{1,4}/SME/SDFM/SG/ESSBO/[0-9]{4}$',max_length=90)
    family=forms.ChoiceField(label=_('Famille documentaire'),choices=CdcDossier.Family.choices)
    assignee=forms.ModelChoiceField(label=_('Membre chargé de préparer le cahier des charges'),
        queryset=get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES),required=False)


class OrderCreateForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reference=forms.CharField(label=_('Référence commande / marché'),max_length=120)
    supplier=forms.ModelChoiceField(label=_('Fournisseur'),queryset=Party.objects.filter(active=True,is_supplier=True))
    ordered_on=forms.DateField(label=_('Date de commande'),initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'}))
    expected_on=forms.DateField(label=_('Livraison confirmée pour le'),widget=forms.DateInput(attrs={'type':'date'}))
    notes=forms.CharField(label=_('Observations'),required=False,widget=forms.Textarea)


class OrderLineForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    plan_line=forms.ModelChoiceField(label=_('Article du plan approuvé'),queryset=ProcurementLine.objects.none())
    quantity=forms.DecimalField(label=_('Quantité commandée en unité d’achat'),max_digits=18,decimal_places=6,min_value=Decimal('.000001'))
    unit_price=forms.DecimalField(label=_('Prix unitaire commandé HT'),max_digits=18,decimal_places=2,min_value=0)
    tax_rate=forms.DecimalField(label=_('Taux de taxe (%)'),max_digits=5,decimal_places=2,min_value=0,max_value=100)
    currency=forms.CharField(label=_('Devise'),max_length=3,initial='DZD')
    variance_reason=forms.CharField(label=_('Justification de l’écart au plan'),max_length=500,required=False,widget=forms.Textarea)

    def __init__(self,*args,order,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['plan_line'].queryset=order.plan.lines.filter(included=True).select_related('article','purchase_unit')
        self.fields['plan_line'].label_from_instance=lambda row:row.article_snapshot['name']+' — '+row.article_snapshot['purchase_unit_name']


class OrderReceiptForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    amount=forms.DecimalField(label=_('Quantité reçue en unité d’achat'),max_digits=18,decimal_places=6,min_value=Decimal('.000001'))
    location=forms.ModelChoiceField(label=_('Emplacement de réception'),queryset=Article.objects.none())
    lot_code=forms.CharField(label=_('Code interne du lot'),max_length=32)
    manufacturer_lot=forms.CharField(label=_('Lot fabricant'),max_length=120)
    container_code=forms.CharField(label=_('Code interne du contenant'),max_length=32)
    received_on=forms.DateField(label=_('Date de réception'),initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'}))
    condition=forms.CharField(label=_('État à la réception'),max_length=255)
    expires_on=forms.DateField(label=_('Péremption fabricant'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    manufactured_on=forms.DateField(label=_('Date de fabrication'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    serial_number=forms.CharField(label=_('Numéro de série'),max_length=120,required=False)
    cold_chain_ok=forms.NullBooleanField(label=_('Chaîne du froid respectée'))
    control_notes=forms.CharField(label=_('Observations du contrôle'),required=False,widget=forms.Textarea)
    actual_unit_price=forms.DecimalField(label=_('Prix réel par unité d’achat HT'),max_digits=18,decimal_places=2,min_value=0,required=False)
    variance_reason=forms.CharField(label=_('Justification de l’écart au prix commandé'),max_length=500,required=False,widget=forms.Textarea)

    def __init__(self,*args,user,line,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['location'].queryset=location_choices(user,Capability.RECEIVE_STOCK)
        if not permitted(user,Capability.EDIT_COST,category=line.plan_line.article.category):
            del self.fields['actual_unit_price']
        groups=[(_('Identification et réception'),['amount','location','lot_code','manufacturer_lot','container_code','received_on','condition']),
            (_('Traçabilité et contrôle'),['expires_on','manufactured_on','serial_number','cold_chain_ok','control_notes','variance_reason'])]
        if 'actual_unit_price' in self.fields:
            groups.append((_('Prix de réception'),['actual_unit_price']))
        self.groups=[{'title':title,'fields':[self[name] for name in names]} for title,names in groups]


class OrderDateForm(PlanActionForm):
    expected_on=forms.DateField(label=_('Nouvelle date confirmée de livraison'),widget=forms.DateInput(attrs={'type':'date'}))
