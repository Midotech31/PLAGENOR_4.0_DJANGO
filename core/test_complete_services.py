"""Contracts for administrative boundaries and infrastructure failure paths."""
import sys
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.test import TestCase, RequestFactory, override_settings

from accounts.models import User, Technique, MemberProfile
from core.models import (Service, ServiceFormField, ServicePricing, Request, Invoice,
                         PlatformContent, FinancialVisibility, IssuedDocument, Announcement,
                         PaymentMethod, Message, SequenceCounter, RevenueArchive)


class CompleteServiceContracts(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('complete-owner', role='CLIENT', first_name='Test')
        self.ops = User.objects.create_user('complete-ops', role='PLATFORM_ADMIN')
        self.req = Request.objects.create(display_id='COMP-1', requester=self.user, channel='GENOCLAB')
        self.service = Service.objects.create(code='COMP', name='Assay')

    def test_identity_role_and_form_labels(self):
        with self.assertRaises(ValueError): User.objects.create_user('')
        for flag in ('is_staff','is_superuser'):
            with self.assertRaises(ValueError): User.objects.create_superuser('bad', **{flag:False})
        for role, prop in [('SUPER_ADMIN','is_superadmin'),('MEMBER','is_analyst'),('FINANCE','is_finance')]:
            self.user.role=role; self.assertTrue(getattr(self.user,prop))
            self.user.role='CLIENT'; self.assertFalse(getattr(self.user,prop))
        mp=MemberProfile(user=self.user,max_load=0)
        self.assertEqual(mp.load_percentage,0)
        self.assertIn('Test',str(mp))
        expected=[(Technique(name='PCR'),'PCR'),(self.service,'COMP'),
                  (ServiceFormField(service=self.service,label='Samples'),'Samples'),
                  (ServicePricing(service=self.service,name='Rate',amount=10),'Rate'),
                  (self.req,'COMP-1'),(Invoice(invoice_number='INV-1'),'INV-1'),
                  (PlatformContent(key='name',lang='fr'),'name [fr]'),
                  (Announcement(title='Hello',audience='ALL'),'Hello'),
                  (PaymentMethod(name='Transfer'),'Transfer'),
                  (Message(from_user=self.user,to_user=self.ops,request=self.req),'COMP-1'),
                  (SequenceCounter(scope='INV',value=3),'INV = 3'),
                  (RevenueArchive(channel='OHB',month=1,year=2026,total_revenue=10),'OHB')]
        for obj,label in expected:self.assertIn(label,str(obj))
        self.assertIsNone(ServiceFormField(service=self.service).pricing_info)

    def test_announcement_audiences_fail_closed(self):
        for audience,role,expected in [('STAFF','MEMBER',True),('STAFF','CLIENT',False),
                                       ('CLIENTS','CLIENT',True),('CLIENTS','MEMBER',False),('INVALID','CLIENT',False)]:
            self.user.role=role
            self.assertEqual(Announcement(active=True,audience=audience).visible_to(self.user),expected)

    def test_admin_cannot_mutate_issued_documents_and_visibility_is_singleton(self):
        from core.admin import InvoiceAdmin, IssuedDocumentAdmin, FinancialVisibilityAdmin, PlatformContentAdmin
        from accounts.admin import CustomUserAdmin
        req=RequestFactory().get('/');req.user=self.ops
        for model,klass in ((Invoice,InvoiceAdmin),(IssuedDocument,IssuedDocumentAdmin)):
            ma=klass(model,admin.site)
            self.assertFalse(ma.has_add_permission(req));self.assertFalse(ma.has_delete_permission(req))
            if model is IssuedDocument:self.assertFalse(ma.has_change_permission(req))
        ma=FinancialVisibilityAdmin(FinancialVisibility,admin.site)
        self.assertFalse(ma.has_add_permission(req));self.assertTrue(ma.has_change_permission(req))
        self.assertFalse(ma.has_delete_permission(req))
        req.user=self.user;self.assertFalse(ma.has_change_permission(req))
        req.user.role='SUPER_ADMIN';FinancialVisibility.objects.all().delete()
        self.assertTrue(ma.has_add_permission(req))
        ma.save_model(req,FinancialVisibility(show_estimates=False),None,False)
        self.assertTrue(FinancialVisibility.objects.filter(pk=1).exists())
        self.assertFalse(ma.has_add_permission(req))
        cms=PlatformContentAdmin(PlatformContent,admin.site)
        self.assertEqual(cms.short_value(PlatformContent(value='a'*81)),'a'*80+'...')
        self.assertEqual(cms.short_value(PlatformContent(value='short')),'short')
        self.assertEqual(CustomUserAdmin(User,admin.site).full_name(self.user),'Test')

    def test_invoice_cancellation_permissions_reason_and_idempotency(self):
        from core.commercial import cancel_unpaid_invoice
        inv=Invoice.objects.create(request=self.req,invoice_number='COMP-INV')
        with self.assertRaises(PermissionDenied):cancel_unpaid_invoice(inv.pk,self.user,'Reason')
        with self.assertRaises(ValidationError):cancel_unpaid_invoice(inv.pk,self.ops,'x')
        first=cancel_unpaid_invoice(inv.pk,self.ops,'Duplicate issue')
        again=cancel_unpaid_invoice(inv.pk,self.ops,'Other reason')
        self.assertEqual(first.cancelled_at,again.cancelled_at)
        self.assertEqual(again.cancellation_reason,'Duplicate issue')

    def test_audit_calls_preserve_actor_and_reason(self):
        from core.audit import log_budget_override,log_workflow_transition
        with patch('core.audit.log_action') as log:
            log_workflow_transition(self.req,'DRAFT','SUBMITTED',self.ops)
            self.assertEqual(log.call_args.kwargs['entity_id'],str(self.req.pk))
            log_budget_override(str(self.req.pk),self.ops,100,'Reviewed')
            self.assertEqual(log.call_args.kwargs['action'],'BUDGET_OVERRIDE')

    def test_sequence_creation_race_retries_and_exhaustion(self):
        from core.sequences import next_value
        from core.models import SequenceCounter
        with patch.object(SequenceCounter.objects,'select_for_update') as locked, patch.object(SequenceCounter.objects,'create',side_effect=IntegrityError):
            counter=SimpleNamespace(value=4,save=MagicMock())
            locked.return_value.get.side_effect=[SequenceCounter.DoesNotExist,counter]
            self.assertEqual(next_value('race'),5)
            locked.return_value.get.side_effect=SequenceCounter.DoesNotExist
            with self.assertRaises(RuntimeError):next_value('exhaust')

    def test_rate_limit_race_cache_eviction_and_invalid_ip(self):
        from core.ratelimit import _database_counter,_cache_counter,_client_ip
        from core.models import RateLimitBucket
        with patch.object(RateLimitBucket.objects,'select_for_update') as locked, patch.object(RateLimitBucket.objects,'create',side_effect=IntegrityError):
            locked.return_value.filter.return_value.first.return_value=None
            with self.assertRaises(IntegrityError):_database_counter('race',2,60)
        with patch('core.ratelimit.cache') as cache:
            cache.get.return_value=0;cache.add.return_value=False;cache.incr.side_effect=ValueError
            self.assertEqual(_cache_counter('evicted',2,60),(False,60))
            self.assertEqual(cache.add.call_count,2)
        with override_settings(TRUST_PROXY_HEADERS=True):
            req=RequestFactory().get('/',HTTP_X_FORWARDED_FOR='invalid',REMOTE_ADDR='invalid')
            self.assertEqual(_client_ip(req),'unknown')

    def test_optional_registry_dependency_absence(self):
        from core import registry
        registry._load_registry_from_disk.cache_clear()
        try:
            with patch.dict(sys.modules,{'yaml':None}):
                self.assertEqual(registry.load_service_registry(),{})
                self.assertEqual(registry.get_all_yaml_files(),[])
        finally:registry._load_registry_from_disk.cache_clear()

    def test_negative_legacy_assignment_limit_does_not_divide(self):
        from core.assignment import compute_member_score
        p=SimpleNamespace(max_load=-1,current_load=1,available=True,productivity_score=50)
        self.assertEqual(compute_member_score(p),30.0)

    def test_cms_fallback_and_database_failure(self):
        from core.templatetags import cms
        from django.utils.translation import override
        cms.clear_cms_cache()
        with override_settings(LANGUAGE_CODE='fr'):
            self.assertEqual(cms._normalize_lang(None),'fr')
            self.assertEqual(cms._normalize_lang('zz'),'fr')
            PlatformContent.objects.create(key='complete',lang='fr',value='Bonjour')
            with override('en'):self.assertEqual(cms.cms('complete'),'Bonjour')
            with patch.object(PlatformContent.objects,'filter',side_effect=RuntimeError):
                with self.assertLogs(cms.logger,level='ERROR'):self.assertEqual(cms.cms('failure','Fallback'),'Fallback')
        cms.clear_cms_cache()

    def test_invalid_icon_options_and_numeric_inputs(self):
        from core.templatetags.icons import icon
        from dashboard.utils import safe_int,safe_float
        svg=icon('unknown',size='bad',stroke_width='bad')
        self.assertIn('width:20px',svg)
        self.assertIn('<circle',svg)
        self.assertEqual(safe_int('bad',7),7);self.assertEqual(safe_float(None,1.5),1.5)

    def test_verified_docx_and_image_upload_signatures(self):
        import io,zipfile
        from PIL import Image
        from core.uploads import _validate_signature
        for valid in (True,False):
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:
                z.writestr('[Content_Types].xml','<Types/>')
                if valid:z.writestr('word/document.xml','<document/>')
            if valid:self.assertIsNone(_validate_signature('.docx',buf.getvalue()))
            else:
                with self.assertRaises(ValidationError):_validate_signature('.docx',buf.getvalue())
        buf=io.BytesIO();Image.new('RGB',(2,2)).save(buf,format='PNG')
        self.assertIsNone(_validate_signature('.png',buf.getvalue()))

    def test_guest_notifications_and_missing_analyst(self):
        from notifications import emails,services
        from notifications.models import Notification
        from django.core.exceptions import ObjectDoesNotExist
        from unittest.mock import PropertyMock
        self.req.requester=None;self.req.guest_email='guest@example.test'
        with patch.object(emails,'send_email_notification') as send:
            emails.notify_status_change(self.req,'QUOTE_DRAFT','QUOTE_SENT')
            emails.notify_appointment(self.req);emails.notify_report_delivery(self.req)
            self.assertEqual(send.call_count,3)
            self.assertEqual(send.call_args.args[0],'guest@example.test')
            emails.notify_assignment(self.req,SimpleNamespace(user=SimpleNamespace(email='')))
            self.assertEqual(send.call_count,3)
        self.assertIsNone(services._safe_assigned_user(self.req))
        for error in (ObjectDoesNotExist,RuntimeError):
            profile=MagicMock()
            type(profile).user=PropertyMock(side_effect=error)
            self.assertIsNone(services._safe_assigned_user(SimpleNamespace(assigned_to=profile,pk=1)))
        self.assertFalse(services.notify_payment_request(self.req))
        self.assertEqual(Notification(link_url='/safe/').get_absolute_url(),'/safe/')

    def test_submission_persists_when_notification_dependencies_fail(self):
        from core.services.genoclab import submit_genoclab_request
        from core.services.ibtikar import submit_ibtikar_request
        from notifications.models import Notification
        for submit in (submit_genoclab_request,submit_ibtikar_request):
            with patch.object(Notification.objects,'create',side_effect=RuntimeError),patch('notifications.emails.notify_submission_confirmation',side_effect=RuntimeError):
                req=submit({'title':'Resilient submission'},self.user)
            self.assertTrue(Request.objects.filter(pk=req.pk).exists())
            self.assertEqual(req.history.count(),1)

    def test_middleware_resilience_and_password_change_requirement(self):
        from dashboard.middleware import UpdateLastSeenMiddleware,PreferredLanguageMiddleware,ForcePasswordChangeMiddleware
        from django.http import HttpResponse
        from unittest.mock import PropertyMock
        req=RequestFactory().get('/dashboard/');req.user=self.user
        response=HttpResponse('OK')
        with patch.object(User.objects,'filter',side_effect=RuntimeError):
            self.assertIs(UpdateLastSeenMiddleware(lambda r:response)(req),response)
        user=MagicMock();type(user).preferred_language=PropertyMock(side_effect=RuntimeError)
        req.user=user
        self.assertIs(PreferredLanguageMiddleware(lambda r:response)(req),response)
        req.user=self.user;self.user.must_change_password=True
        self.assertEqual(ForcePasswordChangeMiddleware(lambda r:response)(req).url,'/accounts/force-change-password/')

    def test_stats_filters_legacy_json_and_orphaned_member(self):
        from core import stats,bilan
        from django.utils import timezone
        today=timezone.localdate()
        self.assertEqual(stats._apply_filters(Request.objects.all(),status=self.req.status,date_from=today,date_to=today,client_id=self.user.pk).count(),1)
        self.req.service_params=['legacy'];self.req.save()
        self.assertEqual(stats.breakdown_by_analysis_frame(),[])
        rows=bilan._rows_param('mode')(Request.objects.all())
        self.assertEqual(rows[0]['label'],'—');self.assertEqual(rows[0]['count'],1)
        self.req.channel='IBTIKAR';self.req.budget_amount=12;self.req.save()
        self.assertEqual(bilan._rows_param('mode')(Request.objects.all())[0]['ib'],12)
        for gran in ('quarter','year'):
            self.assertEqual(len(bilan._rows_period(Request.objects.all(),gran)),1)
        qs=MagicMock();qs.annotate.return_value.values.return_value.annotate.return_value.order_by.return_value=[{'p':None,'count':1,'ib':0,'gc':0}]
        self.assertEqual(bilan._rows_period(qs)[0]['label'],'—')
        member=User.objects.create_user('orphaned-member',role='MEMBER')
        MemberProfile.objects.filter(user=member).delete()
        member=User.objects.get(pk=member.pk)
        self.assertEqual(stats.stats_for_user(member)['scope'],'analyst')

    def test_previous_month_revenue_archive_and_relative_qr(self):
        from core.financial import archive_monthly_revenue
        from core.qrcode_utils import generate_report_qr
        with patch('core.financial.datetime') as clock:
            clock.now.return_value=datetime(2026,1,3)
            result=archive_monthly_revenue()
            self.assertTrue(all(x['month']==12 and x['year']==2025 for x in result))
        import uuid
        self.req.report_token=uuid.uuid4()
        with patch('core.qrcode_utils.generate_qr_data_url',return_value='image') as qr:
            self.assertEqual(generate_report_qr(self.req,base_url=''),'image')
            self.assertTrue(qr.call_args.args[0].startswith('/report/'))

    def test_workflow_side_effect_failures_preserve_business_transition(self):
        from core import workflow as wf
        from notifications import emails
        from notifications.models import Notification
        from documents import generators
        from core.exceptions import InvalidTransitionError
        self.req.status='QUOTE_DRAFT';self.req.save()
        with self.assertRaises(InvalidTransitionError):wf.transition(self.req,'QUOTE_SENT',self.ops)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'QUOTE_DRAFT')
        with patch.object(Notification.objects,'create',side_effect=RuntimeError('notification unavailable')):
            with self.assertLogs(wf.logger,level='ERROR'):wf._create_notifications(self.req,'QUOTE_SENT')
        with patch.object(emails,'notify_status_change',side_effect=RuntimeError('SMTP unavailable')):
            with self.assertLogs(wf.logger,level='ERROR'):wf._send_transition_emails(self.req,'DRAFT','REJECTED')
        real=__import__
        with patch.dict(sys.modules,{'notifications.emails':None}),patch('builtins.__import__', wraps=real) as imp:
            def import_without_notifications(name,*args,**kwargs):
                if name=='notifications':raise ImportError('notification package unavailable')
                return real(name,*args,**kwargs)
            imp.side_effect=import_without_notifications
            with self.assertLogs(wf.logger,level='ERROR'):wf._send_transition_emails(self.req,'DRAFT','REJECTED')
        with patch.object(generators,'generate_platform_note',side_effect=RuntimeError('document unavailable')):
            with self.assertLogs(wf.logger,level='ERROR'):wf._auto_generate_documents(self.req,'PLATFORM_NOTE_GENERATED')
        self.req.channel='IBTIKAR';self.req.requester=None
        wf._deduct_ibtikar_on_complete(self.req,'ANALYSIS_FINISHED','COMPLETED')
        self.assertIsNone(self.req.requester)

    def test_backup_failure_cleanup_and_restore_errors(self):
        import tempfile
        from pathlib import Path
        from core import db_backup as db
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'contract.dump';source.write_bytes(b'PGDMP' + bytes(32))
            config=SimpleNamespace(BASE_DIR=root,DATABASES={'default':{'ENGINE':'django.db.backends.postgresql','NAME':'isolated_test','USER':'test'}})
            with patch.object(db,'settings',config),patch.object(db.subprocess,'run',return_value=SimpleNamespace(returncode=1,stderr='isolated failure')):
                with self.assertRaisesRegex(RuntimeError,'pg_dump failed'):db.perform_backup()
                with patch.object(db.subprocess,'run',side_effect=[SimpleNamespace(returncode=0),SimpleNamespace(returncode=1,stderr='restore failed')]):
                    with self.assertRaisesRegex(RuntimeError,'pg_restore failed'):db.perform_restore(source)
            old=root/'plagenor_old.dump';old.write_bytes(b'old')
            with patch.object(Path,'unlink',side_effect=PermissionError):db._prune_old_backups(root,keep=0)
            self.assertTrue(old.exists())

    def test_e2e_configuration_is_isolated_and_legacy_view_module_imports(self):
        import importlib
        import core.views
        config=importlib.import_module('plagenor.settings_e2e')
        self.assertIn('locmem',config.EMAIL_BACKEND)
        self.assertTrue(str(config.DATABASES['default']['NAME']).endswith('plagenor-e2e.sqlite3'))

    def test_pricing_without_multiplier_and_conditional_tier_limits(self):
        from core.pricing import calculate_price,resolve_cost,calculate_cost_from_db,PricingConfigurationError
        from datetime import timedelta
        from django.utils import timezone
        definition={'pricing':{'model':'per_sample_table_row_with_multiplier','base_price':{'default':100}}}
        self.assertEqual(calculate_price(definition,{},[{'sample':'A'}])['total'],100)
        with patch('core.registry.get_service_def',return_value=definition):
            result=resolve_cost(self.service,'GENOCLAB',[{'sample':'A'}],{})
            self.assertEqual(result['source'],'yaml_registry');self.assertEqual(result['total'],100)
        cfg=ServicePricing.objects.create(service=self.service,name='Expired',channel='GENOCLAB',amount=100,valid_until=timezone.now().date()-timedelta(days=1))
        with self.assertRaises(PricingConfigurationError):calculate_cost_from_db(self.service,'GENOCLAB',[{'sample':'A'}],{})
        cfg.delete()
        ServicePricing.objects.create(service=self.service,name='Base',channel='GENOCLAB',amount=100,priority=0)
        for fields in ({'min_quantity':3},{'max_quantity':1},{'min_amount':300},{'max_amount':50}):
            ServicePricing.objects.create(service=self.service,name='Excluded',channel='GENOCLAB',amount=500,priority=1,**fields)
        result=calculate_cost_from_db(self.service,'GENOCLAB',[{'sample':'A'},{'sample':'B'}],{})
        self.assertEqual(result['total'],200);self.assertEqual(len(result['breakdown']),1)

    def test_seed_helpers_and_missing_document_dependency(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from core.management.commands.seed_demo_request import Command
        import io
        cmd=Command()
        self.assertEqual(cmd._ensure_requester(100).ibtikar_declared_balance,100)
        self.assertEqual(cmd._ensure_analyst().user.role,'MEMBER')
        with patch('core.registry.get_service_def',side_effect=RuntimeError):
            params,rows=cmd._build_service_aware_samples(self.service);self.assertEqual(len(rows),2)
        Service.objects.update(active=False)
        with self.assertRaises(SystemExit):cmd._ensure_service(None)
        with patch('core.management.commands.seed_services.load_service_registry',return_value={'NO-RATE':{'name':'Unpriced'}}):
            call_command('seed_services',stdout=io.StringIO())
        self.assertEqual(Service.objects.get(code='NO-RATE').genoclab_price,0)
        with override_settings(DEBUG=True):call_command('seed_accounts',stdout=io.StringIO())
        with patch.dict(sys.modules,{'docx':None}):
            with self.assertRaises(CommandError):call_command('create_docx_templates',stdout=io.StringIO())
