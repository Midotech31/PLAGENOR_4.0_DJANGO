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
