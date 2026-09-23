"""Source-bound CDC edits reject malformed row operations and ambiguous content."""
import copy
from unittest.mock import patch

from django.test import SimpleTestCase
from erp.cdc import catalog, institutional
from erp.cdc.docengine import DocumentError


class CdcDataContracts(SimpleTestCase):
    def test_row_operations_validate_structure_coordinates_and_cells(self):
        base = catalog.initial_data('equipment')
        table = catalog.profile('equipment')['tables'][0]
        tid = table['id']
        good = {'source_row': 0, 'after_row': 0, 'cells': ['Ligne supplémentaire']}
        data = copy.deepcopy(base)
        data['rows'] = {tid: [good]}
        self.assertEqual(catalog.validate_data(data, 'equipment'), data)
        for rows in ({'unknown': [good]}, {tid: [None]}, {tid: [dict(good, price=10)]},
                     {tid: [dict(good, source_row=True)]}, {tid: [dict(good, after_row=99)]},
                     {tid: [dict(good, cells=[])]}, {tid: [dict(good, cells=['A\nB'])]}):
            data = copy.deepcopy(base)
            data['rows'] = rows
            with self.subTest(rows=rows), self.assertRaises(DocumentError):
                catalog.validate_data(data, 'equipment')

    def test_omitted_and_modified_sections_are_mutually_exclusive(self):
        data = catalog.initial_data('equipment')
        block = next(b for b in catalog.profile('equipment')['paragraphs'] if b.get('omittable') and not b['guard'])
        data.update(omitted=[block['id']], paragraphs={block['id']: 'Texte modifié'})
        with self.assertRaises(DocumentError):
            catalog.validate_data(data, 'equipment')
        data = catalog.initial_data('equipment')
        data['notes'] = 'x' * 100001
        with self.assertRaises(DocumentError):
            catalog.validate_data(data, 'equipment')
        # A large but individually valid edit map must still obey the overall dossier limit.
        data = catalog.initial_data('equipment')
        editable = [b['id'] for b in catalog.profile('equipment')['paragraphs'] if not b['guard']]
        self.assertGreater(len(editable), 81)
        data['paragraphs'] = {pid: 'x' * 100000 for pid in editable[:81]}
        with self.assertRaisesMessage(DocumentError, 'volumineux'):
            catalog.validate_data(data, 'equipment')

    def test_institutional_binding_refuses_unknown_sources_and_conflicting_contacts(self):
        data = catalog.initial_data('equipment')
        data['source_sha256'] = 'changed'
        with self.assertRaises(DocumentError):
            institutional.validate_policy(data)
        cases = [({'keys': ['phone_fax'], 'before': '041.24.63.69'}, 'No phone'),
                 ({'keys': ['phone_fax'], 'before': '041.24.63.69'}, '099.99.99.99'),
                 ({'keys': ['phone_fax'], 'before': '041.24.63.69'}, '041.24.63.69 et 041.24.63.69'),
                 ({'keys': ['postal_code'], 'before': '31000'}, '31999'),
                 ({'keys': ['reagents_ar_lot_numbers'], 'before': 'Avant', 'after': 'Après'}, 'Autre')]
        for binding, value in cases:
            with self.subTest(value=value), self.assertRaises(DocumentError):
                institutional._transform(value, binding, {'phone_fax': '041.24.63.76', 'postal_code': '31000'})
        self.assertEqual(institutional.policy_report({})['status'], 'LEGACY_UNCHANGED')

    def test_required_institutional_anchor_cannot_be_omitted(self):
        data = catalog.initial_data('equipment')
        binding = institutional.policy()['bindings']['equipment'][0]
        data['omitted'] = [binding['id']]
        with self.assertRaisesMessage(DocumentError, 'obligatoire'):
            institutional.apply_policy_edits(data, {}, {})
        data['omitted'] = []
        spans = {binding['id']: [{'segment': binding['segment'], 'before': binding['before'], 'after': binding['before']}]}
        _, updated = institutional.apply_policy_edits(data, {}, spans)
        self.assertEqual(updated[binding['id']][0]['after'], binding['after'])

    def test_empty_paragraph_insertion_and_complex_field_protection(self):
        from erp.cdc import procurement
        from erp.cdc.docengine import NS, parse_xml
        def paragraph(body):
            raw = ('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   + body + '</w:p>').encode()
            return raw, parse_xml(raw)
        raw, node = paragraph('')
        self.assertEqual(procurement._paragraph_fragment(raw, node, ''), raw)
        changed = procurement._paragraph_fragment(raw, node, 'A & B')
        self.assertIn(b'A &amp; B', changed)
        self.assertEqual(procurement.paragraph_value(parse_xml(changed)), 'A & B')
        raw, node = paragraph('<w:r><w:fldChar w:fldCharType="begin"/></w:r>')
        with self.assertRaises(DocumentError):
            procurement._paragraph_fragment(raw, node, 'Unsafe')
        raw = b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        with self.assertRaises(DocumentError):
            procurement._paragraph_fragment(raw, parse_xml(raw), 'No safe anchor')
        raw, node = paragraph('<w:r><w:t>Outer</w:t></w:r><w:p><w:r><w:t>Nested</w:t></w:r></w:p>')
        self.assertEqual(procurement.paragraph_value(node), 'Outer')

    def test_deleting_rows_refuses_crossing_bookmarks_and_word_references(self):
        from types import SimpleNamespace
        from erp.cdc import procurement
        from erp.cdc.docengine import NS, parse_xml
        prefix = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        start = '<w:bookmarkStart w:id="1" w:name="target"/>'
        end = '<w:bookmarkEnd w:id="1"/>'
        for row, reference in [(start, ''), (start + end, '<w:hyperlink w:anchor="target"/>'),
            (start + end, '<w:instrText>REF target</w:instrText>')]:
            root = parse_xml((prefix + '<w:tr>' + row + '</w:tr>' + reference + '</w:document>').encode())
            doc = SimpleNamespace(parts={'word/document.xml': (b'', root)})
            with self.subTest(reference=reference), self.assertRaises(DocumentError):
                procurement._deleted_bookmark_guard(doc, next(root.descendants(NS+'tr')))
        root = parse_xml((prefix + '<w:tr><w:bookmarkStart w:id="1"/>' + end + '</w:tr></w:document>').encode())
        procurement._deleted_bookmark_guard(SimpleNamespace(parts={'word/document.xml': (b'', root)}),
            next(root.descendants(NS+'tr')))

    def test_document_engine_edits_and_clones_safe_empty_cells(self):
        from erp.cdc.docengine import Document, NS, parse_xml, guarded_paragraph
        from erp.test_coverage_completion_cdc import _minimal_docx
        def document(cell):
            xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                '<w:body><w:p><w:r><w:t>Original</w:t></w:r></w:p><w:tbl><w:tr><w:tc>'
                + cell + '</w:tc></w:tr></w:tbl></w:body></w:document>').encode()
            return Document(_minimal_docx(xml))
        doc = document('<w:p></w:p>')
        pid = next(iter(doc.paragraphs))
        tid = next(iter(doc.tables))
        output, report = doc.generate({pid: 'Revised'}, {tid: [{'source_row': 0, 'cells': ['New & safe']}]})
        text = Document(output).parts['word/document.xml'][1].text
        self.assertIn('Revised', text)
        self.assertIn('New & safe', text)
        self.assertTrue(report['changes'])
        with self.assertRaises(DocumentError):
            doc.generate({}, span_edits={pid: [{'segment': 0, 'after': 'Missing before'}]})
        for cell in ['<w:p/>', '<w:p></w:p><w:p></w:p>', '<w:p><w:r><w:fldChar/></w:r></w:p>']:
            candidate = document(cell)
            with self.subTest(cell=cell), self.assertRaises(DocumentError):
                candidate.generate({}, {next(iter(candidate.tables)): [{'source_row': 0, 'cells': ['Unsafe']}]})
        drawing = document('<w:p><w:r><w:t>Source</w:t><w:drawing><wp:docPr id="7" name="Figure"/></w:drawing></w:r></w:p>')
        output, _ = drawing.generate({}, {next(iter(drawing.tables)): [{'source_row': 0, 'cells': ['Clone']}]})
        root = Document(output).parts['word/document.xml'][1]
        identities = [n.attrs['id'] for n in root.descendants() if n.name.endswith('|docPr')]
        self.assertEqual(identities, ['7', '8'])
        tracked = parse_xml(b'<w:ins xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Tracked</w:t></w:r></w:p></w:ins>')
        self.assertIn('suivie', guarded_paragraph(next(tracked.descendants(NS+'p'))))
        self.assertEqual(next(tracked.descendants(NS+'t')).text, 'Tracked')
