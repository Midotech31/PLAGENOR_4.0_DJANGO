import gzip
import io
import json
from pathlib import Path
import tempfile
import zipfile

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from erp.services import legacy_inventory as legacy


XLS_NS = legacy._XLSX_NS
OFFICE_REL_NS = legacy._OFFICE_REL_NS
PACKAGE_REL_NS = legacy._PACKAGE_REL_NS
DOC_NS = legacy._DOCX_NS


def _mini_xlsx_bytes():
    workbook = f"""<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="{XLS_NS}" xmlns:r="{OFFICE_REL_NS}">
      <sheets>
        <sheet name="Data" sheetId="1" r:id="rId1"/>
        <sheet name="Empty" sheetId="2" r:id="rId2"/>
      </sheets>
    </workbook>"""
    rels = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="{PACKAGE_REL_NS}">
      <Relationship Id="rId1" Target="worksheets/sheet1.xml"/>
      <Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/>
    </Relationships>"""
    shared = f"""<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="{XLS_NS}" count="1" uniqueCount="1"><si><t>Shared value</t></si></sst>"""
    sheet1 = f"""<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="{XLS_NS}">
      <sheetData>
        <row r="1">
          <c r="A1" t="inlineStr"><is><t>Name</t></is></c>
          <c r="B1" t="inlineStr"><is><t>Flag</t></is></c>
          <c r="C1" t="inlineStr"><is><t>Name</t></is></c>
          <c r="D1" t="inlineStr"><is><t></t></is></c>
        </row>
        <row r="2">
          <c r="A2" t="s"><v>0</v></c>
          <c r="B2" t="b"><v>1</v></c>
          <c r="C2"><v>12</v></c>
          <c r="D2" t="b"><v>0</v></c>
        </row>
        <row r="4"><c r="B4" t="inlineStr"><is><t>Only B</t></is></c></row>
      </sheetData>
    </worksheet>"""
    sheet2 = f"""<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{XLS_NS}"/>"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet1)
        archive.writestr("xl/worksheets/sheet2.xml", sheet2)
    return out.getvalue()


def _mini_docx_bytes(with_header=True):
    header = (
        "<w:tr><w:tc><w:p><w:r><w:t>Equipment Name</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Model</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Quantity</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Serial Number (S/N)</w:t></w:r></w:p></w:tc></w:tr>"
        if with_header else
        "<w:tr><w:tc><w:p><w:r><w:t>Unrelated</w:t></w:r></w:p></w:tc></w:tr>"
    )
    body = f"""<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="{DOC_NS}"><w:body><w:tbl>
      {header}
      <w:tr>
        <w:tc><w:p><w:r><w:t>Vortex</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>VX</w:t></w:r></w:p><w:p><w:r><w:t>Plus</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>1</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>S1</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr>
    </w:tbl></w:body></w:document>"""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", body)
    return out.getvalue()


def _mini_inventory_zip():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("Laboratory Inventory List 7.docx", _mini_docx_bytes())
        archive.writestr("Laboratory Inventory List XX.docx", _mini_docx_bytes(with_header=False))
        archive.writestr("__MACOSX/ghost.docx", _mini_docx_bytes())
        archive.writestr("notes.txt", "ignored")
    return out.getvalue()


