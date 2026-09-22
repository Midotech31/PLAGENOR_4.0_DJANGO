from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .forms import VersionedForm
from .models import WorkItem
from .permissions import TEAM_ROLES


class OperationForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.HiddenInput, forms.CheckboxInput)):
                field.widget.attrs['class'] = 'form-control'
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3


class WorkForm(VersionedForm):
    class Meta:
        model = WorkItem
        fields = ['kind', 'title', 'assignee', 'due_on', 'priority', 'location', 'category', 'instructions']
        widgets = {'due_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES).order_by('last_name', 'first_name', 'username')
        if 'kind' in self.fields:
            self.fields['kind'].choices = [(code, label) for code, label in WorkItem.Kind.choices
                                          if code in ('RECEIPT', 'TEMPERATURE', 'CONTROL')]


class DelegationForm(VersionedForm):
    reason = forms.CharField(label=_('Justification'), max_length=500, required=False, widget=forms.Textarea)

    class Meta:
        model = WorkItem
        fields = ['assignee', 'due_on', 'priority', 'instructions', 'allow_costs']
        widgets = {'due_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = get_user_model().objects.filter(is_active=True, role__in=TEAM_ROLES).order_by('last_name', 'first_name', 'username')
        self.fields['assignee'].help_text = _('Laissez vide pour retirer la délégation. Le précédent responsable perd immédiatement son accès au dossier.')
        if self.instance.kind not in (WorkItem.Kind.CDC, WorkItem.Kind.PLAN):
            self.fields['allow_costs'].disabled = True
            self.fields['allow_costs'].initial = False


class WorkTransitionForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    state = forms.ChoiceField(label=_('Action'), choices=WorkItem.Status.choices)
    reason = forms.CharField(label=_('Compte rendu / justification'), max_length=500, required=False, widget=forms.Textarea)


class WorkCommentForm(OperationForm):
    body = forms.CharField(label=_('Compte rendu / commentaire'), max_length=10000, widget=forms.Textarea)
