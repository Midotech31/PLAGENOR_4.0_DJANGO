import io
from unittest.mock import patch

from django.db import connection
from django.http import FileResponse
from django.test import TestCase

from plagenor.test_support import close_response


class ResponseResourceTests(TestCase):
    def test_file_cleanup_preserves_the_test_transaction(self):
        response = FileResponse(io.BytesIO(b'regression fixture'))
        self.assertEqual(b''.join(response.streaming_content), b'regression fixture')
        close_response(response)
        self.assertTrue(response.closed)
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            self.assertEqual(cursor.fetchone(), (1,))

    def test_completed_cleanup_is_not_repeated(self):
        response = FileResponse(io.BytesIO(b'regression fixture'))
        close_response(response)
        with patch.object(response, 'close') as close:
            close_response(response)
        close.assert_not_called()
