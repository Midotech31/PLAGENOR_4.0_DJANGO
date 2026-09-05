"""Tests for the registration form: organization type (+ "Autre" detail)
and country, plus duplicate-email rejection.
"""
from django.test import TestCase

from accounts.forms import RegistrationForm
from accounts.models import MemberProfile, Technique, User
from notifications.models import Notification


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
        user.set_totp_secret(secret)
        user.totp_enabled = True
        user.save(update_fields=['totp_secret', 'totp_enabled'])
        return secret

    @override_settings(PRIVILEGED_MFA_ENFORCEMENT=True)
    def test_privileged_user_without_2fa_is_sent_to_enrollment(self):
        resp = self.client.post('/accounts/login/',
                                {'username': 'tfa', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/accounts/2fa/setup/')

    @override_settings(PRIVILEGED_MFA_ENFORCEMENT=False)
    def test_disabled_enforcement_does_not_force_enrollment(self):
        resp = self.client.post('/accounts/login/',
                                {'username': 'tfa', 'password': 'RightPass!42'})
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.url, '/accounts/2fa/setup/')
        self.assertIn('_auth_user_id', self.client.session)

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
        self.assertNotEqual(self.user.totp_secret, secret)
        self.assertTrue(self.user.totp_secret.startswith('fernet$'))
        self.assertEqual(self.user.get_totp_secret(), secret)

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
        resp = self.client.post(
            f'/dashboard/home/user/{self.user.pk}/reset-2fa/',
            {'reason': 'Lost authenticator device'})
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret, '')
        self.assertTrue(Notification.objects.filter(
            user=self.user, notification_type='SECURITY').exists())

    def test_superadmin_reset_requires_a_reason(self):
        self._enable_totp(self.user)
        admin = User.objects.create_user(
            username='sa-no-reason', password='x', role='SUPER_ADMIN',
            is_superuser=True, is_staff=True)
        self.client.force_login(admin)
        self.client.post(
            f'/dashboard/home/user/{self.user.pk}/reset-2fa/',
            {'reason': 'short'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)

    def test_self_disable_requires_password_and_current_totp(self):
        import pyotp
        secret = self._enable_totp(self.user)
        self.client.force_login(self.user)
        self.client.post('/accounts/2fa/disable/', {
            'password': 'wrong', 'code': pyotp.TOTP(secret).now(),
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)
        self.client.post('/accounts/2fa/disable/', {
            'password': 'RightPass!42', 'code': pyotp.TOTP(secret).now(),
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)

    @override_settings(PRIVILEGED_MFA_ENFORCEMENT=True)
    def test_middleware_blocks_privileged_session_until_enrollment(self):
        self.client.force_login(self.user)
        response = self.client.get('/dashboard/analyst/')
        self.assertRedirects(response, '/accounts/2fa/setup/')

    def test_plaintext_totp_migration_is_idempotent(self):
        from django.core.management import call_command
        self.user.totp_secret = 'JBSWY3DPEHPK3PXP'
        self.user.totp_enabled = True
        self.user.save(update_fields=['totp_secret', 'totp_enabled'])
        call_command('migrate_totp_secrets', verbosity=0)
        self.user.refresh_from_db()
        encrypted = self.user.totp_secret
        self.assertTrue(encrypted.startswith('fernet$'))
        self.assertEqual(self.user.get_totp_secret(), 'JBSWY3DPEHPK3PXP')
        call_command('migrate_totp_secrets', verbosity=0)
        self.user.refresh_from_db()
        self.assertEqual(self.user.totp_secret, encrypted)

    def test_enrollment_brute_force_discards_pending_secret(self):
        self.client.force_login(self.user)
        self.client.get('/accounts/2fa/setup/')
        original = self.client.session['pending_totp_secret']
        for _ in range(5):
            response = self.client.post('/accounts/2fa/setup/', {'code': '000000'})
            self.assertEqual(response.status_code, 200)
        response = self.client.post('/accounts/2fa/setup/', {'code': '000000'})
        self.assertRedirects(
            response, '/accounts/2fa/setup/', fetch_redirect_response=False)
        self.assertNotEqual(self.client.session.get('pending_totp_secret'), original)
        self.assertNotIn('pending_totp_attempts', self.client.session)


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
        self.user.must_change_password = True
        self.user.save(update_fields=[
            'login_attempts', 'locked_until', 'must_change_password',
        ])

        self.client.post('/accounts/password-reset/', {'email': 'reset@example.com'})
        # Extract uid/token from the emailed confirm link.
        import re
        m = re.search(r'password-reset/confirm/([^/]+)/([^/\s]+)/', mail.outbox[0].body)
        uidb64, token = m.group(1), m.group(2)
        # Django swaps the token into the session on the first GET.
        r1 = self.client.get(f'/accounts/password-reset/confirm/{uidb64}/{token}/')
        self.assertEqual(r1.status_code, 302)
        r2 = self.client.post(r1.url, {
            'new_password1': 'BrandNew!9942', 'new_password2': 'BrandNew!9942'})
        self.assertEqual(r2.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNew!9942'))
        self.assertEqual(self.user.login_attempts, 0)
        self.assertIsNone(self.user.locked_until)
        self.assertFalse(self.user.must_change_password)


@override_settings(
    STORAGES=_TEST_STORAGES,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AccountPrivacyAndProfileTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_live_email_enumeration_endpoint_is_removed(self):
        User.objects.create_user(
            username='private-account', email='private@example.com',
            password='StrongPass!42', role='CLIENT')
        response = self.client.post(
            '/accounts/check-email/',
            data='{"email":"private@example.com"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_guest_conversion_does_not_disclose_existing_account(self):
        from django.core import mail
        User.objects.create_user(
            username='already', email='already@example.com',
            password='StrongPass!42', role='CLIENT')
        response = self.client.post(
            '/accounts/convert-guest/', {'email': 'already@example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['sent'])
        self.assertNotContains(response, 'Un compte avec cet email existe déjà')
        self.assertEqual(len(mail.outbox), 0)

    def test_member_cannot_self_assign_validated_techniques(self):
        user = User.objects.create_user(
            username='member-profile', email='member@example.com',
            password='StrongPass!42', role='MEMBER')
        profile, _ = MemberProfile.objects.get_or_create(user=user)
        existing = Technique.objects.create(name='PCR', active=True)
        attempted = Technique.objects.create(name='WGS', active=True)
        profile.techniques.add(existing)
        self.client.force_login(user)
        response = self.client.post('/accounts/profile/', {
            'first_name': 'Member', 'last_name': 'One',
            'email': 'attacker-controlled@example.com',
            'techniques': [attempted.pk],
        })
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(user.email, 'member@example.com')
        self.assertEqual(list(profile.techniques.all()), [existing])

    def test_member_profile_renders_competencies_read_only(self):
        user = User.objects.create_user(
            username='member-readonly', email='readonly@example.com',
            password='StrongPass!42', role='MEMBER')
        profile, _ = MemberProfile.objects.get_or_create(user=user)
        technique = Technique.objects.create(name='MALDI-TOF', active=True)
        profile.techniques.add(technique)
        self.client.force_login(user)
        response = self.client.get('/accounts/profile/')
        self.assertContains(response, 'MALDI-TOF')
        self.assertNotContains(response, 'name="techniques"')
        self.assertContains(response, 'readonly')
