import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from erp.models import BiologicalSample, Capability, SampleEvent, StoragePosition
from erp.services.access import save_grant
from erp.services.biobank import (
    _event, _replay, aliquot_sample, build_positions, convert_sample_quantity,
    receive_sample, reconcile_biobank, reserve_position, sample_action,
    transfer_sample,
)
from erp.services.common import Conflict
from erp.services.storage import save_location
from erp.test_operations import OperationFixtures


class BiobankEdgeCoverageTests(OperationFixtures, TestCase):
    def grant_biobank(self, user=None):
        save_grant(self.admin, {
            "user": user or self.operator,
            "capability": Capability.MANAGE_BIOBANK,
            "location": self.freezer,
        })

    def receive_sample(self, code="BIO-1", amount="10"):
        return receive_sample(
            self.admin, key=uuid.uuid4(), code=code, amount=Decimal(amount),
            unit=self.unit, location=self.freezer, received_on=timezone.localdate(),
            reason="Réception biologique vérifiée",
        )

    def test_sample_quantity_conversion_rejects_incompatible_inactive_and_packaging_units(self):
        self.assertEqual(convert_sample_quantity("2", self.unit, self.unit), Decimal("2.000000"))
        self.unit.active = False
        with self.assertRaises(ValidationError):
            convert_sample_quantity("1", self.unit, self.unit)
        self.unit.active = True
        with self.assertRaises(ValidationError):
            convert_sample_quantity("1", self.unit, self.ml)
        self.box.active = True
        other_box = self.box
        with self.assertRaises(ValidationError):
            convert_sample_quantity("1", other_box, self.unit)

    def test_position_build_reservation_and_destination_guards(self):
        with self.assertRaises(ValidationError):
            build_positions(self.admin, self.freezer.pk, expected=self.freezer.version)
        self.freezer.grid_rows = 2
        self.freezer.grid_columns = 2
        self.freezer.capacity = 4
        self.freezer.save()
        positions = list(build_positions(self.admin, self.freezer.pk, expected=self.freezer.version))
        self.assertEqual(len(positions), 4)
        with self.assertRaises(PermissionDenied):
            reserve_position(
                self.operator, positions[0].pk, assignee=self.second,
                until=timezone.now() + timedelta(hours=1), reason="Réservation",
            )
        self.grant_biobank()
        with self.assertRaises(ValidationError):
            reserve_position(
                self.operator, positions[0].pk, assignee=self.operator,
                until=timezone.now() - timedelta(seconds=1), reason="Réservation",
            )
        reservation = reserve_position(
            self.operator, positions[0].pk, assignee=self.operator,
            until=timezone.now() + timedelta(hours=1), reason="Réservation valide",
        )
        self.assertTrue(reservation.active)
        sample = receive_sample(
            self.operator, key=uuid.uuid4(), code="POS-TEST", amount=1, unit=self.unit,
            location=self.freezer, position=positions[0], received_on=timezone.localdate(),
            reason="Réception positionnée",
        )
        reservation.refresh_from_db()
        self.assertFalse(reservation.active)
        with self.assertRaises(ValidationError):
            receive_sample(
                self.admin, key=uuid.uuid4(), code="POS-DUP", amount=1, unit=self.unit,
                location=self.freezer, position=positions[0], received_on=timezone.localdate(),
                reason="Position déjà occupée",
            )
        self.assertEqual(sample.position_id, positions[0].pk)

    def test_receipt_event_replay_and_source_guardrails(self):
        sample = self.receive_sample()
        with self.assertRaises(ValidationError):
            _event(self.admin, sample, uuid.uuid4(), SampleEvent.Kind.ANALYSIS, {}, reason="")
        key = uuid.uuid4()
        event = _event(self.admin, sample, key, SampleEvent.Kind.ANALYSIS, {"x": 1}, reason="Analyse")
        self.assertEqual(_replay(self.admin, key, SampleEvent.Kind.ANALYSIS, {"x": 1}).pk, event.pk)
        with self.assertRaises(Conflict):
            _replay(self.admin, key, SampleEvent.Kind.ANALYSIS, {"x": 2})
        with self.assertRaises(ValidationError):
            receive_sample(
                self.admin, key=uuid.uuid4(), code="BAD-SOURCE", amount=1, unit=self.unit,
                location=self.freezer, received_on=timezone.localdate(), reason="Source",
                source_key="row:0", source_fingerprint="a" * 64,
            )
        with self.assertRaises(ValidationError):
            receive_sample(
                self.admin, key=uuid.uuid4(), code="FUTURE", amount=1, unit=self.unit,
                location=self.freezer, received_on=timezone.localdate() + timedelta(days=1),
                reason="Date future",
            )

    def test_transfer_aliquot_and_action_state_guards(self):
        sample = self.receive_sample("BIO-A")
        with self.assertRaises(ValidationError):
            transfer_sample(
                self.admin, sample.pk, key=uuid.uuid4(), destination=self.freezer,
                reason="Même emplacement", expected=sample.version,
            )
        with self.assertRaises(ValidationError):
            aliquot_sample(
                self.admin, sample.pk, key=uuid.uuid4(), code="ALI-BIG",
                amount=100, unit=self.unit, location=self.freezer,
                reason="Aliquot trop grand", expected=sample.version,
            )
        child = aliquot_sample(
            self.admin, sample.pk, key=uuid.uuid4(), code="ALI-1",
            amount=2, unit=self.unit, location=self.freezer,
            reason="Aliquot documenté", expected=sample.version,
        )
        self.assertEqual(child.remaining_quantity, Decimal("2.000000"))

        sample.refresh_from_db()
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="UNKNOWN", reason="x")
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="CHECK_OUT", reason="x")
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="RETURN", reason="x", destination=self.freezer)
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="CONSUMPTION", reason="x")
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="CONSUMPTION", reason="x", amount=999, unit=self.unit)

        event = sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="QUARANTINE", reason="Contrôle")
        self.assertEqual(event.sample.status, "QUARANTINE")
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="QUARANTINE", reason="Encore")
        sample.refresh_from_db()
        released = sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="RELEASE", reason="Libéré")
        self.assertEqual(released.sample.status, "STORED")

    def test_checkout_return_consumption_final_state_and_reconciliation(self):
        sample = self.receive_sample("BIO-B", "3")
        second_storage = save_location(self.admin, {
            "code": "F20", "name": "Congélateur secondaire", "kind": self.storage_kind,
            "parent": self.lab, "temperature_target": Decimal("-20"),
            "temperature_min": Decimal("-30"), "temperature_max": Decimal("-10"),
        })
        event = sample_action(
            self.admin, sample.pk, key=uuid.uuid4(), action="CHECK_OUT",
            reason="Analyse", destination=second_storage, thawed=True,
        )
        self.assertEqual(event.sample.status, "OUT")
        returned = sample_action(
            self.admin, sample.pk, key=uuid.uuid4(), action="RETURN",
            reason="Retour", destination=self.freezer,
        )
        self.assertEqual(returned.sample.status, "STORED")
        returned.sample.refresh_from_db()
        self.assertEqual(returned.sample.freeze_thaw_cycles, 1)

        consumed = sample_action(
            self.admin, sample.pk, key=uuid.uuid4(), action="CONSUMPTION",
            reason="Consommation totale", amount=3, unit=self.unit,
        )
        self.assertEqual(consumed.sample.status, "EXHAUSTED")
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action="ANALYSIS", reason="Après clôture")

        sample2 = self.receive_sample("BIO-C", "2")
        BiologicalSample.objects.filter(pk=sample2.pk).update(remaining_quantity=Decimal("1"))
        rows = reconcile_biobank(self.admin)
        self.assertEqual(rows[0]["sample"], "BIO-C")
