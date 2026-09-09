"""IBTIKAR signup completeness is enforced even without browser validation."""
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from accounts.forms import RegistrationForm
from accounts.models import User


def requester_data():
    return {
        'username': 'complete-requester', 'first_name': 'Amine', 'last_name': 'Test',
        'email': 'student@example.test', 'role': 'REQUESTER',
        'organization': 'Université de test', 'organization_type': 'academique',
        'country': 'DZ', 'student_level': 'doctorat', 'laboratory': 'Laboratoire de test',
        'supervisor': 'Encadrant Test', 'supervisor_email': 'supervisor@example.test',
        'ibtikar_id': 'IDGRSTD12345', 'phone': '0554050460', 'wilaya': '31', 'gender': 'M',
        'password1': 'DifferentPass!2026', 'password2': 'DifferentPass!2026',
    }


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class RequiredRequesterRegistrationTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_every_applicable_field_is_required_on_server(self):
        data = requester_data()
        self.assertTrue(RegistrationForm(data=data).is_valid())
        for name in data:
            with self.subTest(field=name):
                missing = {key: value for key, value in data.items() if key != name}
                form = RegistrationForm(data=missing)
                self.assertFalse(form.is_valid())
                self.assertIn(name, form.errors)
        for name in ('first_name', 'last_name', 'laboratory', 'supervisor', 'phone'):
            with self.subTest(blank=name):
                form = RegistrationForm(data={**data, name: '   '})
                self.assertFalse(form.is_valid())
                self.assertIn(name, form.errors)

    def test_invalid_supervisor_email_and_identifier_are_rejected(self):
        for field, value in [('supervisor_email', 'not-an-email'),
                             ('ibtikar_id', 'IDGRSTD1234'), ('ibtikar_id', 'OTHER12345')]:
            with self.subTest(field=field, value=value):
                form = RegistrationForm(data={**requester_data(), field: value})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_direct_post_cannot_create_an_incomplete_account(self):
        data = requester_data()
        del data['supervisor_email']
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn('supervisor_email', response.context['form'].errors)
        self.assertFalse(User.objects.filter(username=data['username']).exists())

    def test_registration_persists_supervisor_email_and_displays_it_on_profile(self):
        data = requester_data()
        response = self.client.post(reverse('accounts:register'), data)
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username=data['username'])
        self.assertEqual(user.supervisor_email, data['supervisor_email'])
        response = self.client.get(reverse('accounts:profile'))
        self.assertContains(response, data['supervisor_email'])

    def test_client_registration_does_not_require_academic_or_demographic_fields(self):
        data = requester_data()
        data['role'] = 'CLIENT'
        for field in ('student_level', 'laboratory', 'supervisor', 'supervisor_email',
                      'ibtikar_id', 'phone', 'wilaya', 'gender'):
            del data[field]
        form = RegistrationForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().supervisor_email, '')

    def test_other_organisation_detail_is_only_required_when_selected(self):
        form = RegistrationForm(data={**requester_data(), 'organization_type': 'autre'})
        self.assertFalse(form.is_valid())
        self.assertIn('organization_type_other', form.errors)
        form = RegistrationForm(data={**requester_data(), 'organization_type': 'autre',
                                      'organization_type_other': 'Centre de recherche'})
        self.assertTrue(form.is_valid(), form.errors)

    def test_initial_form_has_required_fields_and_translated_supervisor_email(self):
        for lang, label in [('fr', 'Email du directeur de thèse / encadrant'),
                            ('en', 'Thesis supervisor / academic supervisor email'),
                            ('ar', 'البريد الإلكتروني للمشرف على الأطروحة / المؤطّر')]:
            with self.subTest(language=lang), override(lang):
                form = RegistrationForm()
                self.assertTrue(form.fields['supervisor_email'].required)
                self.assertEqual(str(form.fields['supervisor_email'].label), label)
        self.assertFalse(RegistrationForm(initial={'role': 'CLIENT'}).fields['phone'].required)
