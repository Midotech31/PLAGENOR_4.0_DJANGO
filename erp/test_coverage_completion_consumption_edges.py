import uuid
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp.models import AnalysisRun, RunAllocation, StockContainer
from erp.services.biobank import receive_sample, source_samples
from erp.services.consumption import (
    _active, _operation, calculate_requirements, cancel_run, close_request_resources,
    confirm_run, create_run, lot_trace, reservation_proposal, reserve_run,
    save_profile, save_rule,
)
from erp.services.common import Conflict
from erp.test_operations import OperationFixtures


class ConsumptionEdgeCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.service = Service.objects.create(code="COV-RUN", name="Coverage run")
        member, _ = MemberProfile.objects.get_or_create(user=self.operator)
        self.req = Request.objects.create(
            display_id="COV-RUN-1", requester=self.outsider, assigned_to=member,
            service=self.service, title="Coverage analytical request",
            channel="IBTIKAR", status="ANALYSIS_STARTED",
            sample_table=[{"sample_code": "SRC-1", "quantity": "10", "quantity_unit": "µL"}],
        )
        self.profile = save_profile(self.ops, {
            "code": "COV-BOM", "name": "Coverage BOM", "service": self.service,
            "reference_samples": 1, "protocol_reference": "SOP-COV",
        })
        self.rule = save_rule(self.ops, self.profile.pk, {
            "article": self.article, "quantity": Decimal("2"),
            "unit": self.unit, "basis": "PROPORTIONAL",
        }, expected=self.profile.version)
        self.profile.refresh_from_db()
        self.container, _, _ = self.receive(quantity=20)

    def make_run(self, code="COV-R1", *, source_keys=None, samples=(), sample_count=1):
        if source_keys is None:
            source_keys = [source_samples(self.ops, self.req)[0]["key"]] if not samples else []
        return create_run(
            self.ops, request=self.req, profile=self.profile, code=code,
            name="Coverage series", sample_count=sample_count,
            planned_on=timezone.localdate(), source_keys=source_keys, samples=samples,
        )

    def reserve(self, run):
        proposal = reservation_proposal(self.ops, run)
        reserve_run(
            self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=proposal["allocations"], reason="Coverage reservation",
        )
        run.refresh_from_db()
        return RunAllocation.objects.get(requirement__run=run)

    def test_rule_update_operation_conflict_and_closed_run(self):
        updated = save_rule(
            self.ops, self.profile.pk,
            {"article": self.article, "quantity": Decimal("3"), "unit": self.unit, "basis": "PROPORTIONAL"},
            expected=self.profile.version, pk=self.rule.pk,
        )
        self.assertEqual(updated.version, 2)
        self.profile.refresh_from_db()

        run = self.make_run()
        key = uuid.uuid4()
        _operation(self.ops, run, key, "TEST", {"value": 1})
        with self.assertRaises(Conflict):
            _operation(self.ops, run, key, "TEST", {"value": 2})
        AnalysisRun.objects.filter(pk=run.pk).update(status=AnalysisRun.Status.COMPLETED)
        run.refresh_from_db()
        with self.assertRaises(ValidationError):
            _active(self.ops, run, run.version)

    def test_requirement_profile_and_article_guardrails(self):
        self.profile.active = False
        self.profile.save(update_fields=["active"])
        with self.assertRaises(ValidationError):
            calculate_requirements(self.profile, 1)
        self.profile.active = True
        self.profile.save(update_fields=["active"])
        self.article.active = False
        self.article.save(update_fields=["active"])
        with self.assertRaises(ValidationError):
            calculate_requirements(self.profile, 1)

    def test_create_run_rejects_service_duplicates_missing_sources_and_count_mismatch(self):
        other = Service.objects.create(code="COV-OTHER", name="Other")
        other_profile = save_profile(self.ops, {
            "code": "COV-OTHER-BOM", "name": "Other BOM", "service": other,
            "reference_samples": 1, "protocol_reference": "SOP-OTHER",
        })
        with self.assertRaises(ValidationError):
            create_run(
                self.ops, request=self.req, profile=other_profile, code="BAD-SVC",
                name="Bad", sample_count=1, planned_on=timezone.localdate(),
                source_keys=["x"],
            )

        source = source_samples(self.ops, self.req)[0]
        with self.assertRaises(ValidationError):
            self.make_run("DUP-SOURCE", source_keys=[source["key"], source["key"]], sample_count=2)
        with self.assertRaises(Conflict):
            self.make_run("MISSING-SOURCE", source_keys=["row:999"])
        with self.assertRaises(ValidationError):
            self.make_run("COUNT-MISMATCH", source_keys=[])

        manual = receive_sample(
            self.ops, key=uuid.uuid4(), code="MANUAL-OTHER", amount=1,
            unit=self.unit, location=self.freezer, received_on=timezone.localdate(),
            reason="Manual sample",
        )
        with self.assertRaises(ValidationError):
            self.make_run("WRONG-REQUEST", samples=[manual])

        source = source_samples(self.ops, self.req)[0]
        stored = receive_sample(
            self.ops, key=uuid.uuid4(), code="STORED-SOURCE", amount=1,
            unit=self.unit, location=self.freezer, received_on=timezone.localdate(),
            reason="Stored source", request=self.req, source_key=source["key"],
            source_fingerprint=source["fingerprint"],
        )
        with self.assertRaises(ValidationError):
            self.make_run(
                "SOURCE-AND-STORED", source_keys=[source["key"]],
                samples=[stored], sample_count=2,
            )

    def test_reservation_proposal_shortage_and_allocation_validation(self):
        run = self.make_run()
        StockContainer.objects.filter(pk=self.container.pk).update(quantity=Decimal("0"), reserved=Decimal("0"))
        proposal = reservation_proposal(self.ops, run)
        self.assertTrue(proposal["shortages"])

        StockContainer.objects.filter(pk=self.container.pk).update(quantity=Decimal("20"), reserved=Decimal("0"))
        run.refresh_from_db()
        for allocations in (
            [],
            [{"requirement": "x"}],
            [{"requirement": str(uuid.uuid4()), "container": str(self.container.pk), "quantity": "1"}],
        ):
            with self.subTest(allocations=allocations), self.assertRaises(ValidationError):
                reserve_run(
                    self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                    allocations=allocations, reason="Coverage",
                )

        requirement = run.requirements.get()
        duplicate = [
            {"requirement": str(requirement.pk), "container": str(self.container.pk), "quantity": "1"},
            {"requirement": str(requirement.pk), "container": str(self.container.pk), "quantity": "1"},
        ]
        with self.assertRaises(ValidationError):
            reserve_run(
                self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                allocations=duplicate, reason="Duplicate container",
            )
        with self.assertRaises(ValidationError):
            reserve_run(
                self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                allocations=[{"requirement": str(requirement.pk), "container": str(self.container.pk), "quantity": "1"}],
                reason="",
            )

    def test_confirmation_rejects_unknown_biology_and_changed_source(self):
        source = source_samples(self.ops, self.req)[0]
        stored = receive_sample(
            self.ops, key=uuid.uuid4(), code="BIO-CONF", amount=5,
            unit=self.unit, location=self.freezer, received_on=timezone.localdate(),
            reason="Stored sample", request=self.req, source_key=source["key"],
            source_fingerprint=source["fingerprint"],
        )
        run = self.make_run("BIO-CONF-RUN", samples=[stored])
        allocation = self.reserve(run)
        input_row = run.inputs.get()
        with self.assertRaises(ValidationError):
            confirm_run(
                self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                actuals={str(allocation.pk): "1"},
                biological_quantities={str(uuid.uuid4()): "1"},
                reason="Unknown biological input", confirmed=True,
            )

        run2 = self.make_run("SOURCE-CHANGED")
        allocation2 = self.reserve(run2)
        self.req.sample_table = [{"sample_code": "SRC-1", "quantity": "11", "quantity_unit": "µL"}]
        self.req.save(update_fields=["sample_table"])
        with self.assertRaises(Conflict):
            confirm_run(
                self.ops, run2.pk, expected=run2.version, key=uuid.uuid4(),
                actuals={str(allocation2.pk): "1"},
                reason="Source changed", confirmed=True,
            )

    def test_cancel_closure_permissions_replay_conflict_and_lot_trace(self):
        run = self.make_run()
        AnalysisRun.objects.filter(pk=run.pk).update(status=AnalysisRun.Status.COMPLETED)
        run.refresh_from_db()
        with self.assertRaises(ValidationError):
            cancel_run(
                self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                reason="Closed run",
            )

        run2 = self.make_run("CLOSE-RUN")
        self.reserve(run2)
        self.req.archived = True
        self.req.save(update_fields=["archived"])
        with self.assertRaises(PermissionDenied):
            close_request_resources(AnonymousUser(), self.req, "Close")

        close_request_resources(self.ops, self.req, "Close")
        self.assertFalse(lot_trace(self.ops, self.container.lot).exists())
