from unittest.mock import patch
from decimal import Decimal
from django.test import TestCase, override_settings
from django.db import DatabaseError
from django.urls import reverse
from accounts.models import User
from core.models import Service, ServicePricing


@override_settings(SECURE_SSL_REDIRECT=False, RATE_LIMIT_BACKEND='cache',
    STORAGES={'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PersistenceFailureTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_user(username='failure-test-admin',role='SUPER_ADMIN',password=None)
        self.service=Service.objects.create(code='FAILURE-TEST',name='Test',ibtikar_price=Decimal('123.45'))
        self.client.force_login(self.user)

    def url(self,name,*args):
        return reverse('dashboard:'+name,args=args)

    def test_tariff_write_failure_returns_error_and_keeps_database_unchanged(self):
        with patch('dashboard.views.pricing_api.ServicePricing.save', side_effect=DatabaseError('Test failure')):
            response=self.client.post(self.url('pricing_add_api',self.service.pk),{'name':'Unsaved','amount':'10.50','is_active':'on'})
        self.assertEqual(response.status_code,503)
        self.assertIn('error',response.json())
        self.assertEqual(ServicePricing.objects.count(),0)

    def test_tariff_update_and_delete_failure_preserve_original(self):
        tier=ServicePricing.objects.create(service=self.service,name='Original',amount=Decimal('12.50'))
        with patch('dashboard.views.pricing_api.ServicePricing.save',side_effect=DatabaseError('Test failure')):
            response=self.client.post(self.url('pricing_update_api',tier.pk),{'name':'Changed','amount':'25.00','is_active':'on'})
        self.assertEqual(response.status_code,503)
        tier.refresh_from_db();self.assertEqual(tier.amount,Decimal('12.50'))
        with patch('dashboard.views.pricing_api.ServicePricing.delete',side_effect=DatabaseError('Test failure')):
            response=self.client.post(self.url('pricing_delete_api',tier.pk))
        self.assertEqual(response.status_code,503)
        self.assertTrue(ServicePricing.objects.filter(pk=tier.pk).exists())

    def test_tariff_and_base_price_survive_save_reload_and_another_session(self):
        payload={'name':'Tarif par échantillon','pricing_type':'PER_SAMPLE',
                 'channel':'GENOCLAB','amount':'1250.50','unit':'échantillon',
                 'min_quantity':'1','priority':'2','is_active':'on'}
        created=self.client.post(self.url('pricing_add_api',self.service.pk),payload)
        self.assertEqual(created.status_code,201)
        tier_id=created.json()['config']['id']
        self.assertEqual(self.client.get(self.url('pricing_list_api',self.service.pk)).json()['configs'][0]['id'],tier_id)

        response=self.client.post(self.url('superadmin_service_edit',self.service.pk),{
            'ibtikar_price':'678.90','genoclab_price':'1500.00',
            'pd_base_non_pathogenic':'1200.00','pd_base_pathogenic':'1800.00',
            'pd_multiplier_param':'analysis_mode','pd_mult_key':['Simple'],
            'pd_mult_factor':['1.5'],
        })
        self.assertEqual(response.status_code,302)
        self.service.refresh_from_db()
        self.assertEqual(self.service.ibtikar_price,Decimal('678.90'))
        self.assertEqual(self.service.pricing_data['base_price'],{
            'non_pathogenic':1200.0,'pathogenic':1800.0})
        self.assertEqual(self.service.pricing_data['multipliers'],{'Simple':1.5})

        self.client.logout()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url('superadmin_service_edit',self.service.pk)).status_code,200)
        configs=self.client.get(self.url('pricing_list_api',self.service.pk)).json()['configs']
        self.assertEqual([(entry['id'],entry['amount']) for entry in configs],[(tier_id,1250.5)])
        changed=self.client.post(self.url('pricing_update_api',tier_id),{
            **payload,'amount':'1400.75'})
        self.assertEqual(changed.status_code,200)
        self.assertEqual(ServicePricing.objects.get(pk=tier_id).amount,Decimal('1400.75'))
        self.assertEqual(self.client.get(self.url('pricing_list_api',self.service.pk)).json()['configs'][0]['amount'],1400.75)

    def test_service_write_failure_retains_input_and_never_claims_success(self):
        with patch('dashboard.views.superadmin.Service.save',side_effect=DatabaseError('Test failure')),patch('dashboard.views.superadmin.messages.success') as success:
            response=self.client.post(self.url('superadmin_service_edit',self.service.pk),{'ibtikar_price':'678.90'})
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.context['submitted_editor_values']['ibtikar_price'],['678.90'])
        success.assert_not_called()
        self.service.refresh_from_db();self.assertEqual(self.service.ibtikar_price,Decimal('123.45'))

    def test_read_failure_is_not_swallowed_as_success(self):
        self.client.raise_request_exception=False
        with patch('dashboard.views.superadmin._edit_service',side_effect=DatabaseError('Test read failure')):
            response=self.client.get(self.url('superadmin_service_edit',self.service.pk))
        self.assertEqual(response.status_code,500)

    def test_payment_method_length_validation_does_not_claim_success(self):
        from core.models import PaymentMethod
        response=self.client.post(self.url('superadmin_payment_method_create'),{'name':'X'*101})
        self.assertEqual(response.status_code,302)
        self.assertEqual(PaymentMethod.objects.count(),0)

    def test_cms_requestless_render_and_database_error_have_defined_output(self):
        from types import SimpleNamespace
        from django.utils import translation
        from core.templatetags import cms
        with translation.override('fr'):
            self.assertEqual(cms.cms_tag({},'missing-key','Default text'),'Default text')
            with patch.object(cms,'_rows',side_effect=DatabaseError('Test failure')):
                self.assertEqual(cms.cms_tag({'request':SimpleNamespace()},'missing-key','Default text'),'Default text')

    def test_unknown_multiplier_parameter_is_rejected(self):
        from core.pricing import resolve_cost
        from core.exceptions import PricingConfigurationError
        self.service.pricing_data={'base_price':{'default':10},'multipliers':{'One':1},'multiplier_param':'declared_mode'}
        with self.assertRaises(PricingConfigurationError):
            resolve_cost(self.service,'GENOCLAB',sample_table=[{'id':1}],service_params={'declared_mode':'Unknown'})

    def test_malformed_multiplier_table_is_not_silently_ignored(self):
        from core.pricing import resolve_cost
        from core.exceptions import PricingConfigurationError
        self.service.pricing_data={'base_price':{'default':10},'multipliers':['not-a-map']}
        with self.assertRaises(PricingConfigurationError):
            resolve_cost(self.service,'GENOCLAB',sample_table=[{'id':1}])
