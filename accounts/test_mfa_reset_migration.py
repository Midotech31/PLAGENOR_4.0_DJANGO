from django.apps import apps
from django.test import TestCase

from accounts.models import User


class ExistingMFAResetMigrationTests(TestCase):
    def test_clear_existing_mfa_resets_only_totp_state(self):
        from importlib import import_module

        user = User.objects.create_user(
            username='existing-mfa-user',
            email='existing@example.test',
            password='RightPass!42',
            role='PLATFORM_ADMIN',
            first_name='Existing',
            last_name='User',
        )
        user.totp_enabled = True
        user.totp_secret = 'fernet$legacy-enrollment'
        user.totp_last_step = 123456
        user.save(update_fields=['totp_enabled', 'totp_secret', 'totp_last_step'])

        migration = import_module(
            'accounts.migrations.0016_clear_existing_mfa_enrollment'
        )
        migration.clear_existing_mfa(apps, None)

        user.refresh_from_db()
        self.assertFalse(user.totp_enabled)
        self.assertEqual(user.totp_secret, '')
        self.assertIsNone(user.totp_last_step)
        self.assertEqual(user.email, 'existing@example.test')
        self.assertEqual(user.role, 'PLATFORM_ADMIN')
        self.assertEqual(user.first_name, 'Existing')
        self.assertEqual(user.last_name, 'User')
        self.assertTrue(user.check_password('RightPass!42'))
