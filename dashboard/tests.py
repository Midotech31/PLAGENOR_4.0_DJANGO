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

    def test_serve_media_streams_non_report_file(self):
        name = _save_report('misc/note.txt', b'hello')
        resp = self.client.get('/media/' + name)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), b'hello')

    def test_serve_media_404_on_missing(self):
        resp = self.client.get('/media/misc/does-not-exist.txt')
        self.assertEqual(resp.status_code, 404)
