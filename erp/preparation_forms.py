import uuid
from decimal import Decimal
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Article,Capability,Location,StockContainer,Unit
from .permissions import operational_scope
from .stock_forms import article_choices,location_choices
from .work_forms import OperationForm


class PreparationForm(OperationForm):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    article=forms.ModelChoiceField(label=_('Article produit'),queryset=Article.objects.none())
    location=forms.ModelChoiceField(label=_('Emplacement du produit préparé'),queryset=Location.objects.none())
    lot_code=forms.CharField(label=_('Code du lot de préparation'),max_length=32)
    container_code=forms.CharField(label=_('Code du contenant produit'),max_length=32)
    amount=forms.DecimalField(label=_('Quantité obtenue'),max_digits=18,decimal_places=6,min_value=Decimal('.000001'))
    unit=forms.ModelChoiceField(label=_('Unité de la quantité obtenue'),queryset=Unit.objects.filter(active=True))
    prepared_on=forms.DateField(label=_('Date de préparation'),initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'}))
    expires_on=forms.DateField(label=_('Péremption documentée'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    protocol_reference=forms.CharField(label=_('Protocole / SOP'),max_length=255)
    concentration_value=forms.DecimalField(label=_('Valeur de concentration'),max_digits=18,decimal_places=6,min_value=0,required=False)
    concentration_unit=forms.ModelChoiceField(label=_('Unité de concentration'),queryset=Unit.objects.filter(active=True),required=False)
    concentration=forms.CharField(label=_('Complément de concentration documentée'),max_length=120,required=False)
    reason=forms.CharField(label=_('Justification de la préparation'),max_length=500,widget=forms.Textarea)

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['article'].queryset=article_choices(user,Capability.RECEIVE_STOCK)
        self.fields['location'].queryset=location_choices(user,Capability.RECEIVE_STOCK)


class IngredientForm(OperationForm):
    container=forms.ModelChoiceField(label=_('Contenant source'),queryset=StockContainer.objects.none())
    amount=forms.DecimalField(label=_('Quantité prélevée'),max_digits=18,decimal_places=6,min_value=Decimal('.000001'))
    unit=forms.ModelChoiceField(label=_('Unité du prélèvement'),queryset=Unit.objects.filter(active=True))

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['container'].queryset=operational_scope(StockContainer.objects.filter(quantity__gt=0),user,Capability.CONSUME_STOCK).select_related('lot__article','location')
        self.fields['container'].label_from_instance=lambda row:row.code+' — '+str(row.lot.article)+' — '+str(row.location)


IngredientFormSet=forms.formset_factory(IngredientForm,extra=5,min_num=1,max_num=50,validate_min=True,validate_max=True,absolute_max=50)
