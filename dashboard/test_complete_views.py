"""HTTP contracts for role boundaries, corrections and exceptional inputs."""
import io
import tempfile
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch
from PIL import Image
from django.test import TestCase, RequestFactory, override_settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import Http404
from django.core.exceptions import ValidationError
from accounts.models import User, MemberProfile
from core.models import Request, Service, Invoice
from core.exceptions import InvalidTransitionError
from dashboard.views import admin_ops,analyst,client,requester,superadmin


@override_settings(STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CompleteViewContracts(TestCase):
    def setUp(self):
        # RequestFactory does not manage Django's HTTP lifecycle. Closing a
        # FileResponse emits request_finished, which would close PostgreSQL's
        # connection while TestCase still owns its outer transaction.
        from django.core.signals import request_finished
        from django.db import close_old_connections
        request_finished.disconnect(close_old_connections)
        self.addCleanup(request_finished.connect, close_old_connections)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.media=override_settings(MEDIA_ROOT=self.tmp.name);self.media.enable();self.addCleanup(self.media.disable)
        self.users={r:User.objects.create_user('complete-'+r,role=r) for r in ('SUPER_ADMIN','PLATFORM_ADMIN','MEMBER','CLIENT','REQUESTER','FINANCE')}
        self.req=Request.objects.create(display_id='HTTP-COMP',channel='GENOCLAB',requester=self.users['CLIENT'])
        self.member=self.users['MEMBER'].member_profile
        self.second=User.objects.create_user('complete-second',role='MEMBER').member_profile
        self.factory=RequestFactory()

    def call(self,fn,role='PLATFORM_ADMIN',method='post',data=None,**kwargs):
        req=getattr(self.factory,method)('/dashboard/',data or {})
        req.user=self.users[role];req.session={};req._messages=FallbackStorage(req)
        return fn(req,**kwargs)

    def test_mutations_require_post_even_for_authorized_users(self):
        groups=[(admin_ops,'PLATFORM_ADMIN','assign_request manage_observers modify_appointment adjust_cost confirm_payment'),
                (analyst,'MEMBER','accept_task decline_task workflow_action suggest_appointment accept_alt_date decline_alt_date upload_report'),
                (client,'CLIENT','accept_quote reject_quote upload_order upload_payment_receipt confirm_appointment confirm_receipt suggest_alternative_date rate_service'),
                (requester,'REQUESTER','confirm_receipt confirm_appointment suggest_alternative_date submit_ibtikar_code rate_service'),
                (superadmin,'SUPER_ADMIN','user_toggle_active member_toggle_available member_assign_techniques service_delete technique_delete technique_reactivate service_reactivate content_delete announcement_toggle announcement_delete reset_2fa')]
        for module,role,names in groups:
            for name in names.split():
                fn=getattr(module,name,None)
                if fn is None:continue
                with self.subTest(view=name):
                    response=self.call(fn,role,method='get',pk=self.req.pk)
                    self.assertIn(response.status_code,(403,405))
        for fn in (admin_ops.award_points,admin_ops.upload_gift,admin_ops.send_cheer):
            self.assertEqual(self.call(fn,method='get',member_pk=self.member.pk).status_code,403)

    def test_reassign_requires_reason_resets_acceptance_and_informs_both_analysts(self):
        self.req.assigned_to=self.member;self.req.status='ANALYSIS_STARTED';self.req.assignment_accepted=True;self.req.save()
        data={'member_id':self.second.pk}
        self.call(admin_ops.assign_request,data=data,pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.assigned_to_id,self.member.pk)
        data['reason']='Absence confirmed'
        self.call(admin_ops.assign_request,data=data,pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.assigned_to_id,self.second.pk)
        self.assertFalse(self.req.assignment_accepted)
        self.assertTrue(self.req.history.filter(notes__icontains='Absence confirmed').exists())
        from notifications.models import Notification
        self.assertTrue(Notification.objects.filter(user=self.member.user,request=self.req).exists())
        self.assertTrue(Notification.objects.filter(user=self.second.user,request=self.req).exists())
        self.req.assigned_to=None;self.req.status='ASSIGNED';self.req.save()
        self.call(admin_ops.assign_request,data={'member_id':self.member.pk},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.assigned_to_id,self.member.pk)
        self.second.available=False;self.second.save()
        self.call(admin_ops.assign_request,data={'member_id':self.second.pk,'reason':'Unavailable'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.assigned_to_id,self.member.pk)

    def test_document_downloads_refuse_wrong_channel_or_outsider(self):
        with self.assertRaises(Http404):self.call(admin_ops.platform_note_view,method='get',pk=self.req.pk)
        self.req.channel='IBTIKAR';self.req.save()
        with self.assertRaises(Http404):self.call(admin_ops.download_quote,method='get',pk=self.req.pk)
        self.assertEqual(self.call(admin_ops.platform_note_view,'MEMBER',method='get',pk=self.req.pk).status_code,403)
        self.req.channel='GENOCLAB';self.req.save()
        with self.assertRaises(Http404):self.call(admin_ops.download_quote,method='get',pk=self.req.pk)
        self.req.status='QUOTE_SENT';self.req.quote_detail={'items':[{}]};self.req.save()
        self.assertEqual(self.call(admin_ops.download_quote,'MEMBER',method='get',pk=self.req.pk).status_code,403)
        inv=Invoice.objects.create(request=self.req,client=self.users['CLIENT'],invoice_number='HTTP-INV')
        self.assertEqual(self.call(admin_ops.download_invoice,'MEMBER',method='get',pk=inv.pk).status_code,403)

    def test_gift_upload_and_invoice_cancellation(self):
        buf=io.BytesIO();Image.new('RGB',(2,2)).save(buf,format='PNG')
        image=SimpleUploadedFile('gift.png',buf.getvalue(),content_type='image/png')
        self.assertEqual(self.call(admin_ops.upload_gift,data={'gift_image':image},member_pk=self.member.pk).status_code,302)
        self.member.refresh_from_db();self.assertTrue(self.member.gift_unlocked)
        inv=Invoice.objects.create(request=self.req,invoice_number='HTTP-CANCEL')
        self.assertEqual(self.call(admin_ops.cancel_invoice,method='get',pk=inv.pk).status_code,405)
        self.assertEqual(self.call(admin_ops.cancel_invoice,'CLIENT',pk=inv.pk).status_code,403)
        self.call(admin_ops.cancel_invoice,data={'reason':'x'},pk=inv.pk)
        inv.refresh_from_db();self.assertIsNone(inv.cancelled_at)
        self.call(admin_ops.cancel_invoice,data={'reason':'Duplicate invoice'},pk=inv.pk)
        inv.refresh_from_db();self.assertIsNotNone(inv.cancelled_at)

    def test_quote_and_invoice_invalid_lines_never_create_invoice(self):
        self.req.status='QUOTE_DRAFT';self.req.save()
        valid={'item_label_0':'Analysis','item_unit_price_0':'100','item_quantity_0':'1','vat_rate':'19'}
        for invalid in ({'item_quantity_0':'abc'},{'item_quantity_0':'0'},{'item_label_0':''},{'vat_rate':'101'}):
            self.call(admin_ops.prepare_quote,data={**valid,**invalid},pk=self.req.pk)
            self.req.refresh_from_db();self.assertFalse(self.req.quote_detail)
        self.req.status='ORDER_UPLOADED';self.req.save()
        for items in ([],[{'label':''}],[{'label':'Analysis','unit_price':100,'quantity':'bad'}],[{'label':'Analysis','unit_price':100,'quantity':0}]):
            self.req.quote_detail={'items':items};self.req.save()
            self.call(admin_ops.generate_invoice,pk=self.req.pk)
            self.assertFalse(Invoice.objects.filter(request=self.req).exists())
        self.assertEqual(self.call(admin_ops.generate_invoice,method='get',pk=self.req.pk).status_code,302)
        self.req.status='PAYMENT_PROOF_UPLOADED';self.req.save()
        self.call(admin_ops.confirm_payment,data={'verification_note':'Checked'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertIsNone(self.req.payment_verified_at)

    def test_internal_estimate_failure_is_not_shown_as_zero(self):
        self.assertIsNone(admin_ops._compute_auto_estimate(self.req,None))
        self.req.service=Service.objects.create(code='NOQUOTE',name='No quote')
        with patch('core.pricing.resolve_cost',side_effect=RuntimeError):
            self.assertIsNone(admin_ops._compute_auto_estimate(self.req,None))

    @staticmethod
    def pdf():
        return SimpleUploadedFile('proof.pdf',b'%PDF-1.4\n%%EOF',content_type='application/pdf')

    def test_business_uploads_are_atomic_and_respect_status(self):
        for fn,field,start,end in [(client.upload_order,'order_file','QUOTE_VALIDATED_BY_CLIENT','ORDER_UPLOADED'),
                                    (client.upload_payment_receipt,'payment_receipt_file','PAYMENT_PENDING','PAYMENT_PROOF_UPLOADED')]:
            self.req.status='REQUEST_CREATED';self.req.save()
            self.call(fn,'CLIENT',data={field:self.pdf()},pk=self.req.pk)
            self.req.refresh_from_db();self.assertFalse(getattr(self.req,field))
            self.req.status=start;self.req.save()
            with patch('dashboard.views.client.transition',side_effect=InvalidTransitionError('changed concurrently')):
                self.call(fn,'CLIENT',data={field:self.pdf()},pk=self.req.pk)
            self.req.refresh_from_db();self.assertFalse(getattr(self.req,field));self.assertEqual(self.req.status,start)
            self.call(fn,'CLIENT',data={field:self.pdf()},pk=self.req.pk)
            self.req.refresh_from_db();self.assertTrue(getattr(self.req,field));self.assertEqual(self.req.status,end)

    def test_analyst_cannot_modify_or_view_unassigned_request(self):
        for fn in (analyst.accept_task,analyst.decline_task,analyst.workflow_action,analyst.suggest_appointment,
                   analyst.accept_alt_date,analyst.decline_alt_date,analyst.upload_report,analyst.request_detail):
            self.assertEqual(self.call(fn,'MEMBER',pk=self.req.pk).status_code,403)
        self.assertEqual(self.call(analyst.collect_gift,'MEMBER',method='get').status_code,403)
        self.req.assigned_to=self.member;self.req.save()
        self.call(analyst.accept_alt_date,'MEMBER',pk=self.req.pk)
        self.req.refresh_from_db();self.assertIsNone(self.req.appointment_date)
        self.call(analyst.upload_report,'MEMBER',data={'report_file':self.pdf()},pk=self.req.pk)
        self.req.refresh_from_db();self.assertFalse(self.req.report_file)

    def test_analyst_workflow_and_report_upload_rollbacks(self):
        self.req.assigned_to=self.member;self.req.status='ANALYSIS_STARTED';self.req.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.call(analyst.workflow_action,'MEMBER',data={'to_status':'ANALYSIS_FINISHED'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'ANALYSIS_FINISHED')
        self.req.status='ANALYSIS_STARTED';self.req.save()
        Invoice.objects.create(request=self.req,client=self.users['CLIENT'],invoice_number='ANALYST-INV',total_ttc=119)
        self.call(analyst.workflow_action,'MEMBER',data={'to_status':'ANALYSIS_FINISHED'},pk=self.req.pk)
        self.call(analyst.workflow_action,'MEMBER',data={'to_status':'INVALID'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'ANALYSIS_FINISHED')
        from django.utils import timezone
        self.req.status='PAYMENT_CONFIRMED';self.req.payment_verified_at=timezone.now();self.req.save()
        with patch('dashboard.views.analyst.transition',side_effect=InvalidTransitionError('Concurrent change')):
            self.call(analyst.upload_report,'MEMBER',data={'report_file':self.pdf()},pk=self.req.pk)
        self.req.refresh_from_db();self.assertFalse(self.req.report_file)
        self.call(analyst.upload_report,'MEMBER',data={'report_file':self.pdf()},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'REPORT_UPLOADED');self.assertTrue(self.req.report_file)

    def test_archived_reports_receive_tokens_and_yaml_labels_are_displayed(self):
        service=Service.objects.create(code='LEGACYVIEW',name='Legacy')
        definition={'parameters':[{'name':'mode','label':'Mode label'}], 'sample_table':{'columns':[{'name':'sample','label':'Sample label'}]}}
        for module,role,channel in [(client,'CLIENT','GENOCLAB'),(requester,'REQUESTER','IBTIKAR')]:
            self.req.channel=channel;self.req.requester=self.users[role];self.req.status='COMPLETED'
            self.req.report_file='reports/legacy.pdf';self.req.report_token=None;self.req.service=service
            self.req.service_params={'mode':'test'};self.req.sample_table=[{'sample':'A'}];self.req.save()
            self.assertEqual(self.call(module.index,role,method='get').status_code,200)
            self.req.refresh_from_db();self.assertIsNotNone(self.req.report_token)
            with patch('core.registry.get_service_def',return_value=definition):
                response=self.call(module.request_detail,role,method='get',pk=self.req.pk)
            self.assertEqual(response.status_code,200)
            self.assertIn(b'Mode label',response.content)
        self.assertEqual(self.call(client.index,'REQUESTER',method='get').status_code,403)

    def test_submission_requires_valid_tariff_and_declared_sufficient_budget(self):
        from core.exceptions import PricingConfigurationError
        service=Service.objects.create(code='BADRATE',name='Bad rate',ibtikar_price=100,genoclab_price=100)
        for module,role in [(client,'CLIENT'),(requester,'REQUESTER')]:
            self.assertEqual(self.call(module.create_request,role,method='get').status_code,403)
            user=self.users[role];user.ibtikar_declared_balance=100
            with patch('core.pricing.resolve_cost',side_effect=PricingConfigurationError('invalid')):
                self.assertEqual(self.call(module.create_request,role,data={'service_id':service.pk}).status_code,302)
        self.users['REQUESTER'].ibtikar_declared_balance=None
        self.call(requester.create_request,'REQUESTER',data={'service_id':service.pk})
        self.users['REQUESTER'].ibtikar_declared_balance=1
        self.call(requester.create_request,'REQUESTER',data={'service_id':service.pk})
        self.assertEqual(Request.objects.count(),1)
        self.assertEqual(self.call(requester.declare_ibtikar_balance,'REQUESTER',method='get').status_code,403)

    def test_transition_errors_are_reported_without_advancing_state(self):
        for fn in (client.accept_quote,client.reject_quote):
            with patch('dashboard.views.client.transition',side_effect=InvalidTransitionError('Already changed')):
                self.call(fn,'CLIENT',pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'DRAFT')
        self.req.assigned_to=self.member;self.req.status='ASSIGNED';self.req.save()
        with patch('dashboard.views.analyst.transition',side_effect=InvalidTransitionError('Concurrent change')):
            self.call(analyst.accept_task,'MEMBER',pk=self.req.pk)
            self.call(analyst.suggest_appointment,'MEMBER',data={'appointment_date':'2026-12-01'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'ASSIGNED')
        for module,role,status in [(client,'CLIENT','SENT_TO_CLIENT'),(requester,'REQUESTER','SENT_TO_REQUESTER')]:
            self.req.requester=self.users[role];self.req.status=status;self.req.save()
            target='dashboard.views.client.transition' if role=='CLIENT' else 'core.workflow.transition'
            with patch(target,side_effect=InvalidTransitionError('Changed')):
                self.call(module.confirm_receipt,role,pk=self.req.pk)
            self.req.refresh_from_db();self.assertEqual(self.req.status,status)
        self.req.channel='IBTIKAR';self.req.status='IBTIKAR_SUBMISSION_PENDING';self.req.save()
        with patch('core.workflow.transition',side_effect=InvalidTransitionError('Changed')):
            self.call(requester.submit_ibtikar_code,'REQUESTER',data={'ibtikar_code':'NATIONAL123'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.ibtikar_external_code,'NATIONAL123')

    def test_superadmin_commands_reject_get(self):
        for name in ('service_create','technique_create','content_update','announcement_create','content_save',
                     'content_delete_key','backup_now','create_user','add_payment_method','reset_revenue','upload_template'):
            self.assertEqual(self.call(getattr(superadmin,name),'SUPER_ADMIN',method='get').status_code,403)
        for name in ('technique_edit','force_transition_view','budget_override_view'):
            self.assertEqual(self.call(getattr(superadmin,name),'SUPER_ADMIN',method='get',pk=self.req.pk).status_code,403)

    def test_user_validation_rejects_duplicates_and_weak_passwords(self):
        base={'username':'new-contract','email':'new@example.test','role':'CLIENT','password':'A-long-independent#2026!'}
        existing=self.users['CLIENT'];existing.email='used@example.test';existing.save()
        before=User.objects.count()
        for bad in ({'username':''},{'role':'INVALID'},{'username':existing.username},{'email':existing.email},{'password':'123'}):
            self.call(superadmin.create_user,'SUPER_ADMIN',data={**base,**bad})
            self.assertEqual(User.objects.count(),before)
        target=self.users['REQUESTER']
        for bad in ({'role':'INVALID'},{'email':existing.email},{'new_password':'123'}):
            self.call(superadmin.user_edit,'SUPER_ADMIN',data=bad,pk=target.pk)
            target.refresh_from_db();self.assertEqual(target.role,'REQUESTER')
        self.call(superadmin.user_edit,'SUPER_ADMIN',data={'new_password':base['password']},pk=target.pk)
        target.refresh_from_db();self.assertTrue(target.check_password(base['password']))
        self.assertEqual(self.call(superadmin.reset_account,'SUPER_ADMIN',method='get',pk=target.pk).status_code,200)
        self.assertEqual(self.call(superadmin.reset_account,'SUPER_ADMIN',pk=self.users['SUPER_ADMIN'].pk).status_code,302)
        target.email='reset@example.test';target.save();old=target.password
        with patch('django.core.mail.send_mail',return_value=0):
            self.call(superadmin.reset_account,'SUPER_ADMIN',pk=target.pk)
        target.refresh_from_db();self.assertEqual(target.password,old)

    def test_service_invalid_forms_are_atomic_and_helpers_handle_legacy_values(self):
        service=Service.objects.create(code='EDIT-COMP',name='Original')
        for bad in ({'turnaround_days':'-1'},{'field_name':['repeat','repeat']},
                    {'field_option_pricing':['[]']},{'channel_availability':'INVALID'},
                    {'image':SimpleUploadedFile('fake.png',b'bad')},{'name':''}):
            self.call(superadmin.service_edit,'SUPER_ADMIN',data=bad,pk=service.pk)
            service.refresh_from_db();self.assertEqual(service.name,'Original')
        self.call(superadmin.service_create,'SUPER_ADMIN',data={'code':'BADIMAGE','image':SimpleUploadedFile('fake.png',b'bad')})
        self.assertFalse(Service.objects.filter(code='BADIMAGE').exists())
        self.assertIsNone(superadmin._to_decimal_or_none(' '));self.assertIsNone(superadmin._to_decimal_or_none('bad'))
        self.assertEqual(superadmin._guess_multiplier_param([{'name':'mode','options':['full']}],{'full':2}),'mode')
        self.assertEqual(superadmin._guess_multiplier_param([{'name':'mode','options':['other']}],{'full':2}),'')
        with patch('core.registry.get_service_def',side_effect=RuntimeError):
            self.assertEqual(self.call(superadmin.service_edit,'SUPER_ADMIN',method='get',pk=service.pk).status_code,200)
        from core.models import PlatformContent
        PlatformContent.objects.create(key='multi',lang='fr',value='FR')
        PlatformContent.objects.create(key='multi',lang='en',value='EN')
        with patch('core.registry.load_service_registry',side_effect=RuntimeError):
            self.assertEqual(self.call(superadmin.index,'SUPER_ADMIN',method='get').status_code,200)

    def test_template_replace_preserves_backup_and_downloads_exact_bytes(self):
        from pathlib import Path
        from docx import Document
        buf=io.BytesIO();doc=Document();doc.add_paragraph('Contract');doc.save(buf)
        root=Path(self.tmp.name);dest=root/'documents'/'docx_templates';dest.mkdir(parents=True)
        kind='quote_template';path=dest/(kind+'.docx');path.write_bytes(b'old-template')
        with override_settings(BASE_DIR=root):
            for type_,blob in [('invalid',buf.getvalue()),(kind,b'bad')]:
                self.call(superadmin.upload_template,'SUPER_ADMIN',data={'template_type':type_,'template_file':SimpleUploadedFile('template.docx',blob,content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
                self.assertEqual(path.read_bytes(),b'old-template')
            self.call(superadmin.upload_template,'SUPER_ADMIN',data={'template_type':kind,'template_file':SimpleUploadedFile('template.docx',buf.getvalue(),content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
            self.assertEqual(path.read_bytes(),buf.getvalue())
            self.assertEqual(path.with_suffix('.backup.docx').read_bytes(),b'old-template')
            response=self.call(superadmin.download_template,'SUPER_ADMIN',method='get',template_type=kind)
            try:self.assertEqual(b''.join(response.streaming_content),buf.getvalue())
            finally:response.close()
            for type_ in ('invalid','reception_form_template'):
                self.assertEqual(self.call(superadmin.download_template,'SUPER_ADMIN',method='get',template_type=type_).status_code,302)

    def test_opt_in_restore_cleans_staging_files_on_success_and_failure(self):
        from pathlib import Path
        root=Path(self.tmp.name)
        with override_settings(ALLOW_WEB_DATABASE_RESTORE=True,BASE_DIR=root):
            self.assertEqual(self.call(superadmin.restore_db,'SUPER_ADMIN',method='get').status_code,302)
            for error in (ValueError('invalid'),RuntimeError('unavailable'),None):
                with patch('core.db_backup.perform_restore',side_effect=error) as restore:
                    self.call(superadmin.restore_db,'SUPER_ADMIN',data={'db_file':SimpleUploadedFile('backup.sqlite3',b'example')})
                    restore.assert_called_once()
                    self.assertFalse(restore.call_args.args[0].exists())

    def test_forced_transitions_budget_override_and_financial_archiving(self):
        self.req.channel='IBTIKAR';self.req.budget_amount=10;self.req.save()
        self.call(superadmin.force_transition_view,'SUPER_ADMIN',data={'to_status':'INVALID','justification':'Documented reason'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'DRAFT')
        self.call(superadmin.force_transition_view,'SUPER_ADMIN',data={'to_status':'REJECTED','justification':'Documented reason'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'REJECTED')
        self.call(superadmin.budget_override_view,'SUPER_ADMIN',data={'justification':'Verified exceptional budget approval'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.budget_amount,10)
        self.call(superadmin.reset_revenue,'SUPER_ADMIN')
        from core.models import PlatformContent
        self.assertTrue(PlatformContent.objects.filter(key='revenue_reset_date').exists())
        self.req.submitted_as_guest=True;self.req.guest_email='guest-contract@example.test';self.req.save()
        response=self.call(superadmin.export_emails,'SUPER_ADMIN',method='get')
        self.assertIn(b'guest-contract@example.test',response.content)

    def test_report_tokens_citation_gate_and_missing_storage(self):
        import uuid
        from dashboard.views import report
        from notifications.models import Notification
        missing=uuid.uuid4()
        for fn in (report.report_viewer,report.download_report):
            with self.assertRaises(Http404):self.call(fn,'CLIENT',method='get',token=missing)
        self.assertEqual(self.call(report.mark_report_delivered,'CLIENT',token=missing).status_code,404)
        self.assertEqual(self.call(report.acknowledge_citation,'CLIENT',token=missing).status_code,404)
        with self.assertRaises(Http404):self.call(report.rate_report,'CLIENT',data={'rating':5},token=missing)
        self.req.report_token=uuid.uuid4();self.req.channel='IBTIKAR';self.req.save()
        with self.assertRaises(Http404):self.call(report.download_report,'CLIENT',method='get',token=self.req.report_token)
        self.req.report_file='reports/absent.pdf';self.req.assigned_to=self.member;self.req.save()
        self.assertEqual(self.call(report.download_report,'CLIENT',method='get',token=self.req.report_token).status_code,302)
        self.assertEqual(self.call(report.protected_report_media,'CLIENT',method='get',path='absent.pdf').status_code,302)
        for fn,kwargs in ((report.serve_media,{'path':'reports/absent.pdf'}),
                          (report.protected_report_media,{'path':'nonexistent.pdf'}),
                          (report.protected_report_media,{'path':'absent.pdf'})):
            with self.assertRaises(Http404):self.call(fn,'PLATFORM_ADMIN',method='get',**kwargs)
        for method,data in [('get',{}),('post',{'rating':0})]:
            self.assertEqual(self.call(report.rate_report,'CLIENT',method=method,data=data,token=self.req.report_token).status_code,302)
        self.assertEqual(self.call(report.acknowledge_citation,'CLIENT',token=self.req.report_token).status_code,200)
        self.req.refresh_from_db();self.assertTrue(self.req.citation_acknowledged)
        report._notify_report_consulted(self.req)
        self.assertTrue(Notification.objects.filter(user=self.member.user,request=self.req).exists())
        with patch.object(Notification.objects,'create',side_effect=RuntimeError):
            with self.assertLogs(report.logger,level='ERROR'):report._notify_report_consulted(self.req)

    def test_finance_rejections_and_closed_payment_guards(self):
        from dashboard.views import finance
        self.assertEqual(self.call(finance.validate_budget,'FINANCE',method='get',pk=self.req.pk).status_code,403)
        self.assertEqual(self.call(finance.update_payment_status,'FINANCE',method='get',pk=self.req.pk).status_code,403)
        self.req.channel='IBTIKAR';self.req.status='VALIDATION_FINANCE';self.req.save()
        self.call(finance.validate_budget,'FINANCE',data={'action':'reject','reason':'Not approved'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'REJECTED')
        inv=Invoice.objects.create(request=self.req,invoice_number='PAID-COMP',payment_status='COMPLETED')
        self.call(finance.update_payment_status,'FINANCE',data={'payment_status':'INVALID'},pk=inv.pk)
        self.call(finance.update_payment_status,'FINANCE',data={'payment_status':'PENDING','verification_note':'Checked'},pk=inv.pk)
        inv.refresh_from_db();self.assertEqual(inv.payment_status,'COMPLETED')

    def test_messaging_without_recipients_and_analyst_fallback(self):
        from dashboard.views.messaging import send_message
        from core.models import Message
        self.req.requester=None;self.req.save()
        self.call(send_message,pk=self.req.pk,data={'message_text':'Where is the recipient?'})
        self.assertFalse(Message.objects.exists())
        self.req.assigned_to=self.member;self.req.save()
        self.call(send_message,'MEMBER',pk=self.req.pk,data={'message_text':'Please review'})
        self.assertEqual(Message.objects.count(),1)
        self.req.assigned_to=None;self.req.requester=self.users['CLIENT'];self.req.save()
        User.objects.filter(role__in=['SUPER_ADMIN','PLATFORM_ADMIN']).update(is_active=False)
        self.call(send_message,'CLIENT',pk=self.req.pk,data={'message_text':'No administrator'})
        self.assertEqual(Message.objects.count(),1)

    def test_document_download_permissions_cache_and_converter_recovery(self):
        from documents import views as dv
        from documents.models import ServiceTemplate,DocumentBlock
        from core.models import ServiceFormField
        from pathlib import Path
        from uuid import uuid4
        self.req.assigned_to=self.member;self.req.save()
        self.assertTrue(dv._can_download_request_doc(self.users['MEMBER'],self.req))
        self.assertFalse(dv._can_download_request_doc(self.users['MEMBER'],self.req,admin_only=True))
        self.assertFalse(dv._can_download_request_doc(self.users['REQUESTER'],self.req))
        with self.assertRaises(Http404):dv._serve_file(Path(self.tmp.name)/'absent','absent.docx')
        path=Path(self.tmp.name)/'contract.pdf';path.write_bytes(b'%PDF-1.4\ncontract')
        response=dv._serve_docx(path,'contract.pdf');self.assertEqual(response['Content-Type'],'application/pdf');response.close()
        service=Service.objects.create(code='CACHE-COMP',name='Cache');self.req.service=service;self.req.save()
        ServiceFormField.objects.create(service=service,name='sample',label='Sample')
        self.assertNotEqual(dv._service_fields_signature(self.req),'0')
        with patch.object(ServiceFormField.objects,'filter',side_effect=RuntimeError):self.assertEqual(dv._service_fields_signature(self.req),'0')
        for fn in (dv.ibtikar_form_view,dv.reception_form_view,dv.quote_view):
            self.assertEqual(self.call(fn,'REQUESTER',method='get',request_id=self.req.pk).status_code,403)
        for suffix in ('.pdf','.docx'):
            source=Path(self.tmp.name)/'source.docx';source.write_bytes(b'contract')
            rendered=source.with_suffix(suffix);rendered.write_bytes(b'contract')
            with override_settings(DOCUMENT_PDF_ENABLED=True),patch.object(dv,'convert_docx_to_pdf',return_value=rendered):
                response=dv._cached_serve_doc(self.req,'TEST'+suffix,lambda req:source,'contract')
                self.assertTrue(response['Content-Disposition'].endswith(suffix+'"'));response.close()
                self.assertFalse(source.exists())
        for generator in (lambda req:Path(self.tmp.name)/'absent',lambda req:1/0):
            with self.assertRaises(Http404):dv._cached_serve_doc(self.req,'ERROR',generator,'contract')
        source=Path(self.tmp.name)/'unclean.docx';source.write_bytes(b'contract')
        with override_settings(DOCUMENT_PDF_ENABLED=False),patch.object(Path,'unlink',side_effect=OSError):
            response=dv._cached_serve_doc(self.req,'UNCLEAN',lambda req:source,'contract');response.close()
        with override_settings(DOCUMENT_PDF_ENABLED=False):
            for fn in (dv.ibtikar_form_view,dv.reception_form_view,dv.platform_note_view):
                response=self.call(fn,method='get',request_id=self.req.pk);self.assertEqual(response.status_code,200);response.close()
        ServiceTemplate.objects.create(service=service,template_type='QUOTE',name='Active')
        for active in ('0','1'):
            response=self.call(dv.template_list,method='get',data={'type':'QUOTE','service':service.pk,'active':active})
            self.assertEqual(response.status_code,200)
        block=DocumentBlock.objects.create(template_type='QUOTE',position='TOP',language='fr',body='Original')
        data={'template_type':'QUOTE','position':'TOP','language':'fr','body':'Updated','services':[str(uuid4())]}
        response=self.call(dv.block_edit,data=data,pk=block.pk);self.assertEqual(response.status_code,200)
        block.refresh_from_db();self.assertEqual(block.body,'Original')

    def test_authentication_registration_and_existing_two_factor_settings(self):
        from accounts import views as av
        from accounts.forms import RegistrationForm
        from django.contrib.sessions.backends.db import SessionStore
        from django.contrib.auth.models import AnonymousUser
        req=self.factory.post('/accounts/register/');req.session=SessionStore();req.user=AnonymousUser()
        form=RegistrationForm(data={'organization':'University of Oran','organization_type':User.ORGANIZATION_TYPE_CHOICES[0][0],'country':'DZ','username':'new-complete-user','email':'new@example.test','first_name':'New','last_name':'User','role':'REQUESTER','password1':'DifferentPass!2026','password2':'DifferentPass!2026'})
        self.assertTrue(form.is_valid(),form.errors)
        view=av.RegisterView();view.setup(req)
        self.assertEqual(view.form_valid(form).status_code,302)
        self.assertEqual(req.session['_auth_user_id'],str(User.objects.get(username='new-complete-user').pk))
        req=self.factory.get('/accounts/2fa/');req.session={'pending_2fa_user':999999};req.user=AnonymousUser()
        self.assertEqual(av.two_factor_verify(req).status_code,302);self.assertNotIn('pending_2fa_user',req.session)
        self.users['CLIENT'].totp_enabled=True;self.users['CLIENT'].save()
        self.assertEqual(self.call(av.two_factor_setup,'CLIENT',method='get').status_code,302)

    def test_operational_error_feedback_and_redundant_observers(self):
        self.call(admin_ops.transition_request,data={'to_status':'INVALID'},pk=self.req.pk)
        self.req.assigned_to=self.member;self.req.status='ASSIGNED';self.req.save()
        self.call(admin_ops.assign_request,data={'member_id':self.member.pk},pk=self.req.pk)
        self.call(admin_ops.manage_observers,data={'action':'add','member_id':self.member.pk},pk=self.req.pk)
        self.call(admin_ops.manage_observers,data={'action':'remove','member_id':self.second.pk},pk=self.req.pk)
        self.assertEqual(self.req.informed_members.count(),0)
        self.req.appointment_confirmed=True;self.req.save()
        self.call(admin_ops.modify_appointment,data={'appointment_date':'2026-12-01'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertIsNone(self.req.appointment_date)
        self.assertEqual(self.call(admin_ops.adjust_cost,data={'admin_price':'100','cost_justification':'Correction documentée'},pk=self.req.pk).status_code,403)
        with patch.object(admin_ops,'transition',side_effect=InvalidTransitionError('rejected')):
            for action in ('validate','send_back'):
                self.call(admin_ops.report_review,data={'action':action},pk=self.req.pk)
            self.req.status='INVOICE_GENERATED';self.req.assigned_to=None;self.req.save()
            self.call(admin_ops.assign_request,data={'member_id':self.member.pk},pk=self.req.pk)
            for status,action in [('REQUEST_CREATED','save'),('QUOTE_DRAFT','send')]:
                self.req.status=status;self.req.save()
                self.call(admin_ops.prepare_quote,data={'action':action,'item_label_0':'Analysis','item_quantity_0':'1','item_unit_price_0':'100','vat_rate':'0'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'QUOTE_DRAFT')

    def test_analyst_profile_recovery_and_alternative_date_transition_failure(self):
        from django.utils import timezone
        self.member.delete();self.users['MEMBER']=User.objects.get(pk=self.users['MEMBER'].pk)
        response=self.call(analyst.index,'MEMBER',method='get');self.assertEqual(response.status_code,200)
        member=MemberProfile.objects.get(user=self.users['MEMBER'])
        self.req.assigned_to=member;self.req.status='APPOINTMENT_PROPOSED';self.req.alt_date_proposed=timezone.now();self.req.save()
        with patch.object(analyst,'transition',side_effect=InvalidTransitionError('racing transition')):
            self.call(analyst.accept_alt_date,'MEMBER',pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'APPOINTMENT_PROPOSED')
        # A profile may disappear from a leaderboard snapshot during refresh.
        with patch.object(MemberProfile.objects,'order_by') as ordered:
            ordered.return_value.values_list.return_value=[]
            self.assertEqual(self.call(analyst.index,'MEMBER',method='get').status_code,200)
        self.req.channel='IBTIKAR';self.req.status='SAMPLE_RECEIVED';self.req.save()
        self.call(analyst.workflow_action,'MEMBER',data={'to_status':'ANALYSIS_STARTED'},pk=self.req.pk)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'ANALYSIS_STARTED')

    def test_form_metadata_database_failures_and_pdf_statistics(self):
        from dashboard.views import service_form_api as api,stats
        from pathlib import Path
        definition={'code':'FORM-COMP','name':'Form','parameters':[{'name':'free'},{'name':'mode','options':['basic']}],'pricing':{'multipliers':{'basic':1},'base_price':{'default':10}}}
        with patch.object(api,'get_service_def',return_value=definition),patch.object(Service.objects,'filter',side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.call(api.service_form_fragment,method='get',service_code='FORM-COMP').status_code,200)
        pdf=Path(self.tmp.name)/'summary.pdf';pdf.write_bytes(b'%PDF-1.4\nsummary')
        with override_settings(DOCUMENT_PDF_ENABLED=True),patch('documents.pdf_converter.convert_docx_to_pdf',return_value=pdf):
            response=self.call(stats.stats_export,method='get',data={'format':'docx','date_to':'2026-12-31'})
            self.assertEqual(response['Content-Type'],'application/pdf');response.close()
        from accounts import views as av
        from django.core.signing import TimestampSigner
        token=TimestampSigner(salt=av._GUEST_TOKEN_SALT).sign('no-account@example.test')
        self.assertEqual(self.call(av.convert_guest_verify,'CLIENT',method='get',token=token).status_code,200)

    def test_guest_submission_input_caps_and_preference_storage_failure(self):
        from dashboard import views_public as public
        service=Service.objects.create(code='GUEST-LIMIT',name='Guest',genoclab_price=10)
        data={'channel':'GENOCLAB','service_id':str(service.pk),'guest_name':'Guest','guest_email':'guest-limit@example.test','title':'Contract','organization':'University','organization_type':'autre','organization_type_other':'Institute','country':'DZ'}
        data.update({f'param_{i}':'x' for i in range(201)})
        data.update({f'sample_{i}_name':'S' for i in range(201)})
        data.update({f'sample_0_col{i}':'x' for i in range(51)})
        response=self.call(public.guest_submit,'CLIENT',data=data)
        self.assertEqual(response.status_code,200)
        guest=Request.objects.get(guest_email='guest-limit@example.test')
        self.assertEqual(len(guest.service_params),200);self.assertEqual(len(guest.sample_table),200)
        self.assertTrue(all(len(row)<=50 for row in guest.sample_table))
        with patch.object(User,'save',side_effect=RuntimeError('storage unavailable')):
            self.assertEqual(self.call(public.switch_language,'CLIENT',data={'language':'en'}).status_code,302)

    def test_blank_service_configuration_and_cms_latest_translation(self):
        from core.models import PlatformContent
        from django.utils import timezone
        from datetime import timedelta
        service=Service.objects.create(code='BLANK-CONFIG',name='Blank')
        self.call(superadmin.service_edit,'SUPER_ADMIN',data={'field_name':['detail'],**{f'field_label_{lang}':['Detail'] for lang in ('fr','ar','en')},'pd_mult_key':['empty'],'pd_mult_factor':[' ']} ,pk=service.pk)
        self.assertEqual(service.custom_fields.get().option_pricing,{})
        older=PlatformContent.objects.create(key='latest-translation',lang='ar',value='قديم')
        newer=PlatformContent.objects.create(key='latest-translation',lang='fr',value='Récent')
        PlatformContent.objects.filter(pk=older.pk).update(updated_at=timezone.now()-timedelta(days=1))
        self.assertEqual(self.call(superadmin.index,'SUPER_ADMIN',method='get').status_code,200)

    def test_model_validation_and_private_quote_download(self):
        from documents import views as dv
        from dashboard.views.qrcode_view import report_qr
        service=Service.objects.create(code='INVALID-MODEL',name='Original')
        self.call(superadmin.service_edit,'SUPER_ADMIN',data={'ibtikar_price':'99999999999999999999999999999'},pk=service.pk)
        service.refresh_from_db();self.assertEqual(service.name,'Original')
        self.assertEqual(self.call(dv.quote_view,'CLIENT',method='get',request_id=self.req.pk).status_code,403)
        with self.assertRaises(Http404):self.call(report_qr,'REQUESTER',method='get',pk=self.req.pk)

        self.assertEqual(self.call(dv.platform_note_view,'CLIENT',method='get',request_id=self.req.pk).status_code,403)
        self.member.delete();self.users['MEMBER']=User.objects.get(pk=self.users['MEMBER'].pk)
        with self.assertRaises(Http404):self.call(report_qr,'MEMBER',method='get',pk=self.req.pk)
