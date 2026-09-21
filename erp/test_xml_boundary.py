from django.test import SimpleTestCase
from erp.cdc.docengine import DocumentError
from erp.cdc.lot_workbook import xml


class WorkbookXmlBoundaryTests(SimpleTestCase):
    def test_entity_declarations_are_rejected_even_with_utf16_encoding(self):
        payload='<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY e "forbidden">]><x>&e;</x>'
        with self.assertRaises(DocumentError):
            xml(payload.encode('utf-16'))

    def test_plain_xml_is_preserved_and_invalid_xml_is_rejected(self):
        self.assertEqual(xml(b'<x><y>value</y></x>').find('y').text, 'value')
        with self.assertRaises(DocumentError):
            xml(b'<x>')
