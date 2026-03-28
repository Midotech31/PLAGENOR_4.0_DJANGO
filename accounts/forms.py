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
    student_level = forms.ChoiceField(
        choices=[
            ('', '— Sélectionner —'),
            ('master', 'Master (fin de cycle)'),
            ('ingenieur', 'Ingéniorat (fin de cycle)'),
            ('doctorat', 'Doctorat'),
        ],
        required=False,
        label='Niveau',
    )
    laboratory = forms.CharField(max_length=200, required=False, label='Laboratoire')
    supervisor = forms.CharField(max_length=200, required=False, label='Directeur de recherche')
    phone = forms.CharField(
        max_length=50,
        required=False,
        label='Téléphone',
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'role', 'organization', 'student_level', 'laboratory', 'supervisor', 'phone',
            'password1', 'password2',
        )
