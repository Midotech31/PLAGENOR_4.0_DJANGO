"""Spreadsheet identity and row ordering remain mandatory on CDC intake."""
import io
import json
import uuid
import zipfile
from xml.etree import ElementTree as ET
from django.test import SimpleTestCase
from erp.cdc import catalog, lot_workbook
from erp.cdc.docengine import DocumentError
from erp.test_coverage_completion_pure import rewrite_zip


class CdcWorkbookContracts(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.data = catalog.initial_data('equipment')
        cls.dossier = uuid.uuid4()
        cls.payload = lot_workbook.build_workbook(cls.data, cls.dossier, 1, json.dumps)

    def parse(self, payload):
        return lot_workbook.parse_workbook(payload, 'lots.xlsx', self.data, self.dossier, 1, json.loads)

    def test_ambiguous_sheet_names_and_missing_identity_sheet_are_rejected(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            original = archive.read('xl/workbook.xml')
        for mutation, message in [('duplicate', 'ambigus'), ('identity', 'ne provient pas')]:
            root = ET.fromstring(original)
            sheets = root.find(lot_workbook.Q+'sheets')
            if mutation == 'duplicate':
                sheets[1].set('name', sheets[0].get('name'))
            else:
                sheets.remove(next(sheet for sheet in sheets if sheet.get('name') == '_CDC'))
            with self.subTest(mutation=mutation), self.assertRaisesRegex(DocumentError, message):
                self.parse(rewrite_zip(self.payload, [('xl/workbook.xml', ET.tostring(root))]))

    def test_noninteger_duplicate_and_nonpositive_row_orders_report_exact_cell(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            path = lot_workbook._sheet_paths(archive)['Lot_01']
            original = archive.read(path)
        for address, value in [('A7', 'abc'), ('A7', '0'), ('A8', '1')]:
            sheet = ET.fromstring(original)
            lot_workbook.cell(sheet, address, value)
            with self.subTest(address=address, value=value), self.assertRaises(lot_workbook.WorkbookError) as raised:
                self.parse(rewrite_zip(self.payload, [(path, ET.tostring(sheet))]))
            self.assertTrue(any(issue['cell'] == address and 'Ordre entier' in issue['message']
                for issue in raised.exception.issues))

    def test_malformed_number_style_is_not_interpreted_as_a_date(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            path = lot_workbook._sheet_paths(archive)['Lot_01']
            sheet = ET.fromstring(archive.read(path))
        quantity = sheet.find('.//'+lot_workbook.Q+'c[@r="F7"]')
        quantity.set('s', 'invalid-style-index')
        parsed = self.parse(rewrite_zip(self.payload, [(path, ET.tostring(sheet))]))
        self.assertEqual(parsed['diff']['totals']['updated'], 0)

    def test_invalid_relationship_targets_sheet_count_and_signer_are_rejected(self):
        with self.assertRaisesRegex(DocumentError, 'Identité du classeur invalide'):
            lot_workbook.build_workbook(self.data, self.dossier, 1, lambda data: None)
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        rel = next(node for node in rels if node.get('Type', '').endswith('/worksheet'))
        rel.set('Target', '../escape.xml')
        with self.assertRaisesRegex(DocumentError, 'Relation de feuille invalide'):
            self.parse(rewrite_zip(self.payload, [('xl/_rels/workbook.xml.rels', ET.tostring(rels))]))
        sheets = workbook.find(lot_workbook.Q+'sheets')
        attributes = dict(sheets[0].attrib)
        for index in range(53):
            ET.SubElement(sheets, lot_workbook.Q+'sheet', {**attributes, 'name': f'Excess_{index}'})
        with self.assertRaisesRegex(DocumentError, 'trop de feuilles'):
            self.parse(rewrite_zip(self.payload, [('xl/workbook.xml', ET.tostring(workbook))]))

    def test_template_dimensions_views_and_named_ranges_are_normalized(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        base = lot_workbook.BASE.read_bytes()
        changes = []
        with zipfile.ZipFile(io.BytesIO(base)) as archive:
            paths = lot_workbook._sheet_paths(archive)
            for name in ['Lot', '_CDC']:
                sheet = ET.fromstring(archive.read(paths[name]))
                if sheet.find(lot_workbook.Q+'dimension') is None:
                    sheet.insert(0, ET.Element(lot_workbook.Q+'dimension', {'ref': 'A1:A1'}))
                changes.append((paths[name], ET.tostring(sheet)))
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            names = ET.SubElement(workbook, lot_workbook.Q+'definedNames')
            ET.SubElement(names, lot_workbook.Q+'definedName', {'name': 'StaleRange'}).text = 'Lot!$A$1'
            views = workbook.find(lot_workbook.Q+'bookViews')
            if views is None:
                views = ET.SubElement(workbook, lot_workbook.Q+'bookViews')
            ET.SubElement(views, lot_workbook.Q+'workbookView', {'activeTab': '0'})
            changes.append(('xl/workbook.xml', ET.tostring(workbook)))
        changed = rewrite_zip(base, changes)
        with patch.object(lot_workbook, 'BASE', SimpleNamespace(read_bytes=lambda: changed)):
            output = lot_workbook.build_workbook(self.data, self.dossier, 1, json.dumps)
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            paths = lot_workbook._sheet_paths(archive)
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            self.assertIsNone(workbook.find(lot_workbook.Q+'definedNames'))
            self.assertTrue(all(node.get('activeTab') == '1' for node in workbook.iter(lot_workbook.Q+'workbookView')))
            self.assertEqual(ET.fromstring(archive.read(paths['Lot_01'])).find(lot_workbook.Q+'dimension').get('ref'), 'A1:I56')
            self.assertEqual(ET.fromstring(archive.read(paths['_CDC'])).find(lot_workbook.Q+'dimension').get('ref'), 'A1:B3')
        self.assertEqual(self.parse(output)['diff']['totals']['updated'], 0)

    def test_metadata_markers_and_external_relationships_are_mandatory(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            path = lot_workbook._sheet_paths(archive)['_CDC']
            original = archive.read(path)
            rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        for address, value, message in [('A1', 'WRONG', 'Format du classeur'), ('B2', 0, 'identité du classeur')]:
            sheet = ET.fromstring(original)
            lot_workbook.cell(sheet, address, value)
            with self.subTest(address=address), self.assertRaisesRegex(DocumentError, message):
                self.parse(rewrite_zip(self.payload, [(path, ET.tostring(sheet))]))
        ET.SubElement(rels, '{'+lot_workbook.P+'}Relationship', {
            'Id': 'external', 'Type': lot_workbook.R+'/hyperlink', 'TargetMode': 'External', 'Target': 'https://example.invalid/'})
        with self.assertRaisesRegex(DocumentError, 'liens externes'):
            self.parse(rewrite_zip(self.payload, [('xl/_rels/workbook.xml.rels', ET.tostring(rels))]))
        sheets = workbook.find(lot_workbook.Q+'sheets')
        next(sheet for sheet in sheets if sheet.get('name') == 'Lot_01').set('name', 'Renamed')
        with self.assertRaisesRegex(DocumentError, 'feuilles ou les lots ont changé'):
            self.parse(rewrite_zip(self.payload, [('xl/workbook.xml', ET.tostring(workbook))]))

    def test_shared_strings_size_and_existing_article_identity_recovery(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            paths = lot_workbook._sheet_paths(archive)
            original = archive.read(paths['Lot_01'])
            strings = ET.fromstring(archive.read('xl/sharedStrings.xml'))
        string_index = len(strings)
        ET.SubElement(ET.SubElement(strings, lot_workbook.Q+'si'), lot_workbook.Q+'t').text = 'Désignation validée'
        sheet = ET.fromstring(original)
        value = sheet.find('.//'+lot_workbook.Q+'c[@r="B7"]')
        value.clear()
        value.attrib.update(r='B7', t='s')
        ET.SubElement(value, lot_workbook.Q+'v').text = str(string_index)
        output = rewrite_zip(self.payload, [(paths['Lot_01'], ET.tostring(sheet)), ('xl/sharedStrings.xml', ET.tostring(strings))])
        self.assertEqual(self.parse(output)['data']['lot_catalog']['lots'][0]['items'][0]['designation'], 'Désignation validée')
        for index in range(10000):
            ET.SubElement(strings, lot_workbook.Q+'si')
        with self.assertRaisesRegex(DocumentError, 'Chaînes du classeur trop volumineuses'):
            self.parse(rewrite_zip(self.payload, [('xl/sharedStrings.xml', ET.tostring(strings))]))
        sheet = ET.fromstring(original)
        for cell in sheet.iter(lot_workbook.Q+'c'):
            if cell.get('r', '').startswith('I') and int(cell.get('r')[1:]) >= 7:
                lot_workbook.cell(sheet, cell.get('r'), '')
        parsed = self.parse(rewrite_zip(self.payload, [(paths['Lot_01'], ET.tostring(sheet))]))
        self.assertEqual(parsed['diff']['totals']['added'], 0)
        self.assertEqual(parsed['diff']['totals']['removed'], 0)

    def test_dates_oversized_quantities_and_negative_prices_are_not_silent(self):
        with zipfile.ZipFile(io.BytesIO(self.payload)) as archive:
            path = lot_workbook._sheet_paths(archive)['Lot_01']
            original = archive.read(path)
            styles = ET.fromstring(archive.read('xl/styles.xml'))
        formats = styles.find(lot_workbook.Q+'cellXfs')
        date_index = len(formats)
        ET.SubElement(formats, lot_workbook.Q+'xf', {'numFmtId': '14'})
        for address, value, style in [('F7', '45678', str(date_index)), ('F7', '1'*65, '0'), ('H7', '-1', '0')]:
            sheet = ET.fromstring(original)
            lot_workbook.cell(sheet, address, value, numeric=True)
            sheet.find('.//'+lot_workbook.Q+'c[@r="'+address+'"]').set('s', style)
            output = rewrite_zip(self.payload, [(path, ET.tostring(sheet)), ('xl/styles.xml', ET.tostring(styles))])
            with self.subTest(address=address, value=value), self.assertRaises(lot_workbook.WorkbookError) as raised:
                self.parse(output)
            self.assertTrue(any(issue['cell'] == address for issue in raised.exception.issues))
        sheet = ET.fromstring(original)
        sheet.find('.//'+lot_workbook.Q+'c[@r="F7"]').set('s', '999999')
        self.assertEqual(self.parse(rewrite_zip(self.payload, [(path, ET.tostring(sheet))]))['diff']['totals']['updated'], 0)

    def test_article_count_limit_and_reagent_packaging_are_enforced(self):
        from unittest.mock import patch
        with patch.object(lot_workbook, 'MAX_ITEMS', 2), self.assertRaisesRegex(DocumentError, '2 articles au maximum'):
            self.parse(self.payload)
        data = catalog.initial_data('reagents')
        payload = lot_workbook.build_workbook(data, self.dossier, 1, json.dumps)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            path = lot_workbook._sheet_paths(archive)['Lot_01']
            sheet = ET.fromstring(archive.read(path))
        lot_workbook.cell(sheet, 'E7', '')
        with self.assertRaises(lot_workbook.WorkbookError) as raised:
            lot_workbook.parse_workbook(rewrite_zip(payload, [(path, ET.tostring(sheet))]), 'lots.xlsx',
                data, self.dossier, 1, json.loads)
        self.assertTrue(any(issue['cell'] == 'E7' and 'conditionnement' in issue['message'] for issue in raised.exception.issues))
