import uuid
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, Http404
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp import biobank_views, consumption_views, inventory_views, work_views
from erp.models import Capability, ConsumptionProfile, ConsumptionRule, StorageTransfer, WorkItem
from erp.services.biobank import receive_sample, source_samples
from erp.services.consumption import create_run, save_profile, save_rule
from erp.services.inventory import create_inventory
from erp.services.storage import save_location
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


class FakeField:
    def __init__(self):
        self.choices = []


class FakeForm:
    def __init__(self, cleaned=None, valid=True, fields=None, actual_fields=None, biological_fields=None):
        self.cleaned_data = cleaned or {}
        self._valid = valid
        self.fields = fields if fields is not None else {'state': FakeField()}
        self.actual_fields = actual_fields or {}
        self.biological_fields = biological_fields or {}
        self.errors = {}
        self.added = []

    def is_valid(self):
        return self._valid

    def add_error(self, field, error):
        self.added.append((field, str(error)))


def req(factory, user, method='get', path='/', data=None):
    request = getattr(factory, method)(path, data or {})
    request.user = user
    return request


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkInventoryViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.container, _, _ = self.receive()
        self.work = create_work(self.ops, kind='CONTROL', title='Tâche couverture', assignee=self.operator)
        self.campaign = create_inventory(self.ops, title='Inventaire couverture',
            assignee=self.operator, location=self.freezer, blind=False)

    def test_work_list_create_and_delegate_orchestration(self):
        request = req(self.rf, self.ops, path='/erp/tasks/?q=couv&kind=CONTROL&state=ASSIGNED&mine=1')
        request.GET = request.GET.copy()
        request.GET.update({'q':'couv','kind':'CONTROL','state':'ASSIGNED','mine':'1','page':'bad'})
        with patch('erp.work_views.render', return_value=HttpResponse('list')) as render:
            self.assertEqual(work_views.work_list(request).status_code, 200)
            self.assertIn('page', render.call_args.args[2])

        form = FakeForm({'expected_version':None, 'kind':'CONTROL', 'title':'Nouvelle',
                         'assignee':self.operator, 'due_on':None, 'priority':'NORMAL',
                         'allow_costs':False, 'instructions':''})
        created = SimpleNamespace(pk=uuid.uuid4())
        request = req(self.rf, self.ops, 'post', '/erp/tasks/new/', {'x':'1'})
        with patch('erp.work_views.WorkForm', return_value=form), \
             patch('erp.work_views.create_work', return_value=created) as service:
            response = work_views.work_create(request)
            self.assertEqual(response.status_code, 302)
            service.assert_called_once()
        with patch('erp.work_views.WorkForm', return_value=form), \
             patch('erp.work_views.create_work', side_effect=ValidationError('bad')), \
             patch('erp.work_views.add_validation') as add, \
             patch('erp.work_views.render', return_value=HttpResponse('bad', status=400)):
            self.assertEqual(work_views.work_create(request).status_code, 400)
            add.assert_called_once()

        delegate = FakeForm({'expected_version':self.work.version, 'assignee':self.second,
                             'due_on':None, 'priority':'HIGH', 'allow_costs':False,
                             'instructions':'x', 'reason':'réaffectation'})
        request = req(self.rf, self.ops, 'post', '/delegate/', {'x':'1'})
        with patch('erp.work_views.DelegationForm', return_value=delegate), \
             patch('erp.work_views.delegate_work') as service, \
             patch('erp.work_views.messages.success'):
            self.assertEqual(work_views.work_delegate(request, self.work.pk).status_code, 302)
            service.assert_called_once()
        with patch('erp.work_views.DelegationForm', return_value=delegate), \
             patch('erp.work_views.delegate_work', side_effect=ValidationError('bad')), \
             patch('erp.work_views.add_validation') as add, \
             patch('erp.work_views.render', return_value=HttpResponse('bad', status=400)):
            self.assertEqual(work_views.work_delegate(request, self.work.pk).status_code, 400)
            add.assert_called_once()

    def test_work_detail_get_comments_transitions_and_errors(self):
        request = req(self.rf, self.operator, path='/detail/')
        with patch('erp.work_views.render', return_value=HttpResponse('ok')) as render:
            self.assertEqual(work_views.work_detail(request, self.work.pk).status_code, 200)
            context = render.call_args.args[2]
            self.assertTrue(context['editable'])

        comment = FakeForm({'body':'Commentaire de couverture'})
        initial = FakeForm(fields={'state':FakeField()})
        request = req(self.rf, self.operator, 'post', '/detail/', {'action':'comment'})
        with patch('erp.work_views.WorkTransitionForm', return_value=initial), \
             patch('erp.work_views.WorkCommentForm', side_effect=[FakeForm(), comment]), \
             patch('erp.work_views.comment_work') as service:
            self.assertEqual(work_views.work_detail(request, self.work.pk).status_code, 302)
            service.assert_called_once()
        with patch('erp.work_views.WorkTransitionForm', return_value=initial), \
             patch('erp.work_views.WorkCommentForm', side_effect=[FakeForm(), comment]), \
             patch('erp.work_views.comment_work', side_effect=ValidationError('bad')), \
             patch('erp.work_views.add_validation') as add, \
             patch('erp.work_views.render', return_value=HttpResponse('bad',status=400)):
            self.assertEqual(work_views.work_detail(request, self.work.pk).status_code, 400)
            add.assert_called_once()

        transition = FakeForm({'expected_version':self.work.version,'state':'IN_PROGRESS','reason':'démarrer'},
                              fields={'state':FakeField()})
        request = req(self.rf, self.operator, 'post', '/detail/', {'action':'transition'})
        with patch('erp.work_views.WorkTransitionForm', side_effect=[initial, transition]), \
             patch('erp.work_views.WorkCommentForm', return_value=FakeForm()), \
             patch('erp.work_views.transition_work') as service:
            self.assertEqual(work_views.work_detail(request, self.work.pk).status_code, 302)
            service.assert_called_once()
        with patch('erp.work_views.WorkTransitionForm', side_effect=[initial, transition]), \
             patch('erp.work_views.WorkCommentForm', return_value=FakeForm()), \
             patch('erp.work_views.transition_work', side_effect=ValidationError('bad')), \
             patch('erp.work_views.add_validation') as add, \
             patch('erp.work_views.render', return_value=HttpResponse('bad',status=400)):
            self.assertEqual(work_views.work_detail(request, self.work.pk).status_code, 400)
            add.assert_called_once()

        submitted = create_work(self.ops, kind='CONTROL', title='Soumise', assignee=self.operator)
        from erp.services.work import transition_work
        submitted = transition_work(self.operator, submitted.pk, expected=submitted.version,
                                    state='SUBMITTED', reason='fait')
        request = req(self.rf, self.ops)
        with patch('erp.work_views.render', return_value=HttpResponse('ok')) as render:
            work_views.work_detail(request, submitted.pk)
            choices = render.call_args.args[2]['form'].fields['state'].choices
            self.assertTrue(choices)

    def test_inventory_list_create_detail_actions_and_count(self):
        request = req(self.rf, self.ops)
        with patch('erp.inventory_views.render', return_value=HttpResponse('ok')):
            self.assertEqual(inventory_views.inventory_list(request).status_code, 200)

        create_form = FakeForm({'expected_version':None,'title':'Inv','assignee':self.operator,
                                'location':self.freezer,'blind':True})
        request = req(self.rf, self.ops, 'post', '/new/', {'x':'1'})
        with patch('erp.inventory_views.InventoryForm', return_value=create_form), \
             patch('erp.inventory_views.create_inventory', return_value=self.campaign):
            self.assertEqual(inventory_views.inventory_create(request).status_code, 302)
        with patch('erp.inventory_views.InventoryForm', return_value=create_form), \
             patch('erp.inventory_views.create_inventory', side_effect=ValidationError('bad')), \
             patch('erp.inventory_views.add_validation') as add, \
             patch('erp.inventory_views.render', return_value=HttpResponse('bad',status=400)):
            self.assertEqual(inventory_views.inventory_create(request).status_code, 400)
            add.assert_called_once()

        request = req(self.rf, self.operator, path='/?q=CONT')
        request.GET = request.GET.copy(); request.GET['q']='CONT'
        with patch('erp.inventory_views.render', return_value=HttpResponse('ok')) as render:
            self.assertEqual(inventory_views.inventory_detail(request, self.campaign.pk).status_code, 200)
            self.assertTrue(render.call_args.args[2]['reveal'])

        cleaned={'expected_version':self.campaign.work.version,'key':uuid.uuid4(),'reason':'raison'}
        for action, target in [('submit','submit_inventory'),('approve','approve_inventory'),('recount','recount_inventory')]:
            request = req(self.rf, self.ops, 'post', '/inv/', {'action':action,'lines':[str(self.campaign.lines.first().pk)]})
            form=FakeForm(dict(cleaned))
            with patch('erp.inventory_views.InventoryDecisionForm', return_value=form), \
                 patch('erp.inventory_views.'+target) as service:
                self.assertEqual(inventory_views.inventory_detail(request, self.campaign.pk).status_code, 302)
                service.assert_called_once()
        request=req(self.rf,self.ops,'post','/inv/',{'action':'unknown'})
        with patch('erp.inventory_views.InventoryDecisionForm',return_value=FakeForm(dict(cleaned))):
            self.assertEqual(inventory_views.inventory_detail(request,self.campaign.pk).status_code,400)

        request=req(self.rf,self.ops,'post','/inv/',{'action':'submit'})
        with patch('erp.inventory_views.InventoryDecisionForm',return_value=FakeForm(dict(cleaned))), \
             patch('erp.inventory_views.submit_inventory',side_effect=ValidationError('bad')), \
             patch('erp.inventory_views.add_validation') as add, \
             patch('erp.inventory_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(inventory_views.inventory_detail(request,self.campaign.pk).status_code,400)
            add.assert_called_once()

        line=self.campaign.lines.first()
        count=FakeForm({'expected_version':line.version,'container_version':line.container.version,
                        'amount':Decimal('9'),'note':'compté'})
        request=req(self.rf,self.operator,'post','/count/',{'x':'1'})
        with patch('erp.inventory_views.CountForm',return_value=count), \
             patch('erp.inventory_views.count_inventory') as service:
            self.assertEqual(inventory_views.inventory_count(request,line.pk).status_code,302)
            service.assert_called_once()
        with patch('erp.inventory_views.CountForm',return_value=count), \
             patch('erp.inventory_views.count_inventory',side_effect=ValidationError('bad')), \
             patch('erp.inventory_views.add_validation') as add, \
             patch('erp.inventory_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(inventory_views.inventory_count(request,line.pk).status_code,400)
            add.assert_called_once()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ConsumptionViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.rf=RequestFactory()
        self.service=Service.objects.create(code='COV-RUN',name='Service couverture')
        member,_=MemberProfile.objects.get_or_create(user=self.operator)
        self.request_obj=Request.objects.create(requester=self.outsider,assigned_to=member,service=self.service,
            title='Demande couverture',status='IN_PROGRESS',sample_table=[{'sample_code':'C1'}])
        self.profile=save_profile(self.ops,{'code':'COV-PROFILE','name':'Profil couverture','service':self.service,
            'reference_samples':1,'protocol_reference':'SOP-COV'})
        self.rule=save_rule(self.ops,self.profile.pk,{'article':self.article,'quantity':Decimal(1),
            'unit':self.unit,'basis':'BATCH'},expected=self.profile.version)
        self.profile.refresh_from_db()
        source=source_samples(self.ops,self.request_obj)[0]
        self.run=create_run(self.ops,request=self.request_obj,profile=self.profile,code='COV-RUN-1',
            name='Série couverture',sample_count=1,planned_on=timezone.localdate(),source_keys=[source['key']])

    def test_lists_detail_and_profile_pages(self):
        request=req(self.rf,self.ops,path='/?q=COV')
        request.GET=request.GET.copy();request.GET['q']='COV'
        with patch('erp.consumption_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(consumption_views.run_list(request).status_code,200)
            self.assertEqual(consumption_views.profile_list(request).status_code,200)
            self.assertEqual(consumption_views.profile_detail(request,self.profile.pk).status_code,200)
        request=req(self.rf,self.outsider)
        with self.assertRaises(PermissionDenied):
            consumption_views.run_list(request)

        request=req(self.rf,self.ops)
        with patch('erp.consumption_views.reservation_proposal',return_value={'allocations':[],'shortages':[]}), \
             patch('erp.consumption_views.render',return_value=HttpResponse('ok')) as render:
            self.assertEqual(consumption_views.run_detail(request,self.run.pk).status_code,200)
            self.assertIn('requirements',render.call_args.args[2])

    def test_run_create_and_operations_cover_all_routes(self):
        create_form=FakeForm({'profile':self.profile,'code':'NEW-COV','name':'Nouvelle',
                              'sample_count':1,'planned_on':timezone.localdate(),
                              'source_keys':[],'samples':[]})
        request=req(self.rf,self.ops,'post','/run/new/',{'x':'1'})
        with patch('erp.consumption_views.forms.RunCreateForm',return_value=create_form), \
             patch('erp.consumption_views.create_run',return_value=self.run) as service:
            self.assertEqual(consumption_views.run_create(request,self.request_obj.pk).status_code,302)
            service.assert_called_once()
        with patch('erp.consumption_views.forms.RunCreateForm',return_value=create_form), \
             patch('erp.consumption_views.create_run',side_effect=ValidationError('bad')), \
             patch('erp.consumption_views.add_validation') as add, \
             patch('erp.consumption_views._form',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(consumption_views.run_create(request,self.request_obj.pk).status_code,400)
            add.assert_called_once()

        requirement=self.run.requirements.first()
        container,_move,_values=self.receive(quantity=10)
        reserve_form=FakeForm({'expected_version':self.run.version,'key':uuid.uuid4(),
            'requirement':requirement,'container':container,'amount':Decimal(1),'reason':'reserve'})
        confirm_form=FakeForm({'expected_version':self.run.version,'key':uuid.uuid4(),
            'actual_x':Decimal('0.5'),'bio_x':Decimal('1'),'reason':'confirm','confirmed':True},
            actual_fields={'a':'actual_x'},biological_fields={'b':'bio_x'})
        cancel_form=FakeForm({'expected_version':self.run.version,'key':uuid.uuid4(),'reason':'cancel'})
        configs=[('reserve','RunReserveForm',reserve_form,'reserve_run'),
                 ('confirm','RunConfirmForm',confirm_form,'confirm_run'),
                 ('cancel','RunCancelForm',cancel_form,'cancel_run')]
        for operation,form_name,form,target in configs:
            request=req(self.rf,self.ops,'post','/op/',{'x':'1'})
            with patch('erp.consumption_views.forms.'+form_name,return_value=form), \
                 patch('erp.consumption_views.'+target) as service:
                self.assertEqual(consumption_views.run_operation(request,self.run.pk,operation).status_code,302)
                service.assert_called_once()
            with patch('erp.consumption_views.forms.'+form_name,return_value=form), \
                 patch('erp.consumption_views.'+target,side_effect=ValidationError('bad')), \
                 patch('erp.consumption_views.add_validation') as add, \
                 patch('erp.consumption_views._form',return_value=HttpResponse('bad',status=400)):
                self.assertEqual(consumption_views.run_operation(request,self.run.pk,operation).status_code,400)
                add.assert_called_once()
        request=req(self.rf,self.ops)
        with self.assertRaises(Http404):
            consumption_views.run_operation(request,self.run.pk,'unknown')

    def test_profile_and_rule_edit_success_and_error_paths(self):
        request=req(self.rf,self.ops,'post','/profile/',{'x':'1'})
        form=FakeForm({'expected_version':None,'code':'P2','name':'P2','service':self.service,
                       'reference_samples':1,'protocol_reference':'SOP'})
        with patch('erp.consumption_views.forms.ProfileForm',return_value=form), \
             patch('erp.consumption_views.save_profile',return_value=self.profile):
            self.assertEqual(consumption_views.profile_edit(request).status_code,302)
        with patch('erp.consumption_views.forms.ProfileForm',return_value=form), \
             patch('erp.consumption_views.save_profile',side_effect=ValidationError('bad')), \
             patch('erp.consumption_views.add_validation') as add, \
             patch('erp.consumption_views._form',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(consumption_views.profile_edit(request).status_code,400)
            add.assert_called_once()

        rule_form=FakeForm({'expected_version':self.profile.version,'article':self.article,
                            'quantity':Decimal(1),'unit':self.unit,'basis':'BATCH','active':True})
        with patch('erp.consumption_views.forms.RuleForm',return_value=rule_form), \
             patch('erp.consumption_views.save_rule') as service:
            self.assertEqual(consumption_views.rule_edit(request,self.profile.pk).status_code,302)
            service.assert_called_once()
        with patch('erp.consumption_views.forms.RuleForm',return_value=rule_form), \
             patch('erp.consumption_views.save_rule',side_effect=ValidationError('bad')), \
             patch('erp.consumption_views.add_validation') as add, \
             patch('erp.consumption_views._form',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(consumption_views.rule_edit(request,self.profile.pk).status_code,400)
            add.assert_called_once()


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BiobankViewCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.rf=RequestFactory()
        self.box=save_location(self.admin,{'code':'COVBOX','name':'Boîte couverture','kind':self.storage_kind,
            'parent':self.freezer,'grid_rows':2,'grid_columns':2})
        self.target=save_location(self.admin,{'code':'COVBOX2','name':'Boîte cible','kind':self.storage_kind,
            'parent':self.freezer,'grid_rows':2,'grid_columns':2})
        self.position=self.box.positions.order_by('row','column').first()
        self.target_position=self.target.positions.order_by('row','column').first()
        self.sample=receive_sample(self.ops,key=uuid.uuid4(),code='COV-SAMPLE',amount=Decimal(10),
            unit=self.ul,location=self.box,position=self.position,received_on=timezone.localdate(),
            reason='Réception couverture')
        self.service=Service.objects.create(code='BIO-COV',name='Biobanque couverture')
        member,_=MemberProfile.objects.get_or_create(user=self.operator)
        self.request_obj=Request.objects.create(requester=self.outsider,assigned_to=member,service=self.service,
            title='Source couverture',status='IN_PROGRESS',sample_table=[{'sample_code':'SRC1','quantity':'5','quantity_unit':'µL'}])

    def test_lists_sources_initial_detail_positions_and_maps(self):
        request=req(self.rf,self.ops,path='/?q=COV&state=STORED')
        request.GET=request.GET.copy();request.GET.update({'q':'COV','state':'STORED'})
        with patch('erp.biobank_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(biobank_views.sample_list(request).status_code,200)
            self.assertEqual(biobank_views.sample_detail(request,self.sample.pk).status_code,200)
            self.assertEqual(biobank_views.storage_maps(request).status_code,200)
            self.assertEqual(biobank_views.storage_grid(request,self.box.pk).status_code,200)

        source={'sample_type':'DNA','matrix':'serum','preservation':'cold','collected_on':None,
                'declared_unit':'µL','declared_quantity':'2.5'}
        initial=biobank_views.source_initial(source)
        self.assertEqual(initial['amount'],Decimal('2.5'))
        source['declared_quantity']='bad'
        self.assertNotIn('amount',biobank_views.source_initial(source))
        source['declared_unit']='unknown'
        self.assertNotIn('amount',biobank_views.source_initial(source))

        with patch('erp.biobank_views.source_samples',return_value=[{'code':'SRC1'}]), \
             patch('erp.biobank_views.render',return_value=HttpResponse('ok')) as render:
            self.assertEqual(biobank_views.source_list(request,self.request_obj.pk).status_code,200)
            self.assertFalse(render.call_args.args[2]['source_error'])
        with patch('erp.biobank_views.source_samples',side_effect=ValidationError('bad')), \
             patch('erp.biobank_views.render',return_value=HttpResponse('ok')) as render:
            self.assertEqual(biobank_views.source_list(request,self.request_obj.pk).status_code,200)
            self.assertTrue(render.call_args.args[2]['source_error'])

        request=req(self.rf,self.ops,path='/?location='+str(self.box.pk))
        request.GET=request.GET.copy();request.GET['location']=str(self.box.pk)
        response=biobank_views.position_options(request)
        self.assertEqual(response.status_code,200)
        request=req(self.rf,self.ops,path='/?parent='+str(self.freezer.pk))
        request.GET=request.GET.copy();request.GET['parent']=str(self.freezer.pk)
        with patch('erp.biobank_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(biobank_views.storage_maps(request).status_code,200)

    def test_sample_receive_and_operations_orchestration(self):
        source={'key':'src-key','fingerprint':'f'*64,'sample_type':'DNA','matrix':'serum','preservation':'cold',
                'collected_on':None,'declared_unit':'µL','declared_quantity':'2','code':'SRC1'}
        form=FakeForm({'key':uuid.uuid4(),'code':'NEW','amount':Decimal(2),'unit':self.ul,
                       'location':self.box,'position':self.box.positions.order_by('row','column')[1],
                       'received_on':timezone.localdate(),'reason':'reçu'},fields={})
        request=req(self.rf,self.ops,'post','/receive/',{'x':'1'})
        with patch('erp.biobank_views.forms.SampleReceiveForm',return_value=form), \
             patch('erp.biobank_views.receive_sample',return_value=self.sample) as service:
            self.assertEqual(biobank_views.sample_receive(request).status_code,302)
            service.assert_called_once()
        with patch('erp.biobank_views.forms.SampleReceiveForm',return_value=form), \
             patch('erp.biobank_views.receive_sample',side_effect=ValidationError('bad')), \
             patch('erp.biobank_views.add_validation') as add, \
             patch('erp.biobank_views._form',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(biobank_views.sample_receive(request).status_code,400)
            add.assert_called_once()

        with patch('erp.biobank_views.source_samples',return_value=[source]), \
             patch('erp.biobank_views.forms.SampleReceiveForm',return_value=form), \
             patch('erp.biobank_views.receive_sample',return_value=self.sample) as service:
            self.assertEqual(biobank_views.sample_receive(request,self.request_obj.pk,'src-key').status_code,302)
            self.assertEqual(service.call_args.kwargs['source_key'],'src-key')

        operation_forms={
          'transfer':FakeForm({'expected_version':self.sample.version,'destination':self.target,
                               'position':self.target_position,'reason':'move','key':uuid.uuid4()}),
          'aliquot':FakeForm({'expected_version':self.sample.version,'destination':self.target,
                              'position':self.target_position,'code':'A1','amount':Decimal(1),'unit':self.ul,
                              'reason':'aliquot','key':uuid.uuid4()}),
          'action':FakeForm({'expected_version':self.sample.version,'action':'FREEZE','amount':Decimal(1),
                             'unit':self.ul,'reason':'action','key':uuid.uuid4()})
        }
        targets={'transfer':'transfer_sample','aliquot':'aliquot_sample','action':'sample_action'}
        for op in operation_forms:
            request=req(self.rf,self.ops,'post','/op/',{'x':'1'})
            fake=operation_forms[op]
            child=SimpleNamespace(pk=uuid.uuid4())
            with patch('erp.biobank_views.forms.'+{'transfer':'SampleTransferForm','aliquot':'AliquotForm','action':'SampleActionForm'}[op],
                       return_value=fake), \
                 patch('erp.biobank_views.'+targets[op],return_value=child) as service:
                self.assertEqual(biobank_views.sample_operation(request,self.sample.pk,op).status_code,302)
                service.assert_called_once()
        with self.assertRaises(Http404):
            biobank_views.sample_operation(req(self.rf,self.ops),self.sample.pk,'missing')

    def test_position_temperature_incident_and_mass_transfer_paths(self):
        reserve_form=FakeForm({'assignee':self.operator,'until':timezone.now()+timedelta(hours=1),'reason':'reserve'})
        request=req(self.rf,self.ops,'post','/reserve/',{'x':'1'})
        with patch('erp.biobank_views.forms.PositionReservationForm',return_value=reserve_form), \
             patch('erp.biobank_views.reserve_position') as service:
            self.assertEqual(biobank_views.position_reserve(request,self.target_position.pk).status_code,302)
            service.assert_called_once()

        temp=FakeForm({'location':self.box,'value':Decimal('-80'),'recorded_at':timezone.now(),'note':'ok'})
        request=req(self.rf,self.ops,'post','/temp/',{'x':'1'})
        with patch('erp.biobank_views.forms.TemperatureForm',return_value=temp), \
             patch('erp.biobank_views.record_temperature') as service:
            self.assertEqual(biobank_views.temperature_create(request).status_code,302)
            service.assert_called_once()

        incident_form=FakeForm({'location':self.box,'kind':'TEMPERATURE','reason':'alarm'})
        request=req(self.rf,self.ops,'post','/inc/',{'x':'1'})
        with patch('erp.biobank_views.forms.IncidentForm',return_value=incident_form), \
             patch('erp.biobank_views.create_incident') as service:
            self.assertEqual(biobank_views.cold_incidents(request).status_code,302)
            service.assert_called_once()
        incident=Mock(pk=uuid.uuid4(),version=1,location=self.box)
        resolution=FakeForm({'expected_version':1,'reason':'résolu'})
        with patch('erp.biobank_views.get_object_or_404',return_value=incident), \
             patch('erp.biobank_views.forms.IncidentResolutionForm',return_value=resolution), \
             patch('erp.biobank_views.resolve_incident') as service:
            self.assertEqual(biobank_views.incident_resolve(request,incident.pk).status_code,302)
            service.assert_called_once()

        preview_form=FakeForm({'source':self.box,'destination':self.target,'preview_token':''})
        request=req(self.rf,self.ops,'post','/mass/',{'action':'preview'})
        with patch('erp.biobank_views.forms.MassTransferForm',side_effect=[preview_form,FakeForm()]), \
             patch('erp.biobank_views.transfer_plan',return_value=[{'sample':'x'}]), \
             patch('erp.biobank_views.render',return_value=HttpResponse('ok')) as render:
            self.assertEqual(biobank_views.mass_transfer(request).status_code,200)
            self.assertIsNotNone(render.call_args.args[2]['preview'])

        token=signing.dumps({'actor':self.ops.pk,'source':str(self.box.pk),'destination':str(self.target.pk),
                             'mapping':[{'sample':'x'}]},salt='erp.biobank.transfer',compress=True)
        apply_form=FakeForm({'source':self.box,'destination':self.target,'preview_token':token})
        transfer=SimpleNamespace(pk=uuid.uuid4())
        request=req(self.rf,self.ops,'post','/mass/',{'action':'apply'})
        with patch('erp.biobank_views.forms.MassTransferForm',return_value=apply_form), \
             patch('erp.biobank_views.apply_transfer_plan',return_value=transfer) as service:
            self.assertEqual(biobank_views.mass_transfer(request).status_code,302)
            service.assert_called_once()
        bad=FakeForm({'source':self.box,'destination':self.target,'preview_token':'broken'})
        with patch('erp.biobank_views.forms.MassTransferForm',return_value=bad), \
             patch('erp.biobank_views.render',return_value=HttpResponse('bad',status=400)):
            self.assertEqual(biobank_views.mass_transfer(request).status_code,400)

        fake_transfer=SimpleNamespace(pk=uuid.uuid4())
        with patch('erp.biobank_views.get_object_or_404',return_value=fake_transfer), \
             patch('erp.biobank_views.render',return_value=HttpResponse('ok')):
            self.assertEqual(biobank_views.mass_transfer_detail(req(self.rf,self.ops),fake_transfer.pk).status_code,200)
