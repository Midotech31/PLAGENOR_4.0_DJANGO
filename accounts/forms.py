from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User


class RegistrationForm(UserCreationForm):
    role = forms.ChoiceField(choices=[
        ('REQUESTER', 'Demandeur IBTIKAR (étudiant/chercheur)'),
        ('CLIENT', 'Client GENOCLAB (externe)'),
    ])
    organization = forms.CharField(
        max_length=200,
        required=True,
        label='Université / Organisation',
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label='Téléphone',
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'organization', 'phone',
            'password1', 'password2',
        )
