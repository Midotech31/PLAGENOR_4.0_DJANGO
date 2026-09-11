"""Equipment presentation is localized, optional and independent of billing."""
import io
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape
from django.utils.translation import override
from core.catalogue import catalogue_text
from core.models import Service
from core.registry import load_service_registry
from dashboard.templatetags.dashboard_extras import service_presentation


@override_settings(STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ServiceEquipmentTests(TestCase):
    def setUp(self):
        call_command('seed_services', stdout=io.StringIO())

    def test_equipment_and_overview_for_every_service_in_each_locale(self):
        for lang in ('fr', 'en', 'ar'):
            self.client.cookies['django_language'] = lang
            for code, definition in load_service_registry().items():
                service = Service.objects.get(code=code)
                presentation = definition['presentation']
                with override(lang):
                    figure = render_to_string('includes/service_equipment.html', {'service': service})
                    detail = render_to_string('includes/service_equipment_details.html', {'service': service})
                    self.assertIn(escape(catalogue_text(presentation['equipment'])), figure)
                    self.assertIn(escape(catalogue_text(presentation['overview'])), detail)
                self.assertNotIn(str(service.ibtikar_price), detail)

    def test_uploaded_photo_overrides_external_photo_on_every_public_page(self):
        service = Service.objects.get(code='EGTP-Illumina-Microbial-WGS')
        service.image = 'service_images/actual-miseq.jpg'
        service.save(update_fields=['image'])
        for url in ('/', reverse('services'), reverse('service_detail', args=[service.code]),
                    reverse('service_landing', args=[service.code])):
            response = self.client.get(url)
            self.assertContains(response, service.image.url)
            self.assertNotContains(response, '960px-Illumina_MiSeq_sequencer.jpg')

    def test_future_service_without_registry_or_photo_has_safe_fallback(self):
        service = Service(code='FUTURE', name='Future equipment')
        self.assertEqual(service_presentation(service), {})
        result = render_to_string('includes/service_equipment.html', {'service': service})
        self.assertNotIn('<img', result)
        self.assertIn('service-equipment-placeholder', result)

    def test_external_photo_has_provenance_and_no_referrer(self):
        service = Service.objects.get(code='EGTP-PCR')
        with override('en'):
            result = render_to_string('includes/service_equipment.html', {'service': service, 'detail': True})
        self.assertIn('referrerpolicy="no-referrer"', result)
        self.assertIn('https://commons.wikimedia.org/wiki/File:PCR_machine.jpg', result)
        self.assertIn('model not confirmed at PLAGENOR', result)
        self.assertIn('Illustrative photo taken outside PLAGENOR.', result)
