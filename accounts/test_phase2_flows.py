"""End-to-end account recovery, conversion, and security-flow regressions."""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.test import TestCase, override_settings

from accounts.models import User
from core.models import Request


_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    STORAGES=_TEST_STORAGES,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class GuestConversionFlowTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.email = "guest-convert@example.test"
        self.request_obj = Request.objects.create(
            channel="GENOCLAB", status="REQUEST_CREATED",
            submitted_as_guest=True, guest_email=self.email,
            guest_name="Guest Convert", display_id="GCL-CONVERT-1",
        )
        self.token = TimestampSigner(salt="guest-conversion").sign(self.email)

    def test_request_link_sends_email_without_disclosing_account_state(self):
        from django.core import mail
        response = self.client.post("/accounts/convert-guest/", {"email": self.email.upper()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["sent"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("convert-guest/verify/", mail.outbox[0].body)

    def test_blank_email_and_mail_failure_are_handled(self):
        blank = self.client.post("/accounts/convert-guest/", {"email": "  "})
        self.assertEqual(blank.status_code, 200)
        self.assertFalse(blank.context["sent"])
        with patch("accounts.views.send_mail", side_effect=OSError("smtp down")):
            failed = self.client.post("/accounts/convert-guest/", {"email": self.email})
        self.assertEqual(failed.status_code, 200)
        self.assertTrue(failed.context["sent"])

    def test_verify_rejects_bad_expired_and_already_registered_tokens(self):
        with patch("accounts.views.TimestampSigner.unsign", side_effect=SignatureExpired):
            response = self.client.get(f"/accounts/convert-guest/verify/{self.token}/")
        self.assertRedirects(response, "/accounts/convert-guest/")
        with patch("accounts.views.TimestampSigner.unsign", side_effect=BadSignature):
            response = self.client.get(f"/accounts/convert-guest/verify/{self.token}/")
        self.assertRedirects(response, "/accounts/convert-guest/")

        User.objects.create_user(username="already-converted", email=self.email, password="StrongPass!42")
        response = self.client.get(f"/accounts/convert-guest/verify/{self.token}/")
        self.assertRedirects(response, "/accounts/login/")

    def test_verify_validates_password_then_creates_client_and_links_requests(self):
        weak = self.client.post(f"/accounts/convert-guest/verify/{self.token}/", {
            "first_name": "Guest", "last_name": "Person", "phone": "123", "password": "weak",
        })
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(User.objects.filter(email=self.email).exists())

        # Exercise deterministic collision handling for the email local part.
        User.objects.create_user(username="guest-convert", email="other@example.test")
        response = self.client.post(f"/accounts/convert-guest/verify/{self.token}/", {
            "first_name": "Guest", "last_name": "Person", "phone": "123",
            "password": "VeryStrongPass!459",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=self.email)
        self.assertEqual(user.username, "guest-convert1")
        self.assertEqual(user.role, "CLIENT")
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.requester, user)
        self.assertIn("_auth_user_id", self.client.session)


@override_settings(STORAGES=_TEST_STORAGES)
class ForcedPasswordAndProfileTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user(
            username="forced-user", email="forced@example.test",
            password="OldStrongPass!42", role="CLIENT", must_change_password=True,
        )
        self.client.force_login(self.user)

    def test_force_change_password_rejects_mismatch_and_weak_then_succeeds(self):
        mismatch = self.client.post("/accounts/force-change-password/", {
            "new_password1": "StrongPass!88", "new_password2": "StrongPass!99",
        })
        self.assertEqual(mismatch.status_code, 200)
        weak = self.client.post("/accounts/force-change-password/", {
            "new_password1": "password", "new_password2": "password",
        })
        self.assertEqual(weak.status_code, 200)
        success = self.client.post("/accounts/force-change-password/", {
            "new_password1": "NewStrongPass!8842", "new_password2": "NewStrongPass!8842",
        })
        self.assertEqual(success.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password("NewStrongPass!8842"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_force_change_is_skipped_when_not_required(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        response = self.client.get("/accounts/force-change-password/")
        self.assertRedirects(response, "/accounts/profile/")

    def test_profile_rejects_corrupt_avatar_and_invalid_language(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        response = self.client.post("/accounts/profile/", {
            "first_name": "Updated", "preferred_language": "not-supported",
            "avatar": SimpleUploadedFile("avatar.png", b"not-an-image", "image/png"),
        })
        self.assertRedirects(response, "/accounts/profile/")
        self.user.refresh_from_db()
        # Validation returns before save; neither a partial profile update nor
        # a tampered language choice may be persisted.
        self.assertNotEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.preferred_language, "")

    def test_two_factor_disable_get_and_not_enabled_are_safe(self):
        self.user.must_change_password = False
        self.user.save(update_fields=["must_change_password"])
        get_response = self.client.get("/accounts/2fa/disable/")
        self.assertRedirects(get_response, "/accounts/profile/")
        post_response = self.client.post("/accounts/2fa/disable/", {
            "password": "OldStrongPass!42", "code": "000000",
        })
        self.assertRedirects(post_response, "/accounts/profile/")
