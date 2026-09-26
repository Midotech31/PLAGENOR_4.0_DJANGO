import io
import tempfile
import uuid
import zipfile
from collections import Counter
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from erp.management.commands.bootstrap_plagenor_inventory import Command
from erp.models import Article, LegacyInventoryRecord, StockContainer
from erp.services import legacy_inventory as legacy


def _manifest(*, equipment=None, excel=None, chemicals=None, consumables=None):
    return {
        "schema": legacy.SCHEMA_VERSION,
        "source": {
            "baseline_date": "2026-09-25",
            "xlsx": {"name": legacy.SOURCE_XLSX, "sha256": "test-xlsx"},
            "zip": {"name": legacy.SOURCE_ZIP, "sha256": "test-zip"},
        },
        "sheets": {
            "Equipement": excel or [],
            "Produit chimique": chemicals or [],
            "Consommable": consumables or [],
            "Réactifs": [],
        },
        "equipment_room_inventory": equipment or [],
    }


def _equipment(name="Vortex", room="01", row=2, quantity="1", serial=""):
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


class LegacyInventoryPureCoverageTests(SimpleTestCase):
    def test_zip_parser_skips_empty_tables_and_non_equipment_rows(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("Inventory.docx", b"placeholder")
        tables = [
            [],
            [
                ["Equipment Name", "Other"],
                ["", "not an equipment identity"],
            ],
        ]
        with patch.object(legacy, "_docx_tables", return_value=iter(tables)):
            self.assertEqual(legacy._equipment_rows_from_zip(out.getvalue()), [])

    def test_missing_sheet_and_non_continuation_row_are_preserved(self):
        self.assertEqual(legacy._sheet({"sheets": {}}, "Absent"), ("Absent", []))
        logical, continuations = legacy._merge_continuations([
            {"N": "1", "Produit": "", "Quantité": "1", "Note": "isolée"}
        ])
        self.assertEqual(logical, [
            {"N": "1", "Produit": "", "Quantité": "1", "Note": "isolée"}
        ])
        self.assertEqual(continuations, [])

    def test_article_duplicate_and_code_collision_are_rejected(self):
        base_unit = SimpleNamespace(code="PKG")
        category = object()
        duplicate_a = SimpleNamespace(name="Tube", packaging="Boîte", base_unit=base_unit)
        duplicate_b = SimpleNamespace(name="Tube", packaging="Boîte", base_unit=base_unit)
        with patch.object(Article.objects, "filter", return_value=[duplicate_a, duplicate_b]):
            with self.assertRaisesMessage(ValidationError, "Plusieurs articles existants"):
                legacy._find_or_create_article(
                    None,
                    kind="CONSUMABLE",
                    name="Tube",
                    packaging="Boîte",
                    category=category,
                    base_unit=base_unit,
                )

        collision_qs = MagicMock()
        collision_qs.first.return_value = object()

        def filtered(**kwargs):
            if "category" in kwargs:
                return []
            return collision_qs

        with patch.object(Article.objects, "filter", side_effect=filtered):
            with self.assertRaisesMessage(ValidationError, "Collision de code"):
                legacy._find_or_create_article(
                    None,
                    kind="CONSUMABLE",
                    name="Tube",
                    packaging="Boîte",
                    category=category,
                    base_unit=base_unit,
                )

    def test_receive_initial_stock_existing_and_preexisting_guards(self):
        article = SimpleNamespace(pk=uuid.uuid4(), name="Tube")
        location = SimpleNamespace(pk=uuid.uuid4(), code="ROOM03")
        unit = SimpleNamespace(code="PKG")
        expected = Decimal("1.000000")

        conflicting = SimpleNamespace(
            lot=SimpleNamespace(article_id=article.pk),
            location_id=location.pk,
            quantity=Decimal("2.000000"),
        )
        with (
            patch.object(legacy, "_stock_existing", return_value=conflicting),
            patch("erp.services.catalog.convert_quantity", return_value=(Decimal("1"), "PKG")),
        ):
            with self.assertRaisesMessage(ValidationError, "existe avec d’autres données"):
                legacy._receive_initial_stock(
                    None,
                    source_key="S1",
                    article=article,
                    location=location,
                    amount=Decimal("1"),
                    unit=unit,
                    raw={},
                )

        exact_existing = SimpleNamespace(
            lot=SimpleNamespace(article_id=article.pk),
            location_id=location.pk,
            quantity=expected,
        )
        with (
            patch.object(legacy, "_stock_existing", return_value=exact_existing),
            patch("erp.services.catalog.convert_quantity", return_value=(Decimal("1"), "PKG")),
        ):
            container, existed, issue = legacy._receive_initial_stock(
                None,
                source_key="S2",
                article=article,
                location=location,
                amount=Decimal("1"),
                unit=unit,
                raw={},
            )
        self.assertIs(container, exact_existing)
        self.assertTrue(existed)
        self.assertEqual(issue, "")

        exact_preexisting = SimpleNamespace(quantity=expected)
        query = MagicMock()
        query.exclude.return_value.select_related.return_value = [exact_preexisting]
        with (
            patch.object(legacy, "_stock_existing", return_value=None),
            patch.object(StockContainer.objects, "filter", return_value=query),
            patch("erp.services.catalog.convert_quantity", return_value=(Decimal("1"), "PKG")),
        ):
            container, existed, issue = legacy._receive_initial_stock(
                None,
                source_key="S3",
                article=article,
                location=location,
                amount=Decimal("1"),
                unit=unit,
                raw={},
            )
        self.assertIs(container, exact_preexisting)
        self.assertTrue(existed)
        self.assertEqual(issue, "")

        ambiguous = SimpleNamespace(quantity=Decimal("2.000000"))
        query = MagicMock()
        query.exclude.return_value.select_related.return_value = [ambiguous]
        with (
            patch.object(legacy, "_stock_existing", return_value=None),
            patch.object(StockContainer.objects, "filter", return_value=query),
            patch("erp.services.catalog.convert_quantity", return_value=(Decimal("1"), "PKG")),
        ):
            container, existed, issue = legacy._receive_initial_stock(
                None,
                source_key="S4",
                article=article,
                location=location,
                amount=Decimal("1"),
                unit=unit,
                raw={},
            )
        self.assertIsNone(container)
        self.assertFalse(existed)
        self.assertIn("ne peut pas être rapproché", issue)

    def test_detailed_equipment_invalid_quantity_and_missing_location(self):
        report = Counter()
        with patch.object(legacy, "_record_legacy") as record:
            legacy._apply_detailed_equipment(
                None,
                _manifest(equipment=[_equipment(quantity="bad")]),
                {},
                report,
            )
        record.assert_called_once()
        self.assertEqual(report["equipment_review"], 1)

        with self.assertRaisesMessage(ValidationError, "Emplacement ROOM01 non préparé"):
            legacy._apply_detailed_equipment(
                None,
                _manifest(equipment=[_equipment(quantity="1")]),
                {},
                Counter(),
            )

    def test_generic_excel_equipment_exact_match_is_reused(self):
        detailed = [_equipment(name="Vortex", room="01", quantity="2")]
        excel = [{
            "Equipement": "Vortex",
            "Nombre": "2",
            "Emplacement": "Salle 01",
            "__row__": 2,
        }]
        report = Counter()
        with (
            patch.object(legacy, "_already_applied", return_value=None),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_excel_equipment_reconciliation(
                _manifest(equipment=detailed, excel=excel),
                report,
            )
        self.assertEqual(report["equipment_excel_matched"], 1)
        self.assertEqual(record.call_args.kwargs["resolution"], LegacyInventoryRecord.Resolution.REUSED)

    def test_chemical_guard_branches(self):
        categories = {"CHEMICALS": object()}
        unit_g = SimpleNamespace(code="G")
        units = {"G": unit_g}
        article = SimpleNamespace(pk=uuid.uuid4(), name="Produit")
        location = SimpleNamespace(pk=uuid.uuid4(), code="ROOM03")

        report = Counter()
        legacy._apply_chemical_rows(
            None,
            _manifest(chemicals=[{"Produit": "", "__row__": 1}]),
            categories,
            units,
            {},
            report,
        )
        self.assertEqual(report["chemical_review"], 0)

        report = Counter()
        with patch.object(legacy, "_record_legacy") as record:
            legacy._apply_chemical_rows(
                None,
                _manifest(chemicals=[{
                    "Produit": "Inconnu",
                    "Quantité": "?",
                    "Quantité reste": "?",
                    "__row__": 2,
                }]),
                categories,
                units,
                {},
                report,
            )
        record.assert_called_once()
        self.assertEqual(report["chemical_review"], 1)

        row = {
            "Produit": "Produit",
            "Quantité": "1g",
            "Quantité reste": "1g",
            "Emplacement": "Salle 03",
            "__row__": 3,
        }
        report = Counter()
        with (
            patch.object(legacy, "_find_or_create_article", return_value=(article, False)),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_chemical_rows(
                None, _manifest(chemicals=[row]), categories, units, {}, report
            )
        record.assert_called_once()
        self.assertEqual(report["chemical_review"], 1)

        report = Counter()
        with (
            patch.object(legacy, "_find_or_create_article", return_value=(article, False)),
            patch.object(legacy, "_receive_initial_stock", return_value=(None, False, "conflit stock")),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_chemical_rows(
                None,
                _manifest(chemicals=[row]),
                categories,
                units,
                {"ROOM03": location},
                report,
            )
        record.assert_called_once()
        self.assertEqual(report["chemical_review"], 1)

    def test_packaged_stock_guard_branches(self):
        categories = {"CONSUMABLES": object()}
        unit_pkg = SimpleNamespace(code="PKG")
        units = {"PKG": unit_pkg}
        article = SimpleNamespace(pk=uuid.uuid4(), name="Tube")
        location = SimpleNamespace(pk=uuid.uuid4(), code="ROOM03")

        report = Counter()
        legacy._apply_packaged_rows(
            None,
            _manifest(consumables=[{"N": "1", "Produit": "", "Quantité": "1", "__row__": 1}]),
            sheet_needle="Consommable",
            kind="CONSUMABLE",
            category_code="CONSUMABLES",
            categories=categories,
            units=units,
            locations={},
            report=report,
        )
        self.assertEqual(report["packaged_review"], 0)

        invalid = {"N": "2", "Produit": "Tube", "Quantité": "bad", "__row__": 2}
        report = Counter()
        with (
            patch.object(legacy, "_already_applied", return_value=None),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_packaged_rows(
                None,
                _manifest(consumables=[invalid]),
                sheet_needle="Consommable",
                kind="CONSUMABLE",
                category_code="CONSUMABLES",
                categories=categories,
                units=units,
                locations={},
                report=report,
            )
        record.assert_called_once()
        self.assertEqual(report["packaged_review"], 1)

        zero = {"N": "3", "Produit": "Tube", "Quantité": "0", "__row__": 3}
        report = Counter()
        with (
            patch.object(legacy, "_already_applied", return_value=None),
            patch.object(legacy, "_find_or_create_article", return_value=(article, False)),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_packaged_rows(
                None,
                _manifest(consumables=[zero]),
                sheet_needle="Consommable",
                kind="CONSUMABLE",
                category_code="CONSUMABLES",
                categories=categories,
                units=units,
                locations={},
                report=report,
            )
        record.assert_called_once()
        self.assertEqual(report["zero_stock_rows"], 1)

        conflict = {
            "N": "4",
            "Produit": "Tube",
            "Quantité": "1",
            "Emplacement": "Salle 03",
            "__row__": 4,
        }
        report = Counter()
        with (
            patch.object(legacy, "_already_applied", return_value=None),
            patch.object(legacy, "_find_or_create_article", return_value=(article, False)),
            patch.object(legacy, "_receive_initial_stock", return_value=(None, False, "conflit stock")),
            patch.object(legacy, "_record_legacy") as record,
        ):
            legacy._apply_packaged_rows(
                None,
                _manifest(consumables=[conflict]),
                sheet_needle="Consommable",
                kind="CONSUMABLE",
                category_code="CONSUMABLES",
                categories=categories,
                units=units,
                locations={"ROOM03": location},
                report=report,
            )
        record.assert_called_once()
        self.assertEqual(report["packaged_review"], 1)

    def test_apply_rejects_unknown_manifest_schema(self):
        with self.assertRaisesMessage(ValidationError, "Version de manifeste"):
            legacy.apply_inventory(object(), {"schema": 999})


class LegacyInventoryDatabaseCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="inventory-coverage-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )

    def test_existing_legacy_record_mismatch_and_update_paths(self):
        source_key = "INV26:COVERAGE:1"
        record = LegacyInventoryRecord.objects.create(
            source_key=source_key,
            source_file="source.xlsx",
            source_section="Section",
            source_row="1",
            kind=LegacyInventoryRecord.Kind.EQUIPMENT,
            fingerprint="same",
            raw_data={"a": 1},
            resolution=LegacyInventoryRecord.Resolution.IMPORTED,
            note="initial",
        )
        base_payload = {
            "source_file": "source.xlsx",
            "source_section": "Section",
            "source_row": "1",
            "kind": LegacyInventoryRecord.Kind.EQUIPMENT,
            "raw_data": {"a": 1},
            "fingerprint": "same",
        }
        with self.assertRaisesMessage(ValidationError, "a changé depuis son import initial"):
            legacy._record_legacy(
                source_key=source_key,
                payload={**base_payload, "fingerprint": "different"},
                resolution=LegacyInventoryRecord.Resolution.REVIEW,
            )

        entity = SimpleNamespace(
            pk=uuid.uuid4(),
            _meta=SimpleNamespace(app_label="erp", model_name="coverageentity"),
        )
        updated, created = legacy._record_legacy(
            source_key=source_key,
            payload=base_payload,
            resolution=LegacyInventoryRecord.Resolution.REUSED,
            entity=entity,
            note="updated",
        )
        self.assertFalse(created)
        self.assertEqual(updated.pk, record.pk)
        updated.refresh_from_db()
        self.assertEqual(updated.resolution, LegacyInventoryRecord.Resolution.REUSED)
        self.assertEqual(updated.entity_type, "erp.coverageentity")
        self.assertEqual(updated.entity_id, entity.pk)
        self.assertEqual(updated.note, "updated")
        self.assertEqual(updated.version, record.version + 1)


class BootstrapInventoryCommandCoverageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="command-coverage-admin",
            password="x",
            role="SUPER_ADMIN",
            is_staff=True,
            is_superuser=True,
        )
        self.manifest = _manifest()

    def test_parser_preview_text_json_and_snapshot_output(self):
        Command().create_parser("manage.py", "bootstrap_plagenor_inventory")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = legacy.write_manifest_gz(self.manifest, tmp / "source.json.gz")
            copied = tmp / "copied.json.gz"

            output = io.StringIO()
            call_command(
                "bootstrap_plagenor_inventory",
                "--from-snapshot", str(source),
                "--snapshot", str(copied),
                stdout=output,
            )
            text = output.getvalue()
            self.assertTrue(copied.exists())
            self.assertIn("PREVIEW", text)
            self.assertIn("Équipements détaillés", text)
            self.assertIn("Numéros de série", text)
            self.assertIn("Zones de stockage", text)

            output = io.StringIO()
            call_command(
                "bootstrap_plagenor_inventory",
                "--from-snapshot", str(source),
                "--json",
                stdout=output,
            )
            self.assertIn('"schema": 1', output.getvalue())

    def test_apply_actor_validation_and_success_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = legacy.write_manifest_gz(self.manifest, Path(tmp) / "source.json.gz")
            with self.assertRaisesMessage(CommandError, "--actor est obligatoire"):
                call_command(
                    "bootstrap_plagenor_inventory",
                    "--from-snapshot", str(source),
                    "--apply",
                )
            with self.assertRaisesMessage(CommandError, "Utilisateur introuvable"):
                call_command(
                    "bootstrap_plagenor_inventory",
                    "--from-snapshot", str(source),
                    "--apply",
                    "--actor", "missing-user",
                )

            output = io.StringIO()
            with patch(
                "erp.management.commands.bootstrap_plagenor_inventory.apply_inventory",
                return_value={"equipment_created": 0, "stock_created": 0},
            ) as apply_mock:
                call_command(
                    "bootstrap_plagenor_inventory",
                    "--from-snapshot", str(source),
                    "--apply",
                    "--actor", self.user.username,
                    stdout=output,
                )
            apply_mock.assert_called_once()
            self.assertIn('"equipment_created": 0', output.getvalue())

    def test_manifest_source_validation_and_raw_sources_path(self):
        command = Command()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            snapshot = legacy.write_manifest_gz(self.manifest, tmp / "snapshot.json.gz")
            xlsx = tmp / "source.xlsx"
            bundle = tmp / "source.zip"
            xlsx.write_bytes(b"xlsx")
            bundle.write_bytes(b"zip")

            with self.assertRaisesMessage(CommandError, "soit --from-snapshot"):
                command._manifest({
                    "from_snapshot": str(snapshot),
                    "xlsx": str(xlsx),
                    "zip_path": None,
                })
            with self.assertRaisesMessage(CommandError, "Manifeste introuvable"):
                command._manifest({
                    "from_snapshot": str(tmp / "missing.json.gz"),
                    "xlsx": None,
                    "zip_path": None,
                })
            loaded = command._manifest({
                "from_snapshot": str(snapshot),
                "xlsx": None,
                "zip_path": None,
            })
            self.assertEqual(loaded["schema"], legacy.SCHEMA_VERSION)

            with self.assertRaisesMessage(CommandError, "--xlsx et --zip"):
                command._manifest({"from_snapshot": None, "xlsx": None, "zip_path": None})
            with self.assertRaisesMessage(CommandError, "XLSX introuvable"):
                command._manifest({
                    "from_snapshot": None,
                    "xlsx": str(tmp / "missing.xlsx"),
                    "zip_path": str(bundle),
                })
            with self.assertRaisesMessage(CommandError, "ZIP introuvable"):
                command._manifest({
                    "from_snapshot": None,
                    "xlsx": str(xlsx),
                    "zip_path": str(tmp / "missing.zip"),
                })

            with patch(
                "erp.management.commands.bootstrap_plagenor_inventory.parse_inventory_sources",
                return_value=self.manifest,
            ) as parse_mock:
                parsed = command._manifest({
                    "from_snapshot": None,
                    "xlsx": str(xlsx),
                    "zip_path": str(bundle),
                })
            self.assertIs(parsed, self.manifest)
            parse_mock.assert_called_once_with(str(xlsx), str(bundle))
