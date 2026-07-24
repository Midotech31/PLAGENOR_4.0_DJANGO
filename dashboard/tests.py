"""Tests for the report-access gate and storage-backed media serving.

The IBTIKAR citation clause must block report downloads until acknowledged;
GENOCLAB clients and internal staff are exempt. These guard
``protected_report_media`` / ``serve_media`` (dashboard/views/report.py).
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase

from core.models import Request


def _save_report(name='reports/gatecheck.pdf', data=b'PDF-BYTES'):
    if default_storage.exists(name):
        default_storage.delete(name)
    return default_storage.save(name, ContentFile(data))


class ReportGateTests(TestCase):
    def tearDown(self):
        for n in ('reports/gatecheck.pdf', 'misc/note.txt'):
            if default_storage.exists(n):
                default_storage.delete(n)

    def test_ibtikar_unacknowledged_is_blocked(self):
        rel = _save_report()
        Request.objects.create(channel='IBTIKAR', report_file=rel,
                               citation_acknowledged=False)
        resp = self.client.get('/media/' + rel)
        self.assertIn(resp.status_code, (302, 403))  # redirect to clause / forbidden

    def test_ibtikar_acknowledged_is_served(self):
        rel = _save_report()
        Request.objects.create(channel='IBTIKAR', report_file=rel,
                               citation_acknowledged=True)
        resp = self.client.get('/media/' + rel)
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content)
        self.assertEqual(body, b'PDF-BYTES')

    def test_genoclab_report_is_served_without_clause(self):
        rel = _save_report()
        Request.objects.create(channel='GENOCLAB', report_file=rel,
                               citation_acknowledged=False)
        resp = self.client.get('/media/' + rel)
        self.assertEqual(resp.status_code, 200)

    def test_serve_media_404_on_missing(self):
        resp = self.client.get('/media/avatars/does-not-exist.png')
        self.assertEqual(resp.status_code, 404)


class MediaAuthorizationTests(TestCase):
    """serve_media prefix policy: public avatars, owner-gated orders/payments,
    staff-only everything else. Denials are 404 (no existence leak)."""

    _FILES = ('avatars/pub.png', 'orders/bc-001.pdf', 'documents/DEVIS_X.docx')

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.owner = User.objects.create(username='own-client', role='CLIENT')
        cls.other = User.objects.create(username='other-client', role='CLIENT')
        cls.staff = User.objects.create(username='fin-1', role='FINANCE')

    def setUp(self):
        for n in self._FILES:
            if default_storage.exists(n):
                default_storage.delete(n)
            default_storage.save(n, ContentFile(b'x'))
        self.req = Request.objects.create(
            channel='GENOCLAB', requester=self.owner,
            order_file='orders/bc-001.pdf')

    def tearDown(self):
        for n in self._FILES:
            if default_storage.exists(n):
                default_storage.delete(n)

    def test_avatar_is_public(self):
        self.assertEqual(self.client.get('/media/avatars/pub.png').status_code, 200)

    def test_order_denied_to_anonymous(self):
        self.assertEqual(self.client.get('/media/orders/bc-001.pdf').status_code, 404)

    def test_order_denied_to_other_client(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/media/orders/bc-001.pdf').status_code, 404)

    def test_order_served_to_owner(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/media/orders/bc-001.pdf').status_code, 200)

    def test_order_served_to_staff(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/media/orders/bc-001.pdf').status_code, 200)

    def test_generated_document_denied_to_anonymous_and_clients(self):
        self.assertEqual(self.client.get('/media/documents/DEVIS_X.docx').status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get('/media/documents/DEVIS_X.docx').status_code, 404)

    def test_generated_document_served_to_staff(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/media/documents/DEVIS_X.docx').status_code, 200)
