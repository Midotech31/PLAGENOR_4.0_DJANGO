import uuid
from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .forms import VersionedForm
from .models import AnalysisRun, AvailabilityBlock, PlanningResource, WorkItem
from .permissions import TEAM_ROLES
from .services.links import request_scope
from .services.planning import GENERIC_KINDS, interval
from .work_forms import OperationForm


def time_input():
    return forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})


class ScheduleForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    starts_at = forms.DateTimeField(label=_('Début prévu'), widget=time_input())
    ends_at = forms.DateTimeField(label=_('Fin prévue'), widget=time_input())
    resources = forms.ModelMultipleChoiceField(label=_('Équipements et salles à réserver'),
        queryset=PlanningResource.objects.filter(active=True), required=False,
        help_text=_('Chaque ressource est réservée exclusivement pendant le créneau.'))
    request = forms.ModelChoiceField(label=_('Demande liée'), queryset=WorkItem.objects.none(), required=False)
    run = forms.ModelChoiceField(label=_('Série analytique liée'), queryset=AnalysisRun.objects.none(), required=False)
    reason = forms.CharField(label=_('Justification de la modification'), max_length=500, required=False, widget=forms.Textarea)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        requests = request_scope(user, write=True).filter(archived=False).exclude(status__in=['REJECTED', 'ARCHIVED'])
        self.fields['request'].queryset = requests
        self.fields['request'].label_from_instance = lambda row: row.display_id
        self.fields['run'].queryset = AnalysisRun.objects.filter(request__in=requests).exclude(status__in=['CANCELLED', 'COMPLETED'])
        self.fields['run'].label_from_instance = lambda row: row.code
        self.fields['resources'].label_from_instance = lambda row: row.code + ' — ' + str(row)

    def clean(self):
        values = super().clean()
        if values.get('starts_at') and values.get('ends_at'):
            interval(values['starts_at'], values['ends_at'])
        return values


class ActivityCreateForm(ScheduleForm):
    frequency = forms.ChoiceField(label=_('Répétition'), choices=[('ONCE', _('Une seule fois')), ('DAILY', _('Chaque jour')), ('WEEKLY', _('Chaque semaine'))], initial='ONCE')
    occurrences = forms.IntegerField(label=_('Nombre d’occurrences à créer'), min_value=1, max_value=60, initial=1, help_text=_('Les occurrences sont créées maintenant et restent modifiables individuellement. Aucun dossier métier n’est dupliqué.'))
    key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    kind = forms.ChoiceField(label=_('Type d’activité'), choices=[(code, title) for code, title in WorkItem.Kind.choices if code in GENERIC_KINDS])
    title = forms.CharField(label=_('Intitulé de l’activité'), max_length=255)
    assignee = forms.ModelChoiceField(label=_('Responsable'), queryset=get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES), required=False)
    instructions = forms.CharField(label=_('Consignes et résultat attendu'), required=False, widget=forms.Textarea)
    priority = forms.ChoiceField(label=_('Priorité'), choices=WorkItem.Priority.choices, initial='NORMAL')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields['expected_version']
        del self.fields['reason']
        self.order_fields(['key', 'kind', 'title', 'assignee', 'priority', 'starts_at', 'ends_at', 'resources', 'request', 'run', 'frequency', 'occurrences', 'instructions'])


class DependencyForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    prerequisites = forms.ModelMultipleChoiceField(label=_('Activités à valider avant le démarrage'),
        queryset=WorkItem.objects.none(), required=False)
    reason = forms.CharField(label=_('Justification des prérequis'), max_length=500, widget=forms.Textarea)

    def __init__(self, *args, work, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prerequisites'].queryset = WorkItem.objects.exclude(pk=work.pk).exclude(status='CANCELLED').order_by('title')


class ReadinessForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    note = forms.CharField(label=_('Vérifications effectuées et références des pièces contrôlées'), max_length=2000, widget=forms.Textarea)
    confirmed = forms.BooleanField(label=_('J’ai vérifié les ressources, les documents et les conditions nécessaires à cette activité'))


class ResourceForm(VersionedForm):
    class Meta:
        model = PlanningResource
        fields = ['code', 'name', 'name_en', 'name_ar', 'kind', 'location', 'serial_number', 'instructions', 'active']


class UnavailabilityForm(OperationForm):
    starts_at = forms.DateTimeField(label=_('Début d’indisponibilité'), widget=time_input())
    ends_at = forms.DateTimeField(label=_('Fin d’indisponibilité'), widget=time_input())
    member = forms.ModelChoiceField(label=_('Membre indisponible'), queryset=get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES), required=False)
    resource = forms.ModelChoiceField(label=_('Ressource indisponible'), queryset=PlanningResource.objects.filter(active=True), required=False)
    reason = forms.CharField(label=_('Motif'), max_length=500, widget=forms.Textarea)

    def clean(self):
        values = super().clean()
        if bool(values.get('member')) == bool(values.get('resource')):
            raise forms.ValidationError(_('Sélectionnez soit un membre, soit une ressource.'))
        if values.get('starts_at') and values.get('ends_at'):
            interval(values['starts_at'], values['ends_at'])
        return values


class UnavailabilityEndForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label=_('Justification de la levée d’indisponibilité'), max_length=500, widget=forms.Textarea)
