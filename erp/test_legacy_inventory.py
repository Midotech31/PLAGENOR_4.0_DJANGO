from copy import deepcopy
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from erp.models import (
    Article, LegacyInventoryRecord, PlanningResource, StockContainer, StockMovement,
)
from erp.services.legacy_inventory import (
    apply_inventory, load_manifest_gz, parse_exact_quantity, preview_inventory,
    review_legacy_record,
)


SNAPSHOT = (
    Path(__file__).resolve().parent / "assets" / "bootstrap"
    / "plagenor_inventory_2026.json.gz"
)

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _manifest(*, equipment=None, chemicals=None, consumables=None, reagents=None):
    return {
        "schema": 1,
        "source": {
            "baseline_date": "2026-09-25",
            "xlsx": {"name": "Inventaire PLAGENOR2026.xlsx", "sha256": "test-xlsx"},
            "zip": {"name": "Inventaire - PLAGENOR.zip", "sha256": "test-zip"},
        },
        "sheets": {
            "Equipement": [],
            "Produit chimique": chemicals or [],
            "Consommable": consumables or [],
            "Réactifs": reagents or [],
        },
        "equipment_room_inventory": equipment or [],
    }


def _equipment(name, room, row, *, quantity="1", serial="", model="Model test", reference="REF"):
    return {
        "Equipment Name": name,
        "Model": model,
        "Reference": reference,
        "Quantity": quantity,
        "Serial Number (S/N)": serial,
        "__source_file__": f"Laboratory Inventory List {room}.docx",
        "__source_row__": row,
        "__room__": room,
    }


class InventorySourcePreviewTests(TestCase):
    def test_bundled_snapshot_is_the_uploaded_real_inventory(self):
        manifest = load_manifest_gz(SNAPSHOT)
        self.assertEqual(
            manifest["source"]["xlsx"]["sha256"],
            "563f86e9bcdf25d15ff05ae5e876d933456180ec803cdb4ca97f680baf6fbcf4",
        )
        self.assertEqual(
            manifest["source"]["zip"]["sha256"],
            "62cb6731f08491cbce8afc17cef7a5aa6a82a279759be5884ed93511353cc109",
        )
        preview = preview_inventory(manifest)
        self.assertEqual(preview["source_rows"]["Equipement"], 156)
        self.assertEqual(preview["source_rows"]["Produit chimique"], 82)
        self.assertEqual(preview["source_rows"]["Consommable"], 83)
        self.assertEqual(preview["source_rows"]["Réactifs"], 93)
        self.assertEqual(preview["equipment"]["detailed_rows"], 239)
        self.assertEqual(preview["equipment"]["physical_assets"], 462)
        self.assertEqual(preview["chemicals"]["review_balances"], 9)
        self.assertEqual(preview["consumables"]["logical_rows"], 81)
        self.assertEqual(preview["reagents"]["logical_rows"], 92)

    def test_exact_quantity_parser_does_not_guess_opened_stock(self):
        self.assertEqual(parse_exact_quantity("2,5lx2")[:2], (5000, "ML"))
        amount, unit, issue = parse_exact_quantity("2,5l (entamé)")
        self.assertIsNone(amount)
        self.assertIsNone(unit)
        self.assertIn("non exactement mesurable", issue)