class LegacyInventoryParserEdgeTests(SimpleTestCase):
    def test_text_slug_columns_and_scalar_parsers(self):
        self.assertEqual(legacy._text(None), "")
        self.assertEqual(legacy._slug("Étage / 3"), "ETAGE-3")
        self.assertEqual(legacy._slug("***", fallback="F"), "F")
        self.assertEqual(legacy._column_number("A1"), 1)
        self.assertEqual(legacy._column_number("AA9"), 27)
        self.assertEqual(legacy._column_number("1"), 0)
        self.assertEqual(legacy._integer("2"), 2)
        self.assertIsNone(legacy._integer("2.5"))
        self.assertIsNone(legacy._integer("-1"))
        self.assertIsNone(legacy._integer("abc"))
        self.assertEqual(legacy._decimal("2,5"), legacy.Decimal("2.5"))
        self.assertIsNone(legacy._decimal("abc"))
        self.assertEqual(legacy._room_code("Salle de stock"), "STOCK")
        self.assertEqual(legacy._room_code("Salle 7"), "ROOM07")
        self.assertEqual(legacy._room_code("nulle part"), "")
        self.assertEqual(legacy._room_label("STOCK"), "Salle de stock")
        self.assertEqual(legacy._room_label("ROOM07"), "Salle 07")
        self.assertEqual(legacy._room_label("X"), "X")
        self.assertEqual(legacy._serials("N/A"), [])
        self.assertEqual(legacy._serials("A / B; C\nD"), ["A", "B", "C", "D"])

    def test_quantity_parser_edge_cases(self):
        self.assertIsNone(legacy._unit_token("no unit"))
        self.assertIsNone(legacy._unit_token("1 kg + 1 l"))
        self.assertEqual(legacy._unit_token("1 kg + 2 g"), "G")
        self.assertEqual(legacy._parse_term("2x250g"), ("MASS", legacy.Decimal("500")))
        self.assertIsNone(legacy._parse_term("unknown"))
        self.assertEqual(
            legacy.parse_exact_quantity("", "G"),
            (None, "G", "quantité restante non renseignée"),
        )
        self.assertEqual(legacy.parse_exact_quantity("0", "G"), (legacy.Decimal("0"), "G", ""))
        amount, unit, issue = legacy.parse_exact_quantity("1g + 1ml")
        self.assertIsNone(amount)
        self.assertIsNone(unit)
        self.assertIn("dimensions différentes", issue)
        self.assertIn("à vérifier", legacy.parse_exact_quantity("nonsense", "G")[2])

    def test_xlsx_low_level_parser_and_records(self):
        sheets = legacy._xlsx_sheets(_mini_xlsx_bytes())
        self.assertIn("Data", sheets)
        self.assertEqual(sheets["Empty"], [])
        records = legacy._records_from_sheet(sheets["Data"])
        self.assertEqual(records[0]["Name"], "Shared value")
        self.assertEqual(records[0]["Flag"], "TRUE")
        self.assertEqual(records[0]["Name_2"], "12")
        self.assertEqual(records[0]["Colonne4"], "FALSE")
        self.assertEqual(records[1]["Flag"], "Only B")
        self.assertEqual(legacy._records_from_sheet([]), [])

    def test_docx_and_inventory_zip_parser(self):
        tables = list(legacy._docx_tables(_mini_docx_bytes()))
        self.assertEqual(tables[0][1][0], "Vortex")
        self.assertEqual(tables[0][1][1], "VX\nPlus")
        rows = legacy._equipment_rows_from_zip(_mini_inventory_zip())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["__room__"], "07")
        self.assertEqual(rows[0]["Equipment Name"], "Vortex")

    def test_parse_sources_and_deterministic_manifest_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            xlsx = tmp / "source.xlsx"
            bundle = tmp / "rooms.zip"
            xlsx.write_bytes(_mini_xlsx_bytes())
            bundle.write_bytes(_mini_inventory_zip())
            manifest = legacy.parse_inventory_sources(xlsx, bundle)
            self.assertEqual(manifest["schema"], 1)
            self.assertEqual(manifest["source"]["xlsx"]["sha256"], legacy._sha256_bytes(xlsx.read_bytes()))
            self.assertEqual(manifest["equipment_room_inventory"][0]["__room__"], "07")
            target = legacy.write_manifest_gz(manifest, tmp / "nested" / "snapshot.json.gz")
            first = target.read_bytes()
            loaded = legacy.load_manifest_gz(target)
            self.assertEqual(loaded, manifest)
            legacy.write_manifest_gz(manifest, target)
            self.assertEqual(target.read_bytes(), first)
            bad = tmp / "bad.json.gz"
            with gzip.open(bad, "wt", encoding="utf-8") as stream:
                json.dump({"schema": 999}, stream)
            with self.assertRaises(ValidationError):
                legacy.load_manifest_gz(bad)

    def test_sheet_field_continuation_and_preview_review_branches(self):
        manifest = {
            "schema": 1,
            "source": {},
            "sheets": {
                "Equipement": [{"Equipement": "X", "Nombre": "2", "Emplacement": "Salle 01", "__row__": 2}],
                "Produit chimique": [
                    {"Produit": "A", "Quantité": "1g", "Quantité reste": "0", "__row__": 2},
                    {"Produit": "B", "Quantité": "1g", "Quantité reste": "?", "__row__": 3},
                ],
                "Consommable": [
                    {"N": "1", "Produit": "Tube", "Unité": "Boîte", "Quantité": "2", "__row__": 2},
                    {"N": "", "Produit": "", "Unité": "100 unités", "Quantité": "", "__row__": 3},
                    {"N": "", "Produit": "", "Unité": "", "Quantité": "", "Extra": "suite", "__row__": 4},
                ],
                "Réactifs": [],
            },
            "equipment_room_inventory": [
                {
                    "Equipment Name": "X", "Quantity": "bad", "__room__": "01",
                    "__source_file__": "r.docx", "__source_row__": 2,
                }
            ],
        }
        self.assertEqual(legacy._field({"Produit": "Tube"}, "Produit"), "Tube")
        self.assertEqual(legacy._field({"Produit": "Tube"}, "Absent"), "")
        logical, continuations = legacy._merge_continuations(manifest["sheets"]["Consommable"])
        self.assertEqual(len(logical), 1)
        self.assertEqual(len(continuations), 2)
        self.assertIn("100 unités", logical[0]["Unité"])
        preview = legacy.preview_inventory(manifest)
        self.assertEqual(preview["equipment"]["review"][0]["issue"], "quantité d’équipement invalide")
        self.assertEqual(preview["chemicals"]["zero_balances"], 1)
        self.assertEqual(preview["chemicals"]["review_balances"], 1)
