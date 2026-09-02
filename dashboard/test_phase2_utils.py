"""Security and state synchronization tests for dashboard navigation helpers."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from core.exceptions import InvalidTransitionError
from dashboard.utils import confirm_appointment_flow, redirect_back, redirect_to_detail


class DashboardRedirectTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_redirect_back_accepts_same_origin_and_rejects_external_referer(self):
        local = self.factory.get("/action", HTTP_REFERER="http://testserver/dashboard/?tab=one")
        self.assertEqual(redirect_back(local).url, "http://testserver/dashboard/?tab=one")
        hostile = self.factory.get("/action", HTTP_REFERER="https://attacker.example/phish")
        self.assertEqual(redirect_back(hostile).url, "/dashboard/")

    def test_redirect_back_survives_invalid_named_fallback(self):
        request = self.factory.get("/action")
        self.assertEqual(redirect_back(request, "missing:url").url, "/")

    def test_redirect_to_detail_is_role_aware_and_falls_back_safely(self):
        request = self.factory.get("/action")
        request.user = SimpleNamespace(role="CLIENT")
        req = SimpleNamespace(pk=uuid.uuid4())
        self.assertIn(str(req.pk), redirect_to_detail(request, req).url)
        request.user = SimpleNamespace(role="FINANCE")
        self.assertEqual(redirect_to_detail(request, req).url, "/dashboard/")
        request.user = SimpleNamespace(role="CLIENT")
        with patch("dashboard.utils.redirect", side_effect=[
            __import__("django.urls").urls.NoReverseMatch(),
            MagicMock(url="/fallback"),
        ]):
            self.assertEqual(redirect_to_detail(request, req).url, "/fallback")


class AppointmentConfirmationHelperTests(SimpleTestCase):
    def setUp(self):
        self.request = SimpleNamespace(user=SimpleNamespace(pk=1))

    def _request_obj(self, **overrides):
        data = {
            "status": "ASSIGNED", "appointment_date": None,
            "appointment_proposed_by": None, "appointment_confirmed": False,
            "appointment_confirmed_at": None, "report_token": None,
            "display_id": "REQ-APPOINTMENT", "save": MagicMock(),
        }
        data.update(overrides)
        return SimpleNamespace(**data)

    @patch("django.contrib.messages.success")
    def test_already_confirmed_state_repairs_flags_idempotently(self, success):
        req = self._request_obj(status="COMPLETED")
        confirm_appointment_flow(self.request, req)
        self.assertTrue(req.appointment_confirmed)
        self.assertIsNotNone(req.appointment_confirmed_at)
        self.assertIsNotNone(req.report_token)
        req.save.assert_called_once()
        success.assert_called_once()

        req.save.reset_mock()
        confirm_appointment_flow(self.request, req)
        req.save.assert_not_called()

    @patch("django.contrib.messages.error")
    def test_missing_proposal_is_rejected(self, error):
        req = self._request_obj()
        confirm_appointment_flow(self.request, req)
        req.save.assert_not_called()
        error.assert_called_once()

    @patch("django.contrib.messages.success")
    @patch("core.workflow.transition")
    def test_assigned_dated_request_is_regularized_then_confirmed(self, transition, success):
        req = self._request_obj(appointment_date="2026-09-05")

        def apply_transition(obj, target, *args, **kwargs):
            obj.status = target

        transition.side_effect = apply_transition
        confirm_appointment_flow(self.request, req)
        self.assertEqual([call.args[1] for call in transition.call_args_list], [
            "APPOINTMENT_PROPOSED", "APPOINTMENT_CONFIRMED",
        ])
        self.assertTrue(req.appointment_confirmed)
        success.assert_called_once()

    @patch("django.contrib.messages.error")
    @patch("core.workflow.transition", side_effect=InvalidTransitionError("blocked"))
    def test_transition_failure_is_reported_without_partial_confirmation(self, transition, error):
        req = self._request_obj(status="APPOINTMENT_PROPOSED")
        confirm_appointment_flow(self.request, req)
        self.assertFalse(req.appointment_confirmed)
        req.save.assert_not_called()
        error.assert_called_once_with(self.request, "blocked")
