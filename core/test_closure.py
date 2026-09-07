"""Cross-cutting regressions for the finalization requirements."""
from datetime import timedelta
from importlib import import_module
from decimal import Decimal
from unittest.mock import patch
from urllib.parse import urlparse
from django.apps import apps
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from core.models import Request, Service, Invoice, PlatformContent, FinancialVisibility, ServicePricing
from core.exceptions import InvalidTransitionError, AuthorizationError
from core.workflow import transition, force_transition, _send_transition_emails
from core.commercial import cancel_unpaid_invoice
from notifications.models import Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   PRIVILEGED_MFA_ENFORCEMENT=False, DOCUMENT_PDF_ENABLED=False)
class ClosureTests(TestCase):
    def setUp(self):
        self.ops = User.objects.create_user(username='closure-ops', role='PLATFORM_ADMIN')
        self.finance = User.objects.create_user(username='closure-finance', role='FINANCE')
        self.owner = User.objects.create_user(username='closure-client', role='CLIENT', email='client@example.test')
        self.service = Service.objects.create(code='CLOSE', name='Prestation', genoclab_price=100)
        self.req = Request.objects.create(display_id='CLOSE-001', channel='GENOCLAB', requester=self.owner,
            service=self.service, status='ORDER_UPLOADED', quote_amount=119,
            quote_detail={'items':[{'label':'Prestation', 'unit_price':100, 'quantity':1, 'total':100}],
                          'vat_rate':0.19})
        self.client.force_login(self.ops)

    def invoice(self, **kw):
        return Invoice.objects.create(request=self.req, client=self.owner, invoice_number='INV-CLOSE',
            total_ttc=119, subtotal_ht=100, vat_amount=19, **kw)

    def test_national_scope_migrates_existing_content_and_seed_preserves_it(self):
        migration = import_module('core.migrations.0028_national_ibtikar_content')
        for lang,key,old,new in migration.CHANGES:
            PlatformContent.objects.update_or_create(key=key,lang=lang,defaults={'value':old})
        migration.forwards(apps,None)
        for lang,key,old,new in migration.CHANGES:
            self.assertEqual(PlatformContent.objects.get(key=key,lang=lang).value,new)
        from django.core.management import call_command
        from io import StringIO
        call_command('seed_content',stdout=StringIO())
        self.assertIn('étudiants algériens',PlatformContent.objects.get(key='ibtikar_description',lang='fr').value)

    def test_invoice_step_cannot_be_skipped_or_faked(self):
        for target in ['ASSIGNED','INVOICE_GENERATED']:
            with self.assertRaises(InvalidTransitionError): transition(self.req,target,self.ops)
        self.assertEqual(self.req.status,'ORDER_UPLOADED')

    def test_invoice_issued_once_then_assignment_is_allowed(self):
        url=reverse('dashboard:admin_generate_invoice',args=[self.req.pk])
        self.assertEqual(self.client.post(url).status_code,302)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status,'INVOICE_GENERATED')
        self.client.post(url)
        self.assertEqual(Invoice.objects.filter(request=self.req).count(),1)
        transition(self.req,'ASSIGNED',self.ops)
        self.assertEqual(self.req.status,'ASSIGNED')

    def test_legacy_invoice_recovery_preserves_workflow_history(self):
        self.req.status='ANALYSIS_FINISHED';self.req.save()
        url=reverse('dashboard:admin_generate_invoice',args=[self.req.pk])
        self.client.post(url)
        self.assertFalse(Invoice.objects.filter(request=self.req).exists())
        self.client.post(url,{'reason':'Régularisation après contrôle'})
        self.req.refresh_from_db()
        self.assertEqual(self.req.status,'ANALYSIS_FINISHED')
        self.assertTrue(Invoice.objects.filter(request=self.req).exists())
        self.assertIn('Régularisation',self.req.history.first().notes)

    def test_cancellation_keeps_number_amount_and_audit(self):
        inv=self.invoice()
        cancel_unpaid_invoice(inv.pk,self.ops,'Erreur administrative')
        inv.refresh_from_db()
        self.assertIsNotNone(inv.cancelled_at)
        self.assertEqual(inv.invoice_number,'INV-CLOSE')
        self.assertEqual(inv.total_ttc,119)
        from core.financial import get_revenue_summary
        self.assertEqual(get_revenue_summary()['total'],0)

    def test_paid_invoice_cannot_be_cancelled(self):
        inv=self.invoice(payment_status='COMPLETED')
        with self.assertRaises(ValidationError):cancel_unpaid_invoice(inv.pk,self.ops,'Erreur administrative')

    def test_finance_confirmation_requires_proof_then_updates_request_and_invoice(self):
        inv=self.invoice();self.client.force_login(self.finance)
        url=reverse('dashboard:finance_payment_status',args=[inv.pk])
        self.client.post(url,{'payment_status':'COMPLETED','verification_note':'Règlement vérifié'})
        inv.refresh_from_db();self.assertEqual(inv.payment_status,'PENDING')
        self.req.status='PAYMENT_PROOF_UPLOADED';self.req.payment_receipt_file='payments/proof.pdf';self.req.save()
        self.client.post(url,{'payment_status':'COMPLETED','verification_note':'Règlement vérifié'})
        self.req.refresh_from_db();inv.refresh_from_db()
        self.assertEqual(self.req.status,'PAYMENT_CONFIRMED')
        self.assertEqual(self.req.payment_verified_by,self.finance)
        self.assertEqual(inv.payment_status,'COMPLETED')

    def test_non_superadmin_cannot_force_transitions(self):
        with self.assertRaises(AuthorizationError):force_transition(self.req,'COMPLETED',self.ops,'Bypass')

    def test_estimate_endpoint_masks_and_matches_canonical_tariffs(self):
        url=reverse('dashboard:cost_estimate',args=[self.service.code])
        self.client.force_login(self.owner)
        data={'channel':'GENOCLAB','sample_0_id':'a','sample_1_id':'b'}
        self.assertEqual(self.client.post(url,data).json(),{'visible':False})
        ServicePricing.objects.create(service=self.service,name='Current',channel='GENOCLAB',amount=321)
        FinancialVisibility.objects.update_or_create(pk=1,defaults={'show_estimates':True,'valid_until':timezone.localdate()})
        self.assertEqual(Decimal(self.client.post(url,data).json()['total']),642)
        self.assertEqual(self.client.post(url,{**data,'channel':'OHB'}).status_code,400)
        ServicePricing.objects.filter(service=self.service).update(valid_until=timezone.localdate()-timedelta(days=1))
        self.assertFalse(self.client.post(url,data).json()['visible'])

    def test_client_cannot_download_draft_quote_even_with_direct_url(self):
        self.req.status='QUOTE_DRAFT';self.req.save()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('documents:quote',args=[self.req.pk])).status_code,403)

    def test_notification_links_match_recipient_roles(self):
        from notifications.services import notify_user
        notify_user(self.owner,'Test',request_obj=self.req,link_url=f'/dashboard/ops/request/{self.req.pk}/')
        n=Notification.objects.get(user=self.owner)
        self.assertEqual(n.link_url,f'/dashboard/client/request/{self.req.pk}/')

    def test_appointment_and_delivery_have_one_email_per_event(self):
        from notifications import emails
        with patch.object(emails,'notify_appointment') as app,patch.object(emails,'notify_status_change') as status,patch.object(emails,'notify_report_delivery') as report:
            _send_transition_emails(self.req,'ASSIGNED','APPOINTMENT_PROPOSED')
            _send_transition_emails(self.req,'REPORT_UPLOADED','REPORT_VALIDATED')
            _send_transition_emails(self.req,'REPORT_VALIDATED','SENT_TO_CLIENT')
        app.assert_called_once();report.assert_called_once();status.assert_not_called()

    def test_email_links_are_absolute_and_recipient_specific(self):
        from notifications.emails import _email_ctx
        ctx=_email_ctx(self.req,report_url='/report/example/')
        self.assertEqual(urlparse(ctx['dashboard_url']).scheme,'https')
        self.assertIn('/dashboard/client/',ctx['dashboard_url'])
        self.assertEqual(urlparse(ctx['report_url']).scheme,'https')

    def test_financial_screens_render_their_real_actions(self):
        self.invoice()
        self.assertEqual(self.client.get(reverse('dashboard:admin_request_detail',args=[self.req.pk])).status_code,200)
        self.client.force_login(self.finance)
        self.assertEqual(self.client.get(reverse('dashboard:finance')).status_code,200)

    def test_issued_documents_are_byte_stable_after_settings_and_price_changes(self):
        from pathlib import Path
        from documents.generators import generate_quote, generate_invoice_document, build_field_map
        from documents.archives import restore_original
        from core.models import IssuedDocument
        self.req.status='QUOTE_SENT';self.req.save()
        quote = Path(generate_quote(self.req)).read_bytes()
        inv = self.invoice(line_items=[{'description':'Prestation','unit_price':100,'quantity':1,'total':100}])
        invoice = Path(generate_invoice_document(inv)).read_bytes()
        PlatformContent.objects.update_or_create(key='genoclab_issuer_name',lang='fr',defaults={'value':'Changed issuer'})
        self.service.genoclab_price=500;self.service.save()
        self.assertEqual(Path(generate_quote(self.req)).read_bytes(),quote)
        self.assertEqual(Path(generate_invoice_document(inv)).read_bytes(),invoice)
        fields=build_field_map(self.req)
        self.assertIn('119',fields['TOTAL_TTC'])
        IssuedDocument.objects.filter(kind='QUOTE').update(content=b'altered')
        with self.assertRaises(ValidationError):restore_original('QUOTE',self.req.quote_number)

    def test_cancelled_copy_is_marked_without_changing_archived_original(self):
        from documents.generators import generate_invoice_document
        from core.models import IssuedDocument
        from docx import Document
        inv=self.invoice(line_items=[{'description':'Prestation','unit_price':100,'quantity':1,'total':100}])
        generate_invoice_document(inv)
        before=IssuedDocument.objects.get(kind='INVOICE').sha256
        cancel_unpaid_invoice(inv.pk,self.ops,'Doublon administratif');inv.refresh_from_db()
        doc=Document(generate_invoice_document(inv))
        self.assertIn('FACTURE ANNULÉE',doc.sections[0].header._element.xml)
        self.assertIn('Doublon administratif',' '.join(p.text for p in doc.paragraphs))
        self.assertEqual(IssuedDocument.objects.get(kind='INVOICE').sha256,before)

    def test_ohb_revenue_is_separate_and_cancellation_excluded(self):
        from core.financial import get_budget_dashboard, archive_monthly_revenue
        self.req.billing_channel='OHB';self.req.save()
        self.invoice(document_snapshot={'billing_channel':'OHB'})
        data=get_budget_dashboard()
        self.assertEqual(data['ohb']['total'],119)
        self.assertEqual(data['genoclab']['total'],0)
        rows={r['channel']:r for r in archive_monthly_revenue(timezone.now().month,timezone.now().year)}
        self.assertEqual(rows['OHB']['total_revenue'],119)
        self.assertEqual(rows['GENOCLAB']['total_revenue'],0)

    def test_ops_can_manage_tariffs_but_not_users_and_invalid_input_is_atomic(self):
        url=reverse('dashboard:superadmin_service_edit',args=[self.service.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.get(reverse('dashboard:superadmin')).status_code,403)
        self.assertEqual(self.client.get(reverse('dashboard:ops_services')).status_code,200)
        self.client.post(url,{'name':'Changed','ibtikar_price':'NaN'})
        self.service.refresh_from_db();self.assertEqual(self.service.name,'Prestation')
        self.client.post(url,{'name':'Changed','ibtikar_price':'123','genoclab_price':'456','turnaround_days':'5'})
        self.service.refresh_from_db();self.assertEqual(self.service.genoclab_price,456)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url,{'genoclab_price':'1'}).status_code,403)

    def test_email_subject_and_body_use_recipient_language_and_failure_is_visible(self):
        from django.core import mail
        from notifications.emails import notify_submission_confirmation, send_email_notification
        self.owner.preferred_language='ar';self.owner.save()
        notify_submission_confirmation(self.req)
        self.assertIn('تأكيد',mail.outbox[-1].subject)
        self.assertIn('dir="rtl"',mail.outbox[-1].alternatives[0].content)
        with patch('notifications.emails.send_mail',return_value=0):
            with self.assertLogs('plagenor.email',level='ERROR'):
                self.assertFalse(send_email_notification('test@example.test','Subject','Body'))

    def test_commercial_documents_keep_client_details_and_revision_history(self):
        from documents.generators import generate_quote
        from documents.tests import _docx_text
        self.req.status='REQUEST_CREATED';self.req.save()
        url=reverse('dashboard:admin_prepare_quote',args=[self.req.pk])
        data={'item_label_0':'Analyse','item_unit_price_0':'100','item_quantity_0':'1',
              'vat_rate':'19','action':'send','billing_client_name':'Université de démonstration',
              'billing_client_details':'Adresse test\nNIS : TEST-123','payment_terms':'Virement à 30 jours',
              'commercial_terms':'Validité du devis : 30 jours','quote_notes':'CONFIDENTIEL-OPS'}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.req.refresh_from_db();self.assertEqual(self.req.status,'QUOTE_SENT')
        first=self.req.quote_number
        text=_docx_text(generate_quote(self.req))
        for value in ['Université de démonstration','TEST-123','Virement à 30 jours','Validité du devis : 30 jours']:
            self.assertIn(value,text)
        self.assertNotIn('CONFIDENTIEL-OPS',text)
        self.assertEqual(self.client.post(url,data).status_code,403)
        self.client.force_login(self.owner)
        self.client.post(reverse('dashboard:client_reject_quote',args=[self.req.pk]))
        self.client.force_login(self.ops)
        self.client.post(url,{**data,'item_unit_price_0':'200'})
        self.req.refresh_from_db()
        self.assertNotEqual(self.req.quote_number,first)
        from core.models import IssuedDocument
        self.assertEqual(IssuedDocument.objects.filter(kind='QUOTE').count(),2)

    def test_financial_visibility_requires_future_expiry_and_keeps_internal_amounts(self):
        url=reverse('dashboard:financial_visibility')
        self.client.post(url,{'show_estimates':'on','valid_until':'2000-01-01'})
        self.assertFalse(FinancialVisibility.objects.get(pk=1).estimates_visible())
        self.client.post(url,{'show_estimates':'on','valid_until':str(timezone.localdate()+timedelta(days=1))})
        self.assertTrue(FinancialVisibility.objects.get(pk=1).estimates_visible())
        self.client.post(url,{})
        self.assertFalse(FinancialVisibility.objects.get(pk=1).estimates_visible())
        self.req.refresh_from_db();self.assertEqual(self.req.quote_amount,119)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url,{}).status_code,403)
