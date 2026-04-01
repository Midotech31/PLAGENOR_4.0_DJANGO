import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import EmailValidator, RegexValidator
from django.utils.translation import gettext_lazy as _
from .models import User
from .choices import (
    IBTIKAR_POSITION_CHOICES,
    GENOCLAB_POSITION_CHOICES,
    MEMBER_POSITION_CHOICES,
    ALL_POSITION_CHOICES,
    get_position_choices_for_channel,
)

_email_validator = EmailValidator()

phone_regex = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message=_("Numéro de téléphone invalide. Format: '+999999999' jusqu'à 15 chiffres.")
)


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
        validators=[phone_regex],
    )
    position = forms.ChoiceField(
        choices=[('', _('— Sélectionner —'))] + IBTIKAR_POSITION_CHOICES,
        required=False,
        label=_('Position'),
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'organization', 'student_level', 'student_level_other',
            'laboratory', 'supervisor', 'ibtikar_id', 'phone', 'position',
            'password1', 'password2',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['position'].choices = [('', _('— Sélectionner —'))] + IBTIKAR_POSITION_CHOICES

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('Cet email est déjà enregistré'))
        return email

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        position = cleaned_data.get('position')

        if role == 'REQUESTER' and not position:
            self.add_error('position', _('La position est requise pour les demandeurs IBTIKAR.'))

        return cleaned_data


class IbtikarRegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=200,
        required=True,
        label=_('Nom complet'),
        help_text=_('Prénom et nom de famille'),
    )
    email = forms.EmailField(
        required=True,
        label=_('Email'),
        validators=[_email_validator],
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    phone = forms.CharField(
        max_length=50,
        required=True,
        label=_('Téléphone'),
        validators=[phone_regex],
    )
    institution = forms.CharField(
        max_length=200,
        required=True,
        label=_('Université / École'),
    )
    laboratory = forms.CharField(
        max_length=200,
        required=False,
        label=_('Laboratoire'),
    )
    position = forms.ChoiceField(
        choices=[('', _('— Sélectionner —'))] + IBTIKAR_POSITION_CHOICES,
        required=True,
        label=_('Position'),
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_('Mot de passe'),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_('Confirmer le mot de passe'),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('Cet email est déjà enregistré'))
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if len(full_name.split()) < 2:
            raise forms.ValidationError(_('Veuillez entrer votre prénom et nom de famille.'))
        return full_name

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', _('Les mots de passe ne correspondent pas.'))

        return cleaned_data

    def get_first_name_last_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        parts = full_name.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return parts[0], ' '.join(parts[1:])


class GenoclabRegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=200,
        required=True,
        label=_('Nom complet'),
        help_text=_('Prénom et nom de famille'),
    )
    email = forms.EmailField(
        required=True,
        label=_('Email'),
        validators=[_email_validator],
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )
    phone = forms.CharField(
        max_length=50,
        required=True,
        label=_('Téléphone'),
        validators=[phone_regex],
    )
    organization = forms.CharField(
        max_length=200,
        required=True,
        label=_('Organisation / Institution'),
    )
    sector = forms.ChoiceField(
        choices=[('', _('— Sélectionner —'))] + GENOCLAB_POSITION_CHOICES,
        required=True,
        label=_('Secteur / Position'),
    )
    address = forms.CharField(
        max_length=300,
        required=True,
        label=_('Adresse'),
    )
    country = forms.CharField(
        max_length=100,
        required=True,
        label=_('Pays'),
    )
    password = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_('Mot de passe'),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput,
        required=True,
        label=_('Confirmer le mot de passe'),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('Cet email est déjà enregistré'))
        return email

    def clean_full_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        if len(full_name.split()) < 2:
            raise forms.ValidationError(_('Veuillez entrer votre prénom et nom de famille.'))
        return full_name

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', _('Les mots de passe ne correspondent pas.'))

        return cleaned_data

    def get_first_name_last_name(self):
        full_name = self.cleaned_data.get('full_name', '').strip()
        parts = full_name.split()
        if len(parts) == 2:
            return parts[0], parts[1]
        else:
            return parts[0], ' '.join(parts[1:])


class ProfileUpdateForm(forms.ModelForm):
    email = forms.EmailField(
        required=True,
        label=_('Email'),
        validators=[_email_validator],
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label=_('Téléphone'),
        validators=[phone_regex],
    )
    position = forms.ChoiceField(
        required=False,
        label=_('Position'),
    )
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label=_('Prénom'),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label=_('Nom'),
    )
    organization = forms.CharField(
        max_length=200,
        required=False,
        label=_('Organisation'),
    )
    laboratory = forms.CharField(
        max_length=200,
        required=False,
        label=_('Laboratoire'),
    )

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'email',
            'phone',
            'position',
            'organization',
            'laboratory',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance
        if user and user.role:
            if user.role == 'REQUESTER':
                self.fields['position'].choices = get_position_choices_for_channel('IBTIKAR')
            elif user.role == 'CLIENT':
                self.fields['position'].choices = get_position_choices_for_channel('GENOCLAB')
            elif user.role == 'MEMBER':
                self.fields['position'].choices = get_position_choices_for_channel('MEMBER')
            else:
                self.fields['position'].choices = [('', _('— Sélectionner —'))] + ALL_POSITION_CHOICES
        else:
            self.fields['position'].choices = [('', _('— Sélectionner —'))] + ALL_POSITION_CHOICES
