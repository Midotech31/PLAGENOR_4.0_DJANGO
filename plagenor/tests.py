import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase


BASE_DIR = Path(__file__).resolve().parent.parent
FERNET_TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


class ProductionSettingsTests(SimpleTestCase):
    """Production must fail closed when durable integrations are unsafe."""

    def _import_settings(self, **overrides):
        env = os.environ.copy()
        for key in (
            'EMAIL_BACKEND', 'SMTP_HOST', 'SMTP_USER', 'SMTP_PASSWORD',
            'SMTP_FROM', 'SUPABASE_S3_ENDPOINT',
            'SUPABASE_S3_ACCESS_KEY_ID', 'SUPABASE_S3_SECRET_ACCESS_KEY',
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
            [sys.executable, '-c', 'import plagenor.settings'],
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
