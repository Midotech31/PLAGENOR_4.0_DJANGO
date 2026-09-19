from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import patch

import pyotp
from django.core.cache import cache
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import User
from accounts.totp import consume_totp, enable_totp, matching_step


NOW = 1800000000
SEED = 'JBSWY3DPEHPK3PXP'


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TotpReplayTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('mfa-user', 'mfa@example.test', 'Mfa-test-password!2026', role='CLIENT')
        self.user.set_totp_secret(SEED)
        self.user.totp_enabled = True
        self.user.save()

    def test_period_is_consumed_once_across_stale_instances(self):
        stale = User.objects.get(pk=self.user.pk)
        code = pyotp.TOTP(SEED).at(NOW)
        self.assertTrue(consume_totp(self.user, code, now=NOW))
        self.assertFalse(consume_totp(stale, code, now=NOW))
        self.assertTrue(consume_totp(stale, pyotp.TOTP(SEED).at(NOW + 30), now=NOW + 30))
        self.assertFalse(consume_totp(self.user, code, now=NOW + 30))
        stale.refresh_from_db()
        self.assertEqual(stale.totp_last_step, NOW // 30 + 1)

    def test_invalid_expired_future_and_disabled_codes(self):
        for code in ('', '123', 'abcdef', None, pyotp.TOTP(SEED).at(NOW - 60)):
            self.assertFalse(consume_totp(self.user, code, now=NOW))
        self.assertIsNone(matching_step('', '123456', NOW))
        self.assertEqual(matching_step(SEED, pyotp.TOTP(SEED).at(NOW - 30), NOW), NOW // 30 - 1)
        self.assertTrue(consume_totp(self.user, pyotp.TOTP(SEED).at(NOW + 30), now=NOW))
        self.assertFalse(consume_totp(self.user, pyotp.TOTP(SEED).at(NOW), now=NOW))
        self.user.is_active = False
        self.assertFalse(consume_totp(self.user, pyotp.TOTP(SEED).at(NOW + 60), now=NOW + 60))

    def test_password_then_same_code_in_two_sessions(self):
        from django.test import Client
        code = pyotp.TOTP(SEED).at(NOW)
        accepted = []
        with patch('time.time', return_value=NOW):
            for _ in range(2):
                client = Client()
                response = client.post(reverse('accounts:login'), {'username': self.user.username, 'password': 'Mfa-test-password!2026'})
                self.assertRedirects(response, reverse('accounts:two_factor_verify'), fetch_redirect_response=False)
                self.assertNotIn('_auth_user_id', client.session)
                client.post(reverse('accounts:two_factor_verify'), {'code': code})
                accepted.append('_auth_user_id' in client.session)
            fresh = Client()
            fresh.post(reverse('accounts:two_factor_verify'), {'code': code})
            self.assertNotIn('_auth_user_id', fresh.session)
            fresh.post(reverse('accounts:login'), {'username': self.user.username, 'password': 'wrong'})
            self.assertNotIn('pending_2fa_user', fresh.session)
        self.assertEqual(accepted, [True, False])

    def test_enrollment_claims_period_and_disabling_requires_fresh_code(self):
        self.user.totp_enabled = False
        self.user.totp_secret = ''
        self.user.save()
        self.assertFalse(enable_totp(self.user, SEED, 'wrong', now=NOW))
        self.assertTrue(enable_totp(self.user, SEED, pyotp.TOTP(SEED).at(NOW), now=NOW))
        self.assertFalse(enable_totp(self.user, SEED, pyotp.TOTP(SEED).at(NOW), now=NOW))
        self.assertFalse(consume_totp(self.user, pyotp.TOTP(SEED).at(NOW), disable=True, now=NOW))
        self.assertTrue(consume_totp(self.user, pyotp.TOTP(SEED).at(NOW + 30), disable=True, now=NOW + 30))
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertEqual(self.user.totp_secret, '')

    def test_disable_password_failure_does_not_consume_code(self):
        self.client.force_login(self.user)
        code = pyotp.TOTP(SEED).at(NOW)
        with patch('time.time', return_value=NOW):
            self.client.post(reverse('accounts:two_factor_disable'), {'password': 'wrong', 'code': code})
            self.user.refresh_from_db()
            self.assertIsNone(self.user.totp_last_step)
            self.client.post(reverse('accounts:two_factor_disable'), {'password': 'Mfa-test-password!2026', 'code': code})
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)


class TotpConcurrencyTests(TransactionTestCase):
    def test_concurrent_same_code_has_one_winner(self):
        user = User.objects.create_user('parallel-mfa', 'parallel@example.test', 'Concurrent-password!2026')
        user.set_totp_secret(SEED)
        user.totp_enabled = True
        user.save()
        barrier = threading.Barrier(2)
        code = pyotp.TOTP(SEED).at(NOW)

        def attempt():
            close_old_connections()
            try:
                local = User.objects.get(pk=user.pk)
                barrier.wait(timeout=5)
                return consume_totp(local, code, now=NOW)
            finally:
                connections['default'].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(results), [False, True])
        user.refresh_from_db()
        self.assertEqual(user.totp_last_step, NOW // 30)
