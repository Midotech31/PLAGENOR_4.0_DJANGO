import io
import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from erp import cdc_views, procurement_views, stock_views
from erp.cdc import catalog
from erp.cdc.consultation import FIELDS
from erp.models import CdcGeneration, Capability
from erp.services.cdc import create_dossier
from erp.services.procurement import add_plan_article, create_plan
from erp.services.stock import reserve_stock
from erp.test_operations import OperationFixtures
from erp.test_coverage_completion_views import FakeField, FakeForm, req


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class StockViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.rf=RequestFactory()
        self.container,self.receipt_move,_=self.receive(quantity=12)
        self.lot=self.container.lot

    def test_stock_lists_detail_ledger_and_reconcile_filters(self):
        for state in ('all','usable','blocked','empty','reserved'):
            request=req(self.rf,self.ops,path='/?q=TIPS&state='+state)
            request.GET=request.GET.copy(); request.GET.update({'q':'TIPS','state':state})
            with patch('erp.stock_views.render',return_value=HttpResponse('ok')):
                self.assertEqual(stock_views.stock_list(request).status_code,200)
        request=req(self.rf,self.ops,path='/?location='+str(self.freezer.pk))
        request.GET=request.GET.copy();request.GET['location']=str(self.freezer.pk)
        with patch('erp.stock_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(stock_views.stock_list(request).status_code,200)
        request=req(self.rf,self.ops)
        with patch('erp.stock_views.storage_compatibility',create=True,return_value=[]):
            pass
        with patch('erp.stock_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(stock_views.stock_detail(request,self.container.pk).status_code,200)
        request=req(self.rf,self.ops,path='/?q=TIPS');request.GET=request.GET.copy();request.GET['q']='TIPS'
        with patch('erp.stock_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(stock_views.ledger(request).status_code,200)
            self.assertEqual(stock_views.reconcile(request).status_code,200)

    def test_receipt_and_all_stock_operations_success_and_validation_errors(self):
        receipt=FakeForm({'key':uuid.uuid4(),'article':self.article,'amount':Decimal(1),'unit':self.unit,
                          'location':self.freezer,'lot_code':'NEWLOT','container_code':'NEWCONT',
                          'received_on':timezone.localdate(),'condition':'Intact'})
        movement=SimpleNamespace(receipt=SimpleNamespace(container_id=self.container.pk))
        request=req(self.rf,self.ops,'post','/receipt/',{'x':'1'})
        with patch('erp.stock_views.forms.ReceiptForm',return_value=receipt), \
             patch('erp.stock_views.receive_stock',return_value=movement), \
             patch('erp.stock_views.messages.success'):
            self.assertEqual(stock_views.receipt_create(request).status_code,302)
        with patch('erp.stock_views.forms.ReceiptForm',return_value=receipt), \
             patch('erp.stock_views.receive_stock',side_effect=ValidationError('bad')), \
             patch('erp.stock_views.add_validation') as add, \
             patch('erp.stock_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(stock_views.receipt_create(request).status_code,400)
            add.assert_called_once()

        for action in stock_views.OPERATIONS:
            form=FakeForm({'expected_version':self.container.version,'reason':'couverture'})
            factory=Mock(return_value=form)
            service=Mock()
            request=req(self.rf,self.ops,'post','/action/',{'x':'1'})
            with patch.dict(stock_views.OPERATIONS,{action:(factory,service,'Titre',None)}):
                self.assertEqual(stock_views.stock_action(request,self.container.pk,action).status_code,302)
                service.assert_called_once()
            service=Mock(side_effect=ValidationError('bad'))
            with patch.dict(stock_views.OPERATIONS,{action:(factory,service,'Titre',None)}), \
                 patch('erp.stock_views.add_validation') as add, \
                 patch('erp.stock_views.render',return_value=HttpResponse('bad',status=400)):
                self.assertEqual(stock_views.stock_action(request,self.container.pk,action).status_code,400)
                add.assert_called_once()
        with self.assertRaises(Http404):
            stock_views.stock_action(req(self.rf,self.ops),self.container.pk,'unknown')

    def test_release_reverse_and_lot_control_paths(self):
        fake_res=SimpleNamespace(pk=uuid.uuid4(),container=self.container)
        form=FakeForm({'reason':'libération'})
        request=req(self.rf,self.ops,'post','/release/',{'x':'1'})
        with patch('erp.stock_views.get_object_or_404',return_value=fake_res), \
             patch('erp.stock_views.permitted',return_value=True), \
             patch('erp.stock_views.forms.ReasonForm',return_value=form), \
             patch('erp.stock_views.release_stock') as service:
            self.assertEqual(stock_views.reservation_release(request,fake_res.pk).status_code,302)
            service.assert_called_once()
        with patch('erp.stock_views.get_object_or_404',return_value=fake_res), \
             patch('erp.stock_views.permitted',return_value=False):
            with self.assertRaises(PermissionDenied):
                stock_views.reservation_release(req(self.rf,self.operator),fake_res.pk)

        movement=SimpleNamespace(pk=uuid.uuid4())
        with patch('erp.stock_views.get_object_or_404',return_value=movement), \
             patch('erp.stock_views.forms.ReasonForm',return_value=form), \
             patch('erp.stock_views.reverse_stock') as service:
            self.assertEqual(stock_views.movement_reverse(request,movement.pk).status_code,302)
            service.assert_called_once()

        control=FakeForm({'expected_version':self.lot.version,'status':'ACCEPTED','note':'contrôle'})
        with patch('erp.stock_views.forms.ControlForm',return_value=control), \
             patch('erp.stock_views.control_lot') as service:
            self.assertEqual(stock_views.lot_control(request,self.lot.pk).status_code,302)
            service.assert_called_once()
        with patch('erp.stock_views.forms.ControlForm',return_value=control), \
             patch('erp.stock_views.control_lot',side_effect=ValidationError('bad')), \
             patch('erp.stock_views.add_validation') as add, \
             patch('erp.stock_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(stock_views.lot_control(request,self.lot.pk).status_code,400)
            add.assert_called_once()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CdcViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.rf=RequestFactory()
        self.dossier=create_dossier(self.ops,family='equipment',
            reference='77/SME/SDFM/SG/ESSBO/2026',title='CDC vues couverture',
            assignee=self.operator,allow_costs=True)
        self.lot=self.dossier.lots.first()
        self.item=self.lot.items.first()

    def test_list_create_detail_actions_and_consultation(self):
        request=req(self.rf,self.ops,path='/?q=77');request.GET=request.GET.copy();request.GET['q']='77'
        with patch('erp.cdc_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(cdc_views.cdc_list(request).status_code,200)
        create=FakeForm({'expected_version':None,'family':'equipment','reference':'78/SME/SDFM/SG/ESSBO/2026',
                         'title':'CDC','assignee':self.operator,'due_on':None,'priority':'NORMAL',
                         'allow_costs':False,'instructions':''})
        request=req(self.rf,self.ops,'post','/new/',{'x':'1'})
        with patch('erp.cdc_views.forms.CdcCreateForm',return_value=create), \
             patch('erp.cdc_views.create_dossier',return_value=self.dossier):
            self.assertEqual(cdc_views.cdc_create(request).status_code,302)
        with patch('erp.cdc_views.forms.CdcCreateForm',return_value=create), \
             patch('erp.cdc_views.create_dossier',side_effect=ValidationError('bad')), \
             patch('erp.cdc_views._error') as err, \
             patch('erp.cdc_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(cdc_views.cdc_create(request).status_code,400);err.assert_called_once()

        decision=FakeForm({'expected_version':self.dossier.version,'reason':'couverture'})
        for action,target in [('submit','submit_dossier'),('generate','generate_cdc')]:
            request=req(self.rf,self.ops,'post','/detail/',{'action':action})
            with patch('erp.cdc_views.forms.CdcDecisionForm',return_value=decision), \
                 patch('erp.cdc_views.'+target) as service, \
                 patch('erp.cdc_views.messages.success'):
                self.assertEqual(cdc_views.cdc_detail(request,self.dossier.pk).status_code,302)
                service.assert_called_once()
        request=req(self.rf,self.ops,'post','/detail/',{'action':'unknown'})
        with patch('erp.cdc_views.forms.CdcDecisionForm',return_value=decision):
            self.assertEqual(cdc_views.cdc_detail(request,self.dossier.pk).status_code,400)
        request=req(self.rf,self.ops)
        with patch('erp.cdc_views.document_data',return_value=self.dossier.data), \
             patch('erp.cdc_views.controls',return_value=[]), \
             patch('erp.cdc_views.estimate_totals',return_value={'currencies':{},'incomplete_lines':0}), \
             patch('erp.cdc_views.render',return_value=HttpResponse('ok')) as render:
            self.assertEqual(cdc_views.cdc_detail(request,self.dossier.pk).status_code,200)
            self.assertIn('findings',render.call_args.args[2])

        values={key:self.dossier.data['consultation'][key] for key in FIELDS}
        values.update(expected_version=self.dossier.version,reference=self.dossier.reference,reason='raison')
        form=FakeForm(values)
        request=req(self.rf,self.operator,'post','/consult/',{'x':'1'})
        with patch('erp.cdc_views.forms.ConsultationForm',return_value=form), \
             patch('erp.cdc_views.save_consultation') as service:
            self.assertEqual(cdc_views.cdc_consultation(request,self.dossier.pk).status_code,302)
            service.assert_called_once()

    def test_lot_item_approval_download_revision_clauses_and_paragraph(self):
        request=req(self.rf,self.operator)
        with patch('erp.cdc_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(cdc_views.cdc_lot(request,self.lot.pk).status_code,200)

        lotform=FakeForm({'expected_version':self.dossier.version,'name':'Lot','name_ar':'حصة','reason':'raison'})
        request=req(self.rf,self.operator,'post','/lot/',{'x':'1'})
        with patch('erp.cdc_views.forms.CdcLotForm',return_value=lotform), \
             patch('erp.cdc_views.save_cdc_lot') as service:
            self.assertEqual(cdc_views.cdc_lot_edit(request,self.lot.pk).status_code,302)
            service.assert_called_once()

        itemform=FakeForm({'expected_version':self.dossier.version,'article':None,'purchase_unit':None,
            'reason':'raison','refresh_catalog':False,'designation':self.item.designation,
            'specifications':self.item.specifications,'unit_label':self.item.unit_label,
            'packaging':self.item.packaging,'quantity':self.item.quantity,'details':self.item.details,
            'active':True,'estimated_price':None,'tax_rate':None,'price_source':'','currency':'DZD'})
        with patch('erp.cdc_views.forms.CdcItemForm',return_value=itemform), \
             patch('erp.cdc_views.save_cdc_item') as service:
            self.assertEqual(cdc_views.cdc_item_edit(request,self.lot.pk,self.item.pk).status_code,302)
            service.assert_called_once()

        revision=self.dossier.revisions.get(number=self.dossier.revision_number)
        generation=CdcGeneration.objects.create(revision=revision,actor=self.ops,docx=b'DOCX',pdf=b'%PDF',
            docx_sha256='a'*64,pdf_sha256='b'*64,pages=1,checks={})
        approval=FakeForm({'expected_version':self.dossier.version,'generation':generation,'reviewed_pages':1,
                           'statement':'validé','visual_review':True,'content_review':True})
        request=req(self.rf,self.ops,'post','/approve/',{'x':'1'})
        with patch('erp.cdc_views.forms.CdcApprovalForm',return_value=approval), \
             patch('erp.cdc_views.approve_dossier') as service, \
             patch('erp.cdc_views.messages.success'):
            self.assertEqual(cdc_views.cdc_approve(request,self.dossier.pk).status_code,302)
            service.assert_called_once()

        for ext in ('pdf','docx'):
            response=cdc_views.cdc_download(req(self.rf,self.ops),generation.pk,ext)
            self.assertEqual(response.status_code,200)
        with self.assertRaises(Http404):
            cdc_views.cdc_download(req(self.rf,self.ops),generation.pk,'txt')
        with patch('erp.cdc_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(cdc_views.cdc_revision(req(self.rf,self.ops),revision.pk).status_code,200)

        request=req(self.rf,self.operator,path='/?q=acquisition');request.GET=request.GET.copy();request.GET['q']='acquisition'
        with patch('erp.cdc_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(cdc_views.cdc_clauses(request,self.dossier.pk).status_code,200)

        source=catalog.document('equipment')
        pid=next(b['id'] for b in source.source_index if b['text'] and not b['guard'])
        request=req(self.rf,self.operator,path='/?paragraph_id='+pid);request.GET=request.GET.copy();request.GET['paragraph_id']=pid
        with patch('erp.cdc_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(cdc_views.cdc_paragraph(request,self.dossier.pk).status_code,200)
        pform=FakeForm({'expected_version':self.dossier.version,'paragraph_id':pid,'value':'Texte','reason':'raison'})
        request=req(self.rf,self.operator,'post','/p/',{'paragraph_id':pid})
        with patch('erp.cdc_views.forms.CdcParagraphForm',return_value=pform), \
             patch('erp.cdc_views.edit_cdc_paragraph') as service:
            self.assertEqual(cdc_views.cdc_paragraph(request,self.dossier.pk).status_code,302)
            service.assert_called_once()
        request=req(self.rf,self.operator,path='/?paragraph_id=missing');request.GET=request.GET.copy();request.GET['paragraph_id']='missing'
        with self.assertRaises(Http404):
            cdc_views.cdc_paragraph(request,self.dossier.pk)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],SECURE_SSL_REDIRECT=False)
class ProcurementViewCoverageTests(OperationFixtures,TestCase):
    def setUp(self):
        self.rf=RequestFactory()
        self.plan=create_plan(self.ops,reference='COV-PLAN',year=timezone.localdate().year+1,
            title='Plan couverture',assignee=self.operator,allow_costs=True)
        self.line=add_plan_article(self.operator,self.plan.pk,expected=self.plan.version,article=self.article,lot_name='Lot couverture')
        self.plan.refresh_from_db()

    def test_plan_list_create_detail_article_line_forecast_and_export(self):
        request=req(self.rf,self.ops,path='/?q=COV');request.GET=request.GET.copy();request.GET['q']='COV'
        with patch('erp.procurement_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(procurement_views.plan_list(request).status_code,200)

        create=FakeForm({'expected_version':None,'reference':'NEW','year':timezone.localdate().year+1,
                         'title':'Nouveau','assignee':self.operator,'allow_costs':True})
        request=req(self.rf,self.ops,'post','/new/',{'x':'1'})
        with patch('erp.procurement_views.forms.PlanCreateForm',return_value=create), \
             patch('erp.procurement_views.create_plan',return_value=self.plan):
            self.assertEqual(procurement_views.plan_create(request).status_code,302)

        action=FakeForm({'expected_version':self.plan.version,'reason':'raison'}, fields={'reason':FakeField()})
        for name,target in [('submit','submit_plan'),('approve','approve_plan')]:
            request=req(self.rf,self.ops,'post','/detail/',{'action':name})
            with patch('erp.procurement_views.forms.PlanActionForm',return_value=action), \
                 patch('erp.procurement_views.'+target):
                self.assertEqual(procurement_views.plan_detail(request,self.plan.pk).status_code,302)
        with patch('erp.procurement_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(procurement_views.plan_detail(req(self.rf,self.ops),self.plan.pk).status_code,200)

        articleform=FakeForm({'expected_version':self.plan.version,'article':self.article,'lot_name':'Lot'})
        request=req(self.rf,self.operator,'post','/article/',{'x':'1'})
        with patch('erp.procurement_views.forms.PlanArticleForm',return_value=articleform), \
             patch('erp.procurement_views.add_plan_article') as service:
            self.assertEqual(procurement_views.plan_article(request,self.plan.pk).status_code,302);service.assert_called_once()

        decision=FakeForm({'expected_version':self.plan.version,'retained_quantity':Decimal(10),'included':True,
                           'lot_name':'Lot','priority':'NORMAL','estimated_price':Decimal(1),'tax_rate':Decimal(19),
                           'currency':'DZD','price_source':'source','decision_reason':'raison'})
        with patch('erp.procurement_views.forms.PlanDecisionForm',return_value=decision), \
             patch('erp.procurement_views.decide_plan_line') as service:
            self.assertEqual(procurement_views.plan_line(request,self.line.pk).status_code,302);service.assert_called_once()

        with patch('erp.procurement_views.forms.PlanActionForm',return_value=action), \
             patch('erp.procurement_views.refresh_forecast') as service:
            self.assertEqual(procurement_views.forecast_detail(request,self.line.pk).status_code,302);service.assert_called_once()
        with patch('erp.procurement_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(procurement_views.forecast_detail(req(self.rf,self.operator),self.line.pk).status_code,200)

        with patch('erp.services.report_exports.export_plan',return_value=b'xlsx'):
            response=procurement_views.plan_export(req(self.rf,self.ops),self.plan.pk)
            self.assertEqual(response.status_code,200)

    def test_cdc_order_create_detail_line_receive_and_date_orchestration(self):
        request=req(self.rf,self.ops,'post','/x/',{'x':'1'})
        cdcform=FakeForm({'expected_version':self.plan.version,'reference':'99/SME/SDFM/SG/ESSBO/2026',
                          'family':'reagents','assignee':self.second})
        dossier=SimpleNamespace(pk=uuid.uuid4())
        with patch('erp.procurement_views.forms.CdcFromPlanForm',return_value=cdcform), \
             patch('erp.procurement_views.plan_to_cdc',return_value=dossier):
            self.assertEqual(procurement_views.cdc_from_plan(request,self.plan.pk).status_code,302)

        fake_lines=Mock(); fake_lines.select_related.return_value=[]
        fake_order=SimpleNamespace(pk=uuid.uuid4(),version=1,plan=self.plan,status='DRAFT',
            lines=fake_lines,reference='PO-COV',expected_on=timezone.localdate())
        createform=FakeForm({'expected_version':self.plan.version,'reference':'PO','supplier':self.party,
                             'ordered_on':timezone.localdate(),'expected_on':timezone.localdate()+timedelta(days=1)})
        with patch('erp.procurement_views.forms.OrderCreateForm',return_value=createform), \
             patch('erp.procurement_views.create_order',return_value=fake_order):
            self.assertEqual(procurement_views.order_create(request,self.plan.pk).status_code,302)

        action=FakeForm({'expected_version':1,'reason':'raison'})
        for verb,target in [('confirm','confirm_order'),('cancel','cancel_order')]:
            request=req(self.rf,self.ops,'post','/order/',{'action':verb})
            with patch('erp.procurement_views.order_scope',return_value=Mock()), \
                 patch('erp.procurement_views.get_object_or_404',return_value=fake_order), \
                 patch('erp.procurement_views.forms.PlanActionForm',return_value=action), \
                 patch('erp.procurement_views.'+target):
                self.assertEqual(procurement_views.order_detail(request,fake_order.pk).status_code,302)
        with patch('erp.procurement_views.order_scope',return_value=Mock()), \
             patch('erp.procurement_views.get_object_or_404',return_value=fake_order), \
             patch('erp.procurement_views.forms.PlanActionForm',return_value=action), \
             patch('erp.procurement_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(procurement_views.order_detail(req(self.rf,self.ops),fake_order.pk).status_code,200)

        fake_line=SimpleNamespace(pk=uuid.uuid4(),order=fake_order,order_id=fake_order.pk,
            plan_line=self.line,quantity=Decimal(10),unit_price=Decimal(1),tax_rate=Decimal(19),
            currency='DZD',variance_reason='',article_snapshot={'name':'Article','purchase_unit_name':'Pièce'})
        lineform=FakeForm({'expected_version':1,'plan_line':self.line,'quantity':Decimal(10),
                           'unit_price':Decimal(1),'tax_rate':Decimal(19),'currency':'DZD','variance_reason':''})
        with patch('erp.procurement_views.order_scope',return_value=Mock()), \
             patch('erp.procurement_views.get_object_or_404',side_effect=[fake_order,fake_line]), \
             patch('erp.procurement_views.forms.OrderLineForm',return_value=lineform), \
             patch('erp.procurement_views.save_order_line') as service:
            self.assertEqual(procurement_views.order_line(request,fake_order.pk,fake_line.pk).status_code,302)
            service.assert_called_once()

        receipt=FakeForm({'expected_version':1,'key':uuid.uuid4(),'amount':Decimal(1),'location':self.freezer,
                          'lot_code':'L','manufacturer_lot':'M','container_code':'C',
                          'received_on':timezone.localdate(),'condition':'ok'})
        with patch('erp.procurement_views.order_scope',return_value=Mock()), \
             patch('erp.procurement_views.get_object_or_404',return_value=fake_line), \
             patch('erp.procurement_views.forms.OrderReceiptForm',return_value=receipt), \
             patch('erp.procurement_views.receive_order_line') as service:
            self.assertEqual(procurement_views.order_receive(request,fake_line.pk).status_code,302)
            service.assert_called_once()

        dateform=FakeForm({'expected_version':1,'expected_on':timezone.localdate()+timedelta(days=2),'reason':'retard'})
        with patch('erp.procurement_views.order_scope',return_value=Mock()), \
             patch('erp.procurement_views.get_object_or_404',return_value=fake_order), \
             patch('erp.procurement_views.forms.OrderDateForm',return_value=dateform), \
             patch('erp.procurement_views.revise_delivery_date') as service:
            self.assertEqual(procurement_views.order_date(request,fake_order.pk).status_code,302)
            service.assert_called_once()
