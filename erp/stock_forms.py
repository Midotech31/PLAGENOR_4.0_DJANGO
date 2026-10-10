from datetime import date
from decimal import Decimal
import uuid

from django import forms
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (Article, Capability, Category, InventoryCampaign, Location, LocationClosure,
                     Party, StockContainer, StockLot, StockMovement, Unit, WorkItem)
from .models import StockDispatch
from .permissions import grants, is_manager, operational_scope
from .services.links import request_scope
from .work_forms import OperationForm, WorkForm


def article_choices(user, capability):
    qs = Article.objects.filter(active=True).select_related('category', 'base_unit')
    if is_manager(user):
        return qs
    allowed = grants(user, capability)
    return qs if allowed.filter(category__isnull=True).exists() else qs.filter(category_id__in=allowed.values('category_id'))


def location_choices(user, capability):
    qs = Location.objects.filter(active=True, kind__can_store=True).select_related('kind')
    if is_manager(user):
        return qs
    allowed = grants(user, capability)
    if allowed.filter(location__isnull=True).exists():
        return qs
    return qs.filter(pk__in=LocationClosure.objects.filter(ancestor_id__in=allowed.values('location_id')).values('descendant_id'))


class ReceiptForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    article = forms.ModelChoiceField(label=_('Article'), queryset=Article.objects.none())
    location = forms.ModelChoiceField(label=_('Emplacement de réception'), queryset=Location.objects.none())
    lot_code = forms.CharField(label=_('Code interne du lot'), max_length=32)
    manufacturer_lot = forms.CharField(label=_('Lot fabricant'), max_length=120)
    container_code = forms.CharField(label=_('Code interne du contenant'), max_length=32)
    amount = forms.DecimalField(label=_('Quantité reçue'), max_digits=18, decimal_places=6, min_value=0.000001)
    unit = forms.ModelChoiceField(label=_('Unité de la quantité reçue'), queryset=Unit.objects.filter(active=True))
    received_on = forms.DateField(label=_('Date de réception'), initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
    condition = forms.CharField(label=_('État à la réception'), max_length=255)
    supplier = forms.ModelChoiceField(label=_('Fournisseur'), queryset=Party.objects.filter(is_supplier=True, active=True), required=False)
    order_reference = forms.CharField(label=_('Commande / marché'), max_length=120, required=False)
    delivery_reference = forms.CharField(label=_('Bon de livraison'), max_length=120, required=False)
    unit_price = forms.DecimalField(label=_('Prix unitaire (unité de gestion)'), max_digits=18, decimal_places=2, min_value=0, required=False)
    currency = forms.CharField(label=_('Devise'), max_length=3, initial='DZD', required=False)
    ordered_on = forms.DateField(label=_('Date de commande'), required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ordered_quantity = forms.DecimalField(label=_('Quantité commandée dans l’unité de gestion'), max_digits=18, decimal_places=6, required=False, min_value=0.000001)
    expires_on = forms.DateField(label=_('Péremption fabricant'), required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    manufactured_on = forms.DateField(label=_('Date de fabrication'), required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    serial_number = forms.CharField(label=_('Numéro de série'), max_length=120, required=False)
    cold_chain_ok = forms.NullBooleanField(label=_('Chaîne du froid respectée'))
    control_notes = forms.CharField(label=_('Observations du contrôle'), required=False, widget=forms.Textarea)
    initial = forms.BooleanField(label=_('Reprise du stock physique initial'), required=False)
    barcode = forms.CharField(label=_('Code fabricant / GS1'), max_length=255, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['article'].queryset = article_choices(user, Capability.RECEIVE_STOCK)
        self.fields['location'].queryset = location_choices(user, Capability.RECEIVE_STOCK)
        groups = [(_('Identification et quantité'), ['article', 'location', 'lot_code', 'manufacturer_lot', 'container_code', 'amount', 'unit', 'initial']),
                  (_('Réception et contrôle'), ['received_on', 'supplier', 'condition', 'cold_chain_ok', 'control_notes']),
                  (_('Commande et traçabilité'), ['order_reference', 'delivery_reference', 'ordered_on', 'ordered_quantity', 'expires_on', 'manufactured_on', 'serial_number', 'barcode'])]
        from .permissions import permitted
        if is_manager(user) or grants(user, Capability.EDIT_COST).exists():
            groups.append((_('Prix'), ['unit_price', 'currency']))
        else:
            self.fields.pop('unit_price')
            self.fields.pop('currency')
        self.groups = [{'title': label, 'fields': [self[field] for field in fields]} for label, fields in groups]

    def clean_currency(self):
        value = (self.cleaned_data.get('currency') or 'DZD').strip().upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise forms.ValidationError(_('Code de devise à trois lettres requis.'))
        return value


class ControlForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    status = forms.ChoiceField(label=_('État contrôlé'), choices=StockLot.Status.choices)
    reason = forms.CharField(label=_('Justification du contrôle'), max_length=500, widget=forms.Textarea)


class OpenForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    opened_on = forms.DateField(label=_('Date d’ouverture'), initial=date.today, widget=forms.DateInput(attrs={'type': 'date'}))
    reason = forms.CharField(label=_('Observation'), max_length=500, required=False, widget=forms.Textarea)


class RemoveForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    amount = forms.DecimalField(label=_('Quantité sortie'), max_digits=18, decimal_places=6, min_value=0.000001)
    unit = forms.ModelChoiceField(label=_('Unité'), queryset=Unit.objects.filter(active=True))
    kind = forms.ChoiceField(label=_('Type de mouvement'), choices=[])
    reason = forms.CharField(label=_('Motif / justification FEFO'), max_length=500, required=False, widget=forms.Textarea)
    request = forms.ModelChoiceField(label=_('Demande PLAGENOR associée'), queryset=Article.objects.none(), required=False)
    reservation = forms.ModelChoiceField(label=_('Réservation à consommer'), queryset=Article.objects.none(), required=False)

    def __init__(self, *args, user, container, **kwargs):
        from .permissions import permitted
        from .services.stock import OUTFLOWS
        super().__init__(*args, **kwargs)
        self.fields['unit'].initial = container.lot.article.base_unit_id
        self.fields['request'].queryset = request_scope(user, write=True).filter(archived=False).exclude(status='REJECTED')
        self.fields['reservation'].queryset = container.reservations.filter(remaining__gt=0).filter(Q(request__isnull=True) | Q(request__in=self.fields['request'].queryset))
        may_control = permitted(user, Capability.CONTROL_STOCK, category=container.lot.article.category, location=container.location)
        may_consume = permitted(user, Capability.CONSUME_STOCK, category=container.lot.article.category, location=container.location)
        self.fields['kind'].choices = [(code, label) for code, label in StockMovement.Kind.choices
            if code in OUTFLOWS and ((code == 'CONSUMPTION' and may_consume) or (code != 'CONSUMPTION' and may_control))]


class TransferForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    destination = forms.ModelChoiceField(label=_('Destination'), queryset=Location.objects.none())
    amount = forms.DecimalField(label=_('Quantité transférée'), max_digits=18, decimal_places=6, required=False, min_value=0.000001,
        help_text=_('Laissez vide pour déplacer le contenant entier, avec ses réservations.'))
    unit = forms.ModelChoiceField(label=_('Unité'), queryset=Unit.objects.filter(active=True), required=False)
    destination_code = forms.CharField(label=_('Code du nouveau contenant en cas de division'), max_length=32, required=False)
    reason = forms.CharField(label=_('Motif du transfert'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, container, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = location_choices(user, Capability.TRANSFER_STOCK).exclude(pk=container.location_id)
        self.fields['unit'].initial = container.lot.article.base_unit_id


class ReserveForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    amount = forms.DecimalField(label=_('Quantité réservée'), max_digits=18, decimal_places=6, min_value=0.000001)
    unit = forms.ModelChoiceField(label=_('Unité'), queryset=Unit.objects.filter(active=True))
    request = forms.ModelChoiceField(label=_('Demande PLAGENOR associée'), queryset=Article.objects.none(), required=False)
    reference = forms.CharField(label=_('Run / projet / justification'), max_length=255)

    def __init__(self, *args, user, container, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['request'].queryset = request_scope(user, write=True).filter(archived=False).exclude(status='REJECTED')
        self.fields['unit'].initial = container.lot.article.base_unit_id


class ReasonForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    reason = forms.CharField(label=_('Justification'), max_length=500, widget=forms.Textarea)


class AliquotForm(TransferForm):
    def __init__(self, *args, user, container, **kwargs):
        super().__init__(*args, user=user, container=container, **kwargs)
        self.fields['destination'].queryset = location_choices(user, Capability.TRANSFER_STOCK)
        self.fields['destination'].initial = container.location_id
        self.fields['amount'].required = True
        self.fields['destination_code'].required = True


class DispatchForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    mode = forms.ChoiceField(label=_('Mode de distribution'), choices=StockDispatch.Mode.choices)
    beneficiary = forms.CharField(label=_('Laboratoire / bénéficiaire'), max_length=255)
    distributed_on = forms.DateField(label=_('Date de distribution'), initial=timezone.localdate,
        widget=forms.DateInput(attrs={'type': 'date'}))
    destination = forms.ModelChoiceField(label=_('Destination du transfert interne'),
        queryset=Location.objects.none(), required=False)
    reason = forms.CharField(label=_('Motif'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = location_choices(user, Capability.TRANSFER_STOCK)


class ContainerSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if hasattr(value, 'instance'):
            option['attrs'].update({'data-version': value.instance.version,
                'data-unit': str(value.instance.lot.article.base_unit_id)})
        return option


class ContainerChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return ' | '.join((obj.code, str(obj.lot.article), obj.lot.article.catalog_reference or '—',
            obj.lot.manufacturer_lot, obj.location.code, str(obj.quantity - obj.reserved), obj.lot.article.base_unit.code))


class DispatchLineForm(OperationForm):
    container_search = forms.CharField(label=_('Rechercher un contenant'), required=False,
        widget=forms.TextInput(attrs={'type': 'search', 'class': 'form-control', 'data-container-search': 'true'}))
    container = ContainerChoice(label=_('Contenant / référence / lot / emplacement / disponible'),
        queryset=StockContainer.objects.none(), widget=ContainerSelect)
    expected = forms.IntegerField(widget=forms.HiddenInput, required=False)
    amount = forms.DecimalField(label=_('Quantité distribuée'), max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))
    unit = forms.ModelChoiceField(label=_('Unité'), queryset=Unit.objects.filter(active=True))
    destination_code = forms.CharField(label=_('Code du contenant après division interne'), max_length=32, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        from .services.stock import usable_filter
        scoped = operational_scope(StockContainer.objects.filter(usable_filter(), quantity__gt=F('reserved')), user)
        selected = self.data.get(self.add_prefix('container')) or self.initial.get('container')
        try:
            selected = uuid.UUID(str(getattr(selected, 'pk', selected)))
        except (ValueError, TypeError, AttributeError):
            selected = None
        first = scoped.order_by('lot__article__code', 'code').values('pk')[:40]
        self.fields['container'].queryset = scoped.filter(Q(pk__in=first) | Q(pk=selected)).select_related(
            'lot__article__base_unit', 'location').order_by('lot__article__code', 'code')


DispatchLineFormSet = forms.formset_factory(DispatchLineForm, extra=3, max_num=100,
    min_num=1, validate_min=True, validate_max=True, absolute_max=100)


class ReturnForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    amount = forms.DecimalField(label=_('Quantité retournée'), max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))
    unit = forms.ModelChoiceField(label=_('Unité'), queryset=Unit.objects.filter(active=True))
    destination = forms.ModelChoiceField(label=_('Emplacement du retour'), queryset=Location.objects.none())
    container_code = forms.CharField(label=_('Code interne du contenant retourné'), max_length=32)
    returned_on = forms.DateField(label=_('Date de retour'), initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
    condition = forms.CharField(label=_('État au retour'), max_length=255)
    reason = forms.CharField(label=_('Motif'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, line, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = location_choices(user, Capability.RECEIVE_STOCK)
        self.fields['unit'].initial = line.container.lot.article.base_unit_id


class InventoryForm(WorkForm):
    blind = forms.BooleanField(label=_('Masquer les quantités théoriques pendant le comptage'), initial=True, required=False)

    class Meta(WorkForm.Meta):
        fields = ['title', 'assignee', 'due_on', 'priority', 'location', 'category', 'instructions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CountForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    container_version = forms.IntegerField(widget=forms.HiddenInput)
    amount = forms.DecimalField(label=_('Quantité physique comptée (unité de gestion)'), min_value=0, max_digits=18, decimal_places=6)
    note = forms.CharField(label=_('Observation de comptage'), max_length=500, required=False, widget=forms.Textarea)


class InventoryDecisionForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    reason = forms.CharField(label=_('Justification / compte rendu'), max_length=500, required=False, widget=forms.Textarea)
