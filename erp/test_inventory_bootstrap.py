from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
import io

from accounts.models import User
from erp.models import (
    Article, InventorySourceRecord, Location, PlanningResource, StockContainer, StockMovement,
)
from erp.services.inventory_bootstrap import (
    _duplicate_room_serials, apply_inventory, load_source, parse_exact_chemical_balance, room_enrichment,
    summarize, workbook_rows,
)


TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(STORAGES=TEST_STORAGES)
class PlagenorInventoryBootstrapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="inventory-bootstrap-admin",
            password="test",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_embedded_source_matches_institutional_files(self):
        source = load_source()
        self.assertEqual(source["schema"], 2)
        self.assertEqual(len(source["xlsx"]["Equipement"]) - 1, 156)
        self.assertEqual(len(source["xlsx"]["Produit chimique"]) - 1, 82)
        self.assertEqual(len(source["xlsx"]["Consommable"]) - 1, 83)
        self.assertEqual(len(source["xlsx"]["Réactifs"]) - 1, 93)
        self.assertEqual(len(source["room_lists"]), 239)
        self.assertEqual(len(source["sources"]["room_archive"]["files"]), 15)
        self.assertEqual(
            source["sources"]["workbook"]["sha256"],
            "563f86e9bcdf25d15ff05ae5e876d933456180ec803cdb4ca97f680baf6fbcf4",
        )
        self.assertEqual(
            source["sources"]["room_archive"]["sha256"],
            "62cb6731f08491cbce8afc17cef7a5aa6a82a279759be5884ed93511353cc109",
        )
        qtower = next(
            row for row in source["room_lists"]
            if row["source_file"] == "Laboratory Inventory List 13.docx"
            and row["source_row"] == 3
        )
        self.assertEqual(qtower["values"][2], "qTower³")
        self.assertEqual(
            qtower["values"][5],
            "3107B-3322475\n3107B-3322477",
        )

    def test_room_matching_uses_room_quantity_and_refuses_ambiguous_balance(self):
        source = load_source()
        equipment = [
            item for _, domain, item in workbook_rows(source)
            if domain == InventorySourceRecord.Domain.EQUIPMENT
        ]
        matches, _ = room_enrichment(source, equipment)
        self.assertIn(11, matches)
        self.assertEqual(matches[11]["row"]["values"][2], "qTower³")
        # Salle 10 contains two different precision balances; the generic
        # workbook wording is deliberately not forced onto either one.
        self.assertNotIn(31, matches)

    def test_duplicate_serials_in_room_files_are_detected_before_assignment(self):
        duplicates = _duplicate_room_serials(load_source())
        self.assertIn("2280021120286", duplicates)
        self.assertIn("33141 090", duplicates)

    def test_ambiguous_opened_chemical_is_never_fabricated(self):
        self.assertIsNone(parse_exact_chemical_balance("2l (entamé)"))
        self.assertIsNone(parse_exact_chemical_balance("500g x1 + 1 entamé"))
        self.assertEqual(parse_exact_chemical_balance("2,5l x 2"), (Decimal("5000.0"), "ML"))
        self.assertEqual(parse_exact_chemical_balance("1kg + 500g x 2"), (Decimal("2000"), "G"))

    def test_preview_is_read_only_and_reports_reconciliation(self):
        before = (
            Article.objects.count(), PlanningResource.objects.count(),
            InventorySourceRecord.objects.count(), StockMovement.objects.count(),
        )
        report = summarize()
        after = (
            Article.objects.count(), PlanningResource.objects.count(),
            InventorySourceRecord.objects.count(), StockMovement.objects.count(),
        )
        self.assertEqual(before, after)
        self.assertEqual(report["room_list_rows"], 239)
        self.assertGreater(report["equipment_enrichments"], 0)
        self.assertGreater(report["stock_rows_without_exact_balance"], 0)

    def test_apply_preserves_every_source_row_and_is_idempotent(self):
        source = load_source()
        equipment_units = sum(
            int(Decimal(str(item["values"][2])))
            for _, domain, item in workbook_rows(source)
            if domain == InventorySourceRecord.Domain.EQUIPMENT
        )
        first = apply_inventory(self.admin, date(2026, 9, 25))
        self.assertEqual(PlanningResource.objects.filter(code__startswith="PLG26-EQ-").count(), equipment_units)
        self.assertEqual(InventorySourceRecord.objects.count(), 156 + 82 + 83 + 93 + 239)
        self.assertEqual(StockMovement.objects.filter(kind="INITIAL").count(), first["stock_rows_imported"])
        self.assertGreater(InventorySourceRecord.objects.filter(status="NEEDS_REVIEW").count(), 0)
        self.assertTrue(
            InventorySourceRecord.objects.filter(
                domain="CHEMICAL", status="NEEDS_REVIEW",
                notes__icontains="stock physique non créé",
            ).exists()
        )
        qpcr = list(
            PlanningResource.objects.filter(
                code__in=["PLG26-EQ-011-01", "PLG26-EQ-011-02"]
            ).order_by("code")
        )
        self.assertEqual([item.model_name for item in qpcr], ["qTower³", "qTower³"])
        self.assertEqual(
            [item.serial_number for item in qpcr],
            ["3107B-3322475", "3107B-3322477"],
        )
        self.assertTrue(all(item.inventory_status == "UNVERIFIED" for item in qpcr))
        duplicated_serials = (
            PlanningResource.objects.exclude(serial_number="")
            .values_list("serial_number", flat=True)
        )
        self.assertEqual(len(list(duplicated_serials)), len(set(duplicated_serials)))
        self.assertIn("Server room", Location.objects.get(code="ROOM-01").notes)
        zero = InventorySourceRecord.objects.get(
            source_file="Inventaire PLAGENOR2026.xlsx",
            source_sheet="Produit chimique",
            source_row=16,
            domain="CHEMICAL",
        )
        self.assertEqual(zero.status, "IMPORTED")
        self.assertTrue(zero.normalized_data["zero_confirmed"])
        zero_article = Article.objects.get(pk=zero.target_id)
        self.assertFalse(zero_article.stock_lots.exists())
        counts = (
            Article.objects.count(),
            PlanningResource.objects.count(),
            StockContainer.objects.count(),
            StockMovement.objects.count(),
            InventorySourceRecord.objects.count(),
        )
        apply_inventory(self.admin, date(2026, 9, 25))
        self.assertEqual(
            counts,
            (
                Article.objects.count(),
                PlanningResource.objects.count(),
                StockContainer.objects.count(),
                StockMovement.objects.count(),
                InventorySourceRecord.objects.count(),
            ),
        )

    def test_room_list_unmatched_rows_are_evidence_not_active_equipment(self):
        apply_inventory(self.admin, date(2026, 9, 25))
        unmatched = InventorySourceRecord.objects.filter(
            source_kind="ROOM_LIST", status="NEEDS_REVIEW"
        )
        self.assertTrue(unmatched.exists())
        self.assertTrue(unmatched.filter(target_id__isnull=True).exists())

    def test_management_preview_is_safe_and_apply_requires_explicit_context(self):
        output = io.StringIO()
        call_command("seed_plagenor_inventory_2026", stdout=output)
        self.assertIn("Aucune donnée n'a été modifiée", output.getvalue())
        self.assertEqual(InventorySourceRecord.objects.count(), 0)
        with self.assertRaises(CommandError):
            call_command("seed_plagenor_inventory_2026", apply=True, actor=self.admin.username)

    def test_manager_can_review_inventory_provenance(self):
        apply_inventory(self.admin, date(2026, 9, 25))
        self.client.force_login(self.admin)
        response = self.client.get(reverse("erp:inventory-source"), {"status": "NEEDS_REVIEW"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventaire PLAGENOR 2026")
        self.assertContains(response, "À vérifier")
        response = self.client.get(reverse("erp:inventory-source"), {"q": "qTower"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "qTower")
        source = load_source()
        expected_hash = next(
            item["sha256"] for item in source["sources"]["room_archive"]["files"]
            if item["filename"] == "Laboratory Inventory List 13.docx"
        )
        room_record = InventorySourceRecord.objects.filter(
            source_kind="ROOM_LIST",
            source_file="Laboratory Inventory List 13.docx",
            normalized_data__model="qTower³",
        ).first()
        self.assertIsNotNone(room_record)
        self.assertEqual(room_record.source_sha256, expected_hash)

    def test_manager_can_apply_initial_inventory_from_review_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("erp:inventory-source"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "653")
        self.assertContains(response, "Intégrer l’inventaire initial")
        response = self.client.post(
            reverse("erp:inventory-source-apply"),
            {"snapshot_date": "2026-09-25", "confirm": "PLAGENOR-2026"},
        )
        self.assertRedirects(response, reverse("erp:inventory-source"))
        self.assertGreater(InventorySourceRecord.objects.count(), 0)
