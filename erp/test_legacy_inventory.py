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


def _equipment(name, room, row, *, quantity="1", serial=""):
    return {
        "Equipment Name": name,
        "Model": "Model test",
        "Reference": "REF",
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

        client_user = get_user_model().objects.create_user(
            username="inventory-client", password="x", role="CLIENT"
        )
        self.client.force_login(client_user)
        self.assertEqual(self.client.get(url).status_code, 403)

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
