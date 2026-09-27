import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from erp.models import LegacyInventoryRecord, PlanningResource, StockContainer
from erp.services import legacy_inventory as legacy
from erp.services.legacy_inventory import apply_inventory


SNAPSHOT = (
    Path(__file__).resolve().parent / "assets" / "bootstrap"
    / "plagenor_inventory_2026.json.gz"
)

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _manifest(*, equipment=None, excel_equipment=None, chemicals=None, consumables=None, reagents=None):
    return {
        "schema": 1,
        "source": {
            "baseline_date": "2026-09-25",
            "xlsx": {"name": "Inventaire PLAGENOR2026.xlsx", "sha256": "coverage-xlsx"},
            "zip": {"name": "Inventaire PLAGENOR.zip", "sha256": "coverage-zip"},
        },
        "sheets": {
            "Equipement": excel_equipment or [],
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


class InventoryCoveragePureFunctionTests(SimpleTestCase):
    def test_parser_skips_empty_tables_and_rows_without_equipment_identity(self):
        original = legacy._docx_tables
        with patch.object(
            legacy,
            "_docx_tables",
            side_effect=[iter([[]]), iter([[["Equipment Name", "Model"], ["", ""]]])],
        ):
            out = io.BytesIO()
            import zipfile
            with zipfile.ZipFile(out, "w") as archive:
                archive.writestr("Inventory A.docx", b"a")
                archive.writestr("Inventory B.docx", b"b")
            self.assertEqual(legacy._equipment_rows_from_zip(out.getvalue()), [])
        self.assertIs(legacy._docx_tables, original)

    def test_sheet_fallback_and_unattached_continuation_are_preserved(self):
        self.assertEqual(legacy._sheet({"sheets": {}}, "Missing"), ("Missing", []))
        rows = [{"N": "", "Produit": "", "Unité": "", "Extra": "orphan", "__row__": 9}]
        logical, continuations = legacy._merge_continuations(rows)
        self.assertEqual(logical, rows)
        self.assertEqual(continuations, [])

    def test_preview_exercises_reagent_and_location_projections(self):
        manifest = _manifest(
            equipment=[_equipment("Microscope", "01", 2)],
            chemicals=[{
                "Produit": "Water", "Quantité": "1L", "Quantité reste": "1L",
                "Emplacement": "Salle 03", "__row__": 2,
            }],
            consumables=[{
                "N": "1", "Produit": "Tube", "Unité": "Box", "Quantité": "1",
                "Emplacement": "Salle de stock", "__row__": 2,
            }],
            reagents=[{
                "N": "1", "Produit": "Buffer", "Unité": "Bottle", "Quantité": "2",
                "Emplacement": "Salle 08", "__row__": 2,
            }],
        )
        preview = legacy.preview_inventory(manifest)
        self.assertEqual(preview["reagents"]["logical_rows"], 1)
        self.assertEqual(preview["reagents"]["continuation_rows_merged"], 0)
        self.assertEqual(preview["locations"]["stock_enabled"], ["ROOM03", "ROOM08", "STOCK"])
        self.assertEqual(preview["locations"]["physical_only"], ["ROOM01"])

    def test_deterministic_codes_are_stable(self):
        article = legacy._article_code("CHEMICAL", "CHEMICAL|ethanol|g")
        self.assertTrue(article.startswith("INV26-CHEM-"))
        self.assertEqual(legacy._deterministic_uuid("source"), legacy._deterministic_uuid("source"))
        lot, container, manufacturer = legacy._stock_codes("source")
        self.assertTrue(lot.startswith("INV26-L-"))
        self.assertTrue(container.startswith("INV26-C-"))
        self.assertTrue(manufacturer.startswith("LEGACY-2026-"))


@override_settings(STORAGES=TEST_STORAGES)
class InventoryCommandCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coverage-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_preview_json_and_human_output(self):
        stdout = io.StringIO()
        call_command(
            "bootstrap_plagenor_inventory",
            "--from-snapshot", str(SNAPSHOT),
            "--json",
            stdout=stdout,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["schema"], 1)
        self.assertIn("equipment", payload)

        stdout = io.StringIO()
        call_command(
            "bootstrap_plagenor_inventory",
            "--from-snapshot", str(SNAPSHOT),
            stdout=stdout,
        )
        rendered = stdout.getvalue()
        self.assertIn("Inventaire PLAGENOR 2026", rendered)
        self.assertIn("Équipements détaillés", rendered)
        self.assertIn("Produits chimiques", rendered)
        self.assertIn("Consommables", rendered)
        self.assertIn("Réactifs", rendered)

    def test_snapshot_write_and_apply_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot.json.gz"
            stdout = io.StringIO()
            with patch(
                "erp.management.commands.bootstrap_plagenor_inventory.apply_inventory",
                return_value={"equipment_created": 0, "stock_created": 0},
            ):
                call_command(
                    "bootstrap_plagenor_inventory",
                    "--from-snapshot", str(SNAPSHOT),
                    "--snapshot", str(target),
                    "--apply",
                    "--actor", self.user.username,
                    stdout=stdout,
                )
            self.assertTrue(target.exists())
            self.assertIn("Manifeste écrit", stdout.getvalue())
            self.assertIn("equipment_created", stdout.getvalue())

    def test_command_validation_paths_and_source_parser_path(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("bootstrap_plagenor_inventory", "--apply", "--from-snapshot", str(SNAPSHOT))

        with self.assertRaises(CommandError):
            call_command(
                "bootstrap_plagenor_inventory",
                "--from-snapshot", str(SNAPSHOT),
                "--xlsx", "x.xlsx",
            )

        with self.assertRaises(CommandError):
            call_command("bootstrap_plagenor_inventory", "--from-snapshot", "missing.json.gz")

        with self.assertRaises(CommandError):
            call_command("bootstrap_plagenor_inventory", "--xlsx", "missing.xlsx", "--zip", "missing.zip")

        with self.assertRaises(CommandError):
            call_command("bootstrap_plagenor_inventory", "--xlsx", str(SNAPSHOT), "--zip", "missing.zip")

        with self.assertRaisesMessage(CommandError, "Utilisateur introuvable"):
            call_command(
                "bootstrap_plagenor_inventory",
                "--from-snapshot", str(SNAPSHOT),
                "--apply", "--actor", "missing-user",
            )

        with tempfile.TemporaryDirectory() as tmp:
            xlsx = Path(tmp) / "source.xlsx"
            bundle = Path(tmp) / "source.zip"
            xlsx.write_bytes(b"x")
            bundle.write_bytes(b"z")
            fake = _manifest()
            with patch(
                "erp.management.commands.bootstrap_plagenor_inventory.parse_inventory_sources",
                return_value=fake,
            ) as parser:
                stdout = io.StringIO()
                call_command(
                    "bootstrap_plagenor_inventory",
                    "--xlsx", str(xlsx), "--zip", str(bundle), "--json",
                    stdout=stdout,
                )
            parser.assert_called_once_with(str(xlsx), str(bundle))
            self.assertEqual(json.loads(stdout.getvalue())["schema"], 1)


@override_settings(STORAGES=TEST_STORAGES)
class InventoryCoverageDatabaseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="coverage-db-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_exact_serial_reuse_and_conflicting_designation(self):
        first = _manifest(equipment=[
            _equipment("Centrifuge", "01", 2, serial="SER-COVER-1"),
        ])
        apply_inventory(self.user, first)

        reuse = _manifest(equipment=[
            _equipment("Centrifuge", "01", 3, serial="SER-COVER-1"),
        ])
        report = apply_inventory(self.user, reuse)
        self.assertEqual(report["equipment_reused"], 1)
        self.assertEqual(
            PlanningResource.objects.filter(serial_number="SER-COVER-1").count(), 1,
        )

        conflict = _manifest(equipment=[
            _equipment("Different instrument", "01", 4, serial="SER-COVER-1"),
        ])
        report = apply_inventory(self.user, conflict)
        self.assertEqual(report["equipment_review"], 1)
        self.assertTrue(
            LegacyInventoryRecord.objects.filter(
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
                note__icontains="désignation est contradictoire",
            ).exists()
        )

    def test_duplicate_serial_candidates_require_review(self):
        from erp.services.legacy_inventory import _ensure_bootstrap_references
        from erp.services.planning import save_resource
        from erp.services.storage import save_location

        _, _, site_type, room_type, _ = _ensure_bootstrap_references(self.user)
        root = save_location(self.user, {
            "code": "PLAGENOR", "name": "PLAGENOR", "kind": site_type, "active": True,
        })
        room = save_location(self.user, {
            "code": "ROOM02", "name": "Salle 02", "kind": room_type,
            "parent": root, "active": True,
        })
        for code in ("DUP-A", "DUP-B"):
            save_resource(self.user, {
                "code": code,
                "name": "Instrument",
                "kind": PlanningResource.Kind.EQUIPMENT,
                "location": room,
                "serial_number": "DUP-SERIAL",
                "instructions": "",
                "active": True,
            })
        report = apply_inventory(self.user, _manifest(equipment=[
            _equipment("Instrument", "02", 8, serial="DUP-SERIAL"),
        ]))
        self.assertEqual(report["equipment_review"], 1)
        self.assertTrue(
            LegacyInventoryRecord.objects.filter(note__icontains="plusieurs équipements").exists()
        )

    def test_multiple_known_family_candidates_require_review(self):
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
        for code, name in (("MISEQ-A", "Illumina MiSeq"), ("MISEQ-B", "MiSeq sequencer")):
            save_resource(self.user, {
                "code": code,
                "name": name,
                "kind": PlanningResource.Kind.EQUIPMENT,
                "location": room,
                "serial_number": "",
                "instructions": "MiSeq",
                "active": True,
            })
        report = apply_inventory(self.user, _manifest(equipment=[
            _equipment(
                "Next-Generation Sequencer- Illumina", "11", 9,
                serial="", model="MiSeqTM", reference="20020579",
            ),
        ]))
        self.assertEqual(report["equipment_review"], 1)
        self.assertTrue(
            LegacyInventoryRecord.objects.filter(note__icontains="Plusieurs ressources").exists()
        )

    def test_excel_reconciliation_family_generic_and_review(self):
        manifest = _manifest(
            equipment=[
                _equipment(
                    "Next-Generation Sequencer- Illumina", "11", 2,
                    serial="MISEQ-COVER", model="MiSeqTM", reference="20020579",
                ),
                _equipment("Vortex", "03", 3, serial="VTX-COVER"),
            ],
            excel_equipment=[
                {"Equipement": "MiSeq", "Nombre": "1", "Emplacement": "Salle 11", "__row__": 2},
                {"Equipement": "Vortex", "Nombre": "1", "Emplacement": "Salle 03", "__row__": 3},
                {"Equipement": "MALDI Biotyper Sirius", "Nombre": "1", "Emplacement": "Salle 14", "__row__": 4},
            ],
        )
        report = apply_inventory(self.user, manifest)
        self.assertGreaterEqual(report["equipment_excel_matched"], 1)
        self.assertGreaterEqual(report["equipment_excel_review"], 1)

    def test_chemical_review_zero_exact_and_idempotent_paths(self):
        chemicals = [
            {"Produit": "", "Quantité": "1L", "Quantité reste": "1L", "Emplacement": "Salle 03", "__row__": 1},
            {"Produit": "Mystery", "Quantité": "box", "Quantité reste": "?", "Emplacement": "Salle 03", "__row__": 2},
            {"Produit": "Opened ethanol", "Quantité": "1L", "Quantité reste": "entamé", "Emplacement": "Salle 03", "__row__": 3},
            {"Produit": "Zero ethanol", "Quantité": "1L", "Quantité reste": "0", "Emplacement": "Salle 03", "__row__": 4},
            {"Produit": "Missing location", "Quantité": "1L", "Quantité reste": "1L", "Emplacement": "", "__row__": 5},
            {"Produit": "Exact ethanol", "Quantité": "1L", "Quantité reste": "500ml", "Emplacement": "Salle 03", "__row__": 6},
        ]
        manifest = _manifest(chemicals=chemicals)
        report = apply_inventory(self.user, manifest)
        self.assertGreaterEqual(report["chemical_review"], 3)
        self.assertEqual(report["zero_stock_rows"], 1)
        self.assertEqual(report["stock_created"], 1)
        self.assertEqual(StockContainer.objects.count(), 1)

        again = apply_inventory(self.user, manifest)
        self.assertGreaterEqual(again["stock_unchanged"], 5)

    def test_low_level_article_and_stock_lookup_helpers(self):
        from erp.models import Article, Category, Unit
        from erp.services.catalog import save_article
        from erp.services.legacy_inventory import _find_or_create_article, _stock_existing

        unit = Unit.objects.create(code="CVG", name="Coverage gram", dimension="MASS", factor=1)
        category = Category.objects.create(code="CVCAT", name="Coverage", active=True)
        created, reused = _find_or_create_article(
            self.user,
            kind="CHEMICAL",
            name="Coverage chemical",
            packaging="1 g",
            category=category,
            base_unit=unit,
        )
        self.assertFalse(reused)
        self.assertIsInstance(created, Article)
        found, reused = _find_or_create_article(
            self.user,
            kind="CHEMICAL",
            name="Coverage chemical",
            packaging="different",
            category=category,
            base_unit=unit,
        )
        self.assertTrue(reused)
        self.assertEqual(found.pk, created.pk)
        self.assertIsNone(_stock_existing("NO-SUCH-CONTAINER"))
