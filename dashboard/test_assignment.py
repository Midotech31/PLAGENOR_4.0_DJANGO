"""Assignment must agree with the UI and commit the entire workflow atomically."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection, connections
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Technique, User
from core.ibtikar.models import IbtikarSubmission
from core.models import Request, RequestHistory, Service
from notifications.models import Notification
from dashboard.views.admin_ops import assign_request


@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class AssignmentHTTPTests(TestCase):
    def setUp(self):
        self.ops = User.objects.create_user('assignment-ops', role='PLATFORM_ADMIN')
        self.member = User.objects.create_user('assignment-member', role='MEMBER').member_profile
        self.member.techniques.add(Technique.objects.create(name_fr='MALDI-TOF'))
        self.service = Service.objects.create(code='EGTP-IMT', name_fr='Identification microbienne via MALDI-TOF MS')
        self.req = Request.objects.create(display_id='ASSIGN-PRIMARY', channel='IBTIKAR', status='IBTIKAR_CODE_SUBMITTED',
                                          service=self.service, title='Synthetic MALDI assignment',
                                          ibtikar_external_code='SYNTHETIC-CODE')
        self.form = IbtikarSubmission.objects.create(request=self.req, submitted_at=timezone.now(),
                                                     estimate={'total': 2500})
        self.url = reverse('dashboard:admin_assign', args=[self.req.pk])
        self.detail = reverse('dashboard:admin_request_detail', args=[self.req.pk])
        self.client.force_login(self.ops)

    def test_maldi_assignment_persists_status_assignee_load_audit_and_notification(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, {'member_id': self.member.pk})
        self.assertRedirects(response, self.detail)
        self.req.refresh_from_db()
        self.member.refresh_from_db()
        self.assertEqual(self.req.status, 'ASSIGNED')
        self.assertEqual(self.req.assigned_to_id, self.member.pk)
        self.assertEqual(self.member.current_load, 1)
        self.assertEqual(RequestHistory.objects.filter(request=self.req, to_status='ASSIGNED').count(), 1)
        self.assertTrue(Notification.objects.filter(request=self.req, user=self.member.user,
                                                   notification_type='WORKFLOW').exists())

    def test_workflow_rejection_rolls_back_the_assignment_and_load(self):
        self.form.submitted_at = None
        self.form.save()
        response = self.client.post(self.url, {'member_id': self.member.pk})
        self.assertEqual(response.status_code, 302)
        self.req.refresh_from_db()
        self.member.refresh_from_db()
        self.assertIsNone(self.req.assigned_to_id)
        self.assertEqual(self.req.status, 'IBTIKAR_CODE_SUBMITTED')
        self.assertEqual(self.member.current_load, 0)
        self.assertFalse(RequestHistory.objects.filter(request=self.req).exists())
        self.assertFalse(Notification.objects.filter(request=self.req).exists())

    def test_unavailable_candidate_is_disabled_and_server_reports_the_exact_reason(self):
        self.member.available = False
        self.member.save()
        page = self.client.get(self.detail)
        candidate = page.context['assignment_candidates'][0]
        self.assertIn('Analyste indisponible.', candidate['reasons'])
        self.assertFalse(page.context['has_eligible_candidates'])
        self.assertContains(page, f'value="{self.member.pk}" disabled')
        response = self.client.post(self.url, {'member_id': self.member.pk})
        self.assertIn('Analyste indisponible.', ' '.join(str(m) for m in get_messages(response.wsgi_request)))
        self.req.refresh_from_db()
        self.assertIsNone(self.req.assigned_to_id)

    def test_full_capacity_remains_a_server_guard_even_with_a_forged_selection(self):
        self.member.max_load = 1
        self.member.save()
        Request.objects.create(display_id='ASSIGN-CAPACITY', channel='IBTIKAR', status='ASSIGNED', assigned_to=self.member)
        response = self.client.post(self.url, {'member_id': self.member.pk})
        self.assertIn('Capacité atteinte (1/1).', ' '.join(str(m) for m in get_messages(response.wsgi_request)))
        self.req.refresh_from_db()
        self.assertIsNone(self.req.assigned_to_id)

    def test_declined_task_has_assignment_form_and_can_receive_replacement(self):
        self.req.status = 'ASSIGNED'
        self.req.save()
        page = self.client.get(self.detail)
        self.assertTrue(page.context['can_assign'])
        self.assertContains(page, 'id="assignment-member"')
        self.client.post(self.url, {'member_id': self.member.pk})
        self.req.refresh_from_db()
        self.assertEqual(self.req.assigned_to_id, self.member.pk)
        self.assertEqual(self.req.status, 'ASSIGNED')

    def test_invalid_profile_ids_do_not_change_request(self):
        self.assertEqual(self.client.post(self.url, {'member_id': 999999}).status_code, 404)
        self.assertEqual(self.client.post(self.url, {'member_id': 'invalid'}).status_code, 302)
        self.req.refresh_from_db()
        self.assertIsNone(self.req.assigned_to_id)

    def test_qualification_options_do_not_filter_out_observers(self):
        observer = User.objects.create_user('unqualified-observer', role='MEMBER').member_profile
        response = self.client.get(self.detail)
        self.assertIn(observer, response.context['available_members'])
        candidate = next(c for c in response.context['assignment_candidates'] if c['member'] == observer)
        self.assertTrue(candidate['reasons'])
        # Quick assignment and the request detail use the same qualification rules.
        dashboard = self.client.get(reverse('dashboard:admin_ops'))
        pending = next(r for r in dashboard.context['assignable_requests'] if r.pk == self.req.pk)
        self.assertEqual(pending.assignment_candidates, response.context['assignment_candidates'])

    def test_actions_follow_header_and_ibtikar_link_belongs_to_documents(self):
        html = self.client.get(self.detail).content.decode()
        self.assertLess(html.index('<h1 '), html.index('id="request-operations-heading"'))
        self.assertLess(html.index('Documents</h3>'), html.index('Consulter le formulaire IBTIKAR et sa validation'))
        self.assertNotIn('name="to_status" value="ASSIGNED"', html)

    def test_other_roles_cannot_assign_and_generic_transition_cannot_skip_selection(self):
        for role in ('MEMBER', 'FINANCE', 'REQUESTER', 'CLIENT'):
            user = User.objects.create_user('assignment-denied-' + role, role=role)
            self.client.force_login(user)
            self.assertEqual(self.client.post(self.url, {'member_id': self.member.pk}).status_code, 403)
        self.client.force_login(self.ops)
        self.client.post(reverse('dashboard:admin_transition', args=[self.req.pk]), {'to_status': 'ASSIGNED'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, 'IBTIKAR_CODE_SUBMITTED')
        self.assertIsNone(self.req.assigned_to_id)


@skipUnless(connection.vendor == 'postgresql', 'Row-lock concurrency is exercised by PostgreSQL CI.')
class AssignmentConcurrencyTests(TransactionTestCase):
    def test_two_operators_cannot_exceed_one_remaining_assignment_slot(self):
        ops = User.objects.create_user('concurrent-assignment-ops', role='PLATFORM_ADMIN')
        member = User.objects.create_user('concurrent-assignment-member', role='MEMBER').member_profile
        member.max_load = 1
        member.save()
        requests = [Request.objects.create(display_id='CONCURRENT-ASSIGN-' + str(index),
                                          channel='IBTIKAR', status='IBTIKAR_CODE_SUBMITTED')
                    for index in range(2)]
        barrier = Barrier(2)

        def assign(pk):
            try:
                request = RequestFactory().post('/dashboard/ops/assign/', {'member_id': member.pk})
                request.user = User.objects.get(pk=ops.pk)
                request.session = {}
                request._messages = FallbackStorage(request)
                barrier.wait(timeout=10)
                return assign_request(request, pk=pk).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(assign, req.pk) for req in requests]
            self.assertEqual([future.result(timeout=20) for future in futures], [302, 302])
        member.refresh_from_db()
        self.assertEqual(member.current_load, 1)
        self.assertEqual(Request.objects.filter(assigned_to=member).count(), 1)
        self.assertEqual(RequestHistory.objects.filter(to_status='ASSIGNED').count(), 1)
