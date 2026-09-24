from decimal import Decimal
import uuid

from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from .forms import VersionedForm
from .models import AnalysisRun, BiologicalSample, ConsumptionProfile, ConsumptionRule, ProcurementPlan, RunAllocation, StockContainer, WorkItem
from .permissions import is_manager, operational_scope
from .services.biobank import biobank_scope, source_samples
from .services.links import request_scope
from .work_forms import OperationForm


class ProfileForm(VersionedForm):
    class Meta:
        model = ConsumptionProfile
        fields = ['code', 'name', 'name_en', 'name_ar', 'service', 'reference_samples', 'protocol_reference', 'notes', 'active']


class RuleForm(VersionedForm):
    class Meta:
        model = ConsumptionRule
        fields = ['article', 'quantity', 'unit', 'basis']


class RunCreateForm(OperationForm):
    code = forms.CharField(label=_('Code interne de la série'), max_length=32,
        initial=lambda: 'RUN-' + uuid.uuid4().hex[:12].upper())
    name = forms.CharField(label=_('Intitulé de la série'), max_length=255)
    profile = forms.ModelChoiceField(label=_('Nomenclature de consommation du service'), queryset=ConsumptionProfile.objects.none())
    sample_count = forms.IntegerField(label=_('Nombre d’échantillons analysés'), min_value=1, max_value=50000)
    source_keys = forms.MultipleChoiceField(label=_('Échantillons déclarés dans la demande'), required=False,
        widget=forms.CheckboxSelectMultiple)
    samples = forms.ModelMultipleChoiceField(label=_('Échantillons ou aliquots stockés'), queryset=BiologicalSample.objects.none(),
        required=False, widget=forms.CheckboxSelectMultiple)
    planned_on = forms.DateField(label=_('Date prévue de la série'), initial=timezone.localdate,
        widget=forms.DateInput(attrs={'type': 'date'}))
    incremental_demand = forms.BooleanField(label=_('Activité supplémentaire au rythme habituel'), required=False)
    committed = forms.BooleanField(label=_('Activité prévisionnelle confirmée par l’administration'), required=False)

    def __init__(self, *args, user, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profile'].queryset = ConsumptionProfile.objects.filter(service=request.service, active=True)
        self.fields['source_keys'].choices = [(row['key'], row['code']) for row in source_samples(user, request)]
        self.fields['samples'].queryset = biobank_scope(user).filter(Q(origin_request=request) | Q(root_sample__origin_request=request),
            status__in=['STORED', 'OUT'])
        self.fields['samples'].label_from_instance = lambda sample: sample.code + ' — ' + str(sample.location)
        if not is_manager(user):
            del self.fields['incremental_demand']
            del self.fields['committed']


class RunReserveForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    requirement = forms.ModelChoiceField(label=_('Article prévu dans la série'), queryset=ConsumptionRule.objects.none())
    container = forms.ModelChoiceField(label=_('Contenant réellement retenu'), queryset=StockContainer.objects.none())
    amount = forms.DecimalField(label=_('Quantité dans l’unité de gestion de l’article'), min_value=Decimal('0.000001'), max_digits=18, decimal_places=6)
    reason = forms.CharField(label=_('Motif / justification du choix du lot'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, user, run, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['requirement'].queryset = run.requirements.select_related('article', 'unit')
        self.fields['requirement'].label_from_instance = lambda row: str(row.article) + ' — ' + str(row.quantity) + ' ' + row.unit.code
        self.fields['container'].queryset = operational_scope(StockContainer.objects.filter(quantity__gt=0,
            lot__article_id__in=run.requirements.values('article_id')), user).select_related('lot__article', 'location')
        self.fields['container'].label_from_instance = lambda row: row.code + ' — ' + str(row.lot.article) + ' — ' + str(row.location)


class RunConfirmForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    reason = forms.CharField(label=_('Compte rendu des consommations réellement effectuées'), max_length=500, widget=forms.Textarea)
    confirmed = forms.BooleanField(label=_('Je confirme les quantités réellement consommées et les lots utilisés'))

    def __init__(self, *args, run, **kwargs):
        super().__init__(*args, **kwargs)
        self.actual_fields, self.biological_fields = {}, {}
        for row in RunAllocation.objects.filter(requirement__run=run).select_related('reservation__container', 'requirement__unit'):
            name = 'actual_' + row.pk.hex
            self.actual_fields[str(row.pk)] = name
            self.fields[name] = forms.DecimalField(label=row.reservation.container.code + ' (' + row.requirement.unit.code + ')',
                max_digits=18, decimal_places=6, min_value=0, max_value=row.reservation.remaining,
                initial=row.reservation.remaining, widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}))
        for row in run.inputs.filter(sample__isnull=False).select_related('sample__unit'):
            name = 'biology_' + row.pk.hex
            self.biological_fields[str(row.pk)] = name
            self.fields[name] = forms.DecimalField(label=row.sample.code + ' (' + row.sample.unit.code + ')',
                max_digits=18, decimal_places=6, min_value=0, initial=0,
                help_text=_('Indiquez zéro uniquement si aucune quantité biologique n’a été consommée.'),
                widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.000001'}))
        self.groups = [{'title': _('Consommation réelle des réactifs et consommables'), 'fields': [self[name] for name in self.actual_fields.values()]},
            {'title': _('Quantités biologiques consommées'), 'fields': [self[name] for name in self.biological_fields.values()]},
            {'title': _('Confirmation et traçabilité'), 'fields': [self['reason'], self['confirmed']]}]


class RunCancelForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    reason = forms.CharField(label=_('Motif de l’annulation'), max_length=500, widget=forms.Textarea)


class RunProcurementForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    plan=forms.ModelChoiceField(label=_('Plan d’approvisionnement'),queryset=ProcurementPlan.objects.none())
    reason=forms.CharField(label=_('Justification du transfert des manques'),max_length=500,widget=forms.Textarea)
    def __init__(self,*args,user,run,**kwargs):
        super().__init__(*args,**kwargs)
        from .services.procurement import plan_scope
        self.fields['expected_version'].initial=run.version
        self.fields['plan'].queryset=plan_scope(user).filter(approved_revision__isnull=True,work__status__in=[WorkItem.Status.DRAFT,WorkItem.Status.ASSIGNED,WorkItem.Status.IN_PROGRESS,WorkItem.Status.CHANGES_REQUESTED],starts_on__lte=run.planned_on,ends_on__gte=run.planned_on)
