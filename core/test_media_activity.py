from datetime import timedelta
import io
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.db import connection
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import User
from core.media_paths import canonical_media_path, validate_storage_path
from core.models import Request
from dashboard.middleware import UpdateLastSeenMiddleware
from dashboard.views.report import _may_access_media, serve_media
from plagenor.test_support import close_response


class MediaCanonicalizationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('media-owner', role='CLIENT')
        self.other = User.objects.create_user('media-other', role='CLIENT')
        Request.objects.create(requester=self.user, channel='GENOCLAB', order_file='orders/private.pdf')

    def request(self, user=None):
        req = self.factory.get('/media/test/')
        req.user = user or AnonymousUser()
        return req

    def test_path_matrix_rejected_before_authorization_or_storage(self):
        invalid = ['', '../orders/private.pdf', 'avatars/../orders/private.pdf', 'avatars/./photo.png',
                   'avatars//photo.png', 'avatars\\..\\orders\\private.pdf', 'avatars/%2e%2e/orders/private.pdf',
                   'avatars/%252e%252e/orders/private.pdf', '/avatars/photo.png', 'C:/avatars/photo.png',
                   'avatars/photo.png:stream', 'avatars/photo.png.', 'avatars/photo.png ', 'avatars/CON.png',
                   'avatars/COM1.png', 'avatars/photo\x00.png', 'avatars/∕orders/private.pdf',
                   'avatars/é.png', 'avatars/a?b.png', 'avatars/a#b.png', None, 'a' * 1025]
        for path in invalid:
            with self.subTest(path=path):
                with self.assertRaises(ValidationError): canonical_media_path(path)
                self.assertFalse(_may_access_media(self.request(self.user), path))
                with patch('dashboard.views.report.default_storage') as storage:
                    with self.assertRaises(Http404): serve_media(self.request(self.user), path)
                    storage.exists.assert_not_called(); storage.open.assert_not_called()
        self.assertEqual(canonical_media_path('avatars/échantillon.png'), 'avatars/échantillon.png')
        self.assertFalse(_may_access_media(self.request(), 'avatars-private/private.pdf'))

    def test_local_public_private_owner_and_missing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            storage = FileSystemStorage(location=folder)
            for key in ('avatars/photo.png', 'orders/private.pdf'):
                path = Path(folder)/key; path.parent.mkdir(exist_ok=True); path.write_bytes(b'Synthetic file')
            with patch('dashboard.views.report.default_storage', storage):
                response = serve_media(self.request(), 'avatars/photo.png')
                self.assertEqual(response.status_code, 200); close_response(response)
                for user in (None, self.other):
                    with self.assertRaises(Http404): serve_media(self.request(user), 'orders/private.pdf')
                response = serve_media(self.request(self.user), 'orders/private.pdf')
                self.assertEqual(b''.join(response.streaming_content), b'Synthetic file'); close_response(response)
                with self.assertRaises(Http404): serve_media(self.request(), 'avatars/missing.png')
                with self.assertRaises(Http404): serve_media(self.request(self.user), 'reports/direct.pdf')
                with self.assertRaises(Http404): serve_media(self.request(self.user), 'ibtikar_attachments/direct.pdf')
            self.assertEqual(validate_storage_path(storage, 'avatars/photo.png'), 'avatars/photo.png')
            with patch.object(Path, 'resolve', side_effect=[Path(folder), Path(folder).parent/'outside']):
                with self.assertRaises(ValidationError): validate_storage_path(storage, 'avatars/photo.png')
            with patch.object(Path, 'resolve', side_effect=[Path(folder), Path(folder)/'orders/private.pdf']):
                with self.assertRaises(ValidationError): validate_storage_path(storage, 'avatars/photo.png')

    def test_object_storage_uses_authorized_canonical_key(self):
        storage = Mock()
        storage.exists.return_value = True
        storage.open.return_value = io.BytesIO(b'Object data')
        with patch('dashboard.views.report.default_storage', storage):
            response = serve_media(self.request(self.user), 'orders/private.pdf')
            self.assertEqual(b''.join(response.streaming_content), b'Object data'); close_response(response)
        storage.exists.assert_called_once_with('orders/private.pdf')
        storage.open.assert_called_once_with('orders/private.pdf', 'rb')
        storage.path.assert_not_called()


class LastSeenThrottlingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('active-user', role='CLIENT')
        self.factory = RequestFactory()
        self.middleware = UpdateLastSeenMiddleware(lambda request: HttpResponse('ok'))

    def visit(self, user):
        req = self.factory.get('/'); req.user = user
        with CaptureQueriesContext(connection) as queries:
            self.middleware(req)
        return [item['sql'] for item in queries if item['sql'].lstrip().upper().startswith('UPDATE')]

    def test_five_minute_window_and_anonymous_requests(self):
        now = timezone.now()
        with patch('dashboard.middleware.timezone.now', return_value=now):
            self.assertEqual(len(self.visit(self.user)), 1)
            self.assertEqual(len(self.visit(self.user)), 0)
            self.user.refresh_from_db()
            self.assertEqual(len(self.visit(self.user)), 0)
            self.assertEqual(len(self.visit(AnonymousUser())), 0)
        with patch('dashboard.middleware.timezone.now', return_value=now + timedelta(minutes=5)):
            self.assertEqual(len(self.visit(self.user)), 1)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_seen, now + timedelta(minutes=5))

    def test_stale_instances_do_not_overwrite_newer_activity(self):
        stale = User.objects.get(pk=self.user.pk)
        now = timezone.now()
        with patch('dashboard.middleware.timezone.now', return_value=now): self.visit(self.user)
        with patch('dashboard.middleware.timezone.now', return_value=now + timedelta(seconds=10)): self.visit(stale)
        stale.refresh_from_db()
        self.assertEqual(stale.last_seen, now)
