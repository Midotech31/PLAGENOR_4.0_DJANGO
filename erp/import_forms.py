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

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['plan'].queryset=plan_scope(user).exclude(approved_revision__isnull=False)


class ImportApplyForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    confirmed=forms.BooleanField(label=_('J’ai examiné toutes les lignes et je confirme leur application atomique'))


class ImportCancelForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reason=forms.CharField(label=_('Motif de l’abandon'),max_length=500,widget=forms.Textarea)
