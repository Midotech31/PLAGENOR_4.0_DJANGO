"""Tests for the report-access gate and storage-backed media serving.

The IBTIKAR citation clause must block report downloads until acknowledged;
GENOCLAB clients and internal staff are exempt. These guard
``protected_report_media`` / ``serve_media`` (dashboard/views/report.py).
"""
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.template import Context, Template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from core.models import Request, RequestHistory

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


@override_settings(STORAGES=_TEST_STORAGES)
class ReportGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.owner = User.objects.create_user(
            username='report-owner', password='x', role='CLIENT')
        cls.staff = User.objects.create_user(
            username='report-staff', password='x', role='PLATFORM_ADMIN')

    def tearDown(self):
        for n in ('reports/gatecheck.pdf', 'misc/note.txt'):
            if default_storage.exists(n):
                default_storage.delete(n)

    def test_ibtikar_unacknowledged_is_blocked(self):
        rel = _save_report()
        Request.objects.create(channel='IBTIKAR', report_file=rel,
                               requester=self.owner,
                               citation_acknowledged=False)
        self.client.force_login(self.owner)
        resp = self.client.get('/media/' + rel)
        self.assertIn(resp.status_code, (302, 403))  # redirect to clause / forbidden

    def test_ibtikar_acknowledged_is_served(self):
        rel = _save_report()
        Request.objects.create(channel='IBTIKAR', report_file=rel,
                               requester=self.owner,
                               citation_acknowledged=True)
        self.client.force_login(self.owner)
        resp = self.client.get('/media/' + rel)
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content)
        self.assertEqual(body, b'PDF-BYTES')

    def test_raw_genoclab_report_is_not_public(self):
        rel = _save_report()
        Request.objects.create(channel='GENOCLAB', report_file=rel,
                               requester=self.owner,
                               citation_acknowledged=False)
        resp = self.client.get('/media/' + rel)
        self.assertEqual(resp.status_code, 404)

    def test_raw_genoclab_report_is_served_to_owner(self):
        rel = _save_report()
        Request.objects.create(channel='GENOCLAB', report_file=rel,
                               requester=self.owner)
        self.client.force_login(self.owner)
        resp = self.client.get('/media/' + rel)
        self.assertEqual(resp.status_code, 200)

    def test_report_token_download_remains_available_to_guest(self):
        rel = _save_report()
        token = uuid.uuid4()
        Request.objects.create(
            channel='GENOCLAB', report_file=rel, report_token=token,
            requester=self.owner, display_id='GCL-REPORT-TOKEN',
        )
        resp = self.client.get(f'/report/{token}/download/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), b'PDF-BYTES')

    def test_serve_media_404_on_missing(self):
        resp = self.client.get('/media/avatars/does-not-exist.png')
        self.assertEqual(resp.status_code, 404)

    def test_delivery_beacon_requires_csrf(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel='GENOCLAB', report_token=token, requester=self.owner,
            display_id='CSRF-REPORT',
        )
        strict = Client(enforce_csrf_checks=True)
        page = strict.get(f'/report/{token}/')
        self.assertEqual(page.status_code, 200)
        denied = strict.post(f'/report/{token}/delivered/')
        self.assertEqual(denied.status_code, 403)
        csrf = strict.cookies['csrftoken'].value
        accepted = strict.post(
            f'/report/{token}/delivered/', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(accepted.status_code, 204)
        req.refresh_from_db()
        self.assertTrue(req.report_delivered)

    def test_rating_comment_is_bounded(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel='GENOCLAB', report_token=token, requester=self.owner,
            display_id='RATING-BOUND',
        )
        response = self.client.post(
            f'/report/{token}/rate/', {'rating': '4', 'comment': 'x' * 5000})
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.service_rating, 4)
        self.assertEqual(len(req.rating_comment), 2000)


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

    @override_settings(TRUST_PROXY_HEADERS=True)
    def test_proxy_ip_uses_rightmost_valid_forwarded_address(self):
        from core.ratelimit import _client_ip
        request = RequestFactory().post(
            '/', HTTP_X_FORWARDED_FOR='203.0.113.50, 198.51.100.7',
            REMOTE_ADDR='10.0.0.5')
        self.assertEqual(_client_ip(request), '198.51.100.7')

    @override_settings(TRUST_PROXY_HEADERS=False)
    def test_untrusted_proxy_header_is_ignored(self):
        from core.ratelimit import _client_ip
        request = RequestFactory().post(
            '/', HTTP_X_FORWARDED_FOR='203.0.113.50',
            REMOTE_ADDR='127.0.0.1')
        self.assertEqual(_client_ip(request), '127.0.0.1')


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


@override_settings(STORAGES=_TEST_STORAGES)
class AnnouncementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.admin = User.objects.create_user(
            username='ann-admin', password='x', role='SUPER_ADMIN',
            is_superuser=True, is_staff=True)
        cls.requester = User.objects.create_user(
            username='ann-req', password='x', role='REQUESTER')
        cls.client_user = User.objects.create_user(
            username='ann-cli', password='x', role='CLIENT')

    def test_visible_to_audience_targeting(self):
        from core.models import Announcement
        a = Announcement.objects.create(title='T', message='M', audience='REQUESTERS')
        self.assertTrue(a.visible_to(self.requester))
        self.assertFalse(a.visible_to(self.client_user))
        a.audience = 'ALL'
        self.assertTrue(a.visible_to(self.client_user))
        a.active = False
        self.assertFalse(a.visible_to(self.requester))

    def test_admin_can_create_and_it_shows_on_dashboard(self):
        self.client.force_login(self.admin)
        resp = self.client.post('/dashboard/home/announcement/create/', {
            'title': 'Maintenance', 'message': 'Samedi 22h', 'level': 'warning',
            'audience': 'ALL'})
        self.assertEqual(resp.status_code, 302)
        from core.models import Announcement
        self.assertTrue(Announcement.objects.filter(title='Maintenance').exists())
        # The banner appears on a dashboard for a targeted user.
        self.client.force_login(self.requester)
        page = self.client.get('/dashboard/requester/')
        self.assertContains(page, 'Maintenance')

    def test_non_admin_cannot_create(self):
        self.client.force_login(self.requester)
        resp = self.client.post('/dashboard/home/announcement/create/', {
            'title': 'X', 'message': 'Y'})
        self.assertEqual(resp.status_code, 403)


@override_settings(STORAGES=_TEST_STORAGES)
class AccountResetDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.admin = User.objects.create_user(
            username='reset-admin', password='x', role='SUPER_ADMIN',
            is_superuser=True, is_staff=True,
        )
        cls.target = User.objects.create_user(
            username='reset-target', password='old-password',
            email='target@example.test', role='REQUESTER',
        )

    def _post(self):
        from django.urls import reverse
        self.client.force_login(self.admin)
        return self.client.post(
            reverse('dashboard:superadmin_reset_account', args=[self.target.pk])
        )

    def test_reset_rolls_back_when_email_transport_fails(self):
        from django.contrib.messages import get_messages
        from unittest.mock import patch

        with patch('django.core.mail.send_mail', side_effect=OSError('SMTP unavailable')):
            response = self._post()

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertFalse(self.target.must_change_password)
        self.assertTrue(self.target.check_password('old-password'))
        queued = [(message.tags, str(message)) for message in get_messages(response.wsgi_request)]
        self.assertFalse(any('success' in tags for tags, _ in queued))
        self.assertTrue(any('error' in tags and 'n’a pas pu être livré' in text
                            for tags, text in queued))

    def test_reset_does_not_show_delivery_warning_when_email_is_sent(self):
        from django.contrib.messages import get_messages
        from unittest.mock import patch

        with patch('django.core.mail.send_mail', return_value=1):
            response = self._post()

        queued = [(message.tags, str(message)) for message in get_messages(response.wsgi_request)]
        self.target.refresh_from_db()
        self.assertTrue(self.target.must_change_password)
        self.assertFalse(self.target.check_password('old-password'))
        self.assertTrue(any('success' in tags for tags, _ in queued))
        self.assertFalse(any('error' in tags for tags, _ in queued))

    def test_reset_without_verified_email_is_rejected(self):
        from django.contrib.messages import get_messages
        from unittest.mock import patch

        self.target.email = ''
        self.target.save(update_fields=['email'])
        with patch('django.core.mail.send_mail') as send_mail:
            response = self._post()

        send_mail.assert_not_called()
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password('old-password'))
        queued = [(message.tags, str(message)) for message in get_messages(response.wsgi_request)]
        self.assertTrue(any('error' in tags and 'email vérifiée' in text
                            for tags, text in queued))


