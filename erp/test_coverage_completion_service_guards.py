import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from erp.models import (
    AvailabilityBlock, Capability, HazardTag, StorageIncident,
    StockContainer, StockMovement,
)
from erp.services import cold_storage, planning, safety, stock
from erp.services.access import save_grant
from erp.services.common import Conflict
from erp.services.work import create_work, transition_work
from erp.test_operations import OperationFixtures


class PlanningGuardCoverageTests(OperationFixtures, TestCase):
    def test_editability_readiness_dependencies_and_series_guards(self):
        work = create_work(self.ops, kind="CONTROL", title="Planning guard")
        result = planning.readiness(self.ops, work)
        self.assertFalse(result["ready"])
        self.assertIsNone(result["schedule"])

        for status in ("SUBMITTED", "APPROVED", "CANCELLED"):
            work.status = status
            with self.subTest(status=status), self.assertRaises(ValidationError):
                planning._editable(work)
        work.status = "DRAFT"

        with self.assertRaises(ValidationError):
            planning.set_dependencies(
                self.ops, work.pk, expected=work.version,
                prerequisites=[], reason="",
            )
        with self.assertRaises(ValidationError):
            planning.set_dependencies(
                self.ops, work.pk, expected=work.version,
                prerequisites=[work], reason="Self",
            )

        now = timezone.now() + timedelta(hours=1)
        base = {
            "key": uuid.uuid4(), "kind": "CONTROL", "title": "Recurring",
            "assignee": None, "starts_at": now, "ends_at": now + timedelta(hours=1),
            "resources": (), "request": None, "run": None, "instructions": "",
            "priority": "NORMAL",
        }
        for frequency, occurrences in (("BAD", 1), ("ONCE", 2), ("DAILY", 0), ("DAILY", 61)):
            with self.subTest(frequency=frequency, occurrences=occurrences), self.assertRaises(ValidationError):
                planning.create_activity_series(
                    self.ops, frequency=frequency, occurrences=occurrences, **base
                )
        bad_key = {**base, "key": "not-a-uuid"}
        with self.assertRaises(ValidationError):
            planning.create_activity_series(self.ops, frequency="ONCE", occurrences=1, **bad_key)

    def test_schedule_ordering_and_transition_guards(self):
        now = timezone.now()
        work = create_work(self.ops, kind="CONTROL", title="Scheduled", assignee=self.operator)
        schedule = planning.save_schedule(
            self.ops, work.pk, expected=work.version,
            starts_at=now + timedelta(hours=1),
            ends_at=now + timedelta(hours=2),
        )
        work.refresh_from_db()
        with self.assertRaises(ValidationError):
            planning.save_schedule(
                self.ops, work.pk, expected=work.version,
                starts_at=now + timedelta(hours=2),
                ends_at=now + timedelta(hours=3),
                reason="",
            )
        with self.assertRaises(ValidationError):
            planning.confirm_resources(
                self.operator, work.pk, expected=work.version, note=""
            )
        with self.assertRaises(ValidationError):
            planning.before_transition(self.operator, work, "IN_PROGRESS", "")


