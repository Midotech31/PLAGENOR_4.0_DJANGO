"""The system administration entry point shares PLAGENOR's role and MFA gates."""
from urllib.parse import parse_qs, urlsplit

import pyotp
from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.totp import encrypt_secret


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class SystemAdministrationSecurityTests(TestCase):
    def test_technical_flags_cannot_grant_system_access_to_other_roles(self):
        for role, _ in User.ROLE_CHOICES:
            if role == 'SUPER_ADMIN':
                continue
            with self.subTest(role=role):
                user = User.objects.create_user(
                    'admin-boundary-' + role, role=role,
                    is_staff=True, is_superuser=True,
                )
                self.client.force_login(user)
                response = self.client.get(reverse('admin:accounts_user_changelist'))
                self.assertNotEqual(response.status_code, 200)
                self.assertEqual(self.client.get(reverse('admin:login')).status_code, 403)

    def test_old_admin_login_cannot_bypass_enabled_mfa(self):
        secret = 'JBSWY3DPEHPK3PXP'
        user = User.objects.create_superuser(
            'mfa-system-admin', password='Mfa-test-only!2026',
            totp_enabled=True, totp_secret=encrypt_secret(secret),
        )
        credentials = {'username': user.username, 'password': 'Mfa-test-only!2026'}
        response = self.client.post(reverse('admin:login'), credentials)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(urlsplit(response.url).path, reverse('accounts:login'))
        response = self.client.post(reverse('accounts:login'), {
            **credentials, 'next': reverse('admin:index'),
        })
        self.assertRedirects(response, reverse('accounts:two_factor_verify'))
        self.assertNotIn('_auth_user_id', self.client.session)
        response = self.client.post(reverse('accounts:two_factor_verify'), {
            'code': pyotp.TOTP(secret).now(),
        })
        self.assertRedirects(response, reverse('admin:index'))
        self.assertEqual(self.client.get(reverse('admin:login')).url, reverse('admin:index'))

    def test_anonymous_login_rejects_external_and_insecure_next(self):
        for next_url in ('https://example.invalid/phish', '//example.invalid', 'http://testserver/admin/'):
            with self.subTest(next_url=next_url):
                response = self.client.get(reverse('admin:login'), {'next': next_url}, secure=True)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(urlsplit(response.url).path, reverse('accounts:login'))
                self.assertEqual(parse_qs(urlsplit(response.url).query)['next'], [reverse('admin:index')])
        response = self.client.get(reverse('admin:login'), {'next': reverse('admin:accounts_user_changelist')})
        self.assertEqual(parse_qs(urlsplit(response.url).query)['next'], [reverse('admin:accounts_user_changelist')])

    def test_system_role_still_requires_active_staff_flags(self):
        user = User.objects.create_superuser('active-system-admin')
        from django.test import RequestFactory
        request = RequestFactory().get('/admin/')
        request.user = user
        self.assertTrue(admin.site.has_permission(request))
        user.is_active = False
        self.assertFalse(admin.site.has_permission(request))
        user.is_active = True
        user.is_staff = False
        self.assertFalse(admin.site.has_permission(request))

    def test_role_demotion_takes_effect_in_an_existing_session(self):
        user = User.objects.create_superuser('demoted-system-admin')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code, 200)
        User.objects.filter(pk=user.pk).update(role='PLATFORM_ADMIN')
        self.assertEqual(self.client.get(reverse('admin:login')).status_code, 403)
        self.assertEqual(self.client.get(reverse('dashboard:superadmin')).status_code, 403)
        self.assertEqual(self.client.get(reverse('dashboard:admin_ops')).status_code, 200)

    def test_language_changes_require_post_and_csrf_and_persist(self):
        user = User.objects.create_user('language-boundary', preferred_language='ar')
        self.client.force_login(user)
        response = self.client.get(reverse('switch_language'))
        self.assertEqual(response.status_code, 405)
        user.refresh_from_db()
        self.assertEqual(user.preferred_language, 'ar')
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)
        self.assertEqual(csrf_client.post(reverse('switch_language'), {'language': 'en'}).status_code, 403)
        response = self.client.post(reverse('switch_language'), {'language': 'en', 'next': '/help/'})
        self.assertEqual(response.url, '/help/')
        user.refresh_from_db()
        self.assertEqual(user.preferred_language, 'en')