class HealthEndpointTests(TestCase):
    def test_healthz_ok(self):
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')

    def test_readyz_ok_with_db(self):
        resp = self.client.get('/readyz')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['database'], 'ok')


class TemplateEscapingTests(SimpleTestCase):
    def test_json_filter_preserves_html_escaping(self):
        payload = {"label": "'></div><script>alert(1)</script>"}
        rendered = Template(
            "{% load dashboard_extras %}<div data-json='{{ value|as_json }}'></div>"
        ).render(Context({'value': payload}))
        self.assertNotIn('<script>', rendered)
        self.assertIn('&lt;script&gt;', rendered)


@override_settings(STORAGES=_TEST_STORAGES)
class ServiceFormFragmentTests(TestCase):
    def _url(self, code):
        from django.urls import reverse
        return reverse('dashboard:service_form_fragment', args=[code])

    def test_unknown_service_returns_neutral_not_found_fragment(self):
        with patch('dashboard.views.service_form_api.get_service_def', return_value=None):
            response = self.client.get(self._url('DOES-NOT-EXIST'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Service non trouvé')

    def test_database_only_service_renders_questions_and_sample_columns(self):
        from core.models import Service, ServiceFormField

        service = Service.objects.create(code='DB-FORM', name='DB form')
        ServiceFormField.objects.create(
            service=service, name='urgency_level', label='Niveau urgence',
            field_type='enum', options=['Normal', 'Express'], required=True,
            affects_pricing=True, price_modifier_type='add',
            price_modifier_value='1500', option_pricing={'Express': 1500},
        )
        ServiceFormField.objects.create(
            service=service, name='sample_code', label='Code échantillon',
            field_type='string', field_category='sample_column', required=True,
        )
        with patch('dashboard.views.service_form_api.get_service_def', return_value=None):
            response = self.client.get(self._url(service.code))

        self.assertContains(response, 'Niveau urgence')
        self.assertContains(response, 'Code échantillon')
        self.assertContains(response, 'data-pricing-value="1500.0"')
        self.assertContains(response, 'data-option-price="1500"')
        self.assertContains(response, 'sample_0_sample_code')

    def test_admin_pricing_overrides_registry_and_multiplier_bridge_is_rendered(self):
        from core.models import Service

        Service.objects.create(
            code='PRICED-FORM', name='Priced form',
            pricing_data={
                'base_price': {'non_pathogenic': 4000, 'pathogenic': 6000},
                'multipliers': {'Simple': 1, 'Duplicate': 2},
            },
        )
        definition = {
            'parameters': [{
                'name': 'analysis_mode', 'label': 'Mode analyse',
                'type': 'enum', 'options': ['Simple', 'Duplicate'],
            }],
            'sample_table': {'enabled': True, 'columns': [
                {'name': 'code', 'label': 'Code YAML', 'type': 'string'},
            ]},
            'pricing': {
                'model': 'per_sample_table_row_with_multiplier',
                'base_price': {'non_pathogenic': 1000, 'pathogenic': 2000},
                'multipliers': {'Simple': 1, 'Duplicate': 1.5},
            },
        }
        with patch('dashboard.views.service_form_api.get_service_def', return_value=definition):
            response = self.client.get(self._url('PRICED-FORM'))

        html = response.content.decode()
        self.assertIn('Mode analyse', html)
        self.assertIn('data-option-price="2"', html)
        self.assertIn('&quot;non_pathogenic&quot;: 4000', html)
        self.assertNotIn('&quot;non_pathogenic&quot;: 1000', html)
        self.assertIn('Code YAML', html)

    def test_db_sample_column_merges_without_duplicating_yaml_column(self):
        from core.models import Service, ServiceFormField

        service = Service.objects.create(code='MERGED-FORM', name='Merged form')
        ServiceFormField.objects.create(
            service=service, name='code', label='Duplicate code',
            field_category='sample_column')
        ServiceFormField.objects.create(
            service=service, name='volume', label='Volume DB',
            field_type='number', field_category='sample_column')
        definition = {
            'parameters': [],
            'sample_table': {'enabled': True, 'columns': [
                {'name': 'code', 'label': 'Code YAML', 'type': 'string'},
            ]},
            'pricing': {},
        }
        with patch('dashboard.views.service_form_api.get_service_def', return_value=definition):
            response = self.client.get(self._url(service.code))
        html = response.content.decode()
        self.assertEqual(html.count('data-col="code"'), 1)
        self.assertIn('Volume DB', html)
        self.assertIn('sample_0_volume', html)


@override_settings(STORAGES=_TEST_STORAGES)
class GuestSubmissionWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import Service
        cls.ibtikar_service = Service.objects.create(
            code='GUEST-IBT-SERVICE', name='Guest IBTIKAR service',
            channel_availability='IBTIKAR', ibtikar_price='1250',
        )
        cls.genoclab_service = Service.objects.create(
            code='GUEST-GCL-SERVICE', name='Guest GENOCLAB service',
            channel_availability='GENOCLAB', genoclab_price='2500',
        )

    def _post(self, service, channel, **extra):
        from unittest.mock import patch
        data = {
            'guest_name': 'Guest User',
            'guest_email': 'guest@example.test',
            'guest_phone': '+213000000000',
            'service_id': str(service.pk),
            'channel': channel,
            'title': f'{channel} guest request',
            'sample_0_code': 'S-1',
        }
        data.update(extra)
        with (
            patch('notifications.emails.notify_submission_confirmation'),
            patch('notifications.emails.notify_guest_tracking_code'),
        ):
            return self.client.post('/guest-submit/', data)

    def test_guest_ibtikar_uses_canonical_submitted_state_and_budget(self):
        response = self._post(
            self.ibtikar_service, 'IBTIKAR',
            declared_balance='50000', ibtikar_id='IBT-EXT-1',
        )
        self.assertEqual(response.status_code, 200)
        req = Request.objects.get(title='IBTIKAR guest request')
        self.assertEqual(req.status, 'SUBMITTED')
        self.assertTrue(req.display_id.startswith('IBK-'))
        self.assertEqual(req.budget_amount, 1250)
        self.assertTrue(req.submitted_as_guest)
        self.assertIsNotNone(req.guest_token)
        self.assertTrue(req.history.filter(to_status='SUBMITTED').exists())

    def test_guest_genoclab_uses_canonical_request_created_state_and_quote(self):
        response = self._post(self.genoclab_service, 'GENOCLAB')
        self.assertEqual(response.status_code, 200)
        req = Request.objects.get(title='GENOCLAB guest request')
        self.assertEqual(req.status, 'REQUEST_CREATED')
        self.assertTrue(req.display_id.startswith('GCL-'))
        self.assertEqual(req.quote_amount, 2500)
        self.assertTrue(req.history.filter(to_status='REQUEST_CREATED').exists())

    def test_cross_channel_service_is_rejected_server_side(self):
        response = self._post(self.ibtikar_service, 'GENOCLAB')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Request.objects.exists())
        self.assertContains(response, "Ce service n&#x27;est pas disponible")


@override_settings(STORAGES=_TEST_STORAGES)
class GuestTrackingSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.analyst = User.objects.create_user(
            username='guest-track-analyst', password='x', role='MEMBER',
            first_name='HiddenAnalystName',
        )

    def test_guest_code_submission_requires_tracking_token(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel='IBTIKAR', submitted_as_guest=True, guest_token=token,
            status='IBTIKAR_CODE_SUBMITTED', display_id='IBT-GUEST-CODE',
        )
        wrong = self.client.post(
            f'/track/ibtikar-code/{uuid.uuid4()}/',
            {'ibtikar_code': 'UNAUTHORIZED'},
        )
        self.assertEqual(wrong.status_code, 404)
        req.refresh_from_db()
        self.assertEqual(req.ibtikar_external_code, '')

        ok = self.client.post(
            f'/track/ibtikar-code/{token}/',
            {'ibtikar_code': 'AUTHORIZED'},
        )
        self.assertEqual(ok.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.ibtikar_external_code, 'AUTHORIZED')

    def test_public_tracking_hides_analyst_identity(self):
        token = uuid.uuid4()
        Request.objects.create(
            channel='IBTIKAR', submitted_as_guest=True, guest_token=token,
            assigned_to=self.analyst.member_profile,
            status='ASSIGNED', display_id='IBT-GUEST-PRIVATE',
        )
        response = self.client.get('/track/', {'q': str(token)})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'HiddenAnalystName')

    def test_public_tracking_hides_internal_history_notes(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel='IBTIKAR', submitted_as_guest=True, guest_token=token,
            assigned_to=self.analyst.member_profile,
            status='ASSIGNED', display_id='IBT-GUEST-NOTES',
        )
        RequestHistory.objects.create(
            request=req, actor=self.analyst, to_status='ASSIGNED',
            notes='INTERNAL-ONLY-ANALYST-NOTE',
        )
        response = self.client.get('/track/', {'q': str(token)})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'INTERNAL-ONLY-ANALYST-NOTE')

    def test_completed_request_without_report_renders_safely(self):
        token = uuid.uuid4()
        Request.objects.create(
            channel='GENOCLAB', submitted_as_guest=True, guest_token=token,
            status='COMPLETED', display_id='GCL-NO-REPORT',
        )
        response = self.client.get('/track/', {'q': str(token)})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Télécharger le rapport')

    def test_tracking_backfills_legacy_report_token(self):
        token = uuid.uuid4()
        req = Request.objects.create(
            channel='GENOCLAB', submitted_as_guest=True, guest_token=token,
            status='COMPLETED', display_id='GCL-LEGACY-REPORT',
            report_file='reports/legacy.pdf', report_token=None,
        )
        response = self.client.get('/track/', {'q': str(token)})
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertIsNotNone(req.report_token)

    def test_guest_ibtikar_form_uses_tracking_token(self):
        from django.http import HttpResponse
        from unittest.mock import patch

        token = uuid.uuid4()
        Request.objects.create(
            channel='IBTIKAR', submitted_as_guest=True, guest_token=token,
            status='IBTIKAR_SUBMISSION_PENDING', display_id='IBT-GUEST-FORM',
        )
        with patch(
            'documents.views._cached_serve_doc',
            return_value=HttpResponse(b'DOCX'),
        ) as serve:
            response = self.client.get(f'/documents/guest/ibtikar-form/{token}/')
        self.assertEqual(response.status_code, 200)
        serve.assert_called_once()
        wrong = self.client.get(
            f'/documents/guest/ibtikar-form/{uuid.uuid4()}/')
        self.assertEqual(wrong.status_code, 404)


