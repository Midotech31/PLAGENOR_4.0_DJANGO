from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Article,Capability,InventoryCampaign,InventoryLine,Location,StockContainer
from .permissions import catalog_scope,grants,is_manager,operational_scope,storage_scope
from .services.reports import KINDS
from .services.work import work_scope
from .work_forms import OperationForm


class ReportFilterForm(OperationForm):
    kind=forms.ChoiceField(label=_('Rapport'),choices=KINDS)
    year=forms.IntegerField(label=_('Année'),min_value=2000)
    article=forms.ModelChoiceField(label=_('Article'),queryset=Article.objects.none(),required=False)
    location=forms.ModelChoiceField(label=_('Emplacement et descendants'),queryset=Location.objects.none(),required=False)
    campaign=forms.ModelChoiceField(label=_('Campagne d’inventaire'),queryset=InventoryCampaign.objects.none(),required=False)
    state=forms.ChoiceField(label=_('Filtre du stock'),required=False,choices=[('',_('Tous les états')),
        ('USABLE',_('Stock utilisable disponible')),('BLOCKED',_('Stock non utilisable')),('EXPIRING',_('Péremption proche ou dépassée')),('EMPTY',_('Contenants épuisés'))])
    days=forms.IntegerField(label=_('Fenêtre de péremption (jours)'),min_value=1,max_value=3660,required=False)
    granularity=forms.ChoiceField(label=_('Regroupement des consommations'),required=False,choices=[('MONTH',_('Par mois')),('YEAR',_('Par année'))])
    q=forms.CharField(label=_('Recherche'),max_length=200,required=False)

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['year'].max_value=timezone.localdate().year+2
        allowed={'TASKS','INVENTORY'}
        if is_manager(user) or grants(user,Capability.VIEW_STOCK).exists():
            allowed.update(['STOCK','MOVEMENTS','CONSUMPTION','LOSSES','RECEIPTS','TRACE'])
        if is_manager(user) or grants(user,Capability.VIEW_BIOBANK).exists():
            allowed.update(['SAMPLES','STORAGE'])
        self.fields['kind'].choices=[(key,label) for key,label in KINDS if key in allowed]
        stock=operational_scope(StockContainer.objects.all(),user)
        inventory=InventoryLine.objects.filter(campaign__work__in=work_scope(user))
        catalogue=catalog_scope(Article.objects.all(),user)
        self.fields['article'].queryset=Article.objects.filter(Q(pk__in=catalogue.values('pk'))|
            Q(pk__in=stock.values('lot__article_id'))|Q(pk__in=inventory.values('container__lot__article_id'))).order_by('code')
        locations=storage_scope(Location.objects.all(),user)
        bio=storage_scope(Location.objects.all(),user,Capability.VIEW_BIOBANK)
        self.fields['location'].queryset=Location.objects.filter(Q(pk__in=locations.values('pk'))|Q(pk__in=bio.values('pk'))|
            Q(pk__in=stock.values('location_id'))|Q(pk__in=inventory.values('location_id'))).order_by('code')
        self.fields['campaign'].queryset=InventoryCampaign.objects.filter(work__in=work_scope(user)).select_related('work')
        self.fields['campaign'].label_from_instance=lambda value:value.work.title