class ColdStorageGuardCoverageTests(OperationFixtures, TestCase):
    def grant_storage(self):
        for capability in (Capability.EDIT_STORAGE, Capability.MANAGE_BIOBANK):
            save_grant(self.admin, {
                "user": self.operator,
                "capability": capability,
                "location": self.freezer,
            })

    def test_temperature_permissions_and_input_guards(self):
        with self.assertRaises(PermissionDenied):
            cold_storage._temperature_permission(self.operator, self.freezer)
        self.grant_storage()
        cold_storage._temperature_permission(self.operator, self.freezer)

        now = timezone.now() - timedelta(minutes=1)
        for value in ("NaN", "-274", "1001", "1.234"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                cold_storage.record_temperature(
                    self.operator, location=self.freezer,
                    measured_at=now, value=value,
                )
        with self.assertRaises(ValidationError):
            cold_storage.record_temperature(
                self.operator, location=self.freezer,
                measured_at=timezone.now() + timedelta(hours=1), value="-80",
            )
        with self.assertRaises(ValidationError):
            cold_storage.record_temperature(
                self.operator, location=self.freezer,
                measured_at=now, value="-80", source="OTHER",
            )
        with self.assertRaises(ValidationError):
            cold_storage.record_temperature(
                self.admin, location=self.lab, measured_at=now, value="20",
            )
        reading = cold_storage.record_temperature(
            self.operator, location=self.freezer, measured_at=now, value="-95"
        )
        self.assertTrue(reading.out_of_range)
        self.assertIsNotNone(reading.incident_id)

    def test_incident_open_close_guards(self):
        self.grant_storage()
        now = timezone.now() - timedelta(minutes=1)
        with self.assertRaises(ValidationError):
            cold_storage.create_incident(
                self.operator, location=self.freezer, kind="FAILURE",
                started_at=now, description="",
            )
        incident = cold_storage.create_incident(
            self.operator, location=self.freezer, kind="FAILURE",
            started_at=now, description="Panne documentée",
        )
        with self.assertRaises(PermissionDenied):
            cold_storage.resolve_incident(
                self.operator, incident.pk, expected=incident.version,
                resolved_at=timezone.now(), corrective_action="Correction",
            )
        with self.assertRaises(ValidationError):
            cold_storage.resolve_incident(
                self.admin, incident.pk, expected=incident.version,
                resolved_at=timezone.now(), corrective_action="",
            )
        closed = cold_storage.resolve_incident(
            self.admin, incident.pk, expected=incident.version,
            resolved_at=timezone.now(), corrective_action="Équipement stabilisé",
        )
        self.assertIsNotNone(closed.resolved_at)


class SafetyGuardCoverageTests(OperationFixtures, TestCase):
    def test_target_resolution_cost_access_and_document_input_guards(self):
        with self.assertRaises(ValidationError):
            safety.require_target(self.admin, "unknown", uuid.uuid4())
        article = safety.require_target(self.admin, "article", self.article.pk, write=False)
        self.assertEqual(article.pk, self.article.pk)
        self.assertTrue(safety.target_cost_access(self.admin, "article", self.article))
        dummy = type("D", (), {
            "article_id": None, "receipt_id": None, "work_id": None,
            "sample_id": None, "order_id": None,
        })()
        with self.assertRaises(ValidationError):
            safety.document_target(dummy)

        with self.assertRaises(ValidationError):
            safety.attach_document(
                self.admin, "article", self.article.pk, title="Doc", kind="SDS",
                filename="x.txt", data=b"x", source="source",
            )
        with self.assertRaises(ValidationError):
            safety.attach_document(
                self.admin, "article", self.article.pk, title="", kind="SDS",
                filename="x.pdf", data=b"%PDF", source="source",
            )
        with self.assertRaises(ValidationError):
            safety.attach_document(
                self.admin, "article", self.article.pk, title="Doc", kind="SDS",
                filename="x.pdf", data=b"%PDF", source="source",
                documented_on=timezone.localdate() + timedelta(days=1),
            )

    def test_hazard_and_storage_rule_validation(self):
        with self.assertRaises(ValidationError):
            safety.save_hazard_tag(self.admin, {"bad": "field"})
        first = safety.save_hazard_tag(self.admin, {
            "code": "H1", "name": "Danger 1", "ghs_code": "GHS01",
            "description": "Description", "active": True,
        })
        second = safety.save_hazard_tag(self.admin, {
            "code": "H2", "name": "Danger 2", "ghs_code": "GHS02",
            "description": "Description", "active": True,
        })
        with self.assertRaises(ValidationError):
            safety.save_storage_rule(self.admin, {
                "location": self.freezer, "mode": "INCOMPATIBLE",
                "first_tag": first, "second_tag": first,
                "blocking": True, "active": True, "reference": "Référence",
            })
        with self.assertRaises(ValidationError):
            safety.save_storage_rule(self.admin, {
                "location": self.freezer, "mode": "INCOMPATIBLE",
                "first_tag": first, "second_tag": second,
                "blocking": True, "active": True, "reference": "",
            })
        rule = safety.save_storage_rule(self.admin, {
            "location": self.freezer, "mode": "INCOMPATIBLE",
            "first_tag": first, "second_tag": second,
            "blocking": True, "active": True, "reference": "Guide sécurité",
        })
        self.assertTrue(rule.active)


class StockPrimitiveCoverageTests(OperationFixtures, TestCase):
    def test_key_movement_location_and_post_guardrails(self):
        with self.assertRaises(ValidationError):
            stock._key("bad")
        key = uuid.uuid4()
        movement, created = stock._movement(
            self.admin, key, StockMovement.Kind.INVENTORY, {"x": 1}, reason="ok"
        )
        self.assertTrue(created)
        replay, created = stock._movement(
            self.admin, key, StockMovement.Kind.INVENTORY, {"x": 1}, reason="ok"
        )
        self.assertEqual(replay.pk, movement.pk)
        self.assertFalse(created)
        with self.assertRaises(Conflict):
            stock._movement(
                self.admin, key, StockMovement.Kind.INVENTORY, {"x": 2}, reason="ok"
            )
        with self.assertRaises(ValidationError):
            stock._movement(
                self.admin, uuid.uuid4(), StockMovement.Kind.INVENTORY,
                {"x": 1}, reason="x" * 501,
            )
        with self.assertRaises(ValidationError):
            stock._location(self.lab.pk)

        container, _, _ = self.receive()
        before = container.version
        stock._post(movement, container)
        container.refresh_from_db()
        self.assertEqual(container.version, before)
        with self.assertRaises(ValidationError):
            stock._post(movement, container, physical=-(container.quantity + 1))

    def test_control_and_reconciliation_error_paths(self):
        container, _, _ = self.receive(accepted=False)
        with self.assertRaises(ValidationError):
            stock.control_container(
                self.admin, container.pk, expected=container.version,
                status="UNKNOWN", reason="x",
            )
        with self.assertRaises(ValidationError):
            stock.control_container(
                self.admin, container.pk, expected=container.version,
                status="AVAILABLE", reason="",
            )
        StockContainer.objects.filter(pk=container.pk).update(quantity=Decimal("9"))
        rows = stock.reconcile_stock(self.admin)
        self.assertTrue(any(row["container"] == container.code for row in rows))
