"""Strict CDC data contracts prevent malformed or ambiguous purchase requirements."""
import copy
import uuid

from django.test import SimpleTestCase

from erp.cdc import lot_catalog as catalog
from erp.cdc.docengine import DocumentError


class LotCatalogContracts(SimpleTestCase):
    def sample(self):
        return {'schema': 1, 'lots': [{'id': str(uuid.uuid4()), 'number': 1, 'name': 'Laboratoire',
            'name_ar': '', 'source_slot': 1, 'items': [{'key': 'source-1-1', 'position': 1,
                'designation': 'Équipement', 'specifications': 'Précision documentée', 'unit': 'Unité',
                'packaging': '', 'quantity': '1', 'details': ''}]}]}

    def test_rejects_unknown_schema_and_invalid_lot_structure(self):
        values = [None, {}, {'schema': True, 'lots': []}, {'schema': 2, 'lots': []},
                  {'schema': 1, 'lots': []}, {'schema': 1, 'lots': {}},
                  {'schema': 1, 'lots': [{}]}, {'schema': 1, 'lots': [None]}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(DocumentError):
                catalog.validate_catalog(value)
        for field, value in [('id', 'bad'), ('number', True), ('number', 2),
                             ('source_slot', -1), ('source_slot', True), ('source_slot', 51),
                             ('items', {}), ('items', [{}] * 1001)]:
            data = self.sample()
            data['lots'][0][field] = value
            with self.subTest(field=field, value=str(value)[:50]), self.assertRaises(DocumentError):
                catalog.validate_catalog(data)

    def test_rejects_duplicate_lot_id_or_normalized_name(self):
        for duplicate_id in [True, False]:
            data = self.sample()
            second = copy.deepcopy(data['lots'][0])
            second.update(number=2, items=[])
            if duplicate_id:
                second['name'] = 'Autre lot'
            else:
                second.update(id=str(uuid.uuid4()), name='  LABORATOIRE  ')
            data['lots'].append(second)
            with self.subTest(duplicate_id=duplicate_id), self.assertRaises(DocumentError):
                catalog.validate_catalog(data)

    def test_rejects_item_shape_keys_numbering_and_template_markers(self):
        for field, value in [('key', 123), ('key', 'unknown'), ('key', 'new-' + '-' * 36),
                             ('position', 2), ('position', True), ('designation', None),
                             ('designation', ''), ('unit', 'x' * 101), ('unit', 'a\nb'),
                             ('details', 'a\tb'), ('details', 'a\rb'),
                             ('designation', '{{injection}}'), ('details', '[[IF:condition]]')]:
            data = self.sample()
            data['lots'][0]['items'][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DocumentError):
                catalog.validate_catalog(data)
        data = self.sample()
        data['lots'][0]['items'][0]['price'] = 10
        with self.assertRaises(DocumentError):
            catalog.validate_catalog(data)
        data = self.sample()
        data['lots'][0]['items'].append(dict(data['lots'][0]['items'][0], position=2))
        with self.assertRaises(DocumentError):
            catalog.validate_catalog(data)

    def test_total_item_limit_spans_multiple_lots(self):
        data = self.sample()
        item = data['lots'][0]['items'][0]
        second = dict(data['lots'][0], id=str(uuid.uuid4()), number=2, name='Second lot')
        data['lots'].append(second)
        for number, lot in enumerate(data['lots'], 1):
            lot['items'] = [dict(item, key=f'source-{number}-{n}', position=n) for n in range(1, 502)]
        with self.assertRaisesMessage(DocumentError, '1000'):
            catalog.validate_catalog(data)

    def test_catalog_replacement_and_read_are_independent_copies(self):
        original = {'family': 'equipment', 'procurement': {'legacy': True}, 'title': 'Document'}
        value = self.sample()
        replaced = catalog.replace_catalog(original, value)
        self.assertNotIn('procurement', replaced)
        self.assertIn('procurement', original)
        loaded = catalog.get_catalog(replaced)
        loaded['lots'][0]['name'] = 'Changed'
        value['lots'][0]['name'] = 'Also changed'
        self.assertEqual(replaced['lot_catalog']['lots'][0]['name'], 'Laboratoire')
        self.assertEqual(catalog.validate_catalog(replaced['lot_catalog']), replaced['lot_catalog'])
        self.assertFalse(catalog.valid_uuid('invalid'))
        self.assertFalse(catalog.valid_uuid(None))

    def test_diff_reports_every_item_of_removed_lots(self):
        before = self.sample()
        after = self.sample()
        after['lots'][0].update(name='Remplacement', source_slot=0)
        after['lots'][0]['items'][0]['key'] = 'new-' + str(uuid.uuid4())
        difference = catalog.diff_catalog(before, after)
        self.assertEqual(difference['totals'], {'added': 1, 'removed': 1, 'updated': 0, 'unchanged': 0})
        self.assertEqual((difference['lots'], difference['items']), (1, 1))
        removed = next(row for row in difference['rows'] if row['action'] == 'removed')
        self.assertEqual(removed['lot'], 'Laboratoire')
        self.assertEqual(removed['before'], before['lots'][0]['items'][0])
        self.assertIsNone(removed['after'])
        self.assertEqual(catalog.diff_catalog(before, before)['totals']['unchanged'], 1)
