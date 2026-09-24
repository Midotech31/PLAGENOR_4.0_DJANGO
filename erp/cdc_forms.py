from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .forms import VersionedForm
from .models import Article, CdcDossier, CdcGeneration, CdcItem, Unit, WorkItem
from .permissions import TEAM_ROLES
from .services.work import work_allowed
from .work_forms import OperationForm, WorkForm


class CdcCreateForm(WorkForm):
    family = forms.ChoiceField(label=_('Famille documentaire'), choices=CdcDossier.Family.choices)
    reference = forms.RegexField(label=_('Référence du dossier'), max_length=90,
        regex=r'^[0-9]{1,4}/SME/SDFM/SG/ESSBO/[0-9]{4}$',
        help_text=_('Structure institutionnelle : numéro/SME/SDFM/SG/ESSBO/année.'))

    class Meta(WorkForm.Meta):
        fields = ['title', 'assignee', 'due_on', 'priority', 'instructions', 'allow_costs']


class ConsultationForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reference = forms.CharField(label=_('Référence'), max_length=90)
    object_fr = forms.CharField(label=_('Objet en français'), max_length=2000, widget=forms.Textarea)
    object_ar = forms.CharField(label=_('Objet en arabe'), max_length=2000, widget=forms.Textarea(attrs={'dir': 'rtl'}))
    operation_fr = forms.CharField(label=_('Opération'), max_length=2000, widget=forms.Textarea)
    financing_label = forms.CharField(label=_('Financement'), max_length=2000)
    budget_year = forms.IntegerField(label=_('Exercice budgétaire'), min_value=2000, max_value=2100)
    preparation_days = forms.IntegerField(label=_('Délai de préparation des offres (jours)'), min_value=1, max_value=365)
    preparation_fr = forms.CharField(label=_('Délai en français, en lettres et en chiffres'), max_length=2000)
    preparation_ar = forms.CharField(label=_('Délai en arabe, en lettres et en chiffres'), max_length=2000, widget=forms.TextInput(attrs={'dir': 'rtl'}))
    deposit_time = forms.TimeField(label=_('Heure limite de dépôt'), widget=forms.TimeInput(attrs={'type': 'time'}))
    opening_time = forms.TimeField(label=_('Heure d’ouverture des plis'), widget=forms.TimeInput(attrs={'type': 'time'}))
    validity_months = forms.IntegerField(label=_('Validité des offres (mois)'), min_value=1, max_value=60)
    validity_fr = forms.CharField(label=_('Validité en français, en lettres et en chiffres'), max_length=2000)
    validity_ar = forms.CharField(label=_('Validité en arabe, en lettres et en chiffres'), max_length=2000, widget=forms.TextInput(attrs={'dir': 'rtl'}))
    withdrawal_fr = forms.CharField(label=_('Modalités de retrait en français'), max_length=2000, widget=forms.Textarea)
    withdrawal_ar = forms.CharField(label=_('Modalités de retrait en arabe'), max_length=2000, widget=forms.Textarea(attrs={'dir': 'rtl'}))
    confirmed = forms.BooleanField(label=_('J’ai vérifié les informations propres à ce dossier et leur cohérence bilingue'), required=False)
    reason = forms.CharField(label=_('Justification des modifications'), max_length=500, required=False, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        groups = [(_('Dossier et objet'), ['reference', 'object_fr', 'object_ar', 'operation_fr', 'financing_label', 'budget_year']),
                  (_('Délais et horaires'), ['preparation_days', 'preparation_fr', 'preparation_ar', 'deposit_time', 'opening_time', 'validity_months', 'validity_fr', 'validity_ar']),
                  (_('Retrait et confirmation'), ['withdrawal_fr', 'withdrawal_ar', 'confirmed', 'reason'])]
        self.groups = [{'title': label, 'fields': [self[field] for field in fields]} for label, fields in groups]

    def clean(self):
        values = super().clean()
        for name in ('deposit_time', 'opening_time'):
            if name in values:
                values[name] = values[name].strftime('%H:%M')
        return values


class CdcLotForm(OperationForm):
    source_slot = forms.IntegerField(label=_('Numéro du lot dans le modèle documentaire'), min_value=0, max_value=50, required=False,
        help_text=_('Rattachez chaque lot à son emplacement dans le modèle. Zéro signifie non rattaché ; la génération restera bloquée.'))
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    name = forms.CharField(label=_('Intitulé du lot en français'), max_length=180)
    name_ar = forms.CharField(label=_('Intitulé du lot en arabe'), max_length=240, required=False,
                             widget=forms.TextInput(attrs={'dir': 'rtl'}))
    reason = forms.CharField(label=_('Justification'), max_length=500, required=False, widget=forms.Textarea)


class CdcItemForm(VersionedForm):
    reason = forms.CharField(label=_('Justification'), max_length=500, required=False, widget=forms.Textarea)
    refresh_catalog = forms.BooleanField(label=_('Actualiser explicitement la fiche à partir du catalogue commun'), required=False,
        help_text=_('La désignation, les spécifications, le conditionnement et l’unité seront repris du catalogue. Les anciennes révisions resteront inchangées.'))

    class Meta:
        model = CdcItem
        fields = ['article', 'purchase_unit', 'designation', 'specifications', 'unit_label', 'packaging',
                  'quantity', 'details', 'active', 'estimated_price', 'tax_rate', 'price_source', 'currency']

    def __init__(self, *args, dossier, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expected_version'].initial = dossier.version
        articles = Article.objects.filter(active=True)
        if dossier.work.category_id:
            articles = articles.filter(category_id=dossier.work.category_id)
        self.fields['article'].queryset = articles
        self.fields['purchase_unit'].queryset = Unit.objects.filter(active=True)
        for name in ('designation', 'unit_label'):
            self.fields[name].required = False
        if not work_allowed(self.user, dossier.work, costs=True):
            for name in ('estimated_price', 'tax_rate', 'price_source', 'currency'):
                del self.fields[name]
        groups = [(_('Référentiel commun'), ['article', 'purchase_unit', 'refresh_catalog']),
                  (_('Besoin technique'), ['designation', 'specifications', 'unit_label', 'packaging', 'quantity', 'details', 'active'])]
        if 'estimated_price' in self.fields:
            groups.append((_('Estimation interne'), ['estimated_price', 'tax_rate', 'price_source', 'currency']))
        groups.append((_('Historique'), ['reason']))
        self.groups = [{'title': label, 'fields': [self[field] for field in fields]} for label, fields in groups]

    def _post_clean(self):
        if self.cleaned_data.get('article') is not None and self.cleaned_data.get('purchase_unit') is not None:
            article, unit = self.cleaned_data['article'], self.cleaned_data['purchase_unit']
            if not self.cleaned_data.get('designation'):
                self.cleaned_data['designation'] = article.name
            if not self.cleaned_data.get('unit_label'):
                self.cleaned_data['unit_label'] = unit.name
        super()._post_clean()


class CdcDecisionForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label=_('Compte rendu'), max_length=500, required=False, widget=forms.Textarea)


class CdcApprovalForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    generation = forms.ModelChoiceField(label=_('PDF examiné'), queryset=CdcGeneration.objects.none())
    reviewed_pages = forms.IntegerField(label=_('Nombre de pages examinées'), min_value=1)
    statement = forms.CharField(label=_('Justification de validation'), max_length=500, widget=forms.Textarea)
    visual_review = forms.BooleanField(label=_('J’ai examiné toutes les pages du PDF et vérifié leur présentation'))
    content_review = forms.BooleanField(label=_('J’ai vérifié le contenu institutionnel, technique et administratif destiné à la diffusion'))

    def __init__(self, *args, dossier, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['generation'].queryset = CdcGeneration.objects.filter(revision__dossier=dossier, revision__number=dossier.revision_number)
        self.fields['generation'].label_from_instance = lambda value: str(_('Révision %(revision)s — %(pages)s pages')) % {'revision': value.revision.number, 'pages': value.pages}


class CdcParagraphForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    paragraph_id = forms.CharField(widget=forms.HiddenInput, max_length=160)
    value = forms.CharField(label=_('Texte de la clause'), max_length=100000, widget=forms.Textarea, required=False)
    reason = forms.CharField(label=_('Justification de la modification'), max_length=500, widget=forms.Textarea)


class CdcDuplicateForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reference=forms.RegexField(label=_('Nouvelle référence'),max_length=90,regex=r'^[0-9]{1,4}/SME/SDFM/SG/ESSBO/[0-9]{4}$')
    title=forms.CharField(label=_('Intitulé du nouveau dossier'),max_length=255)
    assignee=forms.ModelChoiceField(label=_('Membre chargé de préparer le nouveau cahier des charges'),queryset=get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES),required=False)
    due_on=forms.DateField(label=_('Échéance'),required=False,widget=forms.DateInput(attrs={'type':'date'}))
    priority=forms.ChoiceField(label=_('Priorité'),choices=WorkItem.Priority.choices,initial=WorkItem.Priority.NORMAL)
    instructions=forms.CharField(label=_('Consignes'),required=False,widget=forms.Textarea)
    allow_costs=forms.BooleanField(label=_('Autoriser l’accès aux estimations financières'),required=False)
    copy_estimates=forms.BooleanField(label=_('Reprendre explicitement les estimations internes'),required=False,help_text=_('Par défaut, les prix et taxes ne sont pas recopiés afin d’éviter de réutiliser des estimations obsolètes.'))
    reason=forms.CharField(label=_('Justification de la duplication'),max_length=500,widget=forms.Textarea)

class CdcArchiveForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    reason=forms.CharField(label=_('Justification de l’archivage'),max_length=500,widget=forms.Textarea)

class CdcProcurementForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    plan_reference=forms.CharField(label=_('Référence du plan d’approvisionnement'),max_length=90)
    year=forms.IntegerField(label=_('Année du plan'),min_value=2000,max_value=2100)
    assignee=forms.ModelChoiceField(label=_('Responsable du plan'),queryset=get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES),required=False)
    reason=forms.CharField(label=_('Justification / origine du besoin'),max_length=500,widget=forms.Textarea)
