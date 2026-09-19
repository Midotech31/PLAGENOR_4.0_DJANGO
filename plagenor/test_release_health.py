import json
from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, TestCase

from plagenor.health import readyz


class ReleaseHealthTests(TestCase):
    def test_readiness_reports_only_valid_hosted_commit(self):
        request = RequestFactory().get('/readyz')
        for value, expected in [('', None), ('short-sha', None), ('x' * 40, None), ('a' * 40, 'a' * 40)]:
            with self.subTest(value=value), patch.dict('os.environ', {'RENDER_GIT_COMMIT': value}):
                response = readyz(request)
                payload = json.loads(response.content)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(payload['database'], 'ok')
                self.assertEqual(payload.get('commit'), expected)
                self.assertIn('no-store', response['Cache-Control'])

    def test_unavailable_database_never_reports_ready_or_exposes_driver_details(self):
        with patch('plagenor.health.connection.cursor', side_effect=DatabaseError('private connection details')):
            with self.assertLogs('plagenor', level='ERROR'):
                response = readyz(RequestFactory().get('/readyz'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(json.loads(response.content), {'status': 'error', 'database': 'unavailable'})
        self.assertNotIn(b'private connection', response.content)