@override_settings(STORAGES=_TEST_STORAGES)
class QuoteTemplateSecurityTests(TestCase):
    def test_existing_quote_json_cannot_close_script_tag(self):
        from accounts.models import User
        from core.models import Service

        admin = User.objects.create_user(
            username='quote-admin', password='x', role='PLATFORM_ADMIN')
        service = Service.objects.create(code='QUOTE-XSS', name='Quote service')
        req = Request.objects.create(
            channel='GENOCLAB', service=service, display_id='GCL-QUOTE-XSS',
            quote_detail={'items': [{'label': '</script><script>alert(1)</script>',
                                     'unit_price': 1, 'quantity': 1}]},
        )
        self.client.force_login(admin)
        response = self.client.get(f'/dashboard/ops/quote/{req.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '</script><script>alert(1)</script>')
        self.assertContains(response, '\\u003C/script\\u003E')


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


class PricingApiIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from core.models import Service

        cls.admin = User.objects.create_user(
            username='pricing-admin', password='x', role='PLATFORM_ADMIN')
        cls.service = Service.objects.create(
            code='STRICT-PRICE', name='Strict pricing service')

    def setUp(self):
        self.client.force_login(self.admin)

    def _post(self, **overrides):
        from django.urls import reverse

        payload = {
            'name': 'Tarif institutionnel',
            'pricing_type': 'BASE',
            'channel': 'GENOCLAB',
            'amount': '1500.50',
            'min_quantity': '1',
            'max_quantity': '',
            'min_amount': '',
            'max_amount': '',
            'priority': '0',
            'is_active': 'on',
        }
        payload.update(overrides)
        return self.client.post(
            reverse('dashboard:pricing_add_api', args=[self.service.pk]),
            payload,
        )

    def test_malformed_amount_is_rejected_not_saved_as_zero(self):
        from core.models import ServicePricing

        response = self._post(amount='not-a-number')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ServicePricing.objects.count(), 0)

    def test_active_zero_or_nonfinite_amount_is_rejected(self):
        from core.models import ServicePricing

        for amount in ('0', '-1', 'NaN', 'Infinity'):
            with self.subTest(amount=amount):
                response = self._post(amount=amount)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(ServicePricing.objects.count(), 0)

    def test_incoherent_quantity_and_amount_ranges_are_rejected(self):
        self.assertEqual(
            self._post(min_quantity='5', max_quantity='2').status_code, 400)
        self.assertEqual(
            self._post(min_amount='500', max_amount='100').status_code, 400)

    def test_valid_tariff_is_created_exactly(self):
        from decimal import Decimal
        from core.models import ServicePricing

        response = self._post()
        self.assertEqual(response.status_code, 201)
        tier = ServicePricing.objects.get()
        self.assertEqual(tier.amount, Decimal('1500.50'))


class AdminFinancialMutationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from core.models import Service

        cls.admin = User.objects.create_user(
            username='finance-admin', password='x', role='SUPER_ADMIN')
        cls.client_user = User.objects.create_user(
            username='finance-client', password='x', role='CLIENT')
        cls.service = Service.objects.create(
            code='FINANCE-STRICT', name='Financial integrity service')

    def setUp(self):
        self.client.force_login(self.admin)

    def _request(self, **overrides):
        values = {
            'display_id': f'GCL-FIN-{uuid.uuid4().hex[:8]}',
            'title': 'Financial request',
            'channel': 'GENOCLAB',
            'status': 'ORDER_UPLOADED',
            'service': self.service,
            'requester': self.client_user,
            'quote_amount': '1190.00',
            'quote_detail': {
                'items': [{
                    'label': 'Analyse', 'unit_price': 1000,
                    'quantity': 1, 'total': 1000,
                }],
                'admin_fees': 0,
                'report_fees': 0,
                'vat_rate': 0.19,
            },
        }
        values.update(overrides)
        return Request.objects.create(**values)

    def test_cost_adjustment_requires_positive_finite_amount_and_reason(self):
        from django.urls import reverse

        req = self._request(status='REQUEST_CREATED')
        url = reverse('dashboard:admin_adjust_cost', args=[req.pk])
        for payload in (
            {'admin_price': '-1', 'cost_justification': 'Correction documentée'},
            {'admin_price': 'NaN', 'cost_justification': 'Correction documentée'},
            {'admin_price': '1000', 'cost_justification': 'court'},
        ):
            with self.subTest(payload=payload):
                self.client.post(url, payload)
                req.refresh_from_db()
                self.assertIsNone(req.admin_validated_price)

    def test_valid_cost_adjustment_is_saved_as_decimal(self):
        from decimal import Decimal
        from django.urls import reverse

        req = self._request(status='REQUEST_CREATED')
        self.client.post(reverse('dashboard:admin_adjust_cost', args=[req.pk]), {
            'admin_price': '1234.56',
            'cost_justification': 'Correction tarifaire documentée',
        })
        req.refresh_from_db()
        self.assertEqual(req.admin_validated_price, Decimal('1234.56'))

    def test_malformed_quote_does_not_replace_existing_quote(self):
        from django.urls import reverse

        req = self._request(status='REQUEST_CREATED')
        original = req.quote_detail
        response = self.client.post(
            reverse('dashboard:admin_prepare_quote', args=[req.pk]),
            {
                'item_label_0': 'Analyse',
                'item_unit_price_0': 'garbage',
                'item_quantity_0': '1',
                'admin_fees': '0', 'report_fees': '0', 'vat_rate': '19',
            },
        )
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.quote_detail, original)

    def test_invoice_and_transition_succeed_together(self):
        from core.models import Invoice
        from django.urls import reverse

        req = self._request()
        response = self.client.post(
            reverse('dashboard:admin_generate_invoice', args=[req.pk]))
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'INVOICE_GENERATED')
        invoice = Invoice.objects.get(request=req)
        self.assertEqual(str(invoice.total_ttc), '1190.00')

    def test_invoice_recomputes_tampered_quote_line_total(self):
        from core.models import Invoice
        from django.urls import reverse

        req = self._request(quote_detail={
            'items': [{
                'label': 'Analyse', 'unit_price': 1000,
                'quantity': 2, 'total': 1,
            }],
            'admin_fees': 0, 'report_fees': 0, 'vat_rate': 0.19,
        })
        self.client.post(
            reverse('dashboard:admin_generate_invoice', args=[req.pk]))
        invoice = Invoice.objects.get(request=req)
        self.assertEqual(str(invoice.subtotal_ht), '2000.00')
        self.assertEqual(str(invoice.total_ttc), '2380.00')
        self.assertEqual(invoice.line_items[0]['total'], 2000.0)

    def test_transition_failure_rolls_invoice_back(self):
        from unittest.mock import patch
        from core.exceptions import InvalidTransitionError
        from core.models import Invoice
        from django.urls import reverse

        req = self._request()
        with patch(
            'dashboard.views.admin_ops.transition',
            side_effect=InvalidTransitionError('simulated transition failure'),
        ):
            response = self.client.post(
                reverse('dashboard:admin_generate_invoice', args=[req.pk]))
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'ORDER_UPLOADED')
        self.assertFalse(Invoice.objects.filter(request=req).exists())


