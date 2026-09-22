from django.test import TestCase, override_settings
from django.urls import reverse
from lxml import html

from core.models import Request, Service


@override_settings(SECURE_SSL_REDIRECT=False, RATE_LIMIT_BACKEND='cache',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class GuestChannelChoiceTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.service = Service.objects.create(code='EGTP-CAN', name='Contrôle qualité',
                                               channel_availability='BOTH', active=True)
        self.contact = {'guest_name': 'Demandeur de contrôle', 'guest_email': 'guest@example.test',
                        'guest_phone': '0555000000', 'organization': 'Institution de contrôle',
                        'service_id': str(self.service.pk), 'channel': 'IBTIKAR'}

    def test_channel_menu_contains_both_options_without_header_link(self):
        response = self.client.get(reverse('guest_submit'))
        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.content)
        self.assertEqual(page.xpath('//select[@name="channel"]/option/@value'), ['GENOCLAB', 'IBTIKAR'])
        self.assertFalse(page.xpath('//a[@href="/ibtikar/"]'))
        self.assertNotContains(response, 'id="ibtikar-guest-fields"')
        self.assertEqual(Request.objects.count(), 0)

    def test_ibtikar_selection_preserves_contact_and_opens_single_canonical_form(self):
        response = self.client.post(reverse('guest_submit'), self.contact)
        self.assertRedirects(response, reverse('ibtikar:new', args=[self.service.code]), fetch_redirect_response=False)
        self.assertEqual(Request.objects.count(), 0)
        saved = self.client.session['ibtikar_import_' + self.service.code]['applicant']
        self.assertEqual(saved['full_name'], self.contact['guest_name'])
        self.assertEqual(saved['email'], self.contact['guest_email'])
        self.assertEqual(saved['institution'], self.contact['organization'])
        response = self.client.get(response.url)
        self.assertContains(response, 'id="ibk-editor"')
        self.assertEqual(response.context['applicant_form'].initial['email'], self.contact['guest_email'])

    def test_error_keeps_the_selected_channel(self):
        response = self.client.post(reverse('guest_submit'), {**self.contact, 'guest_email': 'invalid'})
        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.content)
        self.assertEqual(page.xpath('//select[@name="channel"]/option[@selected]/@value'), ['IBTIKAR'])
        self.assertEqual(Request.objects.count(), 0)

    def test_internal_channel_and_ineligible_service_are_rejected(self):
        for values in ({**self.contact, 'channel': 'OHB'}, {**self.contact, 'service_id': 'invalid'}):
            self.assertEqual(self.client.post(reverse('guest_submit'), values).status_code, 200)
        self.service.channel_availability = 'GENOCLAB'
        self.service.save(update_fields=['channel_availability'])
        self.assertEqual(self.client.post(reverse('guest_submit'), self.contact).status_code, 200)
        self.assertEqual(Request.objects.count(), 0)
