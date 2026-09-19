import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from core.exceptions import AuthorizationError
from core.guest_forms import GuestContactForm, guest_contact
from core.ibtikar.services import record_code, record_guest_code
from core.models import Request, RequestHistory, Service
from core.service_eligibility import resolve_service, services_for, validate_service
from core.services.genoclab import submit_genoclab_request
from core.services.ibtikar import submit_ibtikar_request
from core.workflow import transition


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', DOCUMENT_PDF_ENABLED=False, STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class SubmissionSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('owner', 'owner@example.test', 'A-test-password!2026', role='CLIENT')
        self.other = User.objects.create_user('other', 'other@example.test', 'Another-test-password!2026', role='REQUESTER')
        self.both = Service.objects.create(code='SHARED-TEST', name='Shared service', channel_availability='BOTH', ibtikar_price=100, genoclab_price=100)
        self.ibtikar = Service.objects.create(code='IBTIKAR-TEST', name='Academic service', channel_availability='IBTIKAR', ibtikar_price=100)
        self.commercial = Service.objects.create(code='COMMERCIAL-TEST', name='Commercial service', channel_availability='GENOCLAB', genoclab_price=100)
        self.inactive = Service.objects.create(code='INACTIVE-TEST', name='Inactive service', active=False)

    def make_guest(self, **extra):
        values = dict(title='Synthetic request', display_id='TEST-' + uuid.uuid4().hex[:12],
                      channel='IBTIKAR', status='IBTIKAR_SUBMISSION_PENDING', service=self.ibtikar,
                      submitted_as_guest=True, guest_token=uuid.uuid4(), guest_email='new@example.test', guest_name='Test Guest')
        values.update(extra)
        return Request.objects.create(**values)

    def test_service_eligibility_matrix_and_error_codes(self):
        for channel in ('IBTIKAR', 'GENOCLAB'):
            self.assertIn(self.both, services_for(channel))
            self.assertEqual(resolve_service(str(self.both.pk), channel), self.both)
        cases = [(None, 'IBTIKAR', 'invalid_service_id'), ('broken', 'GENOCLAB', 'invalid_service_id'),
                 (uuid.uuid4(), 'IBTIKAR', 'unknown_service'), (self.inactive.pk, 'IBTIKAR', 'inactive_service'),
                 (self.ibtikar.pk, 'GENOCLAB', 'incompatible_service'), (self.commercial.pk, 'IBTIKAR', 'incompatible_service'),
                 (self.both.pk, 'OHB', 'invalid_channel')]
        for value, channel, code in cases:
            with self.subTest(value=value, channel=channel), self.assertRaises(ValidationError) as raised:
                resolve_service(value, channel)
            self.assertEqual(raised.exception.code, code)
        with self.assertRaises(ValidationError):
            services_for('invalid')
        with self.assertRaises(ValidationError):
            validate_service(None, 'IBTIKAR')

    def test_business_submissions_enforce_channel_and_active_service(self):
        for submit, allowed, forbidden in [(submit_genoclab_request, self.commercial, self.ibtikar),
                                           (submit_ibtikar_request, self.ibtikar, self.commercial)]:
            for service in (allowed, self.both):
                created = submit({'service_id': str(service.pk)}, self.user)
                self.assertEqual(created.service, service)
            for key in (forbidden.pk, self.inactive.pk, uuid.uuid4(), 'invalid', None):
                before = Request.objects.count()
                with self.subTest(key=key), self.assertRaises(ValidationError):
                    submit({'service_id': key}, self.user)
                self.assertEqual(Request.objects.count(), before)

    def test_authenticated_service_ids_never_cause_server_errors(self):
        self.client.force_login(self.user)
        for name, wrong in [('dashboard:client_create', self.ibtikar), ('dashboard:requester_create', self.commercial)]:
            for key in ('bad-uuid', str(uuid.uuid4()), str(self.inactive.pk), str(wrong.pk)):
                response = self.client.post(reverse(name), {'service_id': key, 'title': 'Must not be created'})
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Request.objects.exists())

    def test_guest_email_validation_preserves_other_fields(self):
        for email in ('not-an-email', '', 'x' * 255 + '@example.test'):
            cache.clear()
            response = self.client.post(reverse('guest_submit'), {
                'guest_name': 'Test <Guest>', 'guest_email': email, 'service_id': str(self.both.pk),
                'channel': 'GENOCLAB', 'title': 'Preserved request title', 'param_mode': 'chosen',
                'sample_0_code': 'S01', 'sample_1_code': 'S02',
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Preserved request title')
            self.assertContains(response, 'Test &lt;Guest&gt;')
            self.assertEqual(response.context['saved_form_values']['sample_1_code'], ['S02'])
            self.assertFalse(Request.objects.exists())
        form = GuestContactForm({'guest_name': ' Test Guest ', 'guest_email': ' guest@example.test '})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['guest_email'], 'guest@example.test')
        with self.assertRaises(ValidationError):
            guest_contact({'guest_name': 'Test', 'guest_email': 'wrong'})

    def test_unknown_channel_is_rejected_not_silently_reassigned(self):
        response = self.client.post(reverse('guest_submit'), {
            'guest_name': 'Test Guest', 'guest_email': 'guest@example.test',
            'service_id': str(self.both.pk), 'channel': 'tampered',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Request.objects.exists())

    def test_guest_business_validation_and_normalization(self):
        payload = {'service_id': str(self.both.pk), 'submitted_as_guest': True, 'guest_token': uuid.uuid4(),
                   'guest_name': ' Test Guest ', 'guest_email': ' guest@example.test '}
        result = submit_genoclab_request(payload)
        self.assertEqual(result.guest_email, 'guest@example.test')
        self.assertEqual(result.guest_name, 'Test Guest')
        with self.assertRaises(ValidationError):
            submit_genoclab_request({**payload, 'guest_email': 'invalid'})

    def test_guest_reference_is_token_scoped_and_idempotent(self):
        req = self.make_guest()
        other = self.make_guest()
        for token in (None, uuid.uuid4(), other.guest_token):
            with self.assertRaises(ValidationError):
                record_guest_code(req, 'REFERENCE', guest_token=token)
        self.assertFalse(req.history.exists())
        result = record_guest_code(req, ' REFERENCE ', guest_token=req.guest_token)
        self.assertEqual(result.status, 'IBTIKAR_CODE_SUBMITTED')
        before = req.history.count()
        record_guest_code(req, 'REFERENCE', guest_token=req.guest_token)
        self.assertEqual(req.history.count(), before)
        with self.assertRaises(ValidationError):
            record_guest_code(req, 'CHANGED', guest_token=req.guest_token)
        req.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(req.ibtikar_external_code, 'REFERENCE')
        self.assertEqual(other.ibtikar_external_code, '')

    def test_guest_reference_rejects_wrong_channel_stage_and_owner(self):
        cases = [{'channel': 'GENOCLAB'}, {'status': 'SUBMITTED'}, {'submitted_as_guest': False}]
        for values in cases:
            req = self.make_guest(**values)
            with self.assertRaises(ValidationError):
                record_guest_code(req, 'REFERENCE', guest_token=req.guest_token)
            req.refresh_from_db()
            self.assertEqual(req.ibtikar_external_code, '')
        req = self.make_guest(requester=self.user)
        with self.assertRaises(ValidationError):
            record_code(req, 'REFERENCE', self.other)
        self.user.is_active = False
        with self.assertRaises(ValidationError):
            record_code(req, 'REFERENCE', self.user)
        self.user.is_active = True
        for code in ('', 'x' * 51, None):
            with self.assertRaises(ValidationError):
                record_code(req, code, self.user)
        result = record_code(req, 'OWNED', self.user)
        self.assertEqual(result.ibtikar_external_code, 'OWNED')

    def test_guest_http_reference_matrix_does_not_allow_force(self):
        req = self.make_guest()
        self.assertEqual(self.client.post(reverse('guest_ibtikar_code', args=[uuid.uuid4()]), {'ibtikar_code': 'TEST'}).status_code, 404)
        for code in ('', 'x' * 51, 'REFERENCE', 'REFERENCE', 'CHANGED'):
            response = self.client.post(reverse('guest_ibtikar_code', args=[req.guest_token]), {'ibtikar_code': code})
            self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'IBTIKAR_CODE_SUBMITTED')
        self.assertEqual(req.ibtikar_external_code, 'REFERENCE')
        self.assertEqual(req.history.count(), 1)
        with self.assertRaises(AuthorizationError):
            transition(req, 'COMPLETED', None, force=True, notes='Unauthorized')

    def test_mixed_channel_conversion_keeps_all_owned_requests_visible(self):
        academic = self.make_guest(status='SUBMITTED')
        commercial = self.make_guest(channel='GENOCLAB', service=self.commercial, status='REQUEST_CREATED')
        foreign = self.make_guest(requester=self.other)
        token = TimestampSigner(salt='guest-conversion').sign('new@example.test')
        response = self.client.post(reverse('accounts:convert_guest_verify', args=[token]), {
            'password': 'Synthetic-conversion!2026', 'first_name': 'Test', 'last_name': 'Guest',
        })
        self.assertEqual(response.status_code, 302)
        academic.refresh_from_db(); commercial.refresh_from_db(); foreign.refresh_from_db()
        self.assertEqual(academic.requester_id, commercial.requester_id)
        self.assertEqual(foreign.requester_id, self.other.pk)
        for name in ('dashboard:client', 'dashboard:requester'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            keys = set(response.context['active_requests'].values_list('pk', flat=True))
            self.assertEqual(keys, {academic.pk, commercial.pk})
        self.assertEqual(self.client.get(reverse('dashboard:client_request_detail', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('dashboard:requester_request_detail', args=[foreign.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse('dashboard:client_request_detail', args=[academic.pk])),
                             reverse('dashboard:requester_request_detail', args=[academic.pk]), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('dashboard:requester_request_detail', args=[commercial.pk])),
                             reverse('dashboard:client_request_detail', args=[commercial.pk]), fetch_redirect_response=False)

    def test_wrong_channel_actions_cannot_modify_owned_requests(self):
        req = self.make_guest(requester=self.user, status='SENT_TO_REQUESTER')
        self.client.force_login(self.user)
        response = self.client.post(reverse('dashboard:client_confirm', args=[req.pk]))
        self.assertEqual(response.status_code, 404)
        req.refresh_from_db()
        self.assertFalse(req.receipt_confirmed)
