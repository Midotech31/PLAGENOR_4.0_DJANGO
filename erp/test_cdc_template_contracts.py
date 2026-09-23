"""Source-template drift is rejected before any public CDC generation."""
from unittest.mock import patch

from django.test import SimpleTestCase
from erp.cdc import catalog, procurement, schedule_adapter
from erp.cdc.docengine import Document, DocumentError, NS, parse_xml


class CdcTemplateContracts(SimpleTestCase):
    def test_equipment_and_reagent_template_structure_and_price_guards(self):
        for family in ['equipment', 'reagents']:
            model = catalog.document(family).data
            mapping = schedule_adapter.source_mapping(family)
            def check():
                return procurement.mapping.__wrapped__() if family == 'equipment' else schedule_adapter.source_mapping.__wrapped__(family)
            for damage in ['missing_table', 'row_count', 'columns', 'price_prompt', 'prefilled_price']:
                doc = Document(model)
                table_id = mapping[0]['tables']['bpu']['id']
                table = doc.tables[table_id][1]
                rows = procurement.children(table, 'tr')
                cells = procurement.children(rows[1], 'tc')
                if damage == 'missing_table':
                    del doc.tables[table_id]
                elif damage == 'row_count':
                    table.children.remove(rows[-1])
                elif damage == 'columns':
                    rows[1].children.remove(cells[-1])
                elif damage == 'price_prompt':
                    for p in procurement.cell_paragraphs(cells[1]):
                        if 'Prix unitaire en lettres' in procurement.paragraph_value(p):
                            for n in p.descendants(NS+'t'):
                                n.characters = ''
                else:
                    p = parse_xml(b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>100 DZD</w:t></w:r></w:p>')
                    p.parent = cells[3]
                    cells[3].children.append(p)
                with self.subTest(family=family, damage=damage), patch('erp.cdc.catalog.document', return_value=doc):
                    with self.assertRaises(DocumentError):
                        check()

    def test_schedule_bindings_reject_unknown_family_and_cross_lot_source(self):
        from erp.cdc.lot_catalog import get_catalog
        with self.assertRaises(DocumentError):
            schedule_adapter.source_mapping('unknown')
        self.assertEqual(schedule_adapter.managed_ids('unknown'), (set(), set()))
        schedule_adapter.validate_targets({'family': 'unknown'})
        data = catalog.initial_data('equipment')
        data['lot_catalog'] = get_catalog(data)
        first = data['lot_catalog']['lots'][0]
        first['items'][0]['key'] = 'source-2-1'
        with self.assertRaises(DocumentError):
            schedule_adapter.validate_targets(data)
        data['lot_catalog'] = get_catalog(catalog.initial_data('equipment'))
        tid = next(iter(schedule_adapter.managed_ids('equipment')[1]))
        data['rows'] = {tid: []}
        with self.assertRaises(DocumentError):
            schedule_adapter.validate_targets(data)
        data['rows'] = {}
        data['lot_catalog']['lots'][0]['items'] = []
        self.assertIn('LOT_EMPTY', [finding['id'] for finding in schedule_adapter.binding_findings(data)])

    def test_source_bound_lot_catalog_cannot_edit_protected_word_fields(self):
        from erp.cdc.lot_catalog import get_catalog
        data = catalog.initial_data('equipment')
        data['lot_catalog'] = get_catalog(data)
        item = data['lot_catalog']['lots'][1]['items'][4]
        item['specifications'] += ' Modification non autorisée'
        with self.assertRaises(DocumentError):
            schedule_adapter.validate_targets(data)

    def test_institutional_manifest_hash_schema_and_anchors_are_verified(self):
        import copy
        import json
        from erp.cdc import institutional
        from erp.cdc.docengine import sha
        with patch('pathlib.Path.read_bytes', return_value=b'changed policy'):
            with self.assertRaises(DocumentError):
                institutional.policy.__wrapped__()
        invalid = json.dumps({'schema': 2, 'id': institutional.CURRENT_POLICY}).encode()
        with patch('pathlib.Path.read_bytes', return_value=invalid), patch.object(institutional, 'POLICY_SHA256', sha(invalid)):
            with self.assertRaises(DocumentError):
                institutional.policy.__wrapped__()
        data = catalog.initial_data('equipment')
        for change in [{'id': 'missing-anchor'}, {'before': 'Changed source text'}]:
            manifest = copy.deepcopy(institutional.policy())
            manifest['bindings']['equipment'][0].update(change)
            with patch.object(institutional, 'policy', return_value=manifest), self.assertRaises(DocumentError):
                institutional.apply_policy_edits(data, {}, {})
        binding = institutional.policy()['bindings']['equipment'][0]
        paragraphs, _ = institutional.apply_policy_edits(data, {binding['id']: binding['before']}, {})
        self.assertEqual(paragraphs[binding['id']], binding['after'])

    def test_footer_cleanup_refuses_drift_and_conflicting_edits(self):
        from types import SimpleNamespace
        from erp.cdc import source_noise
        doc = catalog.document('equipment')
        pid = next(iter(source_noise.noise_ids('equipment')))
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans('equipment', {pid: [{'segment': 0}]}, doc)
        damaged = SimpleNamespace(source_index=[], editable_segments=doc.editable_segments)
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans('equipment', {}, damaged)
        damaged.source_index = doc.source_index
        for segments in ([], [[SimpleNamespace(characters='Unexpected footer')]]):
            damaged.editable_segments = lambda value: segments
            with self.subTest(segments=segments), self.assertRaises(DocumentError):
                source_noise.apply_noise_spans('equipment', {}, damaged)

    def test_number_cells_and_prototypes_require_unambiguous_editable_structure(self):
        from types import SimpleNamespace
        raw = b'<w:tc xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:fldChar/></w:r></w:p></w:tc>'
        with self.assertRaises(DocumentError):
            schedule_adapter.number_patch(raw, parse_xml(raw), '1')
        with self.assertRaises(DocumentError):
            schedule_adapter.prototype({'items': [{'fields': {'bpu': {'designation': []}}}], 'tables': {}})
        self.assertEqual(schedule_adapter.lot_label_projection({'family': 'unknown'}), ({}, {}))
        from erp.cdc.lot_catalog import get_catalog
        data = catalog.initial_data('equipment')
        data['lot_catalog'] = get_catalog(data)
        for lot in data['lot_catalog']['lots']:
            lot['source_slot'] = 0
        self.assertEqual(schedule_adapter.lot_label_projection(data), ({}, {}))
        payload = catalog.document('equipment').data
        self.assertEqual(schedule_adapter.rename_labels(payload, data), (payload, []))

    def test_bookmark_repairs_preserve_live_word_references(self):
        from types import SimpleNamespace
        prefix = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        suffix = '</w:document>'
        start = '<w:bookmarkStart w:id="1" w:name="target"/>'
        end = '<w:bookmarkEnd w:id="1"/>'
        original = (prefix+start+end+suffix).encode()
        current = SimpleNamespace(parts={'word/document.xml': (original, parse_xml(original))})
        for ref in ['<w:hyperlink w:anchor="target"/>', '<w:instrText>REF target</w:instrText>']:
            updated = (prefix+end+ref+suffix).encode()
            with self.subTest(ref=ref), self.assertRaises(DocumentError):
                schedule_adapter.repair_removed_bookmarks(current, updated)
        incomplete = (prefix+start+suffix).encode()
        source = SimpleNamespace(parts={'word/document.xml': (incomplete, parse_xml(incomplete))})
        self.assertEqual(schedule_adapter.repair_removed_bookmarks(source, incomplete), (incomplete, []))

    def test_works_subtotals_prevent_silent_reordering_of_articles(self):
        from erp.cdc.lot_catalog import get_catalog
        data = catalog.initial_data('works')
        data['lot_catalog'] = get_catalog(data)
        data['lot_catalog']['lots'][0]['items'].reverse()
        self.assertEqual(schedule_adapter.binding_findings(data)[0]['id'], 'WORKS_STRUCTURE_MAPPING')
        with self.assertRaises(DocumentError):
            schedule_adapter.apply_works_updates(catalog.document('works').data, data)

    def test_legacy_article_migration_preserves_values_and_rejects_dual_sources(self):
        from erp.cdc.lot_catalog import get_catalog
        data = catalog.initial_data('equipment')
        data['procurement'] = procurement.initial_procurement()
        item = data['procurement']['lots'][0]['items'][0]
        item['designation'] = 'Désignation validée par le responsable'
        item['quantity'] = item['quantity'] + '.0'
        migrated = get_catalog(data)
        self.assertEqual(migrated['lots'][0]['items'][0]['designation'], item['designation'])
        self.assertEqual(migrated['lots'][0]['items'][0]['quantity'], item['quantity'])
        data['lot_catalog'] = migrated
        with self.assertRaisesRegex(DocumentError, 'concurrentes'):
            catalog.validate_data(data, 'equipment')
        del data['lot_catalog']
        item['key'] = 'new-' + 'ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB'
        with self.assertRaisesRegex(DocumentError, 'correspond pas'):
            procurement.validate_procurement(data, 'equipment')

    def test_legacy_generation_reports_real_article_table_changes(self):
        from erp.cdc.docengine import sha
        data = catalog.initial_data('equipment')
        data['procurement'] = procurement.initial_procurement()
        payload = catalog.document('equipment').data
        output, report = procurement.apply_procurement(payload, data)
        self.assertEqual(output, payload)
        self.assertEqual(report['status'], 'UNCHANGED')
        data['procurement']['lots'][0]['items'][0]['quantity'] = '234'
        output, report = catalog.generate_document(data)
        self.assertEqual(report['procurement']['status'], 'GENERATED')
        self.assertIn('word/document.xml', report['changed_parts'])
        self.assertNotIn('word/document.xml', report['preserved_parts'])
        self.assertEqual(report['output_sha256'], sha(output))

    def test_arabic_labels_preserve_missing_anchors_and_explicit_time(self):
        from erp.cdc import consultation, common_data
        self.assertEqual(consultation._display_time('9:05', arabic=True), '09:05')
        self.assertEqual(consultation._split_ar('المشروع (FABLAB) وصف'), ('المشروع', '(FABLAB) وصف'))
        original = consultation.AR_OBJECT_MARKERS['reagents'][0] + ' وصف غير مكتمل'
        self.assertEqual(consultation._replace_ar_object(original, 'reagents', 'الجديد'), original)
        self.assertEqual(common_data.owner_label({'sources': ['CDC', 'Catalogue']}), 'CDC + Catalogue')

    def test_source_test_adapter_rejects_unsupported_marks(self):
        from types import ModuleType, SimpleNamespace
        from erp.cdc.tests.adapter import source_suite
        module = ModuleType('unsupported_source_fixture')
        exec('def test_example(): pass', module.__dict__)
        module.test_example.pytestmark = [SimpleNamespace(name='skip')]
        with self.assertRaisesRegex(RuntimeError, 'Unsupported source test marker: skip'):
            source_suite(module)

    def test_decimal_grammar_and_xml_parser_reject_invalid_inputs(self):
        from decimal import Decimal
        for value in ['1', '1,25', '1.000001', '١٢.٥', '１２.５']:
            self.assertEqual(procurement.quantity(value), Decimal(value.replace(',', '.')))
        for value in ['', 'NaN', 'Infinity', '1e2', '+1', '-1', '1_000', '1.1234567', '1..2', '0']:
            with self.subTest(value=value), self.assertRaises(DocumentError):
                procurement.quantity(value)
        for value in [b'', b' ', b'<!-- comment only -->', b'<first/><second/>', b'<root>']:
            with self.subTest(value=value), self.assertRaisesRegex(DocumentError, 'XML non valide'):
                parse_xml(value)
        self.assertEqual(parse_xml(b'<root/>').name, 'root')

    def test_corrupted_zip_crc_is_rejected_before_document_parsing(self):
        import io
        import zipfile
        from erp.cdc.docengine import safe_zip
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
            archive.writestr('payload.xml', b'<root>unique_payload</root>')
        corrupted = buffer.getvalue().replace(b'unique_payload', b'broken_payload')
        with self.assertRaisesRegex(DocumentError, 'Archive endommagée'):
            safe_zip(corrupted)
