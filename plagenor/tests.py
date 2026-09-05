import os
import subprocess
import sys
from pathlib import Path

from django.contrib.auth import SESSION_KEY
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TestCase

from accounts.models import User
from plagenor.urls_e2e import create_e2e_session


BASE_DIR = Path(__file__).resolve().parent.parent
FERNET_TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class E2ESessionBootstrapTests(TestCase):
    """The browser shortcut must remain test-only and loopback-only."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='admin', role='SUPER_ADMIN', password=None,
        )
        self.factory = RequestFactory()

    def _request(self, *, method='post', remote_addr='127.0.0.1'):
        request = getattr(self.factory, method)(
            '/__e2e__/session/admin/', REMOTE_ADDR=remote_addr,
        )
        SessionMiddleware(lambda _request: None).process_request(request)
        request.session.save()
        return request

    def test_loopback_post_authenticates_seeded_fixture(self):
        request = self._request()

        response = create_e2e_session(request, 'admin')

        self.assertEqual(response.status_code, 204)
        self.assertEqual(request.session[SESSION_KEY], str(self.user.pk))

    def test_external_peer_is_rejected(self):
        with self.assertRaises(Http404):
            create_e2e_session(
                self._request(remote_addr='198.51.100.20'), 'admin',
            )

    def test_non_post_request_is_rejected(self):
        with self.assertRaises(Http404):
            create_e2e_session(self._request(method='get'), 'admin')

    def test_unapproved_username_is_rejected(self):
        with self.assertRaises(Http404):
            create_e2e_session(self._request(), 'outsider')

    def test_missing_seeded_fixture_is_rejected(self):
        with self.assertRaises(Http404):
            create_e2e_session(self._request(), 'client')


class ProductionSettingsTests(SimpleTestCase):
    """Production must fail closed when durable integrations are unsafe."""

    def _import_settings(self, code='import plagenor.settings', **overrides):
        env = os.environ.copy()
        for key in (
            'EMAIL_BACKEND', 'SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD',
            'SMTP_FROM', 'SUPABASE_S3_ENDPOINT',
            'SUPABASE_S3_ACCESS_KEY_ID', 'SUPABASE_S3_SECRET_ACCESS_KEY',
            'DATABASE_SSL_REQUIRE',
            'REQUIRE_PERSISTENT_MEDIA_STORAGE', 'REQUIRE_SMTP',
            'RATE_LIMIT_BACKEND', 'RATE_LIMIT_FAIL_CLOSED',
        ):
            env.pop(key, None)
        env.update({
            'DEBUG': 'false',
            'SECRET_KEY': 'settings-test-key-not-for-production',
            'TOTP_ENCRYPTION_KEY': FERNET_TEST_KEY,
            'DATABASE_URL': 'postgresql://test:test@localhost/test',
            'ALLOWED_HOSTS': 'testserver',
        })
        env.update(overrides)
        return subprocess.run(
            [sys.executable, '-c', code],
            cwd=BASE_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    def test_production_rejects_ephemeral_media_storage(self):
        result = self._import_settings(REQUIRE_SMTP='false')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Persistent private-media storage is required', result.stderr)

    def test_production_rejects_missing_smtp(self):
        result = self._import_settings(
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Production email delivery is required', result.stderr)

    def test_production_rejects_console_email_backend(self):
        result = self._import_settings(
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            SMTP_HOST='smtp.example.test',
            SMTP_USER='mailer',
            SMTP_PASSWORD='settings-test-password',
            SMTP_FROM='noreply@example.test',
            EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires Django\'s SMTP email backend', result.stderr)

    def test_explicit_local_integration_exceptions_allow_ci_boot(self):
        result = self._import_settings(
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_database_tls_is_required_by_default(self):
        result = self._import_settings(
            code=(
                'from plagenor.settings import DATABASES; '
                'print(DATABASES["default"]["OPTIONS"]["sslmode"])'
            ),
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'require')

    def test_trusted_local_database_can_disable_tls(self):
        result = self._import_settings(
            code=(
                'from plagenor.settings import DATABASES; '
                'print(DATABASES["default"].get("OPTIONS", {}))'
            ),
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
            DATABASE_SSL_REQUIRE='false',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('sslmode', result.stdout)

    def test_production_rate_limit_is_shared_and_fails_closed(self):
        result = self._import_settings(
            code=(
                'from plagenor.settings import '
                'RATE_LIMIT_BACKEND, RATE_LIMIT_FAIL_CLOSED; '
                'print(RATE_LIMIT_BACKEND, RATE_LIMIT_FAIL_CLOSED)'
            ),
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'database True')

    def test_invalid_rate_limit_backend_is_rejected(self):
        result = self._import_settings(
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
            RATE_LIMIT_BACKEND='memory-ish',
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('RATE_LIMIT_BACKEND must be either', result.stderr)


class ObservabilityCompatibilityTests(SimpleTestCase):
    """Keep Sentry opt-in, privacy-preserving, and independent of console logs."""

    def test_sentry_initialization_disables_pii_and_blanket_log_export(self):
        code = '''
import json
import sentry_sdk
captured = {}
sentry_sdk.init = lambda **kwargs: captured.update(kwargs)
import plagenor.settings
print(json.dumps({
    "send_default_pii": captured.get("send_default_pii"),
    "enable_logs_present": "enable_logs" in captured,
    "integrations_present": "integrations" in captured,
}))
'''
        result = ProductionSettingsTests()._import_settings(
            code=code,
            REQUIRE_PERSISTENT_MEDIA_STORAGE='false',
            REQUIRE_SMTP='false',
            SENTRY_DSN='https://public@example.invalid/1',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"send_default_pii": false', result.stdout)
        self.assertIn('"enable_logs_present": false', result.stdout)
        self.assertIn('"integrations_present": false', result.stdout)
