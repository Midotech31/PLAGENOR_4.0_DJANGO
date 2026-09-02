"""Focused regression tests for operational helpers hardened in phase 2."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import tempfile
import os

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils import timezone

from core import productivity, registry
from core.uploads import validate_upload


class ServiceRegistryTests(SimpleTestCase):
    def setUp(self):
        registry._load_registry_from_disk.cache_clear()
        self.temp_dir = tempfile.TemporaryDirectory(prefix="plagenor-registry-")
        self.base_dir = Path(self.temp_dir.name)
        self.registry_dir = self.base_dir / "services_registry"
        self.registry_dir.mkdir()

    def tearDown(self):
        registry._load_registry_from_disk.cache_clear()
        self.temp_dir.cleanup()

    def _write(self, name, body):
        (self.registry_dir / name).write_text(body, encoding="utf-8")

    def test_registry_loads_valid_files_and_ignores_bad_or_duplicate_entries(self):
        self._write("01-valid.yaml", """
service_code: TEST-A
service_name: Service A
parameters:
  - name: mode
    type: enum
sample_table:
  enabled: true
  columns: []
requester_fields:
  - name: email
""")
        self._write("02-duplicate.yaml", "service_code: TEST-A\nservice_name: Duplicate\n")
        self._write("03-list.yaml", "- not\n- a\n- mapping\n")
        self._write("04-bad.yaml", "service_code: [unterminated\n")
        self._write("05-empty-code.yaml", "service_name: No code\n")

        with override_settings(BASE_DIR=self.base_dir):
            loaded = registry.load_service_registry(force_reload=True)
            self.assertEqual(list(loaded), ["TEST-A"])
            self.assertEqual(registry.get_all_service_codes(), ["TEST-A"])
            self.assertEqual(registry.get_service_def("TEST-A")["service_name"], "Service A")
            self.assertEqual(registry.get_service_parameters("TEST-A")[0]["name"], "mode")
            self.assertTrue(registry.get_sample_table_schema("TEST-A")["enabled"])
            self.assertEqual(registry.get_requester_fields("TEST-A")[0]["name"], "email")

            files = registry.get_all_yaml_files()
            self.assertEqual({item["filename"] for item in files}, {
                "01-valid.yaml", "02-duplicate.yaml", "05-empty-code.yaml",
            })

    def test_missing_service_and_disabled_table_use_safe_defaults(self):
        self._write("service.yaml", """
service_code: TEST-B
sample_table:
  enabled: false
