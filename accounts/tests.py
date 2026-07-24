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


from django.test import override_settings

# The login template references {% static %}; WhiteNoise's manifest storage
# requires a collectstatic run, which tests don't do. Use plain storages here.
_TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=_TEST_STORAGES)
class LoginLockoutTests(TestCase):
    """Brute-force protection: 5 failures lock the account for 15 minutes."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='lockme', password='RightPass!42', role='CLIENT')

    def _fail(self, n=1):
        for _ in range(n):
            self.client.post('/accounts/login/',
                             {'username': 'lockme', 'password': 'wrong'})

    def test_failures_increment_counter(self):
        self._fail(3)
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_attempts, 3)
        self.assertIsNone(self.user.locked_until)

    def test_fifth_failure_locks_account(self):
        self._fail(5)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.locked_until)

    def test_locked_account_rejects_correct_password(self):
        self._fail(5)
        resp = self.client.post('/accounts/login/',
                                {'username': 'lockme', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 200)  # re-rendered form, not a redirect
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_successful_login_resets_counter(self):
        self._fail(3)
        resp = self.client.post('/accounts/login/',
                                {'username': 'lockme', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 302)  # logged in
        self.user.refresh_from_db()
        self.assertEqual(self.user.login_attempts, 0)

    def test_lock_expires(self):
        from django.utils import timezone
        self._fail(5)
        self.user.refresh_from_db()
        self.user.locked_until = timezone.now() - timezone.timedelta(minutes=1)
        self.user.save(update_fields=['locked_until'])
        resp = self.client.post('/accounts/login/',
                                {'username': 'lockme', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 302)  # lock in the past → login OK
