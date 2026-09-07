"""End-to-end locale selection and catalogue publication contracts."""
import copy
import importlib
import io
from decimal import Decimal
from unittest.mock import patch
from django.apps import apps
from django.contrib import admin
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils.translation import override
from django.utils.html import escape
from accounts.models import User
from core.models import Service
from core.forms import ServiceTextForm, SERVICE_TEXT_FIELDS
from core.registry import load_service_registry
from core.catalogue import catalogue_text, catalogue_items, catalogue_translations


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class TrilingualCatalogueTests(TestCase):
    def setUp(self):
        self.registry = load_service_registry()
        self.admin = User.objects.create_user('translation-admin', role='SUPER_ADMIN', is_staff=True, is_superuser=True)

    def seed(self):
        call_command('seed_services', stdout=io.StringIO())

    def translations(self):
        return {'name_fr': 'Analyse française', 'description_fr': 'Description française complète.',
                'name_ar': 'تحليل مخبري', 'description_ar': 'وصف كامل للتحليل المخبري.',
                'name_en': 'Laboratory analysis', 'description_en': 'Complete laboratory analysis description.'}

    def test_catalogue_and_detail_render_all_eight_services_in_each_language(self):
        self.seed()
        for lang in ('fr', 'ar', 'en'):
            self.client.cookies['django_language'] = lang
            response = self.client.get('/services/')
            self.assertEqual(response.status_code, 200)
            for code, definition in self.registry.items():
                texts = definition['translations'][lang]
                self.assertContains(response, escape(texts['name']))
                detail = self.client.get(reverse('service_detail', args=[code]))
                self.assertContains(detail, escape(texts['name']))
                self.assertContains(detail, escape(texts['description']))
                with override(lang):
                    for item in catalogue_items(definition['compliance']):
                        self.assertContains(detail, escape(item))
            self.assertContains(response, 'dir="rtl"' if lang == 'ar' else 'dir="ltr"')

    def test_import_is_locale_independent_and_preserves_admin_data_on_restart(self):
        with override('ar'):
            self.seed()
        service = Service.objects.get(code='EGTP-CAN')
        service.name_fr = 'Nom personnalisé'; service.description_ar = 'وصف مخصص'
        service.genoclab_price = Decimal('987.65'); service.active = False
        service.channel_availability = 'IBTIKAR'; service.turnaround_days = 19
        service.name_en = ''; service.save()
        self.seed()
        service.refresh_from_db()
        self.assertEqual(service.name_fr, 'Nom personnalisé')
        self.assertEqual(service.description_ar, 'وصف مخصص')
        self.assertEqual(service.name_en, self.registry[service.code]['translations']['en']['name'])
        self.assertEqual(service.genoclab_price, Decimal('987.65'))
        self.assertFalse(service.active)
        self.assertEqual(service.channel_availability, 'IBTIKAR')
        self.assertEqual(service.turnaround_days, 19)
        self.seed()  # A further deployment remains idempotent.
        service.refresh_from_db(); self.assertEqual(service.genoclab_price, Decimal('987.65'))

    def test_incomplete_registry_rejected_before_any_database_mutation(self):
        invalid = copy.deepcopy(self.registry)
        invalid['MISSING'] = {'translations': {'fr': {'name': 'Incomplet'}}}
        with patch('core.management.commands.seed_services.load_service_registry', return_value=invalid):
            with self.assertRaisesMessage(CommandError, 'translation required'):
                self.seed()
        self.assertEqual(Service.objects.count(), 0)

    def test_future_creation_requires_every_language_even_when_browser_validation_is_bypassed(self):
        self.client.force_login(self.admin)
        for field in SERVICE_TEXT_FIELDS:
            data = {'code': 'NEW-TRI', **self.translations()}; data[field] = ' \t '
            self.client.post(reverse('dashboard:superadmin_service_create'), data)
            self.assertFalse(Service.objects.filter(code='NEW-TRI').exists(), field)
        data = {'code': 'NEW-TRI', **self.translations()}
        self.client.cookies['django_language'] = 'ar'
        response = self.client.post(reverse('dashboard:superadmin_service_create'), data)
        self.assertEqual(response.status_code, 302)
        service = Service.objects.get(code='NEW-TRI')
        for field, value in self.translations().items():
            self.assertEqual(getattr(service, field), value)
        self.client.post(reverse('dashboard:superadmin_service_create'), data)
        self.assertEqual(Service.objects.filter(code='NEW-TRI').count(), 1)

    def test_edit_rejects_incomplete_translation_without_changing_prices(self):
        self.seed(); service = Service.objects.get(code='EGTP-CAN')
        self.client.force_login(self.admin)
        before = service.genoclab_price
        data = {**self.translations(), 'description_ar': '', 'genoclab_price': '12'}
        url = reverse('dashboard:superadmin_service_edit', args=[service.pk])
        self.client.post(url, data)
        service.refresh_from_db(); self.assertEqual(service.genoclab_price, before)
        self.client.post(url, self.translations())
        service.refresh_from_db()
        for field, value in self.translations().items():
            self.assertEqual(getattr(service, field), value)
        page = self.client.get(url)
        for field in SERVICE_TEXT_FIELDS:
            self.assertContains(page, f'name="{field}"')

    def test_django_admin_obeys_same_required_translation_contract(self):
        request = RequestFactory().get('/admin/core/service/add/'); request.user = self.admin
        form_class = admin.site._registry[Service].get_form(request)
        form = form_class()
        for field in SERVICE_TEXT_FIELDS:
            self.assertTrue(form.fields[field].required)
        for field in SERVICE_TEXT_FIELDS:
            data = self.translations(); data[field] = ' '
            text_form = ServiceTextForm(data)
            self.assertFalse(text_form.is_valid()); self.assertIn(field, text_form.errors)

    def test_migration_corrects_copied_source_preserves_custom_text_and_prices(self):
        migration = importlib.import_module('core.migrations.0031_trilingual_catalogue')
        text = migration.TRANSLATIONS['EGTP-CAN']
        service = Service.objects.create(code='EGTP-CAN', name_fr=text['name_en'], name_ar=text['name_en'],
                                         name_en='Custom name', description_ar=' ', genoclab_price=45)
        migration.translate_catalogue(apps, connection.schema_editor(atomic=False))
        service.refresh_from_db()
        self.assertEqual(service.name_fr, text['name_fr']); self.assertEqual(service.name_ar, text['name_ar'])
        self.assertEqual(service.name_en, 'Custom name'); self.assertEqual(service.description_ar, text['description_ar'])
        self.assertEqual(service.genoclab_price, 45)

    def test_dynamic_form_translates_labels_without_changing_option_values_or_registry(self):
        self.seed(); original = copy.deepcopy(self.registry)
        for lang, label in [('ar', 'مفرد'), ('fr', 'Simple'), ('en', 'Single')]:
            self.client.cookies['django_language'] = lang
            response = self.client.get(reverse('dashboard:service_form_fragment', args=['EGTP-IMT']))
            self.assertRegex(response.content.decode(), f'value="Simple"[^>]*>{label}</option>')
        self.assertEqual(self.registry, original)

    def test_catalogue_copy_covers_all_displayed_registry_labels_and_options(self):
        neutral = {'% GC', '008', '1', '1275', '16S rRNA', '18S rRNA', '2', '25 µL', '3', '50 µL',
                   'DNA', 'EPS', 'F', 'F+R', 'F+R-long', 'GeneRuler 1 kb Plus', 'ITS', 'RNA', 'Tm (°C)'}
        translations = catalogue_translations()
        for code, definition in self.registry.items():
            fields = definition.get('parameters', []) + definition.get('sample_table', {}).get('columns', [])
            for field in fields:
                for value in [field.get('label', field['name']), *field.get('options', [])]:
                    self.assertTrue(str(value) in set(translations) | neutral, (code, value))

    def test_nested_content_unknown_values_and_regional_languages_are_safe(self):
        with override('ar-dz'):
            self.assertEqual(catalogue_text('  Standard  '), 'قياسي')
            self.assertEqual(catalogue_text(4), 4)
            self.assertEqual(catalogue_text('<script>'), '<script>')
            self.assertEqual(catalogue_items(None), [])
            self.assertEqual(catalogue_items({'Code': ['Standard', None]}), ['الرمز : قياسي'])
        with override('de'):
            self.assertEqual(catalogue_text('Bacterium'), 'Bactérie')

    def test_custom_field_labels_require_and_render_three_explicit_translations(self):
        from core.forms import ServiceFieldAdminForm
        self.seed(); service = Service.objects.get(code='EGTP-CAN')
        self.client.force_login(self.admin)
        url = reverse('dashboard:superadmin_service_edit', args=[service.pk])
        data = {'field_name': ['additional'], 'field_label_fr': ['Détail'],
                'field_label_en': ['Detail'], 'field_label_ar': ['التفصيل']}
        incomplete = dict(data); incomplete.pop('field_label_ar')
        self.client.post(url, incomplete)
        self.assertFalse(service.custom_fields.exists())
        self.client.post(url, data)
        field = service.custom_fields.get()
        self.assertEqual(field.label_ar, 'التفصيل')
        self.assertEqual(field.label_en, 'Detail')
        self.assertEqual(field.label_fr, 'Détail')
        for lang in ('fr', 'ar', 'en'):
            self.assertTrue(ServiceFieldAdminForm().fields[f'label_{lang}'].required)
        self.client.cookies['django_language'] = 'ar'
        response = self.client.get(reverse('dashboard:service_form_fragment', args=[service.code]))
        self.assertContains(response, 'التفصيل')
