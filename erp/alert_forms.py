from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .permissions import TEAM_ROLES,is_manager
from .work_forms import OperationForm


class AlertPolicyForm(OperationForm):
    expected_version=forms.IntegerField(widget=forms.HiddenInput)
    expiry_days=forms.CharField(label=_('Seuils de péremption en jours'),help_text=_('Séparez les seuils par des virgules, par exemple 180, 90, 60, 30, 7.'))
    dormant_days=forms.IntegerField(label=_('Absence de consommation en jours'),min_value=1,max_value=3660)
    receipt_pending_days=forms.IntegerField(label=_('Réception en attente depuis, en jours'),min_value=0,max_value=365)
    occupancy_percent=forms.DecimalField(label=_('Seuil d’occupation des positions (%)'),max_digits=5,decimal_places=2,min_value=.01,max_value=100)
    overstock_multiplier=forms.DecimalField(label=_('Surstock : multiple du stock cible'),max_digits=6,decimal_places=2,min_value=1,max_value=100)
    digest_enabled=forms.BooleanField(label=_('Activer les synthèses quotidiennes'),required=False)

    def clean_expiry_days(self):
        try:
            values=[int(value.strip()) for value in self.cleaned_data['expiry_days'].split(',')]
        except ValueError as exc:
            raise forms.ValidationError(_('Utilisez des nombres entiers séparés par des virgules.')) from exc
        return values


class AlertActionForm(OperationForm):
    reason=forms.CharField(label=_('Action engagée / observation'),max_length=500,widget=forms.Textarea)
    assignee=forms.ModelChoiceField(label=_('Créer une tâche de contrôle pour un membre'),
        queryset=get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES),required=False)

    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        if not is_manager(user):
            del self.fields['assignee']
