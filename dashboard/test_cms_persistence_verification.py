import json
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import translation
from django.db import DatabaseError
from lxml import html
from accounts.models import User, Technique
from core.models import Service, ServicePricing, ServiceFormField, PlatformContent, Announcement, PaymentMethod


@override_settings(SECURE_SSL_REDIRECT=False, RATE_LIMIT_BACKEND='cache',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
              'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CmsPersistenceVerificationTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_user(username='verification-admin',role='SUPER_ADMIN',password='Test-session-only!27')
        self.service=Service.objects.create(code='VERIFY-PERSISTENCE',name_fr='Recette',name_en='Acceptance',name_ar='اختبار',ibtikar_price=Decimal('1234.56'),genoclab_price=Decimal('9876.54'))
        self.client.force_login(self.admin)

    def new_session(self):
        self.client.logout();self.client=Client();self.client.force_login(self.admin)

    def endpoint(self,name,*args):
        return reverse('dashboard:'+name,args=args)

    def test_service_amounts_roundtrip_in_all_languages_and_new_sessions(self):
        url=self.endpoint('superadmin_service_edit',self.service.pk)
        for language in ('fr','en','ar'):
            self.client.cookies['django_language']=language
            response=self.client.post(url,{'ibtikar_price':'2345.67','genoclab_price':'8765.43','turnaround_days':'0'})
            self.assertEqual(response.status_code,302)
            self.service.refresh_from_db()
            self.assertEqual(self.service.ibtikar_price,Decimal('2345.67'))
            self.assertEqual(self.service.turnaround_days,0)
            self.new_session();self.client.cookies['django_language']=language
            page=html.fromstring(self.client.get(url).content)
            self.assertEqual(page.xpath('//input[@name="ibtikar_price"]/@value'),['2345.67'])
            self.assertEqual(page.xpath('//input[@name="genoclab_price"]/@value'),['8765.43'])

    def test_omitted_custom_fields_are_not_interpreted_as_delete(self):
        field=ServiceFormField.objects.create(service=self.service,name='preserved',label_fr='Conservé',label_en='Retained',label_ar='محفوظ')
        self.client.post(self.endpoint('superadmin_service_edit',self.service.pk),{'ibtikar_price':'45.67'})
        self.assertTrue(ServiceFormField.objects.filter(pk=field.pk).exists())

    def test_omitted_pricing_controls_do_not_remove_saved_configuration(self):
        config={'base_price':{'non_pathogenic':150.25},'multipliers':{'double':2.5},'multiplier_param':'mode'}
        self.service.pricing_data=config;self.service.save()
        self.client.post(self.endpoint('superadmin_service_edit',self.service.pk),{'ibtikar_price':'45.67'})
        self.service.refresh_from_db();self.assertEqual(self.service.pricing_data,config)

    def test_tariff_crud_preserves_all_fields_and_new_session(self):
        for channel in ('IBTIKAR','GENOCLAB','OHB','BOTH'):
            values={'name':'Tarif '+channel,'pricing_type':'BASE','channel':channel,'amount':'128.75','unit':'unité','description':'Description durable','min_quantity':'2','max_quantity':'6','min_amount':'0','max_amount':'1000.50','priority':'3','is_active':'on','valid_from':'2026-01-01','valid_until':'2027-12-31'}
            response=self.client.post(self.endpoint('pricing_add_api',self.service.pk),values)
            self.assertEqual(response.status_code,201,response.content)
            pk=response.json()['config']['id'];self.new_session()
            tier=ServicePricing.objects.get(pk=pk)
            self.assertEqual(tier.amount,Decimal('128.75'));self.assertEqual(tier.min_amount,Decimal('0'))
            rows=self.client.get(self.endpoint('pricing_list_api',self.service.pk)).json()['configs']
            saved=next(r for r in rows if r['id']==pk)
            for field in ('name','unit','description','channel','valid_from','valid_until'):
                self.assertEqual(saved[field],values[field])
            values.update(amount='247.25',name='Tarif modifié',is_active='')
            self.assertEqual(self.client.post(self.endpoint('pricing_update_api',pk),values).status_code,200)
            self.new_session();tier.refresh_from_db()
            self.assertEqual(tier.amount,Decimal('247.25'));self.assertFalse(tier.is_active)
            self.assertEqual(self.client.post(self.endpoint('pricing_delete_api',pk)).status_code,200)
            self.assertFalse(ServicePricing.objects.filter(pk=pk).exists())

    def test_tariff_invalid_precision_returns_validation_error_without_write(self):
        for amount in ('12.345','1234567890123.45','NaN','Infinity','-1'):
            response=self.client.post(self.endpoint('pricing_add_api',self.service.pk),{'name':'Invalid','amount':amount,'is_active':'on'})
            self.assertEqual(response.status_code,400,(amount,response.content[:500]))
            self.assertFalse(response.json().get('ok',False))
        self.assertEqual(ServicePricing.objects.count(),0)

    def test_cms_three_languages_create_update_delete_and_fresh_session(self):
        url=self.endpoint('superadmin_content_save')
        values={'key':'hero_title','value_fr':'Accueil de recette','value_en':'Acceptance home','value_ar':'الصفحة الاختبارية'}
        self.assertEqual(self.client.post(url,values).status_code,302)
        self.new_session()
        self.assertEqual(dict(PlatformContent.objects.filter(key='hero_title').values_list('lang','value')),{'fr':values['value_fr'],'en':values['value_en'],'ar':values['value_ar']})
        public=Client()
        for lang in ('fr','en','ar'):
            public.cookies['django_language']=lang
            self.assertContains(public.get('/'),values['value_'+lang])
        values['value_fr']='Accueil modifié'
        self.assertEqual(self.client.post(url,values).status_code,302)
        public.cookies['django_language']='fr';self.assertContains(public.get('/'),'Accueil modifié')
        self.assertEqual(self.client.post(self.endpoint('superadmin_content_delete_key'),{'key':'hero_title'}).status_code,302)
        self.assertFalse(PlatformContent.objects.filter(key='hero_title').exists())
        self.assertNotContains(public.get('/'),'Accueil modifié')

    def test_cms_partial_language_update_does_not_erase_other_languages(self):
        for lang,value in (('fr','Avant'),('en','Before'),('ar','قبل')):
            PlatformContent.objects.create(key='contact_email',lang=lang,value=value)
        self.client.post(self.endpoint('superadmin_content_save'),{'key':'contact_email','value_fr':'Après'})
        rows=dict(PlatformContent.objects.filter(key='contact_email').values_list('lang','value'))
        self.assertEqual(rows,{'fr':'Après','en':'Before','ar':'قبل'})
        self.client.post(self.endpoint('superadmin_content_save'),{'key':'contact_email','value_en':''})
        self.assertEqual(PlatformContent.objects.get(key='contact_email',lang='en').value,'')

    def test_content_multi_language_failure_rolls_back_without_success_message(self):
        create=PlatformContent.objects.update_or_create
        def fail_second(*args,**kwargs):
            if kwargs.get('lang')=='en':raise DatabaseError('Simulated interrupted write')
            return create(*args,**kwargs)
        self.client.raise_request_exception=False
        with patch('dashboard.views.superadmin.PlatformContent.objects.update_or_create',side_effect=fail_second),patch('dashboard.views.superadmin.messages.success') as success:
            response=self.client.post(self.endpoint('superadmin_content_save'),{'key':'atomic','value_fr':'A','value_en':'B','value_ar':'C'})
            self.assertEqual(response.status_code,302);success.assert_not_called()
        self.assertFalse(PlatformContent.objects.filter(key='atomic').exists())

    def test_cms_new_request_observes_external_update_without_worker_cache(self):
        from core.templatetags.cms import cms
        PlatformContent.objects.create(key='freshness',lang='fr',value='old')
        with translation.override('fr'):
            self.assertEqual(cms('freshness'),'old')
            PlatformContent.objects.filter(key='freshness').update(value='new')
            self.assertEqual(cms('freshness'),'new')

    def test_techniques_crud_and_membership_survive_new_session(self):
        url=self.endpoint('superadmin_technique_create')
        self.client.post(url,{'name':'Technique de recette','category':'Équipement'})
        item=Technique.objects.get();self.new_session()
        self.client.post(self.endpoint('superadmin_technique_edit',item.pk),{'name':'Technique modifiée','category':'Analyse'})
        item.refresh_from_db();self.assertEqual(item.name_fr,'Technique modifiée')
        self.client.post(self.endpoint('superadmin_technique_delete',item.pk));item.refresh_from_db();self.assertFalse(item.active)
        self.client.post(self.endpoint('superadmin_technique_reactivate',item.pk));item.refresh_from_db();self.assertTrue(item.active)

    def test_user_create_edit_and_deactivation_persist(self):
        values={'username':'cms-member','email':'member@example.test','role':'MEMBER','password':'Specific-test-password!49','first_name':'Initial','last_name':'Member','phone':'0555000000','organization':'Institution'}
        self.assertEqual(self.client.post(self.endpoint('superadmin_user_create'),values).status_code,302)
        user=User.objects.get(username='cms-member');self.assertTrue(hasattr(user,'member_profile'))
        self.new_session();values.update(first_name='Updated',laboratory='Laboratory',supervisor='Supervisor',student_level='Doctorant')
        self.assertEqual(self.client.post(self.endpoint('superadmin_user_edit',user.pk),values).status_code,302)
        user.refresh_from_db();self.assertEqual(user.first_name,'Updated');self.assertEqual(user.laboratory,'Laboratory')
        self.assertContains(self.client.get(self.endpoint('superadmin_user_edit',user.pk)),'Updated')
        self.client.post(self.endpoint('superadmin_user_toggle',user.pk));user.refresh_from_db();self.assertFalse(user.is_active)
        self.client.post(self.endpoint('superadmin_user_toggle',user.pk));user.refresh_from_db();self.assertTrue(user.is_active)

    def test_announcement_creation_toggle_and_deletion(self):
        self.client.post(self.endpoint('superadmin_announcement_create'),{'title':'Durable announcement','message':'Durable message','audience':'STAFF','level':'warning'})
        item=Announcement.objects.get();self.new_session()
        self.assertContains(self.client.get(self.endpoint('superadmin')),'Durable announcement')
        self.client.post(self.endpoint('superadmin_announcement_toggle',item.pk));item.refresh_from_db();self.assertFalse(item.active)
        self.client.post(self.endpoint('superadmin_announcement_delete',item.pk));self.assertFalse(Announcement.objects.filter(pk=item.pk).exists())

    def test_payment_method_repeated_creation_is_not_duplication(self):
        for _ in range(2):self.client.post(self.endpoint('superadmin_payment_method_create'),{'name':'Test bank transfer'})
        self.new_session();self.assertEqual(PaymentMethod.objects.filter(name='Test bank transfer').count(),1)
        self.assertContains(self.client.get(self.endpoint('superadmin')),'Test bank transfer')

    def test_unauthorised_write_cannot_change_a_tariff(self):
        outsider=User.objects.create_user(username='cms-outsider',role='REQUESTER',password=None)
        self.client.force_login(outsider)
        self.assertEqual(self.client.post(self.endpoint('pricing_add_api',self.service.pk),{'name':'Forbidden','amount':'100'}).status_code,403)
        self.assertEqual(ServicePricing.objects.count(),0)


    def test_technique_validation_and_database_failures_never_report_success(self):
        create_url=self.endpoint('superadmin_technique_create')
        before=Technique.objects.count()
        for data in ({'name':'','category':'X'},{'name':'X'*201,'category':'X'}):
            with patch('dashboard.views.superadmin.messages.success') as success:
                self.client.post(create_url,data);success.assert_not_called()
            self.assertEqual(Technique.objects.count(),before)
        existing=Technique.objects.create(name='Existing technique',category='A')
        with patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(create_url,{'name':existing.name,'category':'B'})
            success.assert_not_called()
        self.assertEqual(Technique.objects.filter(name=existing.name).count(),1)
        with patch('accounts.models.Technique.save',side_effect=DatabaseError('write failed')),patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(create_url,{'name':'Database failure technique','category':'C'})
            success.assert_not_called()
        self.assertFalse(Technique.objects.filter(name='Database failure technique').exists())
        other=Technique.objects.create(name='Other technique',category='B')
        with patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(self.endpoint('superadmin_technique_edit',existing.pk),{'name':other.name,'category':'Changed'})
            success.assert_not_called()
        existing.refresh_from_db();self.assertEqual(existing.name,'Existing technique')
        with patch('accounts.models.Technique.save',side_effect=DatabaseError('write failed')),patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(self.endpoint('superadmin_technique_edit',existing.pk),{'name':'Would not persist','category':'Changed'})
            success.assert_not_called()
        existing.refresh_from_db();self.assertEqual(existing.name,'Existing technique')

    def test_content_validation_readback_and_database_failures_are_atomic(self):
        save_url=self.endpoint('superadmin_content_save')
        update_url=self.endpoint('superadmin_content_update')
        too_long='K'*101
        for url,data in ((save_url,{'key':too_long,'value_fr':'x'}),(save_url,{'key':'no-values'}),(update_url,{'key':too_long,'lang':'fr','value':'x'})):
            with patch('dashboard.views.superadmin.messages.success') as success:
                self.client.post(url,data);success.assert_not_called()
        self.assertFalse(PlatformContent.objects.filter(key__in=[too_long,'no-values']).exists())
        with patch('dashboard.views.superadmin.PlatformContent.objects.update_or_create',side_effect=DatabaseError('write failed')),patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(update_url,{'key':'failed-update','lang':'fr','value':'x'});success.assert_not_called()
        self.assertFalse(PlatformContent.objects.filter(key='failed-update').exists())
        with patch('dashboard.views.superadmin.PlatformContent.objects.filter') as query,patch('dashboard.views.superadmin.messages.success') as success:
            query.return_value.values_list.return_value=[]
            self.client.post(save_url,{'key':'mismatch','value_fr':'expected'});success.assert_not_called()
        self.assertFalse(PlatformContent.objects.filter(key='mismatch').exists())
        fake=type('SavedValue',(),{'value':'wrong','key':'mismatch-single','lang':'fr'})()
        with patch('dashboard.views.superadmin.PlatformContent.objects.get',return_value=fake),patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(update_url,{'key':'mismatch-single','lang':'fr','value':'expected'});success.assert_not_called()
        self.assertFalse(PlatformContent.objects.filter(key='mismatch-single').exists())

    def test_announcement_validation_and_database_failure_do_not_claim_publish(self):
        url=self.endpoint('superadmin_announcement_create')
        for data in ({'title':'','message':'message'},{'title':'A'*201,'message':'message'}):
            with patch('dashboard.views.superadmin.messages.success') as success:
                self.client.post(url,data);success.assert_not_called()
        self.assertEqual(Announcement.objects.count(),0)
        with patch('core.models.Announcement.save',side_effect=DatabaseError('write failed')),patch('dashboard.views.superadmin.messages.success') as success:
            self.client.post(url,{'title':'Database failure','message':'Must not publish'})
            success.assert_not_called()
        self.assertEqual(Announcement.objects.count(),0)
