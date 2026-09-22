from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .forms import VersionedForm
from .models import ChemicalProfile,HazardTag,Location,ResourceDocument,StorageSafetyRule
from .services.safety import target_cost_access
from .work_forms import OperationForm


class DocumentForm(OperationForm):
    title=forms.CharField(label=_('Intitulé du document'),max_length=200)
    kind=forms.ChoiceField(label=_('Type de document'),choices=ResourceDocument.Kind.choices)
    file=forms.FileField(label=_('Document PDF ou DOCX'),help_text=_('10 Mo maximum. Les documents sont conservés dans le dossier et inclus dans la sauvegarde de la base.'))
    source=forms.CharField(label=_('Origine / référence documentaire'),max_length=500)
    documented_on=forms.DateField(label=_('Date du document'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    supersedes=forms.ModelChoiceField(label=_('Remplace une version antérieure'),queryset=ResourceDocument.objects.none(),required=False)
    financial=forms.BooleanField(label=_('Contient des informations financières restreintes'),required=False)

    def __init__(self,*args,user,target_kind,target,**kwargs):
        super().__init__(*args,**kwargs)
        documents=ResourceDocument.objects.filter(**{target_kind:target},replacement__isnull=True).defer('content')
        allowed=target_cost_access(user,target_kind,target)
        if not allowed:
            documents=documents.filter(financial=False)
            del self.fields['financial']
        elif target_kind=='order':
            self.fields['financial'].disabled=True
            self.fields['financial'].initial=True
        self.fields['supersedes'].queryset=documents
        self.fields['supersedes'].label_from_instance=lambda row:row.title+' — '+row.created_at.strftime('%d/%m/%Y')


class HazardForm(VersionedForm):
    class Meta:
        model=HazardTag
        fields=['code','name','name_en','name_ar','ghs_code','description','active']


class ChemicalForm(VersionedForm):
    class Meta:
        model=ChemicalProfile
        fields=['classification','signal_word','handling','source_reference','source_document','reviewed_on','tags']
        widgets={'reviewed_on':forms.DateInput(attrs={'type':'date'})}

    def __init__(self,*args,article,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['expected_version'].initial=article.version
        self.fields['tags'].queryset=HazardTag.objects.filter(active=True)
        self.fields['source_document'].queryset=ResourceDocument.objects.filter(article=article,kind='SDS',financial=False).defer('content')
        self.fields['source_document'].label_from_instance=lambda row:row.title
        if self.instance._state.adding:
            self.fields['reviewed_on'].initial=timezone.localdate()


class StorageRuleForm(VersionedForm):
    class Meta:
        model=StorageSafetyRule
        fields=['location','mode','first_tag','second_tag','blocking','active','reference']

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['location'].queryset=Location.objects.filter(active=True)
        self.fields['first_tag'].queryset=HazardTag.objects.filter(active=True)
        self.fields['second_tag'].queryset=HazardTag.objects.filter(active=True)
