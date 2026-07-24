"""Tests for the DOCX generators.

They produce real .docx files (python-docx, no LibreOffice needed). We
generate a document from known data, reopen it, and assert the key values
made it into the file. Files land under MEDIA_ROOT/documents/ and are cleaned
up afterwards.
"""
import os
from decimal import Decimal

from django.test import TestCase
from docx import Document as _OpenDocx


def _docx_text(path):
    """Flatten all paragraph + table text of a .docx into one string."""
    doc = _OpenDocx(path)
    parts = [p.text for p in doc.paragraphs]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                parts.append(cell.text)
    return '\n'.join(parts)


class InvoiceGeneratorTests(TestCase):
    def setUp(self):
        from accounts.models import User
        from core.models import Invoice
        self.client_user = User.objects.create(
            username='gen-client', role='CLIENT',
            first_name='Ada', last_name='Lovelace')
        self.invoice = Invoice.objects.create(
            invoice_number='GENOCLAB-INV-TEST-001',
            client=self.client_user,
            line_items=[{'description': 'Séquençage', 'quantity': 2,
                         'unit_price': 5000, 'total': 10000}],
            subtotal_ht=Decimal('10000'), vat_rate=Decimal('0.19'),
            vat_amount=Decimal('1900'), total_ttc=Decimal('11900'))
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            if p and os.path.exists(p):
                os.remove(p)

    def test_invoice_docx_is_valid_and_contains_key_values(self):
        from documents.generators import generate_invoice_document
        path = generate_invoice_document(self.invoice)
        self._paths.append(path)
        self.assertTrue(path.endswith('.docx'))
        self.assertTrue(os.path.exists(path))
        text = _docx_text(path)  # opening also proves it's a valid docx
        self.assertIn('GENOCLAB-INV-TEST-001', text)
        self.assertIn('Séquençage', text)


class IbtikarFormGeneratorTests(TestCase):
    def setUp(self):
        from accounts.models import User
        from core.models import Request, Service
        self.service = Service.objects.create(
            code='GEN_IBK', name='Analyse génomique',
            channel_availability='IBTIKAR')
        self.requester = User.objects.create(
            username='gen-req', role='REQUESTER',
            first_name='Alan', last_name='Turing')
        self.req = Request.objects.create(
            channel='IBTIKAR', status='ASSIGNED', service=self.service,
            requester=self.requester, title='Demande test')
        self._paths = []

    def tearDown(self):
        for p in self._paths:
            if p and os.path.exists(p):
                os.remove(p)

    def test_ibtikar_form_is_valid_docx(self):
        from documents.generators import generate_ibtikar_form
        path = generate_ibtikar_form(self.req)
        self._paths.append(path)
        self.assertTrue(os.path.exists(path))
        text = _docx_text(path)  # must open without raising
        self.assertIn(self.req.display_id, text)

    def test_build_field_map_returns_dict(self):
        from documents.generators import build_field_map
        fm = build_field_map(self.req)
        self.assertIsInstance(fm, dict)
        self.assertTrue(len(fm) > 0)