""")
        with override_settings(BASE_DIR=self.base_dir):
            registry.load_service_registry(force_reload=True)
            self.assertIsNone(registry.get_service_def("MISSING"))
            self.assertEqual(registry.get_service_parameters("MISSING"), [])
            self.assertIsNone(registry.get_sample_table_schema("TEST-B"))
            self.assertIsNone(registry.get_sample_table_schema("MISSING"))
            defaults = registry.get_requester_fields("MISSING")
            self.assertEqual(len(defaults), 7)
            self.assertTrue(all(field["required"] for field in defaults))

    def test_missing_directory_returns_empty_registry(self):
        with override_settings(BASE_DIR=self.base_dir / "absent"):
            self.assertEqual(registry.load_service_registry(force_reload=True), {})
            self.assertEqual(registry.get_all_yaml_files(), [])


class UploadValidationEdgeTests(SimpleTestCase):
    def test_unknown_empty_and_extension_policies_fail_closed(self):
        upload = SimpleUploadedFile("x.pdf", b"%PDF-1.4", "application/pdf")
        with self.assertRaises(ValueError):
            validate_upload(upload, "unknown")
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile("empty.pdf", b"", "application/pdf"), "report")
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile("x.exe", b"MZ", "application/octet-stream"), "report")

    def test_invalid_image_signatures_and_corrupt_pixels_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile("x.png", b"not-png", "image/png"), "image")
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile("x.jpg", b"not-jpeg", "image/jpeg"), "image")
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile(
                "x.png", b"\x89PNG\r\n\x1a\ncorrupt", "image/png"), "image")

    def test_invalid_docx_containers_are_rejected(self):
        with self.assertRaises(ValidationError):
            validate_upload(SimpleUploadedFile("x.docx", b"not-a-zip", "application/zip"), "docx_template")


class ProductivityHelperTests(SimpleTestCase):
    def test_threshold_helpers_cover_every_level(self):
        self.assertEqual(productivity.get_productivity_status(85), "EXCELLENT")
        self.assertEqual(productivity.get_productivity_status(70), "GOOD")
        self.assertEqual(productivity.get_productivity_status(50), "NORMAL")
        self.assertEqual(productivity.get_productivity_status(49), "LOW")
        self.assertEqual(productivity.get_performance_level(95)["key"], "fire")
        self.assertEqual(productivity.get_performance_level(80)["key"], "very_good")
        self.assertEqual(productivity.get_performance_level(65)["key"], "good")
        self.assertEqual(productivity.get_performance_level(-1)["key"], "not_bad")

    @patch("core.productivity.Request.objects")
    def test_compute_productivity_counts_completion_progress_and_sla(self, objects):
        now = timezone.now()
        completed = [
            SimpleNamespace(channel="IBTIKAR", created_at=now - timedelta(days=10), updated_at=now),
            SimpleNamespace(channel="GENOCLAB", created_at=now - timedelta(days=30), updated_at=now),
        ]
        assigned = MagicMock()
        assigned.count.return_value = 4
        completed_qs = MagicMock()
        completed_qs.count.return_value = 2
        completed_qs.iterator.return_value = iter(completed)
        assigned.filter.side_effect = [completed_qs, MagicMock(count=MagicMock(return_value=1))]
        objects.filter.return_value = assigned

        metrics = productivity.compute_member_productivity(SimpleNamespace(pk=7))
        self.assertEqual(metrics["completed"], 2)
        self.assertEqual(metrics["in_progress"], 1)
        self.assertEqual(metrics["completion_rate"], 50.0)
        self.assertEqual(metrics["on_time_rate"], 50.0)
        self.assertEqual(metrics["score"], 50.0)

    @patch("core.productivity.Request.objects")
    def test_empty_workload_has_neutral_score(self, objects):
        assigned = MagicMock()
        assigned.count.return_value = 0
        completed_qs = MagicMock()
        completed_qs.count.return_value = 0
        completed_qs.iterator.return_value = iter(())
        assigned.filter.side_effect = [completed_qs, MagicMock(count=MagicMock(return_value=0))]
        objects.filter.return_value = assigned
        metrics = productivity.compute_member_productivity(SimpleNamespace(pk=8))
        self.assertEqual(metrics["score"], 50.0)

    def test_recalculate_helpers_persist_and_add_display_names(self):
        member = MagicMock(productivity_score=0, productivity_status="LOW")
        with patch("core.productivity.compute_member_productivity", return_value={
            "score": 88.5, "status": "EXCELLENT",
        }):
            result = productivity.recalculate_member(member)
        self.assertEqual(result["score"], 88.5)
        member.save.assert_called_once_with(update_fields=["productivity_score", "productivity_status"])

        manager = MagicMock()
        members = [MagicMock(), MagicMock()]
        manager.all.return_value = members
        with patch("core.productivity.MemberProfile.objects", manager), \
                patch("core.productivity.recalculate_member", side_effect=[{"score": 1}, {"score": 2}]):
            self.assertEqual(len(productivity.recalculate_all()), 2)

        member.user.get_full_name.return_value = "Ada Test"
        manager.select_related.return_value.all.return_value = [member]
        with patch("core.productivity.MemberProfile.objects", manager), \
                patch("core.productivity.compute_member_productivity", return_value={"score": 99}) as compute:
            stats = productivity.get_all_productivity_stats()
        self.assertEqual(stats[0]["name"], "Ada Test")
        compute.assert_called_once_with(member)


class SecurityAndTemplateHelperTests(SimpleTestCase):
    def test_dashboard_filters_are_safe_on_malformed_values(self):
        from dashboard.templatetags.dashboard_extras import (
            as_json, filename, get_item, multiply, percentage,
        )
        self.assertIsNone(get_item(None, "x"))
        self.assertIsNone(get_item([], "x"))
        self.assertEqual(get_item({"x": 3}, "x"), 3)
        self.assertEqual(as_json(None), "")
        self.assertEqual(as_json({"é": "</script>"}), '{"é": "</script>"}')
        self.assertEqual(multiply("2.5", 4), 10)
        self.assertEqual(multiply("bad", 4), 0)
        self.assertEqual(percentage(1, 4), 25.0)
        self.assertEqual(percentage(1, 0), 0)
        self.assertEqual(filename(None), "")
        self.assertEqual(filename(Path("a/b/report.pdf")), "report.pdf")
        self.assertEqual(filename(r"a\b\report.pdf"), "report.pdf")

    def test_online_filter_handles_recent_stale_and_missing_activity(self):
        from core.templatetags.online import is_online
        self.assertTrue(is_online(SimpleNamespace(last_seen=timezone.now())))
        self.assertFalse(is_online(SimpleNamespace(last_seen=timezone.now() - timedelta(minutes=6))))
        self.assertFalse(is_online(SimpleNamespace()))

    def test_totp_key_validation_encryption_and_corruption_fail_closed(self):
        from cryptography.fernet import Fernet
        from django.core.exceptions import ImproperlyConfigured
        from accounts.totp import decrypt_secret, encrypt_secret

        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"TOTP_ENCRYPTION_KEY": key}, clear=False):
            encrypted = encrypt_secret("JBSWY3DPEHPK3PXP")
            self.assertTrue(encrypted.startswith("fernet$"))
            self.assertEqual(encrypt_secret(encrypted), encrypted)
            self.assertEqual(decrypt_secret(encrypted), "JBSWY3DPEHPK3PXP")
            self.assertEqual(decrypt_secret("plain"), "plain")
            with self.assertRaises(ImproperlyConfigured):
                decrypt_secret("fernet$corrupt")
        with patch.dict(os.environ, {"TOTP_ENCRYPTION_KEY": "invalid"}, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                encrypt_secret("secret")
        with patch.dict(os.environ, {}, clear=True), override_settings(DEBUG=False):
            with self.assertRaises(ImproperlyConfigured):
                encrypt_secret("secret")

    def test_same_origin_storage_url_never_exposes_s3(self):
        from plagenor.storages import SupabaseMediaStorage
        with override_settings(MEDIA_URL="/media/"):
            self.assertEqual(
                SupabaseMediaStorage.url(object(), "/reports/a.pdf"),
                "/media/reports/a.pdf",
            )
