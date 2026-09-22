from decimal import Decimal
import uuid

from django import forms
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import BiologicalSample, Capability, Location, StorageIncident, StoragePosition, Unit
from .permissions import TEAM_ROLES, is_manager, storage_scope
from .stock_forms import location_choices
from .work_forms import OperationForm


class PositionFieldsMixin:
    def bind_positions(self, user, location_field='location'):
        self.fields[location_field].widget.attrs['data-position-source'] = 'id_position'
        raw = self.data.get(location_field) if self.is_bound else self.initial.get(location_field)
        selected = None
        if raw:
            try:
                selected = self.fields[location_field].queryset.filter(pk=getattr(raw, 'pk', raw)).first()
            except (ValidationError, ValueError):
                selected = None
        positions = StoragePosition.objects.filter(location=selected, active=True) if selected else StoragePosition.objects.none()
        self.fields['position'].queryset = positions
        self.fields['position'].label_from_instance = lambda position: str(position.row) + ':' + str(position.column)


from django.core.exceptions import ValidationError


class SampleReceiveForm(PositionFieldsMixin, OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    code = forms.CharField(label=_('Code interne de l’échantillon'), max_length=32,
        initial=lambda: 'S-' + uuid.uuid4().hex[:16].upper())
    amount = forms.DecimalField(label=_('Quantité physique reçue'), max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))
    unit = forms.ModelChoiceField(label=_('Unité de gestion'), queryset=Unit.objects.filter(active=True))
    location = forms.ModelChoiceField(label=_('Emplacement'), queryset=Location.objects.none())
    position = forms.ModelChoiceField(label=_('Position dans la boîte'), queryset=StoragePosition.objects.none(), required=False)
    received_on = forms.DateField(label=_('Date de réception physique'), initial=timezone.localdate, widget=forms.DateInput(attrs={'type': 'date'}))
    sample_type = forms.CharField(label=_('Type d’échantillon'), max_length=160, required=False)
    matrix = forms.CharField(label=_('Matrice / origine biologique'), max_length=160, required=False)
    collected_on = forms.DateField(label=_('Date de prélèvement'), required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    concentration_value = forms.DecimalField(label=_('Concentration mesurée'), max_digits=18, decimal_places=6, min_value=0, required=False)
    concentration_unit = forms.ModelChoiceField(label=_('Unité de concentration'), queryset=Unit.objects.filter(active=True), required=False)
    temperature_min = forms.DecimalField(label=_('Température minimale de conservation (°C)'), max_digits=7, decimal_places=2, required=False)
    temperature_max = forms.DecimalField(label=_('Température maximale de conservation (°C)'), max_digits=7, decimal_places=2, required=False)
    preservation = forms.CharField(label=_('Conditions de conservation documentées'), max_length=500, required=False, widget=forms.Textarea)
    freeze_thaw_limit = forms.IntegerField(label=_('Seuil de cycles selon le protocole'), min_value=0, required=False,
        help_text=_('Aucun seuil universel n’est appliqué. Laissez vide en l’absence de limite documentée.'))
    notes = forms.CharField(label=_('Observations'), required=False, widget=forms.Textarea)
    reason = forms.CharField(label=_('Motif / référence du contrôle de réception'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = location_choices(user, Capability.MANAGE_BIOBANK)
        self.bind_positions(user)
        groups = [(_('Identification et rangement'), ['code', 'amount', 'unit', 'location', 'position', 'received_on', 'reason']),
                  (_('Caractéristiques biologiques'), ['sample_type', 'matrix', 'collected_on', 'concentration_value', 'concentration_unit']),
                  (_('Conservation et observations'), ['temperature_min', 'temperature_max', 'preservation', 'freeze_thaw_limit', 'notes'])]
        self.groups = [{'title': title, 'fields': [self[name] for name in names]} for title, names in groups]


class SampleTransferForm(PositionFieldsMixin, OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    destination = forms.ModelChoiceField(label=_('Nouvel emplacement'), queryset=Location.objects.none())
    position = forms.ModelChoiceField(label=_('Nouvelle position'), queryset=StoragePosition.objects.none(), required=False)
    reason = forms.CharField(label=_('Motif du transfert'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destination'].queryset = location_choices(user, Capability.MANAGE_BIOBANK)
        self.bind_positions(user, 'destination')


class AliquotForm(SampleTransferForm):
    code = forms.CharField(label=_('Code interne de l’aliquot'), max_length=32,
        initial=lambda: 'A-' + uuid.uuid4().hex[:16].upper())
    amount = forms.DecimalField(label=_('Quantité de l’aliquot'), max_digits=18, decimal_places=6, min_value=Decimal('0.000001'))
    unit = forms.ModelChoiceField(label=_('Unité de la quantité prélevée'), queryset=Unit.objects.filter(active=True))


class SampleActionForm(SampleTransferForm):
    action = forms.ChoiceField(label=_('Action'), choices=[])
    amount = forms.DecimalField(label=_('Quantité consommée'), max_digits=18, decimal_places=6, min_value=Decimal('0.000001'), required=False)
    unit = forms.ModelChoiceField(label=_('Unité de consommation'), queryset=Unit.objects.filter(active=True), required=False)
    thawed = forms.BooleanField(label=_('Décongélation effectivement réalisée pendant cette sortie'), required=False,
        help_text=_('Un transfert ne compte pas automatiquement comme une décongélation.'))

    def __init__(self, *args, user, sample, **kwargs):
        super().__init__(*args, user=user, **kwargs)
        self.fields['destination'].required = False
        states = {
            'STORED': [('CHECK_OUT', _('Sortir pour analyse')), ('CONSUMPTION', _('Consommer une quantité')), ('QUARANTINE', _('Mettre en quarantaine'))],
            'OUT': [('RETURN', _('Retourner au stockage')), ('CONSUMPTION', _('Consommer une quantité'))],
            'QUARANTINE': [('RELEASE', _('Libérer après contrôle'))] if is_manager(user) else [],
        }
        choices = states.get(sample.status, [])
        if sample.status in ('STORED', 'OUT', 'QUARANTINE'):
            choices += [('SHIPMENT', _('Expédier définitivement')), ('DESTRUCTION', _('Détruire'))]
        self.fields['action'].choices = choices
        self.fields['unit'].initial = sample.unit_id


class PositionReservationForm(OperationForm):
    assignee = forms.ModelChoiceField(label=_('Membre bénéficiaire'), queryset=get_user_model().objects.none())
    until = forms.DateTimeField(label=_('Réserver jusqu’au'), widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}))
    reason = forms.CharField(label=_('Motif de réservation'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES) if is_manager(user) else get_user_model().objects.filter(pk=user.pk)
        self.fields['assignee'].initial = user.pk


class TemperatureForm(OperationForm):
    location = forms.ModelChoiceField(label=_('Équipement froid'), queryset=Location.objects.none())
    measured_at = forms.DateTimeField(label=_('Date et heure du relevé'), initial=timezone.now, widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    value = forms.DecimalField(label=_('Température mesurée (°C)'), max_digits=7, decimal_places=2, min_value=Decimal('-273.15'), max_value=1000)
    comment = forms.CharField(label=_('Observation'), max_length=500, required=False, widget=forms.Textarea)

    def __init__(self, *args, user, work=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Location.objects.filter(active=True, kind__cold_storage=True)
        if work is not None and work.location_id:
            from .models import LocationClosure
            qs = qs.filter(pk__in=LocationClosure.objects.filter(ancestor_id=work.location_id).values('descendant_id'))
        else:
            ids = storage_scope(qs, user, Capability.EDIT_STORAGE).values('pk')
            bio = storage_scope(qs, user, Capability.MANAGE_BIOBANK).values('pk')
            qs = qs.filter(Q(pk__in=ids) | Q(pk__in=bio))
        self.fields['location'].queryset = qs


class IncidentForm(OperationForm):
    location = forms.ModelChoiceField(label=_('Stockage concerné'), queryset=Location.objects.none())
    kind = forms.ChoiceField(label=_('Type d’incident'), choices=StorageIncident._meta.get_field('kind').choices)
    started_at = forms.DateTimeField(label=_('Début de l’incident'), initial=timezone.now, widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    description = forms.CharField(label=_('Description et impact observé'), widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].queryset = storage_scope(Location.objects.filter(active=True), user, Capability.MANAGE_BIOBANK)


class IncidentResolutionForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    resolved_at = forms.DateTimeField(label=_('Fin de l’incident'), initial=timezone.now, widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    corrective_action = forms.CharField(label=_('Action corrective et justification de clôture'), widget=forms.Textarea)


class MassTransferForm(OperationForm):
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    source = forms.ModelChoiceField(label=_('Stockage source'), queryset=Location.objects.none())
    destination = forms.ModelChoiceField(label=_('Stockage de destination'), queryset=Location.objects.none())
    reason = forms.CharField(label=_('Motif du transfert collectif'), max_length=500, widget=forms.Textarea)
    incident = forms.ModelChoiceField(label=_('Incident associé'), queryset=StorageIncident.objects.none(), required=False)
    preview_token = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        locations = storage_scope(Location.objects.filter(active=True), user, Capability.MANAGE_BIOBANK)
        self.fields['source'].queryset = locations
        self.fields['destination'].queryset = locations
        self.fields['incident'].queryset = StorageIncident.objects.filter(location__in=locations, resolved_at__isnull=True)
