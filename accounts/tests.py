"""Tests for the registration form: organization type (+ "Autre" detail)
and country, plus duplicate-email rejection.
"""
from django.test import TestCase

from accounts.forms import RegistrationForm
from accounts.models import User


def _base_data(**over):
    data = {
        'username': 'newuser', 'first_name': 'A', 'last_name': 'B',
        'email': 'new@example.com', 'role': 'CLIENT',
        'organization': 'Acme', 'organization_type': 'entreprise',
        'organization_type_other': '', 'country': 'DZ',
        'password1': 'Str0ngPass!23', 'password2': 'Str0ngPass!23',
    }
    data.update(over)
    return data


class RegistrationFormTests(TestCase):
    def test_valid_registration_saves_org_type_and_country(self):
        form = RegistrationForm(data=_base_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.organization_type, 'entreprise')
        self.assertEqual(user.country, 'DZ')

    def test_other_requires_detail(self):
        form = RegistrationForm(data=_base_data(
            organization_type='autre', organization_type_other=''))
        self.assertFalse(form.is_valid())
        self.assertIn('organization_type_other', form.errors)

    def test_other_with_detail_is_valid(self):
        form = RegistrationForm(data=_base_data(
            organization_type='autre', organization_type_other='Coopérative'))
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.organization_type_other, 'Coopérative')

    def test_duplicate_email_rejected(self):
        User.objects.create(username='existing', email='dup@example.com')
        form = RegistrationForm(data=_base_data(
            username='other', email='dup@example.com'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_country_choices_include_algeria_default(self):
        form = RegistrationForm()
        codes = [c for c, _ in form.fields['country'].choices]
        self.assertEqual(codes[0], 'DZ')
