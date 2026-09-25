import copy
import io
import os
import stat
import tempfile
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from pypdf import PdfWriter

from erp.cdc import catalog, docengine, procurement
from erp.cdc.consultation import FIELDS
from erp.cdc.docengine import Document, DocumentError, NS, Node
from erp.models import CdcGeneration, CdcReviewDecision
from erp.services.cdc import (
    approve_dossier, edit_cdc_paragraph, estimate_totals, generate_cdc,
    save_cdc_item, save_cdc_lot, save_consultation, submit_dossier,
)
from erp.services.work import transition_work
from erp.test_operations import OperationFixtures


def _zip(entries, attrs=None):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        for name, value in entries:
            info = zipfile.ZipInfo(name)
            if attrs and name in attrs:
                info.external_attr = attrs[name]
            z.writestr(info, value)
    return out.getvalue()


def _minimal_docx(document_xml=b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>A</w:t></w:r></w:p></w:body></w:document>', extra=()):
    entries = [('[Content_Types].xml', b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'),
               ('word/document.xml', document_xml)]
    entries.extend(extra)
    return _zip(entries)


def _pdf(path, width=595.28, height=841.89, encrypted=False):
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    if encrypted:
        writer.encrypt('secret')
    with open(path, 'wb') as handle:
        writer.write(handle)
    return Path(path)


class DocumentEngineCoverageTests(TestCase):
    def test_text_zip_xml_and_byte_guardrails(self):
        for value in (None, 1, 'x' * 100001):
            with self.subTest(value=type(value)), self.assertRaises(DocumentError):
                docengine.xml_text(value)
        for value in ('bad\x01', '\ud800', '\ufffe'):
            with self.subTest(value=repr(value)), self.assertRaises(DocumentError):
                docengine.xml_text(value)
        self.assertEqual(docengine.xml_text('ok\n'), 'ok\n')
        with self.assertRaises(DocumentError):
            docengine.safe_zip(b'not a zip')
        with self.assertRaises(DocumentError):
            docengine.safe_zip(_zip([('a', b'1'), ('a', b'2')]))
        for name in ('../evil', '/absolute', 'C:bad'):
            with self.subTest(name=name), self.assertRaises(DocumentError):
                docengine.safe_zip(_zip([(name, b'x')]))
        fake_info = Mock(filename='a' + chr(92) + 'b', external_attr=0, file_size=1, flag_bits=0)
        fake_zip = Mock()
        fake_zip.namelist.return_value = [fake_info.filename]
        fake_zip.infolist.return_value = [fake_info]
        fake_zip.testzip.return_value = None
        with patch('erp.cdc.docengine.zipfile.ZipFile', return_value=fake_zip):
            with self.assertRaises(DocumentError):
                docengine.safe_zip(b'anything')
        symlink = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(DocumentError):
            docengine.safe_zip(_zip([('link', b'x')], {'link': symlink}))
        with self.assertRaises(DocumentError):
            docengine.safe_zip(_zip([('big', b'x' * 10)]), maximum=5)
        with self.assertRaises(DocumentError):
            docengine.tag_end(b'<tag', 0)
        with self.assertRaises(DocumentError):
            docengine.parse_xml(b'<!DOCTYPE x><x/>')
        with self.assertRaises(DocumentError):
            docengine.parse_xml(b'<x>')
        with self.assertRaises(DocumentError):
            docengine.parse_xml(b'<x/><y/>')
        root = docengine.parse_xml(b'<x><y>abc</y><z/></x>')
        self.assertEqual(root.text, '')
        self.assertEqual(list(root.descendants())[0].characters, 'abc')
        self.assertIs(list(root.descendants())[0].ancestor('x'), root)
        self.assertIsNone(root.ancestor('x'))
        self.assertEqual(docengine.apply_byte_edits(b'abcdef', [(1, 3, b'X')]), b'aXdef')
        for edits in ([(2, 4, b'x'), (3, 5, b'y')], [(-1, 1, b'x')], [(0, 7, b'x')], [(3, 2, b'x')]):
            with self.subTest(edits=edits), self.assertRaises(DocumentError):
                docengine.apply_byte_edits(b'abcdef', edits)

    def test_edit_nodes_guarded_segments_and_constructor_fail_closed(self):
        raw = b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>A</w:t><w:t>B</w:t></w:r></w:p>'
        p = docengine.parse_xml(raw)
        nodes = docengine.own_text_nodes(p)
        self.assertEqual(docengine.edit_text_nodes(nodes, 'AB', raw), [])
        with self.assertRaises(DocumentError):
            docengine.edit_text_nodes(nodes, 'A\nB', raw)
        with self.assertRaises(DocumentError):
            docengine.edit_text_nodes([], 'x', raw)
        edits = docengine.edit_text_nodes(nodes, ' A&B ', raw)
        self.assertTrue(edits)
        changed = docengine.apply_byte_edits(raw, edits)
        self.assertIn(b'&amp;', changed)
        selfclosing = b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t/></w:r></w:p>'
        sp = docengine.parse_xml(selfclosing)
        sn = docengine.own_text_nodes(sp)
        self.assertTrue(docengine.edit_text_nodes(sn, 'X', selfclosing))
        guarded = docengine.parse_xml(b'<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:br/></w:r></w:p>')
        self.assertTrue(docengine.guarded_paragraph(guarded))
        with self.assertRaises(DocumentError):
            Document(_minimal_docx(), expected_sha='0' * 64)
        with self.assertRaises(DocumentError):
            Document(_zip([('[Content_Types].xml', b'<x/>')]))
        with self.assertRaises(DocumentError):
            Document(_minimal_docx(extra=(('word/vbaProject.bin', b'x'),)))

    def test_document_catalog_inspection_and_generate_paths(self):
        doc = catalog.document('equipment')
        table_catalog = doc.table_catalog()
        self.assertTrue(table_catalog)
        self.assertTrue(doc.inspection()['tables'])
        with self.assertRaises(DocumentError):
            doc.editable_segments('missing')
        editable = next(b for b in doc.source_index if not b['guard'] and b['text'] and not b['in_table'])
        pid = editable['id']
        segments = doc.editable_segments(pid)
        self.assertTrue(segments)
        before = ''.join(n.characters for n in segments[0])
        output, report = doc.generate(span_edits={pid: [{'segment': 0, 'before': before, 'after': before + ' X'}]})
        self.assertNotEqual(output, doc.data)
        self.assertEqual(report['validation'], 'OOXML_CHECKED')
        for bad in (([1], {}, []), ({}, [1], []), ({}, {}, 'x')):
            with self.subTest(bad=bad), self.assertRaises(DocumentError):
                doc.generate(bad[0], bad[1], bad[2])
        with self.assertRaises(DocumentError):
            doc.generate(span_edits=[])
        with self.assertRaises(DocumentError):
            doc.generate(span_edits={pid: 'bad'})
        with self.assertRaises(DocumentError):
            doc.generate(span_edits={pid: [{'segment': 0, 'before': before, 'after': before},
                                           {'segment': 0, 'before': before, 'after': before}]})
        with self.assertRaises(DocumentError):
            doc.generate(span_edits={pid: [{'segment': 9999, 'before': before, 'after': before}]})
        with self.assertRaises(DocumentError):
            doc.generate(span_edits={pid: [{'segment': 0, 'before': 'wrong', 'after': before}]})
        with self.assertRaises(DocumentError):
            doc.generate(paragraph_edits={pid: before}, span_edits={pid: []})
        with self.assertRaises(DocumentError):
            doc.generate(paragraph_edits={'missing': 'x'})
        guarded = next(b for b in doc.source_index if b['guard'])
        with self.assertRaises(DocumentError):
            doc.generate(paragraph_edits={guarded['id']: 'x'})
        with self.assertRaises(DocumentError):
            doc.generate(table_edits={'missing': []})
        tid = next(t['id'] for t in table_catalog if any(row['cloneable'] for row in t['rows']))
        table = next(t for t in table_catalog if t['id'] == tid)
        ri = next(row['index'] for row in table['rows'] if row['cloneable'])
        row = table['rows'][ri]
        output, report = doc.generate(table_edits={tid: [{'source_row': ri, 'after_row': ri,
            'cells': [cell['text'].replace('\n', ' ') for cell in row['cells']]}]})
        self.assertTrue(any(c['kind'] == 'row_added' for c in report['changes']))
        with self.assertRaises(DocumentError):
            doc.generate(table_edits={tid: 'bad'})
        with self.assertRaises(DocumentError):
            doc.generate(table_edits={tid: [{'source_row': -1, 'cells': []}]})
        with self.assertRaises(DocumentError):
            doc.generate(table_edits={tid: [{'source_row': ri, 'cells': []}]})
        unsafe = next((r for t in table_catalog for r in t['rows'] if not r['cloneable'] and r['cells']), None)
        if unsafe:
            unsafe_tid = next(t['id'] for t in table_catalog if unsafe in t['rows'])
            with self.assertRaises(DocumentError):
                doc.generate(table_edits={unsafe_tid: [{'source_row': unsafe['index'], 'cells': [c['text'] for c in unsafe['cells']]}]})
        omittable = next(b for b in doc.source_index if not b['in_table'] and not b['guard']
                         and doc.paragraphs[b['id']][1].parent is not None
                         and doc.paragraphs[b['id']][1].parent.name == NS + 'body'
                         and not any(n.name in (NS+'sectPr', NS+'bookmarkStart', NS+'bookmarkEnd', NS+'fldChar', NS+'drawing')
                                     for n in doc.paragraphs[b['id']][1].descendants()))
        _, omitted_report = doc.generate(omitted=[omittable['id']])
        self.assertTrue(any(c['kind'] == 'paragraph_omitted' for c in omitted_report['changes']))
        with self.assertRaises(DocumentError):
            doc.generate(omitted=['missing'])
        table_pid = next(b['id'] for b in doc.source_index if b['in_table'])
        with self.assertRaises(DocumentError):
            doc.generate(omitted=[table_pid])


class ProcurementDocumentCoverageTests(TestCase):
    def setUp(self):
        procurement.mapping.cache_clear()
        catalog.document.cache_clear()
        self.doc = catalog.document('equipment')
        self.base = procurement.initial_procurement()
        self.data = {'family': 'equipment', 'procurement': copy.deepcopy(self.base),
                     'paragraphs': {}, 'rows': {}}

    def test_quantity_text_mapping_and_presentation(self):
        self.assertEqual(procurement.quantity('1,25'), Decimal('1.25'))
        for value in (None, 1, '', '0', '-1', '1000000001', '1.1234567', 'NaN'):
            with self.subTest(value=value), self.assertRaises(DocumentError):
                procurement.quantity(value)
        self.assertEqual(len(procurement.mapping()), 2)
        self.assertTrue(procurement.managed_paragraphs())
        shown = procurement.editor_lots(self.data)
        self.assertEqual(sum(len(x['items']) for x in shown), 23)
        for value, multiline in [('', False), ('x\t', False), ('x\n', False), ('{{bad}}', True), ('[[IF:X:', True)]:
            with self.subTest(value=value), self.assertRaises(DocumentError):
                procurement._text(value, 'Test', 20, multiline=multiline)
        with self.assertRaises(DocumentError):
            procurement._text('x' * 21, 'Test', 20)
        procurement._text('a\nb', 'Test', 20, multiline=True)

    def test_validate_procurement_rejects_malformed_and_conflicting_payloads(self):
        procurement.validate_procurement(self.data, 'equipment')
        bad = copy.deepcopy(self.data)
        with self.assertRaises(DocumentError):
            procurement.validate_procurement(bad, 'reagents')
        cases = []
        b = copy.deepcopy(self.data); b['procurement'] = []; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['schema'] = 2; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'] = b['procurement']['lots'][:1]; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['number'] = 9; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'] = []; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][0].pop('unit'); cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][1]['key'] = b['procurement']['lots'][0]['items'][0]['key']; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][0]['key'] = 'new-not-a-uuid'; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][0]['designation'] = ''; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][0]['unit'] = 'x\n'; cases.append(b)
        b = copy.deepcopy(self.data); b['procurement']['lots'][0]['items'][0]['quantity'] = '0'; cases.append(b)
        for index, candidate in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(DocumentError):
                procurement.validate_procurement(candidate, 'equipment')
        b = copy.deepcopy(self.data)
        b['paragraphs'][next(iter(procurement.managed_paragraphs()))] = 'conflict'
        with self.assertRaises(DocumentError):
            procurement.validate_procurement(b, 'equipment')
        b = copy.deepcopy(self.data)
        tid = next(t['id'] for lot in procurement.mapping() for t in lot['tables'].values())
        b['rows'][tid] = []
        with self.assertRaises(DocumentError):
            procurement.validate_procurement(b, 'equipment')
        b = copy.deepcopy(self.data)
        source = b['procurement']['lots'][0]['items'][0]
        b['procurement']['lots'][0]['items'].append({**source, 'key': 'new-' + str(uuid.uuid4())})
        procurement.validate_procurement(b, 'equipment')

    def test_apply_procurement_unchanged_modified_reordered_added_and_removed(self):
        same, report = procurement.apply_procurement(self.doc.data, self.data)
        self.assertEqual(same, self.doc.data)
        self.assertEqual(report['status'], 'UNCHANGED')
        absent, report = procurement.apply_procurement(self.doc.data, {'family': 'equipment'})
        self.assertEqual(absent, self.doc.data)
        self.assertEqual(report['status'], 'NOT_REQUESTED')

        changed = copy.deepcopy(self.data)
        first = changed['procurement']['lots'][0]['items'][0]
        first['quantity'] = format(procurement.quantity(first['quantity']) + 1, 'f')
        output, report = procurement.apply_procurement(self.doc.data, changed)
        self.assertNotEqual(output, self.doc.data)
        self.assertEqual(report['status'], 'GENERATED')
        self.assertTrue(report['tables'])

        reordered = copy.deepcopy(self.data)
        reordered['procurement']['lots'][0]['items'][0:2] = reversed(reordered['procurement']['lots'][0]['items'][0:2])
        output, report = procurement.apply_procurement(self.doc.data, reordered)
        self.assertEqual(report['status'], 'GENERATED')

        added = copy.deepcopy(self.data)
        template = copy.deepcopy(added['procurement']['lots'][0]['items'][0])
        template.update(key='new-' + str(uuid.uuid4()), designation='Nouvel article de couverture',
                        specifications='Caractéristiques contrôlées', quantity='2')
        added['procurement']['lots'][0]['items'].append(template)
        output, report = procurement.apply_procurement(self.doc.data, added)
        self.assertEqual(report['status'], 'GENERATED')

        removed = copy.deepcopy(self.data)
        removed['procurement']['lots'][0]['items'].pop()
        output, report = procurement.apply_procurement(self.doc.data, removed)
        self.assertEqual(report['status'], 'GENERATED')

    def test_protected_source_fields_and_oversized_lots_are_rejected(self):
        for index, field in ((4, 'specifications'), (12, 'designation')):
            modified = copy.deepcopy(self.data)
            modified['procurement']['lots'][1]['items'][index][field] = 'Texte modifié sans autorisation'
            with self.subTest(field=field), self.assertRaisesRegex(DocumentError, 'protégé'):
                procurement.validate_procurement(modified, 'equipment')

        oversized = copy.deepcopy(self.data)
        template = oversized['procurement']['lots'][0]['items'][0]
        oversized['procurement']['lots'][0]['items'] = [
            {**template, 'key': 'new-' + str(uuid.uuid5(uuid.NAMESPACE_URL, str(index)))}
            for index in range(1000)]
        with self.assertRaisesRegex(DocumentError, '1 000 articles'):
            procurement.validate_procurement(oversized, 'equipment')

    def test_regeneration_refuses_an_altered_equipment_table(self):
        lot = procurement.mapping()[0]
        raw = self.doc.parts['word/document.xml'][0]
        row = lot['tables']['cptc']['rows'][1]
        original = raw[row.start:row.end]
        altered = original.replace(b'<w:t>', b'<w:t data-test="modified">', 1)
        self.assertNotEqual(altered, original)
        altered_xml = raw[:row.start] + altered + raw[row.end:]
        output = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.doc.data)) as source, zipfile.ZipFile(output, 'w') as target:
            for info in source.infolist():
                target.writestr(info, altered_xml if info.filename == 'word/document.xml' else source.read(info.filename))
        changed = copy.deepcopy(self.data)
        changed['procurement']['lots'][0]['items'][0]['quantity'] = '2'
        with self.assertRaisesRegex(DocumentError, 'Conflit de modification'):
            procurement.apply_procurement(output.getvalue(), changed)

    def test_procurement_private_helpers_fail_closed(self):
        lot = procurement.mapping()[0]
        raw = self.doc.parts['word/document.xml'][0]
        p = lot['items'][0]['fields']['cptc']['designation'][0]
        self.assertTrue(procurement._paragraph_fragment(raw, p, 'Texte contrôlé'))
        self.assertTrue(procurement._field_patches(raw, [p], 'Ligne 1\nLigne 2', 'seed'))
        self.assertTrue(procurement._renumber(raw, procurement.children(lot['tables']['cptc']['rows'][1], 'tc')[0], '9'))
        with self.assertRaises(DocumentError):
            procurement._field_patches(raw, [], 'x', 'seed')
        protected = copy.copy(p)
        protected.attrs = dict(protected.attrs)
        protected.attrs['_protected_field'] = 'true'
        with self.assertRaises(DocumentError):
            procurement._paragraph_fragment(raw, protected, 'x')
        parent = Node(NS+'p', {}, 0, 1)
        start = Node(NS+'bookmarkStart', {NS+'id': '1'}, 0, 0, parent=parent)
        parent.children = [start]
        with self.assertRaises(DocumentError):
            procurement._deleted_bookmark_guard(Mock(parts={}), parent)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CdcServiceCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        from erp.services.cdc import create_dossier
        self.dossier = create_dossier(self.ops, family='equipment',
            reference='18/SME/SDFM/SG/ESSBO/2026', title='CDC couverture',
            assignee=self.operator, allow_costs=True)
        self.lot = self.dossier.lots.first()
        self.item = self.lot.items.first()

    def _confirm_consultation(self):
        values = {key: self.dossier.data['consultation'][key] for key in FIELDS}
        values['confirmed'] = True
        save_consultation(self.operator, self.dossier.pk, expected=self.dossier.version,
                          values=values, reason='Variables confirmées')
        self.dossier.refresh_from_db()

    def _approve_current_reviews(self):
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        stages = [CdcReviewDecision.Stage.TECHNICAL, CdcReviewDecision.Stage.ADMIN_LEGAL]
        if self.dossier.work.allow_costs:
            stages.append(CdcReviewDecision.Stage.FINANCIAL)
        for stage in stages:
            CdcReviewDecision.objects.create(
                dossier=self.dossier, revision=revision, stage=stage,
                outcome=CdcReviewDecision.Outcome.APPROVED, actor=self.ops,
                comment='Revue obligatoire validée pour le scénario de recette')

    def test_lot_item_paragraph_and_estimate_paths(self):
        revision = save_cdc_lot(self.operator, self.lot.pk, expected=self.dossier.version,
            name='Lot couverture', name_ar='حصة تغطية', reason='Renommage contrôlé')
        self.dossier.refresh_from_db()
        self.assertEqual(revision.number, self.dossier.revision_number)
        with self.assertRaises(ValidationError):
            save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                          values={'unknown': 'x'})
        with self.assertRaises(ValidationError):
            save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                          values={}, article=self.article)
        with self.assertRaises(ValidationError):
            save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                          values={}, purchase_unit=self.unit)
        new_revision = save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
            values={'quantity': Decimal('2'), 'estimated_price': Decimal('10'),
                    'tax_rate': Decimal('19'), 'price_source': 'Devis', 'currency': 'dzd'},
            article=self.article, purchase_unit=self.unit, reason='Article structuré')
        self.dossier.refresh_from_db()
        new_item = self.lot.items.order_by('-position').first()
        self.assertEqual(new_item.currency, 'DZD')
        with self.assertRaises(ValidationError):
            save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                          pk=new_item.pk, values={'currency': 'EU'})
        with self.assertRaises(ValidationError):
            save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                          pk=new_item.pk, values={'estimated_price': Decimal('5'), 'price_source': ''})
        totals = estimate_totals(self.operator, self.dossier)
        self.assertEqual(totals['currencies']['DZD']['gross'], Decimal('23.80'))
        self.assertGreater(totals['incomplete_lines'], 0)
        with self.assertRaises(PermissionDenied):
            estimate_totals(self.second, self.dossier)

        data = catalog.initial_data('equipment')
        pid = next(b['id'] for b in catalog.profile('equipment')['paragraphs'] if not b['guard'])
        with self.assertRaises(ValidationError):
            edit_cdc_paragraph(self.operator, self.dossier.pk, expected=self.dossier.version,
                               paragraph_id=pid, value='X', reason='')
        revision = edit_cdc_paragraph(self.operator, self.dossier.pk, expected=self.dossier.version,
                                      paragraph_id=pid, value='Texte révisé', reason='Clause revue')
        self.assertEqual(revision.data['paragraphs'][pid], 'Texte révisé')

    def test_submit_requires_confirmed_clean_generated_revision(self):
        with self.assertRaises(ValidationError):
            submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version)
        self._confirm_consultation()
        with self.assertRaises(ValidationError):
            submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version)
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        CdcGeneration.objects.create(revision=revision, actor=self.ops, docx=b'x', pdf=b'y',
            docx_sha256='a'*64, pdf_sha256='b'*64, pages=1, checks={})
        work = submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version,
                              reason='Dossier prêt')
        self.assertEqual(work.status, 'SUBMITTED')

    def test_generate_cdc_success_reuse_and_failures(self):
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        with patch('erp.services.cdc.controls', return_value=[{'severity':'error'}]):
            with self.assertRaises(ValidationError):
                generate_cdc(self.operator, revision.pk)

        def converter(source):
            return _pdf(source.with_suffix('.pdf'))
        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'DOCX', {'ok': True})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'DOCX2', {'layout': True})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=converter):
            generated = generate_cdc(self.operator, revision.pk)
        self.assertEqual(generated.pages, 1)
        self.assertEqual(generate_cdc(self.operator, revision.pk).pk, generated.pk)

        revision2 = save_cdc_lot(self.operator, self.lot.pk, expected=self.dossier.version,
                                 name='Lot second', name_ar='حصة ثانية', reason='Nouvelle révision')
        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'D', {})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'D', {})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=lambda source: source):
            with self.assertRaises(ValidationError):
                generate_cdc(self.operator, revision2.pk)

        def wrong_size(source):
            return _pdf(source.with_suffix('.pdf'), width=300, height=300)
        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'D', {})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'D', {})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=wrong_size):
            with self.assertRaises(ValidationError):
                generate_cdc(self.operator, revision2.pk)

    def test_final_approval_validates_state_revision_and_review(self):
        self._confirm_consultation()
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        generation = CdcGeneration.objects.create(revision=revision, actor=self.ops, docx=b'x', pdf=b'y',
            docx_sha256='a'*64, pdf_sha256='b'*64, pages=1, checks={})
        with self.assertRaises(ValidationError):
            approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                generation_id=generation.pk, reviewed_pages=1, statement='ok',
                visual_review=True, content_review=True)
        submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version, reason='Préparé')
        self.dossier.refresh_from_db()
        self._approve_current_reviews()
        with self.assertRaises(ValidationError):
            approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                generation_id=generation.pk, reviewed_pages=0, statement='',
                visual_review=False, content_review=False)
        approval = approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            generation_id=generation.pk, reviewed_pages=1,
            statement='Toutes les pages et le contenu ont été vérifiés',
            visual_review=True, content_review=True)
        self.assertEqual(approval.reviewed_pages, 1)
        self.dossier.work.refresh_from_db()
        self.assertEqual(self.dossier.work.status, 'APPROVED')

    def test_encrypted_pdf_and_competing_generation(self):
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        def encrypted(source):
            return _pdf(source.with_suffix('.pdf'), encrypted=True)
        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'DOCX', {})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'DOCX', {})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=encrypted):
            with self.assertRaisesRegex(ValidationError, 'PDF généré est invalide'):
                generate_cdc(self.operator, revision.pk)
        self.assertFalse(revision.generations.exists())
        winner = []
        def competing_conversion(source):
            result = _pdf(source.with_suffix('.pdf'))
            winner.append(CdcGeneration.objects.create(revision=revision, actor=self.ops,
                docx=b'DOCX', pdf=result.read_bytes(), docx_sha256='a'*64, pdf_sha256='b'*64, pages=1, checks={}))
            return result
        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'DOCX', {})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'DOCX', {})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=competing_conversion):
            generated = generate_cdc(self.operator, revision.pk)
        self.assertEqual(generated.pk, winner[0].pk)
        self.assertEqual(revision.generations.count(), 1)

    def test_approval_refuses_pdf_from_previous_revision(self):
        from erp.services.common import Conflict
        from erp.models import WorkItem
        from erp.services.work import transition_work
        self._confirm_consultation()
        old_revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        old_pdf = CdcGeneration.objects.create(revision=old_revision, actor=self.ops, docx=b'old', pdf=b'old',
            docx_sha256='a'*64, pdf_sha256='b'*64, pages=1, checks={})
        latest = save_cdc_lot(self.operator, self.lot.pk, expected=self.dossier.version,
            name='Lot révisé', name_ar='حصة', reason='Actualisation')
        self.dossier.refresh_from_db()
        CdcGeneration.objects.create(revision=latest, actor=self.ops, docx=b'new', pdf=b'new',
            docx_sha256='c'*64, pdf_sha256='d'*64, pages=1, checks={})
        submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version, reason='Version actuelle')
        self.dossier.refresh_from_db()
        self.dossier.work.refresh_from_db()
        with self.assertRaisesRegex(ValidationError, 'depuis son dossier métier'):
            transition_work(self.ops, self.dossier.work_id, expected=self.dossier.work.version,
                state=WorkItem.Status.APPROVED, reason='Validation hors dossier')
        with self.assertRaises(Conflict):
            approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version, generation_id=old_pdf.pk,
                reviewed_pages=1, statement='Ancien PDF', visual_review=True, content_review=True)
        self.dossier.work.refresh_from_db()
        self.assertEqual(self.dossier.work.status, 'SUBMITTED')

    def test_remaining_cdc_permission_governance_and_restore_branches(self):
        from erp.models import CdcClauseSelection
        from erp.permissions import Capability
        from erp.services.cdc import (
            _dossier, create_clause_revision, dossier_findings, dossier_scope,
            governance_findings, restore_governance_snapshot, review_dossier,
            save_clause, save_requirement, stock_status,
        )

        with self.assertRaises(PermissionDenied):
            _dossier(self.outsider, self.dossier.pk)
        with self.assertRaises(PermissionDenied):
            stock_status(self.outsider, self.dossier)

        scoped = __import__('erp.services.cdc', fromlist=['create_dossier']).create_dossier(
            self.ops, family='equipment', reference='19/SME/SDFM/SG/ESSBO/2026',
            title='CDC revue à portée', assignee=self.operator, location=self.freezer,
            category=self.article.category)
        scoped.work.status = 'SUBMITTED'
        scoped.work.save(update_fields=['status'])
        self.grant(Capability.REVIEW_CDC_TECHNICAL, user=self.second,
            category=self.article.category, location=self.freezer)
        self.assertTrue(dossier_scope(self.second).filter(pk=scoped.pk).exists())

        self.dossier.archived_at = timezone.now()
        self.dossier.save(update_fields=['archived_at'])
        with self.assertRaises(ValidationError):
            _dossier(self.operator, self.dossier.pk, edit=True)
        self.dossier.archived_at = None
        self.dossier.save(update_fields=['archived_at'])

        with self.assertRaisesRegex(ValidationError, 'Justifiez'):
            save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
                values={'position': 1, 'kind': 'ELIMINATORY', 'statement': 'Critique',
                    'evidence': 'Certificat', 'verification_method': 'Contrôle',
                    'justification': '', 'active': True})

        clause = save_clause(self.ops, values={'code': 'COV.DRAFT', 'name': 'Clause couverture',
            'name_en': '', 'name_ar': '', 'title': 'Clause en brouillon', 'active': True},
            reason='Couverture')
        draft = create_clause_revision(self.ops, clause, text_fr='Texte brouillon',
            source_reference='Source', activate=False)
        CdcClauseSelection.objects.create(dossier=self.dossier, revision=draft,
            position=1, mandatory=False, active=True)
        self.assertIn('clause-not-active', {row['code'] for row in governance_findings(self.dossier)})
        self.assertIn('clause-not-active', {row.get('code') for row in dossier_findings(self.dossier)})

        with self.assertRaisesRegex(ValidationError, 'inconnue'):
            review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                stage='UNKNOWN', outcome='APPROVED', comment='Test')
        self.dossier.work.status = 'SUBMITTED'
        self.dossier.work.save(update_fields=['status'])
        with self.assertRaises(PermissionDenied):
            review_dossier(self.operator, self.dossier.pk, expected=self.dossier.version,
                stage='TECHNICAL', outcome='APPROVED', comment='Sans droit')
        self.dossier.work.status = 'ASSIGNED'
        self.dossier.work.save(update_fields=['status'])

        active = create_clause_revision(self.ops, clause, text_fr='Texte actif',
            source_reference='Source active', activate=True)
        restore_governance_snapshot(self.ops, self.dossier, {
            'requirements': [{'item_key': 'missing-item'}],
            'criteria': [],
            'clauses': [
                {'code': clause.code, 'revision': active.number, 'position': 2, 'mandatory': True},
                {'code': 'MISSING.CLAUSE', 'revision': 99, 'position': 3, 'mandatory': False},
            ],
        })
        self.assertTrue(self.dossier.clause_selections.filter(revision=active, active=True).exists())

        self.party.active = False
        self.party.save(update_fields=['active'])
        try:
            with self.assertRaisesRegex(ValidationError, 'fournisseur actif'):
                save_cdc_item(self.operator, self.lot.pk, expected=self.dossier.version,
                    pk=self.item.pk, values={'estimate_supplier': self.party}, reason='Fournisseur inactif')
        finally:
            self.party.active = True
            self.party.save(update_fields=['active'])

    def test_governance_annex_report_and_missing_review_gate(self):
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)

        def converter(source):
            return _pdf(source.with_suffix('.pdf'))

        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.governance_snapshot_findings', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'DOCX', {
                 'changed_parts': [], 'preserved_parts': {'word/document.xml': 'seed'}, 'changes': []})), \
             patch('erp.services.cdc.append_governance_annex', return_value=(b'ANNEX', {
                 'status': 'GENERATED', 'requirements': 1, 'criteria': 1, 'clauses': 1})), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'NORMALIZED', {'layout': True})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=converter):
            generation = generate_cdc(self.operator, revision.pk)
        report = generation.checks['source_report']
        self.assertIn('word/document.xml', report['changed_parts'])
        self.assertNotIn('word/document.xml', report['preserved_parts'])
        self.assertEqual(report['changes'][-1]['kind'], 'cdc_governance_annex')

        self._confirm_consultation()
        current = self.dossier.revisions.get(number=self.dossier.revision_number)
        current_generation = CdcGeneration.objects.create(revision=current, actor=self.ops,
            docx=b'x', pdf=b'y', docx_sha256='a'*64, pdf_sha256='b'*64, pages=1, checks={})
        submit_dossier(self.operator, self.dossier.pk, expected=self.dossier.version, reason='Soumission')
        self.dossier.refresh_from_db()
        with self.assertRaisesRegex(ValidationError, 'revues obligatoires'):
            approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                generation_id=current_generation.pk, reviewed_pages=1, statement='Contrôle',
                visual_review=True, content_review=True)

    def test_non_cdc_work_document_read_requires_access(self):
        from erp.services.safety import require_target
        from erp.services.work import create_work

        work = create_work(self.ops, kind='CONTROL', title='Contrôle documentaire',
            assignee=self.operator)
        with self.assertRaises(PermissionDenied):
            require_target(self.outsider, 'work', work.pk)
