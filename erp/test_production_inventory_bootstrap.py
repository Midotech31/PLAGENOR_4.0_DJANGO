import os
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from scripts import production_inventory_bootstrap as bootstrap


class ProductionInventoryBootstrapPureTests(SimpleTestCase):
    def test_canonical_preview_is_exactly_the_expected_real_inventory(self):
        manifest, preview = bootstrap._validated_preview()
        self.assertEqual(
            manifest["source"]["xlsx"]["sha256"],
            bootstrap.EXPECTED_XLSX_SHA256,
        )
        self.assertEqual(
            manifest["source"]["zip"]["sha256"],
            bootstrap.EXPECTED_ZIP_SHA256,
        )
        self.assertEqual(preview["equipment"]["detailed_rows"], 239)
        self.assertEqual(preview["equipment"]["physical_assets"], 462)
        self.assertEqual(preview["chemicals"]["exact_positive_balances"], 71)
        self.assertEqual(preview["chemicals"]["zero_balances"], 2)
        self.assertEqual(preview["chemicals"]["review_balances"], 9)
        self.assertEqual(preview["consumables"]["logical_rows"], 81)
        self.assertEqual(preview["reagents"]["logical_rows"], 92)

    def test_database_url_is_split_into_process_environment_without_echoing_secret(self):
        env = bootstrap._database_environment(
            "postgresql://app_user:p%40ssword@db.example.test:6543/plagenor?sslmode=verify-full"
        )
        self.assertEqual(env["PGHOST"], "db.example.test")
        self.assertEqual(env["PGPORT"], "6543")
        self.assertEqual(env["PGUSER"], "app_user")
        self.assertEqual(env["PGPASSWORD"], "p@ssword")
        self.assertEqual(env["PGDATABASE"], "plagenor")
        self.assertEqual(env["PGSSLMODE"], "verify-full")

    def test_acknowledgement_is_fail_closed(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PLAGENOR_INVENTORY_APPLY_ACK", None)
            with self.assertRaisesMessage(RuntimeError, "acknowledgement"):
                bootstrap._require_ack()
        with patch.dict(
            os.environ,
            {"PLAGENOR_INVENTORY_APPLY_ACK": bootstrap.ACK},
            clear=False,
        ):
            bootstrap._require_ack()

    @override_settings(TOTP_ENCRYPTION_KEY=Fernet.generate_key().decode("ascii"))
    def test_backup_key_derivation_is_separate_and_repeatable(self):
        first = bootstrap._backup_fernet()
        second = bootstrap._backup_fernet()
        token = first.encrypt(b"plagenor-backup")
        self.assertEqual(second.decrypt(token), b"plagenor-backup")


class ProductionInventoryBackupRouteTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="backup-route-admin",
            password="StrongPass!234",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_database_backups_are_never_exposed_by_media_route(self):
        response = self.client.get(
            "/media/database_backups/plagenor-test.dump.fernet"
        )
        self.assertEqual(response.status_code, 404)
