"""Workflow-to-SMTP receipt tests using synthetic recipients and an isolated server."""
import socketserver
import threading
from contextlib import contextmanager
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, MemberProfile
from core.models import Request, Invoice, Service
from core.services.genoclab import submit_genoclab_request
from core.services.ibtikar import submit_ibtikar_request
from core.workflow import transition, _post_commit_transition
from core.exceptions import InvalidTransitionError, AuthorizationError


@contextmanager
def receiving_mailbox(reject=False):
    received = []
    envelopes = []
    class Receiver(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            self.wfile.write(b'220 localhost ESMTP\r\n')
            while line := self.rfile.readline():
                command = line.upper()
                if command.startswith(b'RCPT TO'):
                    envelopes.append(line.decode().strip())
                    self.wfile.write(b'550 Recipient rejected\r\n' if reject else b'250 OK\r\n')
                elif command.startswith(b'DATA'):
                    self.wfile.write(b'354 Send message\r\n')
                    data = []
                    while (part := self.rfile.readline()) not in (b'.\r\n', b''):
                        data.append(part[1:] if part.startswith(b'..') else part)
                    received.append(BytesParser(policy=policy.default).parsebytes(b''.join(data)))
                    self.wfile.write(b'250 Accepted\r\n')
                elif command.startswith(b'QUIT'):
                    self.wfile.write(b'221 Goodbye\r\n'); return
                else:
                    self.wfile.write(b'250 OK\r\n')
    with socketserver.TCPServer(('127.0.0.1', 0), Receiver) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                    EMAIL_HOST='127.0.0.1', EMAIL_PORT=server.server_address[1],
                    EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='', EMAIL_USE_SSL=False,
                    EMAIL_USE_TLS=False, EMAIL_TIMEOUT=3):
                yield received, envelopes
        finally:
            server.shutdown(); thread.join(timeout=5)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   PRIVILEGED_MFA_ENFORCEMENT=False, DOCUMENT_PDF_ENABLED=False,
                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}},
                   PUBLIC_BASE_URL='https://plagenor.example.test')
class WorkflowDeliveryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('mail-owner',role='CLIENT',email='owner@example.test',preferred_language='en')
        self.ops = User.objects.create_user('mail-ops',role='PLATFORM_ADMIN')
        self.member = User.objects.create_user('mail-member',role='MEMBER',email='analyst@example.test')
        self.profile = self.member.member_profile
        self.service = Service.objects.create(code='MAIL',name='Assay',name_en='English assay',name_ar='تحليل')
        self.req = Request.objects.create(display_id='MAIL-001',channel='GENOCLAB',requester=self.owner,
            service=self.service,assigned_to=self.profile,status='ASSIGNED')

    def test_submission_commit_receives_one_email_and_rollback_receives_none(self):
        for submit in (submit_genoclab_request, submit_ibtikar_request):
            with receiving_mailbox() as (inbox,envelope):
                with self.captureOnCommitCallbacks(execute=True):
                    req=submit({'title':'Audit','service_id':self.service.pk},self.owner)
                    self.assertEqual(inbox,[])
                self.assertEqual(len(inbox),1)
                self.assertEqual(inbox[0]['To'],self.owner.email)
                self.assertIn('Submission received',inbox[0]['Subject'])
                self.assertIn(req.display_id,inbox[0].get_body(preferencelist=('html',)).get_content())
                self.assertIn('owner@example.test',envelope[0])
                with self.captureOnCommitCallbacks(execute=True):
                    try:
                        with transaction.atomic():
                            submit({'title':'Rolled back'},self.owner)
                            raise ValueError('Rollback')
                    except ValueError: pass
                self.assertEqual(len(inbox),1)
                self.assertFalse(Request.objects.filter(title='Rolled back').exists())

    def test_guest_submission_receives_one_tracking_message(self):
        with receiving_mailbox() as (inbox,_):
            with self.captureOnCommitCallbacks(execute=True):
                submit_genoclab_request({'guest_email':'guest@example.test','guest_name':'Audit guest',
                    'guest_token':'dc7ed0ac-e2fd-4215-90e2-8a561eb75e9e','submitted_as_guest':True})
            self.assertEqual(len(inbox),1)
            self.assertIn('/track/?q=dc7ed0ac-e2fd-4215-90e2-8a561eb75e9e',inbox[0].get_body(preferencelist=('html',)).get_content())

    def test_assignment_acceptance_then_date_then_confirmation_no_duplicate(self):
        self.client.force_login(self.member)
        with receiving_mailbox() as (inbox,_):
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(reverse('dashboard:analyst_accept',args=[self.req.pk]))
            self.req.refresh_from_db()
            self.assertEqual(self.req.status,'ASSIGNED');self.assertEqual(inbox,[])
            url=reverse('dashboard:analyst_suggest_appointment',args=[self.req.pk])
            data={'appointment_date':str(timezone.localdate()+timedelta(days=2)), 'appointment_time':'10:00','appointment_note':'Bring samples'}
            with self.captureOnCommitCallbacks(execute=True): self.client.post(url,data)
            self.assertEqual(len(inbox),1)
            html=inbox[0].get_body(preferencelist=('html',)).get_content()
            self.assertIn('10:00',html);self.assertIn('Bring samples',html)
            self.assertIn(f'/dashboard/client/request/{self.req.pk}/',html)
            with self.captureOnCommitCallbacks(execute=True): self.client.post(url,data)
            self.assertEqual(len(inbox),1)
            self.req.refresh_from_db()
            with self.captureOnCommitCallbacks(execute=True): transition(self.req,'APPOINTMENT_CONFIRMED',self.owner)
            self.assertEqual(len(inbox),2)
            with self.assertRaises(InvalidTransitionError): transition(self.req,'APPOINTMENT_CONFIRMED',self.owner)
            self.assertEqual(len(inbox),2)

    def test_smtp_refusal_does_not_rollback_workflow_or_emit_duplicates(self):
        self.req.status='QUOTE_DRAFT';self.req.save()
        with receiving_mailbox(reject=True) as (inbox,envelope):
            with self.assertLogs('plagenor.email',level='ERROR'),self.captureOnCommitCallbacks(execute=True):
                transition(self.req,'REJECTED',self.ops)
            self.req.refresh_from_db();self.assertEqual(self.req.status,'REJECTED')
            self.assertEqual(inbox,[]);self.assertEqual(len(envelope),1)
            self.assertTrue(self.owner.notifications.filter(request=self.req).exists())

    def test_paid_revision_upload_path_never_requests_payment_again(self):
        self.req.status='ANALYSIS_FINISHED';self.req.report_file='reports/old.pdf'
        self.req.payment_verified_at=timezone.now();self.req.payment_verified_by=self.ops
        self.req.payment_verification_note='Bank matched';self.req.save()
        inv=Invoice.objects.create(request=self.req,invoice_number='MAIL-INV',payment_status='COMPLETED',total_ttc=119)
        from core.workflow import get_allowed_transitions
        self.assertEqual(get_allowed_transitions(self.req),['REPORT_UPLOADED'])
        with self.assertRaises(InvalidTransitionError):transition(self.req,'PAYMENT_PENDING',self.member)
        self.client.force_login(self.member)
        r=self.client.get(reverse('dashboard:analyst_request_detail',args=[self.req.pk]))
        self.assertContains(r,reverse('dashboard:analyst_upload_report',args=[self.req.pk]))
        transition(self.req,'REPORT_UPLOADED',self.member)
        self.req.status='ANALYSIS_FINISHED';self.req.save()
        inv.payment_status='PENDING';inv.save()
        self.assertNotIn('REPORT_UPLOADED',get_allowed_transitions(self.req))
        with self.assertRaises(InvalidTransitionError):transition(self.req,'REPORT_UPLOADED',self.member)

    def test_missing_documents_and_wrong_owners_cannot_drive_transitions(self):
        for current,target in [('ASSIGNED','APPOINTMENT_PROPOSED'),('PAYMENT_PENDING','PAYMENT_PROOF_UPLOADED'),('REPORT_UPLOADED','REPORT_VALIDATED')]:
            self.req.status=current;self.req.save()
            with self.assertRaises(InvalidTransitionError):transition(self.req,target,self.ops)
        other=User.objects.create_user('other',role='CLIENT')
        self.req.status='QUOTE_SENT';self.req.save()
        with self.assertRaises(AuthorizationError):transition(self.req,'QUOTE_VALIDATED_BY_CLIENT',other)
        self.member.is_active=False
        self.req.status='ANALYSIS_STARTED';self.req.save()
        with self.assertRaises(AuthorizationError):transition(self.req,'ANALYSIS_FINISHED',self.member)

    def test_post_commit_failure_does_not_suppress_other_effects(self):
        with patch('core.workflow.log_workflow_transition',side_effect=OSError),patch('core.workflow._send_transition_emails') as email,patch('core.workflow._create_notifications') as app,patch('core.workflow._auto_generate_documents') as docs,self.assertLogs('plagenor.workflow',level='ERROR'):
            _post_commit_transition(self.req,'ASSIGNED','APPOINTMENT_PROPOSED',self.ops,'',False)
        email.assert_called_once();app.assert_called_once();docs.assert_called_once()

    def test_staff_milestones_route_once_to_active_ops_and_finance(self):
        from notifications.emails import notify_staff_transition
        self.ops.email='ops@example.test';self.ops.save()
        User.objects.create_user('mail-ops-alias',role='PLATFORM_ADMIN',email='OPS@example.test')
        User.objects.create_user('mail-finance',role='FINANCE',email='finance@example.test',preferred_language='ar')
        User.objects.create_user('mail-inactive',role='PLATFORM_ADMIN',email='inactive@example.test',is_active=False)
        with receiving_mailbox() as (inbox,_):
            notify_staff_transition(self.req,'PAYMENT_PROOF_UPLOADED')
            self.assertEqual({m['To'] for m in inbox},{'ops@example.test','finance@example.test'})
            finance=next(m for m in inbox if m['To']=='finance@example.test')
            self.assertIn('إجراء مطلوب',finance['Subject'])
            self.assertIn('/dashboard/finance/',finance.get_body(preferencelist=('html',)).get_content())
            self.assertNotIn('/dashboard/client/',finance.get_body(preferencelist=('html',)).get_content())
            notify_staff_transition(self.req,'ANALYSIS_STARTED')
            self.assertEqual(len(inbox),2)

    def test_complete_workflow_graphs_deliver_expected_email_milestones(self):
        import uuid
        from decimal import Decimal
        from tempfile import TemporaryDirectory
        paths={
            'IBTIKAR':['VALIDATION_PEDAGOGIQUE','VALIDATION_FINANCE','PLATFORM_NOTE_GENERATED','IBTIKAR_SUBMISSION_PENDING','IBTIKAR_CODE_SUBMITTED','ASSIGNED','APPOINTMENT_PROPOSED','APPOINTMENT_CONFIRMED','SAMPLE_RECEIVED','ANALYSIS_STARTED','ANALYSIS_FINISHED','REPORT_UPLOADED','REPORT_VALIDATED','SENT_TO_REQUESTER','COMPLETED','CLOSED'],
            'GENOCLAB':['QUOTE_DRAFT','QUOTE_SENT','QUOTE_VALIDATED_BY_CLIENT','ORDER_UPLOADED','INVOICE_GENERATED','ASSIGNED','APPOINTMENT_PROPOSED','APPOINTMENT_CONFIRMED','SAMPLE_RECEIVED','ANALYSIS_STARTED','ANALYSIS_FINISHED','PAYMENT_PENDING','PAYMENT_PROOF_UPLOADED','PAYMENT_CONFIRMED','REPORT_UPLOADED','REPORT_VALIDATED','SENT_TO_CLIENT','COMPLETED','ARCHIVED'],
        }
        for billing in ('IBTIKAR','GENOCLAB','OHB'):
            channel='IBTIKAR' if billing=='IBTIKAR' else 'GENOCLAB'
            req=Request.objects.create(display_id='SMTP-'+billing,channel=channel,billing_channel=billing if billing!='IBTIKAR' else 'GENOCLAB',
                status='SUBMITTED' if channel=='IBTIKAR' else 'REQUEST_CREATED',requester=self.owner,service=self.service,
                assigned_to=self.profile,appointment_date=timezone.localdate()+timedelta(days=1),
                ibtikar_external_code='EXTERNAL-TEST',order_file='orders/test.pdf',payment_receipt_file='payments/test.pdf',
                report_file='reports/test.pdf',report_token=uuid.uuid4(),payment_verified_at=timezone.now(),
                payment_verified_by=self.ops,payment_verification_note='Verified test receipt',
                quote_detail={'items':[{'label':'Assay','unit_price':100,'quantity':1,'total':100}],'vat_rate':0 if billing=='OHB' else .19})
            if channel=='GENOCLAB':
                Invoice.objects.create(request=req,invoice_number='SMTP-INV-'+billing,total_ttc=100 if billing=='OHB' else 119)
            with TemporaryDirectory() as media,override_settings(MEDIA_ROOT=media),receiving_mailbox() as (inbox,_):
                for status in paths[channel]:
                    with self.captureOnCommitCallbacks(execute=True):transition(req,status,self.ops)
                # Every message has the right reference, body and recipient; no duplicate subjects.
                self.assertTrue(inbox)
                self.assertEqual(len(inbox),len({(str(m['Subject']), m.get_body(preferencelist=('html',)).get_content()) for m in inbox}))
                for m in inbox:
                    self.assertIn(req.display_id,m['Subject'])
                    self.assertIn(m['To'],{self.owner.email,self.member.email})
                    self.assertIn(req.display_id,m.get_body(preferencelist=('plain',)).get_content())
                    self.assertIn('https://plagenor.example.test/',m.get_body(preferencelist=('html',)).get_content())
                self.assertTrue(any('Report available' in m['Subject'] for m in inbox))
                self.assertEqual(req.history.count(),len(paths[channel]))

    def test_zero_validated_budget_does_not_debit_fallback_estimate(self):
        from decimal import Decimal
        self.owner.ibtikar_declared_balance=1000;self.owner.save()
        self.req.channel='IBTIKAR';self.req.status='SENT_TO_REQUESTER'
        self.req.budget_amount=500;self.req.admin_validated_price=0;self.req.save()
        transition(self.req,'COMPLETED',self.ops)
        self.owner.refresh_from_db();self.assertEqual(self.owner.ibtikar_declared_balance,Decimal('1000'))

    def test_reschedule_invalid_dates_and_late_actions_are_safe(self):
        self.client.force_login(self.member)
        self.req.status='APPOINTMENT_PROPOSED';self.req.appointment_date=timezone.localdate()+timedelta(days=2);self.req.save()
        url=reverse('dashboard:analyst_suggest_appointment',args=[self.req.pk])
        tomorrow=str(timezone.localdate()+timedelta(days=1))
        with receiving_mailbox() as (inbox,_):
            with self.captureOnCommitCallbacks(execute=True):self.client.post(url,{'appointment_date':tomorrow})
            self.assertEqual(len(inbox),1)
            with self.captureOnCommitCallbacks(execute=True):self.client.post(url,{'appointment_date':'2000-01-01'})
            self.req.refresh_from_db();self.assertEqual(str(self.req.appointment_date),tomorrow)
            self.req.status='ANALYSIS_STARTED';self.req.save()
            with self.captureOnCommitCallbacks(execute=True):self.client.post(url,{'appointment_date':tomorrow})
            self.assertEqual(len(inbox),1)
            for route in ('dashboard:analyst_accept','dashboard:analyst_decline'):
                self.assertEqual(self.client.post(reverse(route,args=[self.req.pk])).status_code,403)
            other=User.objects.create_user('foreign-analyst',role='MEMBER')
            with self.assertRaises(AuthorizationError):transition(self.req,'ANALYSIS_FINISHED',other)

    def test_guest_helpers_and_missing_email_fail_closed(self):
        from notifications.emails import notify_submission_confirmation,notify_appointment
        self.req.requester=None;self.req.guest_email='guest@example.test';self.req.appointment_date=timezone.localdate()
        with receiving_mailbox() as (inbox,_):
            notify_submission_confirmation(self.req)
            self.req.guest_email='';notify_appointment(self.req)
            self.assertEqual(len(inbox),1)
            self.assertEqual(inbox[0]['To'],'guest@example.test')
            with self.captureOnCommitCallbacks(execute=True):
                submit_ibtikar_request({'guest_email':'guest@example.test','guest_token':'dc7ed0ac-e2fd-4215-90e2-8a561eb75e9e'})
            self.assertEqual(len(inbox),2)

    def test_in_app_overlap_creates_one_localized_notification(self):
        from core.workflow import _create_notifications
        self.req.requester=self.ops;self.req.status='PAYMENT_PROOF_UPLOADED';self.req.save()
        _create_notifications(self.req,'PAYMENT_PROOF_UPLOADED')
        self.assertEqual(self.ops.notifications.filter(request=self.req).count(),1)

    def test_password_reset_email_transport_and_failure_response(self):
        self.owner.set_password('Audit-test-password-924!');self.owner.save()
        url=reverse('accounts:password_reset')
        with receiving_mailbox() as (inbox,_):
            response=self.client.post(url,{'email':self.owner.email})
            self.assertEqual(response.status_code,302)
            self.assertEqual(len(inbox),1)
            self.assertEqual(inbox[0]['To'],self.owner.email)
            self.assertIn('PLAGENOR',inbox[0]['Subject'])
            self.assertIn('/accounts/password-reset/confirm/',inbox[0].get_body(preferencelist=('plain',)).get_content())
        with receiving_mailbox(reject=True) as (inbox,_),self.assertLogs('django.contrib.auth',level='ERROR'):
            response=self.client.post(url,{'email':self.owner.email})
            self.assertEqual(response.status_code,302)
            self.assertEqual(inbox,[])