@override_settings(STORAGES=TEST_STORAGES)
class InventoryBootstrapTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inventory-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_identical_unserialised_equipment_are_distinct_physical_assets(self):
        manifest = _manifest(equipment=[
            _equipment("Vortex", "01", 3, quantity="2"),
        ])
        result = apply_inventory(self.user, manifest)
        self.assertEqual(result["equipment_created"], 2)
        self.assertEqual(
            PlanningResource.objects.filter(kind=PlanningResource.Kind.EQUIPMENT).count(), 2
        )
        self.assertEqual(
            LegacyInventoryRecord.objects.filter(
                kind=LegacyInventoryRecord.Kind.EQUIPMENT,
                resolution=LegacyInventoryRecord.Resolution.IMPORTED,
            ).count(),
            2,
        )

    def test_bootstrap_rejects_site_type_that_is_storage_capable(self):
        from erp.models import LocationType
        LocationType.objects.create(
            code="PLGSITE", name="Bad site", can_store=True, cold_storage=False,
        )
        with self.assertRaisesMessage(ValidationError, "PLGSITE"):
            apply_inventory(self.user, _manifest())

    def test_bootstrap_rejects_generic_room_type_that_is_storage_capable(self):
        from erp.models import LocationType
        LocationType.objects.create(
            code="PLGROOM", name="Bad room", can_store=True, cold_storage=False,
        )
        with self.assertRaisesMessage(ValidationError, "PLGROOM"):
            apply_inventory(self.user, _manifest())

    def test_bootstrap_rejects_storage_type_that_cannot_store(self):
        from erp.models import LocationType
        LocationType.objects.create(
            code="PLGSTOREROOM", name="Bad storage", can_store=False, cold_storage=False,
        )
        with self.assertRaisesMessage(ValidationError, "PLGSTOREROOM"):
            apply_inventory(self.user, _manifest())

    def test_existing_inactive_location_blocks_import(self):
        from erp.models import Location, LocationType
        from erp.services.legacy_inventory import _ensure_location
        kind = LocationType.objects.create(
            code="TESTROOM", name="Test", can_store=False, cold_storage=False,
        )
        Location.objects.create(
            code="ROOM01", name="Salle 01", kind=kind, active=False,
        )
        with self.assertRaisesMessage(ValidationError, "désactivé"):
            _ensure_location(self.user, "ROOM01", "Salle 01", kind)

    def test_storage_required_location_must_really_allow_storage(self):
        from erp.models import Location, LocationType
        from erp.services.legacy_inventory import _ensure_location
        kind = LocationType.objects.create(
            code="TESTROOM", name="Test", can_store=False, cold_storage=False,
        )
        Location.objects.create(
            code="ROOM03", name="Salle 03", kind=kind, active=True,
        )
        with self.assertRaisesMessage(ValidationError, "n’autorise pas le stockage"):
            _ensure_location(
                self.user, "ROOM03", "Salle 03", kind, require_storage=True,
            )

    def test_only_source_documented_stock_rooms_are_storage_capable(self):
        manifest = _manifest(
            equipment=[_equipment("Vortex", "01", 3)],
            chemicals=[{
                "N": "1", "Produit": "Ethanol", "Quantité": "1L",
                "Quantité reste": "1L", "Emplacement": "Salle 03", "__row__": 2,
            }],
        )
        apply_inventory(self.user, manifest)
        from erp.models import Location

        self.assertFalse(Location.objects.get(code="ROOM01").kind.can_store)
        self.assertTrue(Location.objects.get(code="ROOM03").kind.can_store)
        self.assertTrue(Location.objects.get(code="STOCK").kind.can_store)

    def test_known_instrument_family_reuses_unique_existing_resource_and_enriches_serial(self):
        from erp.models import Location, LocationType
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM11", "name": "Salle 11", "kind": room_type,
            "parent": root, "active": True,
        })
        existing = save_resource(self.user, {
            "code": "MISEQ-EXISTING", "name": "Illumina MiSeq",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "", "instructions": "Séquenceur NGS institutionnel",
        })
        source = _equipment(
            "Next-Generation Sequencer- Illumina", "11", 2,
            serial="20006903", model="MiSeqTM", reference="20020579",
        )
        result = apply_inventory(self.user, _manifest(equipment=[source]))
        existing.refresh_from_db()
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_reused"], 1)
        self.assertEqual(result["equipment_canonical_reused"], 1)
        self.assertEqual(existing.serial_number, "20006903")
        self.assertEqual(
            PlanningResource.objects.filter(kind=PlanningResource.Kind.EQUIPMENT).count(), 1
        )
        record = LegacyInventoryRecord.objects.get(
            kind=LegacyInventoryRecord.Kind.EQUIPMENT,
            resolution=LegacyInventoryRecord.Resolution.REUSED,
        )
        self.assertEqual(record.entity_id, existing.pk)
        self.assertIn("canonical_family", record.note)

    def test_known_instrument_family_with_conflicting_serial_is_not_duplicated(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM11", "name": "Salle 11", "kind": room_type,
            "parent": root, "active": True,
        })
        save_resource(self.user, {
            "code": "MISEQ-EXISTING", "name": "Illumina MiSeq",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "OTHER-SERIAL", "instructions": "",
        })
        source = _equipment(
            "Next-Generation Sequencer- Illumina", "11", 2,
            serial="20006903", model="MiSeqTM", reference="20020579",
        )
        result = apply_inventory(self.user, _manifest(equipment=[source]))
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        self.assertEqual(PlanningResource.objects.count(), 1)
        review = LegacyInventoryRecord.objects.get(
            kind=LegacyInventoryRecord.Kind.EQUIPMENT,
            resolution=LegacyInventoryRecord.Resolution.REVIEW,
        )
        self.assertIn("numéro de série divergent", review.note)

    def test_exact_serial_and_matching_identity_reuses_existing_resource(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM01", "name": "Salle 01", "kind": room_type,
            "parent": root, "active": True,
        })
        existing = save_resource(self.user, {
            "code": "EQ-EXISTING", "name": "Vortex",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "SER-EXACT", "instructions": "",
        })
        result = apply_inventory(
            self.user, _manifest(equipment=[
                _equipment("Vortex", "01", 3, serial="SER-EXACT"),
            ])
        )
        self.assertEqual(result["equipment_reused"], 1)
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(PlanningResource.objects.count(), 1)
        self.assertEqual(
            LegacyInventoryRecord.objects.get(
                kind=LegacyInventoryRecord.Kind.EQUIPMENT
            ).entity_id,
            existing.pk,
        )

    def test_same_serial_same_room_but_conflicting_designation_requires_review(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM01", "name": "Salle 01", "kind": room_type,
            "parent": root, "active": True,
        })
        save_resource(self.user, {
            "code": "EQ-EXISTING", "name": "Hot Plate",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "SER-SAME", "instructions": "",
        })
        result = apply_inventory(
            self.user, _manifest(equipment=[
                _equipment("Water Bath", "01", 3, serial="SER-SAME"),
            ])
        )
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        review = LegacyInventoryRecord.objects.get(
            resolution=LegacyInventoryRecord.Resolution.REVIEW
        )
        self.assertIn("désignation est contradictoire", review.note)

    def test_duplicate_existing_serials_are_never_auto_merged(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM01", "name": "Salle 01", "kind": room_type,
            "parent": root, "active": True,
        })
        for index in (1, 2):
            save_resource(self.user, {
                "code": f"EQ-DUP-{index}", "name": "Vortex",
                "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
                "serial_number": "SER-DUP", "instructions": "",
            })
        result = apply_inventory(
            self.user, _manifest(equipment=[
                _equipment("Vortex", "01", 3, serial="SER-DUP"),
            ])
        )
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        self.assertEqual(PlanningResource.objects.count(), 2)
        self.assertIn(
            "plusieurs équipements",
            LegacyInventoryRecord.objects.get(
                resolution=LegacyInventoryRecord.Resolution.REVIEW
            ).note,
        )

    def test_multiple_existing_canonical_family_candidates_require_review(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM11", "name": "Salle 11", "kind": room_type,
            "parent": root, "active": True,
        })
        for index in (1, 2):
            save_resource(self.user, {
                "code": f"MISEQ-{index}", "name": f"Illumina MiSeq {index}",
                "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
                "serial_number": "", "instructions": "",
            })
        result = apply_inventory(
            self.user, _manifest(equipment=[
                _equipment(
                    "Next-Generation Sequencer- Illumina", "11", 2,
                    serial="20006903", model="MiSeqTM", reference="20020579",
                ),
            ])
        )
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        self.assertIn(
            "Plusieurs ressources existantes",
            LegacyInventoryRecord.objects.get(
                resolution=LegacyInventoryRecord.Resolution.REVIEW
            ).note,
        )

    def test_canonical_family_without_source_serial_requires_review(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM11", "name": "Salle 11", "kind": room_type,
            "parent": root, "active": True,
        })
        save_resource(self.user, {
            "code": "MISEQ-1", "name": "Illumina MiSeq",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "", "instructions": "",
        })
        result = apply_inventory(
            self.user, _manifest(equipment=[
                _equipment(
                    "Next-Generation Sequencer- Illumina", "11", 2,
                    serial="", model="MiSeqTM", reference="20020579",
                ),
            ])
        )
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        self.assertIn(
            "ne fournit pas de numéro de série",
            LegacyInventoryRecord.objects.get(
                resolution=LegacyInventoryRecord.Resolution.REVIEW
            ).note,
        )

    def test_safe_deterministic_source_code_can_be_reused_only_with_exact_provenance(self):
        from erp.services.legacy_inventory import (
            _ensure_bootstrap_references, _equipment_code, _equipment_instructions,
        )
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM01", "name": "Salle 01", "kind": room_type,
            "parent": root, "active": True,
        })
        row = _equipment("Vortex", "01", 3)
        code = _equipment_code(row, 1, 1)
        existing = save_resource(self.user, {
            "code": code, "name": "Vortex",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "", "instructions": _equipment_instructions(row, 1),
        })
        result = apply_inventory(self.user, _manifest(equipment=[row]))
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_reused"], 1)
        self.assertEqual(
            LegacyInventoryRecord.objects.get(
                resolution=LegacyInventoryRecord.Resolution.REUSED
            ).entity_id,
            existing.pk,
        )

    def test_deterministic_code_collision_without_provenance_requires_review(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references, _equipment_code
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM01", "name": "Salle 01", "kind": room_type,
            "parent": root, "active": True,
        })
        row = _equipment("Vortex", "01", 3)
        save_resource(self.user, {
            "code": _equipment_code(row, 1, 1), "name": "Unrelated asset",
            "kind": PlanningResource.Kind.EQUIPMENT, "location": room,
            "serial_number": "", "instructions": "No source marker",
        })
        result = apply_inventory(self.user, _manifest(equipment=[row]))
        self.assertEqual(result["equipment_created"], 0)
        self.assertEqual(result["equipment_review"], 1)
        self.assertIn(
            "provenance physique",
            LegacyInventoryRecord.objects.get(
                resolution=LegacyInventoryRecord.Resolution.REVIEW
            ).note,
        )

    def test_conflicting_duplicate_serial_is_flagged_not_silently_merged(self):
        manifest = _manifest(equipment=[
            _equipment("Hot Plate", "01", 3, serial="SER-1"),
            _equipment("Water Bath", "02", 3, serial="SER-1"),
        ])
        result = apply_inventory(self.user, manifest)
        self.assertEqual(result["equipment_created"], 1)
        self.assertEqual(result["equipment_review"], 1)
        self.assertEqual(
            PlanningResource.objects.filter(kind=PlanningResource.Kind.EQUIPMENT).count(), 1
        )
        review = LegacyInventoryRecord.objects.get(
            resolution=LegacyInventoryRecord.Resolution.REVIEW
        )
        self.assertIn("doublon potentiel", review.note)
        self.assertIn("SER-1", review.note)

    def test_same_chemical_name_mass_and_volume_are_not_falsely_merged(self):
        chemicals = [
            {
                "N": "1", "Produit": "Sodium hydroxide", "Quantité": "1L",
                "Quantité reste": "1L", "Emplacement": "Salle 03", "__row__": 2,
            },
            {
                "N": "2", "Produit": "Sodium hydroxide", "Quantité": "1kg",
                "Quantité reste": "1kg", "Emplacement": "Salle 03", "__row__": 3,
            },
        ]
        result = apply_inventory(self.user, _manifest(chemicals=chemicals))
        self.assertEqual(result["stock_created"], 2)
        articles = Article.objects.filter(name="Sodium hydroxide").select_related("base_unit")
        self.assertEqual(articles.count(), 2)
        self.assertEqual(set(articles.values_list("base_unit__code", flat=True)), {"ML", "G"})
        self.assertEqual(StockContainer.objects.count(), 2)

    def test_rerunning_same_manifest_is_idempotent(self):
        manifest = _manifest(
            equipment=[_equipment("Vortex", "01", 3, quantity="2")],
            chemicals=[{
                "N": "1", "Produit": "Ethanol", "Quantité": "1L",
                "Quantité reste": "1L", "Emplacement": "Salle 01", "__row__": 2,
            }],
        )
        first = apply_inventory(self.user, deepcopy(manifest))
        counts = (
            PlanningResource.objects.count(),
            Article.objects.count(),
            StockContainer.objects.count(),
            StockMovement.objects.count(),
            LegacyInventoryRecord.objects.count(),
        )
        second = apply_inventory(self.user, deepcopy(manifest))
        self.assertEqual(
            (
                PlanningResource.objects.count(),
                Article.objects.count(),
                StockContainer.objects.count(),
                StockMovement.objects.count(),
                LegacyInventoryRecord.objects.count(),
            ),
            counts,
        )
        self.assertEqual(first["equipment_created"], 2)
        self.assertEqual(first["stock_created"], 1)
        self.assertEqual(second["equipment_unchanged"], 2)
        self.assertEqual(second["stock_unchanged"], 1)

    def test_changed_source_with_same_provenance_key_is_never_silently_overwritten(self):
        manifest = _manifest(equipment=[_equipment("Vortex", "01", 3)])
        apply_inventory(self.user, deepcopy(manifest))
        changed = deepcopy(manifest)
        changed["equipment_room_inventory"][0]["Equipment Name"] = "Different device"
        with self.assertRaises(ValidationError):
            apply_inventory(self.user, changed)

    def test_initial_inventory_trace_is_manager_only_and_filterable(self):
        manifest = _manifest(equipment=[_equipment("Vortex", "01", 3)])
        apply_inventory(self.user, manifest)
        self.client.force_login(self.user)
        url = reverse("erp:initial-inventory-trace")
        response = self.client.get(url, {"kind": "EQUIPMENT", "resolution": "IMPORTED"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laboratory Inventory List 01.docx")
        self.assertContains(response, "Équipement")
        filtered = self.client.get(url, {"review_status": "OPEN", "q": "Vortex"})
        self.assertEqual(filtered.status_code, 200)

        client_user = get_user_model().objects.create_user(
            username="inventory-client", password="x", role="CLIENT"
        )
        self.client.force_login(client_user)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_review_service_rejects_non_review_records_invalid_status_and_short_note(self):
        exact = _manifest(chemicals=[{
            "N": "1", "Produit": "Ethanol", "Quantité": "1L",
            "Quantité reste": "1L", "Emplacement": "Salle 03", "__row__": 2,
        }])
        apply_inventory(self.user, exact)
        imported = LegacyInventoryRecord.objects.get(
            resolution=LegacyInventoryRecord.Resolution.IMPORTED
        )
        with self.assertRaisesMessage(ValidationError, "À vérifier"):
            review_legacy_record(
                self.user, imported.pk, expected=imported.version,
                review_status=LegacyInventoryRecord.ReviewStatus.CONFIRMED,
                review_note="Source vérifiée.",
            )

        ambiguous = _manifest(chemicals=[{
            "N": "2", "Produit": "Acetone", "Quantité": "2,5L",
            "Quantité reste": "2,5L (entamé)", "Emplacement": "Salle 03", "__row__": 3,
        }])
        apply_inventory(self.user, ambiguous)
        review = LegacyInventoryRecord.objects.get(
            resolution=LegacyInventoryRecord.Resolution.REVIEW
        )
        with self.assertRaisesMessage(ValidationError, "conclusion de revue valide"):
            review_legacy_record(
                self.user, review.pk, expected=review.version,
                review_status=LegacyInventoryRecord.ReviewStatus.OPEN,
                review_note="Toujours à traiter.",
            )
        with self.assertRaisesMessage(ValidationError, "Documentez"):
            review_legacy_record(
                self.user, review.pk, expected=review.version,
                review_status=LegacyInventoryRecord.ReviewStatus.CONFIRMED,
                review_note="x",
            )

    def test_ambiguous_source_review_is_audited_without_mutating_original_data(self):
        manifest = _manifest(chemicals=[{
            "N": "1", "Produit": "Ethanol", "Quantité": "2,5L",
            "Quantité reste": "2,5L (entamé)", "Emplacement": "Salle 03", "__row__": 2,
        }])
        apply_inventory(self.user, manifest)
        record = LegacyInventoryRecord.objects.get(
            resolution=LegacyInventoryRecord.Resolution.REVIEW
        )
        original_raw = deepcopy(record.raw_data)
        original_fingerprint = record.fingerprint
        original_version = record.version
        self.client.force_login(self.user)
        url = reverse("erp:initial-inventory-review", args=[record.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2,5L (entamé)")
        response = self.client.post(url, {
            "expected_version": original_version,
            "review_status": LegacyInventoryRecord.ReviewStatus.CORRECTED,
            "review_note": "Quantité physique vérifiée puis correction reportée manuellement dans PLAGENOR.",
        })
        self.assertRedirects(response, reverse("erp:initial-inventory-trace"))
        record.refresh_from_db()
        self.assertEqual(record.raw_data, original_raw)
        self.assertEqual(record.fingerprint, original_fingerprint)
        self.assertEqual(record.review_status, LegacyInventoryRecord.ReviewStatus.CORRECTED)
        self.assertEqual(record.reviewed_by, self.user)
        self.assertIsNotNone(record.reviewed_at)
        self.assertEqual(record.version, original_version + 1)
        stale = self.client.post(url, {
            "expected_version": original_version,
            "review_status": LegacyInventoryRecord.ReviewStatus.CONFIRMED,
            "review_note": "Tentative basée sur une version obsolète.",
        })
        self.assertEqual(stale.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.review_status, LegacyInventoryRecord.ReviewStatus.CORRECTED)

    def test_real_snapshot_full_apply_is_idempotent_and_conservative(self):
        manifest = load_manifest_gz(SNAPSHOT)
        first = apply_inventory(self.user, deepcopy(manifest))
        self.assertEqual(first["equipment_created"], 457)
        self.assertEqual(first["equipment_review"], 7)
        self.assertEqual(first["equipment_excel_review"], 156)
        self.assertEqual(first["stock_created"], 244)
        self.assertEqual(first["chemical_review"], 9)
        self.assertEqual(first["zero_stock_rows"], 2)
        self.assertEqual(first["continuations_preserved"], 3)
        self.assertEqual(
            PlanningResource.objects.filter(kind=PlanningResource.Kind.EQUIPMENT).count(),
            457,
        )
        self.assertEqual(StockContainer.objects.count(), 244)
        from erp.models import Location
        self.assertEqual(
            set(Location.objects.filter(kind__can_store=True).values_list("code", flat=True)),
            {"STOCK", "ROOM03", "ROOM08", "ROOM10", "ROOM11", "ROOM14", "ROOM15", "ROOM16"},
        )
        self.assertEqual(
            StockMovement.objects.filter(kind=StockMovement.Kind.INITIAL).count(), 244
        )
        counts = (
            PlanningResource.objects.count(),
            Article.objects.count(),
            StockContainer.objects.count(),
            StockMovement.objects.count(),
            LegacyInventoryRecord.objects.count(),
        )
        second = apply_inventory(self.user, deepcopy(manifest))
        self.assertEqual(second["equipment_unchanged"], 457)
        self.assertEqual(second["stock_unchanged"], 246)
        self.assertEqual(
            (
                PlanningResource.objects.count(),
                Article.objects.count(),
                StockContainer.objects.count(),
                StockMovement.objects.count(),
                LegacyInventoryRecord.objects.count(),
            ),
            counts,
        )
