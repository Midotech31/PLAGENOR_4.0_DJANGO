import uuid
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ImportBatch
from .services.procurement import plan_scope
from .work_forms import OperationForm


class ImportUploadForm(OperationForm):
    key=forms.UUIDField(widget=forms.HiddenInput,initial=uuid.uuid4)
    kind=forms.ChoiceField(label=_('Domaine d’import'),choices=ImportBatch.Kind.choices)
    plan=forms.ModelChoiceField(label=_('Plan concerné'),queryset=ImportBatch.objects.none(),required=False)
    file=forms.FileField(label=_('Fichier XLSX ou CSV UTF-8'),help_text=_('Maximum : 10 Mo, 500 lignes de données, 40 colonnes.'))
    reason=forms.CharField(label=_('Origine et justification de l’import'),max_length=500,widget=forms.Textarea)
    assisted = forms.BooleanField(label=_('Choisir la correspondance des colonnes'), required=False)

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['plan'].queryset=plan_scope(user).exclude(approved_revision__isnull=False)


class ImportApplyForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    confirmed=forms.BooleanField(label=_('J’ai examiné toutes les lignes et je confirme leur application atomique'))


class ImportCancelForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reason=forms.CharField(label=_('Motif de l’abandon'),max_length=500,widget=forms.Textarea)


class ImportMappingForm(OperationForm):
    def __init__(self, *args, mapping, **kwargs):
        super().__init__(*args, **kwargs)
        from .services.table_intake import LABELS, SCHEMAS, aliases
        columns = [('', str(_('Non importé')))] + [(str(index), str(index + 1) + ' — ' + value)
            for index, value in enumerate(mapping.matrix[0])]
        suggested = aliases(mapping.kind)
        for name in SCHEMAS[mapping.kind]['required'] + SCHEMAS[mapping.kind]['optional']:
            initial = next((str(index) for index, value in enumerate(mapping.matrix[0])
                if suggested.get(value.strip().casefold()) == name), '')
            self.fields['column_' + name] = forms.ChoiceField(label=LABELS[name], choices=columns,
                required=name in SCHEMAS[mapping.kind]['required'], initial=initial,
                widget=forms.Select(attrs={'class': 'form-control'}))
        if mapping.kind == 'CATALOG':
            self.fields['clear_fields'] = forms.MultipleChoiceField(label=_('Effacer ces champs facultatifs si la cellule est vide'),
                choices=[(name, LABELS[name]) for name in SCHEMAS['CATALOG']['optional']], required=False,
                widget=forms.CheckboxSelectMultiple)
