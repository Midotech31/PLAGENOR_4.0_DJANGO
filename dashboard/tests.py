"""Tests for the report-access gate and storage-backed media serving.

The IBTIKAR citation clause must block report downloads until acknowledged;
GENOCLAB clients and internal staff are exempt. These guard
``protected_report_media`` / ``serve_media`` (dashboard/views/report.py).
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from core.models import Request

# Plain (non-manifest) storages so template {% static %} works without a
# collectstatic run in tests.
_TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


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


@override_settings(STORAGES=_TEST_STORAGES,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RateLimitTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_password_reset_throttles_after_limit(self):
        # ForgotPasswordView: 5 POSTs / hour per IP → the 6th is 429.
        codes = []
        for _ in range(7):
            r = self.client.post('/accounts/password-reset/', {'email': 'x@example.com'})
            codes.append(r.status_code)
        self.assertNotIn(429, codes[:5])
        self.assertEqual(codes[-1], 429)

    def test_get_requests_not_throttled(self):
        for _ in range(10):
            r = self.client.get('/accounts/password-reset/')
            self.assertEqual(r.status_code, 200)


@override_settings(STORAGES=_TEST_STORAGES)
class RoleDashboardAccessTests(TestCase):
    """Router + per-role landing pages: right role renders (200), wrong role
    is forbidden (403), anonymous is redirected to login."""

    LANDINGS = {
        'SUPER_ADMIN': '/dashboard/home/',
        'PLATFORM_ADMIN': '/dashboard/ops/',
        'MEMBER': '/dashboard/analyst/',
        'FINANCE': '/dashboard/finance/',
        'REQUESTER': '/dashboard/requester/',
        'CLIENT': '/dashboard/client/',
    }

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.User = User
        cls.users = {
            role: User.objects.create_user(
                username=f'role-{role}', password='x', role=role,
                is_superuser=(role == 'SUPER_ADMIN'),
                is_staff=(role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')))
            for role in cls.LANDINGS
        }

    def test_router_redirects_each_role_to_its_landing(self):
        targets = {
            'SUPER_ADMIN': '/dashboard/home/', 'PLATFORM_ADMIN': '/dashboard/ops/',
            'MEMBER': '/dashboard/analyst/', 'FINANCE': '/dashboard/finance/',
            'REQUESTER': '/dashboard/requester/', 'CLIENT': '/dashboard/client/',
        }
        for role, target in targets.items():
            self.client.force_login(self.users[role])
            resp = self.client.get('/dashboard/')
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.url.rstrip('/').endswith(target.rstrip('/')),
                            f"{role} → {resp.url}")

    def test_each_landing_renders_for_its_role(self):
        for role, url in self.LANDINGS.items():
            self.client.force_login(self.users[role])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"{role} {url} → {resp.status_code}")

    def test_wrong_role_is_forbidden(self):
        # A CLIENT must not reach any staff/other-role landing.
        self.client.force_login(self.users['CLIENT'])
        for role, url in self.LANDINGS.items():
            if role == 'CLIENT':
                continue
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 403, f"CLIENT reached {url}")

    def test_anonymous_redirected_to_login(self):
        for url in self.LANDINGS.values():
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn('/accounts/login', resp.url)


@override_settings(STORAGES=_TEST_STORAGES)
class PrivacyAndDataExportTests(TestCase):
    def test_privacy_page_is_public(self):
        resp = self.client.get('/confidentialite/')
        self.assertEqual(resp.status_code, 200)

    def test_data_export_requires_login(self):
        resp = self.client.get('/mes-donnees/export/')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/accounts/login', resp.url)

    def test_data_export_returns_own_data_only(self):
        from accounts.models import User
        me = User.objects.create_user(username='exp-me', password='x',
                                      role='CLIENT', email='me@example.com')
        other = User.objects.create_user(username='exp-other', password='x',
                                         role='CLIENT')
        Request.objects.create(channel='GENOCLAB', requester=me, title='Mine',
                               display_id='EXP-MINE-1')
        Request.objects.create(channel='GENOCLAB', requester=other, title='Theirs',
                               display_id='EXP-THEIRS-1')
        self.client.force_login(me)
        resp = self.client.get('/mes-donnees/export/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp['Content-Disposition'])
        data = resp.json()
        self.assertEqual(data['account']['email'], 'me@example.com')
        titles = [r['title'] for r in data['requests']]
        self.assertIn('Mine', titles)
        self.assertNotIn('Theirs', titles)


class HealthEndpointTests(TestCase):
    def test_healthz_ok(self):
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    def test_readyz_ok_with_db(self):
        resp = self.client.get('/readyz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['database'], 'ok')


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
