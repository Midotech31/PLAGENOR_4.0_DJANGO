import uuid
from collections import Counter
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from erp.models import LegacyInventoryRecord
from erp.services import legacy_inventory as legacy
from erp.test_legacy_inventory_coverage import _equipment, _manifest


class LegacyInventoryFinalCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inventory-final-coverage-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_equipment_source_evidence_rejects_metadata_drift(self):
        from erp.models import PlanningResource

        row = _equipment(name="Vortex", room="01", row=7, quantity="1")
        legacy.apply_inventory(self.user, _manifest(equipment=[row]))
        resource = PlanningResource.objects.get(kind=PlanningResource.Kind.EQUIPMENT)
        source_record = LegacyInventoryRecord.objects.get(
            kind=LegacyInventoryRecord.Kind.EQUIPMENT,
            resolution=LegacyInventoryRecord.Resolution.IMPORTED,
        )
        changed = dict(row)
        changed["Model"] = "Different model"
        with self.assertRaisesMessage(
            ValidationError, "métadonnées structurées de cet équipement"
        ):
            legacy._ensure_equipment_inventory_source(
                resource, source_record, changed, 1, ""
            )

    def test_existing_serial_in_another_room_requires_review(self):
        from erp.models import PlanningResource
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = legacy._ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR",
            "name": "PLAGENOR",
            "kind": site_type,
            "active": True,
        })
        room1 = save_location(self.user, {
            "code": "ROOM01",
            "name": "Salle 01",
            "kind": room_type,
            "parent": root,
            "active": True,
        })
        room2 = save_location(self.user, {
            "code": "ROOM02",
            "name": "Salle 02",
            "kind": room_type,
            "parent": root,
            "active": True,
        })
        save_resource(self.user, {
            "code": "SERIAL-EXISTING",
            "name": "Vortex",
            "kind": PlanningResource.Kind.EQUIPMENT,
            "location": room1,
            "serial_number": "SER-X",
            "instructions": "",
            "active": True,
        })
        existing, issue, matched_by = legacy._find_existing_resource(
            "SERIAL-NEW",
            "SER-X",
            "Vortex",
            room2,
            _equipment(name="Vortex", room="02", row=8, serial="SER-X"),
        )
        self.assertIsNone(existing)
        self.assertEqual(matched_by, "")
        self.assertIn("ROOM01", issue)
        self.assertIn("ROOM02", issue)

    def test_duplicate_serial_previous_record_conflicts_are_blocked(self):
        row1 = _equipment(
            name="Hot Plate", room="01", row=3, quantity="1", serial="SER-DUP"
        )
        row2 = _equipment(
            name="Hot Plate", room="02", row=4, quantity="1", serial="SER-DUP"
        )
        manifest = _manifest(equipment=[row1, row2])
        source_key = legacy._source_key(
            "EQ", 1, row1["__source_file__"], row1["__source_row__"], 1
        )
        raw = dict(row1)
        raw["__physical_instance__"] = 1
        payload = legacy._source_record_payload(
            row1["__source_file__"],
            "Salle 01",
            row1["__source_row__"],
            LegacyInventoryRecord.Kind.EQUIPMENT,
            raw,
        )
        previous = LegacyInventoryRecord.objects.create(
            source_key=source_key,
            source_file=payload["source_file"],
            source_section=payload["source_section"],
            source_row=payload["source_row"],
            kind=payload["kind"],
            fingerprint="different-fingerprint",
            raw_data=raw,
            resolution=LegacyInventoryRecord.Resolution.REVIEW,
        )
        locations = {
            "ROOM01": SimpleNamespace(pk=uuid.uuid4(), code="ROOM01"),
            "ROOM02": SimpleNamespace(pk=uuid.uuid4(), code="ROOM02"),
        }
        with self.assertRaisesMessage(ValidationError, "Conflit de provenance"):
            legacy._apply_detailed_equipment(
                self.user, manifest, locations, Counter()
            )

        previous.fingerprint = payload["fingerprint"]
        previous.resolution = LegacyInventoryRecord.Resolution.IMPORTED
        previous.save(update_fields=["fingerprint", "resolution", "updated_at"])
        with self.assertRaisesMessage(ValidationError, "dupliqué dans la source"):
            legacy._apply_detailed_equipment(
                self.user, manifest, locations, Counter()
            )