@override_settings(STORAGES=_TEST_STORAGES)
class QrCodeAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User

        cls.admin = User.objects.create_user(
            username='qr-admin', password='x', role='PLATFORM_ADMIN')
        cls.analyst = User.objects.create_user(
            username='qr-analyst', password='x', role='MEMBER')
        cls.other_analyst = User.objects.create_user(
            username='qr-other', password='x', role='MEMBER')
        cls.owner = User.objects.create_user(
            username='qr-owner', password='x', role='CLIENT')
        cls.req = Request.objects.create(
            display_id='GCL-QR-001', title='QR protected report',
            channel='GENOCLAB', requester=cls.owner,
            assigned_to=cls.analyst.member_profile,
        )

    def test_qr_requires_login(self):
        response = self.client.get(f'/dashboard/qr/{self.req.pk}/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login', response.url)

    def test_qr_hides_request_from_owner_and_unassigned_member(self):
        for user in (self.owner, self.other_analyst):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(f'/dashboard/qr/{self.req.pk}/')
                self.assertEqual(response.status_code, 404)

    def test_assigned_member_gets_png_and_token_is_created(self):
        self.client.force_login(self.analyst)
        response = self.client.get(f'/dashboard/qr/{self.req.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG\r\n\x1a\n'))
        self.req.refresh_from_db()
        self.assertIsNotNone(self.req.report_token)

    def test_admin_can_read_existing_token_and_missing_request_is_404(self):
        self.client.force_login(self.admin)
        first = self.client.get(f'/dashboard/qr/{self.req.pk}/')
        self.assertEqual(first.status_code, 200)
        missing = self.client.get(f'/dashboard/qr/{uuid.uuid4()}/')
        self.assertEqual(missing.status_code, 404)


