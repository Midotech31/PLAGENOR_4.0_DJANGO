"""Regression coverage for public, privacy, and language entry points."""

import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings

from accounts.models import User
from core.exceptions import PricingConfigurationError
from core.models import Request, Service


_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=_TEST_STORAGES)
class PublicPagesAndPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.service = Service.objects.create(
            code="PUBLIC-QUALITY", name="Public quality", active=True,
            channel_availability="BOTH", genoclab_price=1000, ibtikar_price=500,
        )
        cls.inactive = Service.objects.create(
            code="PUBLIC-INACTIVE", name="Inactive", active=False,
        )
        cls.requester = User.objects.create_user(
            username="public-requester", email="requester@example.test",
            password="StrongPass!42", role="REQUESTER", preferred_language="fr",
        )
        cls.client_user = User.objects.create_user(
            username="public-client", password="StrongPass!42", role="CLIENT",
        )
        cls.member = User.objects.create_user(
            username="public-member", password="StrongPass!42", role="MEMBER",
        )

    def test_public_information_pages_render(self):
        for path in ("/", "/about/", "/services/", "/contact/", "/help/", "/confidentialite/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_service_detail_and_role_aware_landing(self):
        detail = self.client.get(f"/service/{self.service.code}/detail/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.context["service"], self.service)
        self.assertEqual(self.client.get(f"/service/{self.inactive.code}/detail/").status_code, 404)

        anonymous = self.client.get(f"/service/{self.service.code}/")
        self.assertEqual(anonymous.status_code, 200)
        for user, expected in (
            (self.requester, "/dashboard/requester/?service="),
            (self.client_user, "/dashboard/client/?service="),
            (self.member, "/dashboard/"),
        ):
            self.client.force_login(user)
            response = self.client.get(f"/service/{self.service.code}/")
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith(expected), response.url)
            self.client.logout()

    def test_personal_data_export_requires_login_and_contains_only_owner_data(self):
        other = User.objects.create_user(username="other-export", role="REQUESTER")
        Request.objects.create(
            channel="IBTIKAR", requester=self.requester, status="SUBMITTED",
            display_id="IBK-EXPORT-MINE", title="Mine", service_rating=4,
        )
        Request.objects.create(
            channel="IBTIKAR", requester=other, status="SUBMITTED",
            display_id="IBK-EXPORT-OTHER", title="Other",
        )
        anonymous = self.client.get("/mes-donnees/export/")
        self.assertEqual(anonymous.status_code, 302)
        self.client.force_login(self.requester)
        response = self.client.get("/mes-donnees/export/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        body = response.json()
        self.assertEqual(body["account"]["email"], "requester@example.test")
        self.assertEqual([item["display_id"] for item in body["requests"]], ["IBK-EXPORT-MINE"])

    def test_tracking_rejects_sequential_ids_and_backfills_report_token(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel="GENOCLAB", status="COMPLETED", display_id="GCL-TRACK-BACKFILL",
            submitted_as_guest=True, guest_token=token, report_file="reports/result.pdf",
        )
        invalid = self.client.get("/track/", {"q": req.display_id})
        self.assertIsNone(invalid.context["tracked_request"])
        valid = self.client.get("/track/", {"q": str(token)})
        self.assertEqual(valid.context["tracked_request"], req)
        req.refresh_from_db()
        self.assertIsNotNone(req.report_token)

    def test_language_switch_blocks_open_redirect_and_persists_valid_choice(self):
        blocked = self.client.post("/switch-language/", {
            "language": "en", "next": "https://attacker.example/phish",
        })
        self.assertEqual(blocked.url, "/")
        self.assertEqual(blocked.cookies["django_language"].value, "en")

        self.client.force_login(self.requester)
        valid = self.client.post("/switch-language/", {"language": "ar", "next": "/help/"})
        self.assertEqual(valid.url, "/help/")
        self.requester.refresh_from_db()
        self.assertEqual(self.requester.preferred_language, "ar")
        unsupported = self.client.post("/switch-language/", {"language": "xx", "next": "/"})
        self.assertNotIn("django_language", unsupported.cookies)


@override_settings(STORAGES=_TEST_STORAGES)
class PublicSubmissionEdgeTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.service = Service.objects.create(
            code="PUBLIC-SUBMIT", name="Public submit", active=True,
            channel_availability="GENOCLAB", genoclab_price=1000,
        )

    def _valid(self, **overrides):
        data = {
            "guest_name": "Guest", "guest_email": "guest@example.test",
            "guest_phone": "123", "service_id": str(self.service.pk),
            "channel": "GENOCLAB", "title": "Guest request",
        }
        data.update(overrides)
        return data

    def test_form_and_required_or_unknown_service_errors(self):
        self.assertEqual(self.client.get("/guest-submit/").status_code, 200)
        missing = self.client.post("/guest-submit/", self._valid(guest_name=""))
        self.assertEqual(missing.status_code, 200)
        self.assertFalse(Request.objects.exists())
        unknown = self.client.post("/guest-submit/", self._valid(service_id=str(uuid.uuid4())))
        self.assertEqual(unknown.status_code, 200)
        self.assertFalse(Request.objects.exists())

    @patch("core.pricing.resolve_cost", side_effect=PricingConfigurationError("bad pricing"))
    def test_pricing_configuration_error_fails_closed(self, resolve):
        response = self.client.post("/guest-submit/", self._valid())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tarification")
        self.assertFalse(Request.objects.exists())
        resolve.assert_called_once()

    def test_tampered_metadata_is_normalized_and_payload_is_bounded(self):
        data = self._valid(
            organization="Org", organization_type="tampered", country="XX",
            channel="tampered", param_note="x" * 5000,
            **{"sample_bad": "ignored", "sample_0_code": "y" * 5000},
        )
        with patch("notifications.emails.notify_guest_tracking_code", side_effect=OSError("mail down")):
            response = self.client.post("/guest-submit/", data)
        self.assertEqual(response.status_code, 200)
        req = Request.objects.get()
        self.assertEqual(req.channel, "GENOCLAB")
        self.assertEqual(req.requester_data, {"organization": "Org"})
        self.assertEqual(len(req.service_params["note"]), 4096)
        self.assertEqual(len(req.sample_table[0]["code"]), 4096)

    def test_guest_ibtikar_code_requires_post_and_nonblank_value(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel="IBTIKAR", submitted_as_guest=True, guest_token=token,
            status="IBTIKAR_SUBMISSION_PENDING", display_id="IBK-CODE-EDGE",
        )
        self.assertRedirects(self.client.get(f"/track/ibtikar-code/{token}/"), "/track/")
        blank = self.client.post(f"/track/ibtikar-code/{token}/", {"ibtikar_code": " "})
        self.assertEqual(blank.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.ibtikar_external_code, "")

        with patch("core.workflow.transition") as transition:
            success = self.client.post(
                f"/track/ibtikar-code/{token}/", {"ibtikar_code": "IBT-EXTERNAL"})
        self.assertEqual(success.status_code, 302)
        transition.assert_called_once()
        req.refresh_from_db()
        self.assertEqual(req.ibtikar_external_code, "IBT-EXTERNAL")
