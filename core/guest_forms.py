from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class GuestContactForm(forms.Form):
    guest_name = forms.CharField(max_length=200, label=_('Nom complet'))
    guest_email = forms.EmailField(max_length=254, label=_('Email'))
    guest_phone = forms.CharField(max_length=50, required=False, label=_('Téléphone'))


def guest_contact(data):
    form = GuestContactForm(data)
    if not form.is_valid():
        raise ValidationError(form.errors.as_data())
    return form.cleaned_data