@override_settings(STORAGES=_TEST_STORAGES)
class RequestMessagingAuthorizationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User

        cls.admin = User.objects.create_user(
            username='msg-admin', password='x', role='PLATFORM_ADMIN')
        cls.superadmin = User.objects.create_user(
            username='msg-superadmin', password='x', role='SUPER_ADMIN')
        cls.analyst = User.objects.create_user(
            username='msg-analyst', password='x', role='MEMBER')
        cls.other_analyst = User.objects.create_user(
            username='msg-other', password='x', role='MEMBER')
        cls.owner = User.objects.create_user(
            username='msg-owner', password='x', role='CLIENT')

    def setUp(self):
        from core.models import Message

        Message.objects.all().delete()
        self.req = Request.objects.create(
            display_id=f'GCL-MSG-{uuid.uuid4().hex[:8]}',
            title='Protected message thread', channel='GENOCLAB',
            requester=self.owner, assigned_to=self.analyst.member_profile,
            status='ASSIGNED',
        )

    def _send(self, user, text='Message documenté'):
        self.client.force_login(user)
        return self.client.post(
            f'/dashboard/message/{self.req.pk}/', {'message_text': text})

    def test_get_blank_and_unrelated_member_cannot_create_messages(self):
        from core.models import Message

        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.get(f'/dashboard/message/{self.req.pk}/').status_code,
            403,
        )
        self.assertEqual(self._send(self.owner, '   ').status_code, 302)
        self.assertEqual(self._send(self.other_analyst).status_code, 403)
        self.assertEqual(Message.objects.count(), 0)

    def test_owner_message_reaches_assignee_and_all_active_admins(self):
        from core.models import Message

        response = self._send(self.owner)
        self.assertEqual(response.status_code, 302)
        recipients = set(Message.objects.values_list('to_user__username', flat=True))
        self.assertEqual(recipients, {'msg-analyst', 'msg-admin', 'msg-superadmin'})

    def test_admin_message_reaches_assignee_only(self):
        from core.models import Message

        self._send(self.admin)
        self.assertEqual(
            list(Message.objects.values_list('to_user__username', flat=True)),
            ['msg-analyst'],
        )

    def test_assigned_member_reaches_owner_and_last_admin(self):
        from core.models import Message

        RequestHistory.objects.create(
            request=self.req, from_status='VALIDATED', to_status='ASSIGNED',
            actor=self.admin,
        )
        self._send(self.analyst)
        recipients = set(Message.objects.values_list('to_user__username', flat=True))
        self.assertEqual(recipients, {'msg-owner', 'msg-admin'})

    def test_admin_without_assignee_falls_back_to_requester(self):
        from core.models import Message

        self.req.assigned_to = None
        self.req.save(update_fields=['assigned_to'])
        self._send(self.admin)
        self.assertEqual(Message.objects.get().to_user, self.owner)


class StatsViewAndExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User

        cls.admin = User.objects.create_user(
            username='stats-admin', password='x', role='PLATFORM_ADMIN')
        cls.client_user = User.objects.create_user(
            username='stats-client', password='x', role='CLIENT')

    def test_common_filters_strips_values_and_omits_blanks(self):
        from dashboard.views.stats import _common_filters

        request = RequestFactory().get('/dashboard/stats/', {
            'channel': ' GENOCLAB ', 'status': ' ',
            'date_from': '2026-01-01', 'date_to': '',
        })
        self.assertEqual(_common_filters(request), {
            'channel': 'GENOCLAB', 'date_from': '2026-01-01',
        })

    def test_stats_view_passes_role_scoped_filters_to_engine(self):
        from dashboard.views.stats import stats_view

        request = RequestFactory().get('/dashboard/stats/', {
            'channel': 'IBTIKAR', 'wilaya': '16',
        })
        request.user = self.admin
        with (
            patch('dashboard.views.stats.stats_for_user', return_value={'ok': True}) as stats,
            patch('core.bilan.available_sections', return_value=['overview']),
            patch('dashboard.views.stats.render') as rendered,
        ):
            rendered.return_value.status_code = 200
            response = stats_view.__wrapped__(request)
        self.assertEqual(response.status_code, 200)
        stats.assert_called_once_with(self.admin, channel='IBTIKAR', wilaya='16')
        self.assertTrue(rendered.call_args.args[2]['is_admin'])

    def test_stats_export_forbids_non_admin(self):
        from dashboard.views.stats import stats_export

        request = RequestFactory().get('/dashboard/stats/export/')
        request.user = self.client_user
        response = stats_export.__wrapped__(request)
        self.assertEqual(response.status_code, 403)

    def test_xlsx_export_validates_granularity_and_streams_file(self):
        from dashboard.views.stats import stats_export

        with tempfile.TemporaryDirectory() as directory:
            xlsx = Path(directory) / 'bilan.xlsx'
            xlsx.write_bytes(b'XLSX-CONTENT')
            request = RequestFactory().get('/dashboard/stats/export/', {
                'format': 'xlsx', 'granularity': 'week',
                'sections': ['overview'], 'organization': ' CNRDPA ',
            })
            request.user = self.admin
            with (
                patch('core.bilan.build_bilan', return_value={'rows': []}) as build,
                patch('documents.stats_excel.generate_bilan_excel', return_value=xlsx),
            ):
                response = stats_export.__wrapped__(request)
                body = b''.join(response.streaming_content)
                response.close()
        self.assertEqual(body, b'XLSX-CONTENT')
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        build.assert_called_once_with(
            {'organization': 'CNRDPA'}, sections=['overview'], granularity='month')

    @override_settings(DOCUMENT_PDF_ENABLED=False)
    def test_docx_export_streams_without_pdf_conversion(self):
        from dashboard.views.stats import stats_export

        with tempfile.TemporaryDirectory() as directory:
            docx = Path(directory) / 'stats.docx'
            docx.write_bytes(b'DOCX-CONTENT')
            request = RequestFactory().get(
                '/dashboard/stats/export/', {'format': 'docx'})
            request.user = self.admin
            with (
                patch('dashboard.views.stats.stats_for_user', return_value={'ok': True}),
                patch('documents.generators.generate_stats_report', return_value=docx),
                patch('documents.pdf_converter.convert_docx_to_pdf') as convert,
            ):
                response = stats_export.__wrapped__(request)
                body = b''.join(response.streaming_content)
                response.close()
        self.assertEqual(body, b'DOCX-CONTENT')
        self.assertIn('.docx', response['Content-Disposition'])
        convert.assert_not_called()
