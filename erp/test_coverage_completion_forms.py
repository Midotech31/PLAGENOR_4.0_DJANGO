from datetime import timedelta
from unittest.mock import patch

from django import forms
from django.test import TestCase
from django.utils import timezone

from core.models import Request
from erp import alert_forms, cdc_forms, planning_forms, stock_forms, work_forms
from erp.models import Capability
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


class OperationalFormCoverageTests(OperationFixtures, TestCase):
    def test_scoped_stock_choices_and_operational_form_initializers(self):
        self.assertFalse(stock_forms.article_choices(self.operator, Capability.RECEIVE_STOCK).exists())
        self.assertFalse(stock_forms.location_choices(self.operator, Capability.RECEIVE_STOCK).exists())
        self.grant(Capability.RECEIVE_STOCK, category=self.category)
        self.grant(Capability.RECEIVE_STOCK, location=self.freezer)
        self.assertIn(self.article, stock_forms.article_choices(self.operator, Capability.RECEIVE_STOCK))
        self.assertIn(self.freezer, stock_forms.location_choices(self.operator, Capability.RECEIVE_STOCK))

        receipt = stock_forms.ReceiptForm(user=self.operator)
        self.assertTrue(receipt.groups)
        self.assertIn(self.article, receipt.fields["article"].queryset)
        self.assertIn(self.freezer, receipt.fields["location"].queryset)

        container, _, _ = self.receive()
        self.grant(Capability.CONTROL_STOCK, category=self.category, location=self.freezer)
        self.grant(Capability.CONSUME_STOCK, category=self.category, location=self.freezer)
        self.grant(Capability.TRANSFER_STOCK, location=self.freezer)
        remove = stock_forms.RemoveForm(user=self.operator, container=container)
        self.assertEqual(remove.fields["unit"].initial, self.unit.pk)
        self.assertTrue(remove.fields["kind"].choices)
        transfer = stock_forms.TransferForm(user=self.operator, container=container)
        self.assertEqual(transfer.fields["unit"].initial, self.unit.pk)
        reserve = stock_forms.ReserveForm(user=self.operator, container=container)
        self.assertEqual(reserve.fields["unit"].initial, self.unit.pk)
        self.assertTrue(stock_forms.InventoryForm(user=self.ops).fields)

    def test_global_stock_scopes_for_manager_and_unscoped_member(self):
        self.assertEqual(stock_forms.article_choices(self.admin, Capability.RECEIVE_STOCK).count(), 2)
        self.assertGreaterEqual(stock_forms.location_choices(self.admin, Capability.RECEIVE_STOCK).count(), 1)
        self.grant(Capability.RECEIVE_STOCK)
        self.assertEqual(stock_forms.article_choices(self.operator, Capability.RECEIVE_STOCK).count(), 2)
        self.grant(Capability.TRANSFER_STOCK)
        self.assertGreaterEqual(stock_forms.location_choices(self.operator, Capability.TRANSFER_STOCK).count(), 1)

    def test_work_forms_restrict_kinds_and_cost_delegation(self):
        work_form = work_forms.WorkForm(user=self.ops)
        self.assertEqual({value for value, _ in work_form.fields["kind"].choices}, {"RECEIPT", "TEMPERATURE", "CONTROL"})
        task = create_work(self.ops, kind="CONTROL", title="Form coverage", assignee=self.operator)
        delegated = work_forms.DelegationForm(instance=task, user=self.ops)
        self.assertTrue(delegated.fields["allow_costs"].disabled)
        self.assertFalse(delegated.fields["allow_costs"].initial)
        cdc = create_work(self.ops, kind="CDC", title="CDC coverage", assignee=self.operator)
        cdc_form = work_forms.DelegationForm(instance=cdc, user=self.ops)
        self.assertFalse(cdc_form.fields["allow_costs"].disabled)
        op = work_forms.OperationForm()
        op.fields["text"] = forms.CharField(widget=forms.Textarea())
        op.__init__()
        self.assertEqual(op.fields["text"].widget.attrs.get("rows"), 3)

    def test_alert_forms_parse_thresholds_and_limit_assignment(self):
        form = alert_forms.AlertPolicyForm(data={
            "expected_version": 1, "expiry_days": "180, 90, 7",
            "dormant_days": 30, "receipt_pending_days": 2,
            "occupancy_percent": "80", "overstock_multiplier": "2",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expiry_days"], [180, 90, 7])
        bad = alert_forms.AlertPolicyForm(data={
            "expected_version": 1, "expiry_days": "bad",
            "dormant_days": 30, "receipt_pending_days": 2,
            "occupancy_percent": "80", "overstock_multiplier": "2",
        })
        self.assertFalse(bad.is_valid())
        member = alert_forms.AlertActionForm(user=self.operator)
        self.assertNotIn("assignee", member.fields)
        manager = alert_forms.AlertActionForm(user=self.ops)
        self.assertIn("assignee", manager.fields)

    def test_planning_form_scopes_cleaning_and_create_layout(self):
        empty_requests = Request.objects.none()
        with patch.object(planning_forms, "request_scope", return_value=empty_requests):
            schedule = planning_forms.ScheduleForm(user=self.ops)
            self.assertFalse(schedule.fields["request"].queryset.exists())
            create = planning_forms.ActivityCreateForm(user=self.ops)
        self.assertNotIn("expected_version", create.fields)
        self.assertNotIn("reason", create.fields)

        now = timezone.now()
        with patch.object(planning_forms, "request_scope", return_value=empty_requests):
            valid = planning_forms.ScheduleForm(user=self.ops, data={
                "expected_version": 0,
                "starts_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            })
            self.assertTrue(valid.is_valid(), valid.errors)
            invalid = planning_forms.ScheduleForm(user=self.ops, data={
                "expected_version": 0,
                "starts_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            })
            self.assertFalse(invalid.is_valid())

        work = create_work(self.ops, kind="CONTROL", title="Dependency")
        dep = planning_forms.DependencyForm(work=work)
        self.assertNotIn(work, dep.fields["prerequisites"].queryset)
        unavailable = planning_forms.UnavailabilityForm(data={
            "starts_at": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
            "reason": "Maintenance",
        })
        self.assertFalse(unavailable.is_valid())

    def test_cdc_consultation_form_groups_and_time_normalization(self):
        form = cdc_forms.ConsultationForm(data={
            "expected_version": 1, "reference": "1/SME/SDFM/SG/ESSBO/2026",
            "object_fr": "Objet", "object_ar": "موضوع", "operation_fr": "Opération",
            "financing_label": "Budget", "budget_year": 2026,
            "preparation_days": 21, "preparation_fr": "21 jours", "preparation_ar": "21 يوما",
            "deposit_time": "12:00", "opening_time": "12:15",
            "validity_months": 3, "validity_fr": "03 mois", "validity_ar": "03 أشهر",
            "withdrawal_fr": "Retrait", "withdrawal_ar": "سحب",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["deposit_time"], "12:00")
        self.assertEqual(form.cleaned_data["opening_time"], "12:15")
        self.assertEqual(len(form.groups), 3)
