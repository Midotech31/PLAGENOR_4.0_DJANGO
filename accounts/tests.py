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
        from django.core.cache import cache
        cache.clear()  # isolate the per-IP login rate-limit counter
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


@override_settings(STORAGES=_TEST_STORAGES)
class TwoFactorTests(TestCase):
    """Opt-in TOTP: enrollment, login gate, and Super Admin reset."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(
            username='tfa', password='RightPass!42', role='MEMBER')

    def _enable_totp(self, user):
        import pyotp
        secret = pyotp.random_base32()
        user.totp_secret = secret
        user.totp_enabled = True
        user.save(update_fields=['totp_secret', 'totp_enabled'])
        return secret

    def test_user_without_2fa_logs_in_directly(self):
        resp = self.client.post('/accounts/login/',
                                {'username': 'tfa', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('/2fa/verify', resp.url)

    def test_2fa_user_is_redirected_to_verify_and_not_logged_in(self):
        self._enable_totp(self.user)
        resp = self.client.post('/accounts/login/',
                                {'username': 'tfa', 'password': 'RightPass!42'})
        self.assertRedirects(resp, '/accounts/2fa/verify/')
        # Password alone must NOT authenticate.
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_2fa_correct_code_completes_login(self):
        import pyotp
        secret = self._enable_totp(self.user)
        self.client.post('/accounts/login/',
                         {'username': 'tfa', 'password': 'RightPass!42'})
        code = pyotp.TOTP(secret).now()
        resp = self.client.post('/accounts/2fa/verify/', {'code': code})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    def test_2fa_wrong_code_rejected(self):
        self._enable_totp(self.user)
        self.client.post('/accounts/login/',
                         {'username': 'tfa', 'password': 'RightPass!42'})
        resp = self.client.post('/accounts/2fa/verify/', {'code': '000000'})
        self.assertEqual(resp.status_code, 200)  # re-rendered with error
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verify_without_pending_session_redirects_to_login(self):
        resp = self.client.get('/accounts/2fa/verify/')
        self.assertRedirects(resp, '/accounts/login/')

    def test_enrollment_confirms_with_valid_code(self):
        import pyotp
        self.client.force_login(self.user)
        r1 = self.client.get('/accounts/2fa/setup/')
        secret = self.client.session['pending_totp_secret']
        code = pyotp.TOTP(secret).now()
        r2 = self.client.post('/accounts/2fa/setup/', {'code': code})
        self.assertEqual(r2.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret, secret)

    def test_2fa_brute_force_is_capped(self):
        """Regression: the password step already succeeded, so the account
        lockout no longer applies — wrong codes must be capped here."""
        self._enable_totp(self.user)
        self.client.post('/accounts/login/',
                         {'username': 'tfa', 'password': 'RightPass!42'})
        for _ in range(5):
            r = self.client.post('/accounts/2fa/verify/', {'code': '000000'})
            self.assertEqual(r.status_code, 200)
        # 6th attempt burns the pending session and sends the user back.
        r = self.client.post('/accounts/2fa/verify/', {'code': '000000'})
        self.assertRedirects(r, '/accounts/login/')
        self.assertNotIn('pending_2fa_user', self.client.session)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_2fa_attempt_counter_resets_after_success(self):
        import pyotp
        secret = self._enable_totp(self.user)
        self.client.post('/accounts/login/',
                         {'username': 'tfa', 'password': 'RightPass!42'})
        self.client.post('/accounts/2fa/verify/', {'code': '000000'})  # 1 échec
        r = self.client.post('/accounts/2fa/verify/',
                             {'code': pyotp.TOTP(secret).now()})
        self.assertEqual(r.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertNotIn('pending_2fa_attempts', self.client.session)

    def test_superadmin_reset_disables_2fa(self):
        self._enable_totp(self.user)
        admin = User.objects.create_user(
            username='sa-2fa', password='x', role='SUPER_ADMIN',
            is_superuser=True, is_staff=True)
        self.client.force_login(admin)
        resp = self.client.post(f'/dashboard/home/user/{self.user.pk}/reset-2fa/')
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret, '')


@override_settings(
    STORAGES=_TEST_STORAGES,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class PasswordResetFlowTests(TestCase):
    """End-to-end self-service reset: request → email link → set new password."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()  # isolate the per-IP password-reset rate-limit counter
        self.user = User.objects.create_user(
            username='resetme', email='reset@example.com',
            password='OldPass!42', role='CLIENT')

    def test_request_sends_email_for_existing_address(self):
        from django.core import mail
        resp = self.client.post('/accounts/password-reset/', {'email': 'reset@example.com'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('password-reset/confirm/', mail.outbox[0].body)

    def test_request_silent_for_unknown_address(self):
        from django.core import mail
        resp = self.client.post('/accounts/password-reset/', {'email': 'nobody@example.com'})
        self.assertEqual(resp.status_code, 302)  # same response — no enumeration
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_sets_new_password_and_clears_lock(self):
        from django.core import mail
        from django.utils import timezone
        # Lock the account first, then reset.
        self.user.login_attempts = 5
        self.user.locked_until = timezone.now() + timezone.timedelta(minutes=15)
        self.user.save(update_fields=['login_attempts', 'locked_until'])

        self.client.post('/accounts/password-reset/', {'email': 'reset@example.com'})
        # Extract uid/token from the emailed confirm link.
        import re
        m = re.search(r'password-reset/confirm/([^/]+)/([^/\s]+)/', mail.outbox[0].body)
        uidb64, token = m.group(1), m.group(2)
        # Django swaps the token into the session on the first GET.
        r1 = self.client.get(f'/accounts/password-reset/confirm/{uidb64}/{token}/')
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.post(r1.url, {
            'new_password1': 'BrandNew!99', 'new_password2': 'BrandNew!99'})
        self.assertEqual(r2.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNew!99'))
        self.assertEqual(self.user.login_attempts, 0)
        self.assertIsNone(self.user.locked_until)
