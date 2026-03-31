from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import EmailValidator
from django.utils.translation import gettext_lazy as _
from .models import User

_email_validator = EmailValidator()


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        label=_('Email'),
        validators=[_email_validator],
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    role = forms.ChoiceField(choices=[
        ('REQUESTER', _('Demandeur IBTIKAR (étudiant/chercheur)')),
        ('CLIENT', _('Client GENOCLAB (externe)')),
    ], label=_('Rôle'))
    organization = forms.CharField(
        max_length=200,
        required=True,
        label=_('Université / Organisation'),
    )
    student_level = forms.ChoiceField(
        choices=[('', _('— Sélectionner —'))] + User.STUDENT_LEVEL_CHOICES,
        required=False,
        label=_('Niveau'),
    )
    student_level_other = forms.CharField(
        max_length=200, required=False,
        label=_('Autre niveau (à préciser)'),
        widget=forms.TextInput(attrs={'placeholder': _('Préciser...')}),
    )
    laboratory = forms.CharField(max_length=200, required=False, label=_('Laboratoire'))
    supervisor = forms.CharField(max_length=200, required=False, label=_('Directeur de recherche'))
    ibtikar_id = forms.CharField(
        max_length=20, required=False,
        label=_('Identifiant IBTIKAR-DGRSDT'),
        help_text=_('Format: IDGRSTDXXXXX'),
        widget=forms.TextInput(attrs={'placeholder': 'IDGRSTD12345', 'pattern': 'IDGRSTD[0-9]{5}'})
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label=_('Téléphone'),
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'organization', 'student_level', 'student_level_other', 'laboratory', 'supervisor', 'ibtikar_id', 'phone',
            'password1', 'password2',
        )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('Cet email est déjà enregistré'))
        return email
