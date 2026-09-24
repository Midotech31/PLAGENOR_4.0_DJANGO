import io
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from lxml import html

from accounts.models import User
from core.models import Request, Service


@override_settings(SECURE_SSL_REDIRECT=False, RATE_LIMIT_BACKEND='cache',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ServiceEntryPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_services', stdout=io.StringIO())

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def test_every_public_service_page_uses_the_same_two_entry_paths(self):
        for service in Service.objects.filter(active=True):
            for route in ('service_landing', 'service_detail'):
                with self.subTest(code=service.code, route=route):
                    response=self.client.get(reverse(route,args=[service.code]))
                    self.assertEqual(response.status_code,200)
                    page=html.fromstring(response.content)
                    self.assertEqual(page.xpath('//*[@data-access-mode]/@data-access-mode'),['account','guest'])
                    self.assertFalse(page.xpath('//a[starts-with(@href,"/ibtikar/")]'))
                    self.assertEqual(len(page.xpath('//h1')),1)
                    login=page.xpath('//a[@data-entry-action="login"]/@href')[0]
                    self.assertEqual(urlsplit(login).path,reverse('accounts:login'))
                    self.assertEqual(parse_qs(urlsplit(login).query),{'next':[reverse('service_landing',args=[service.code])]})
                    for action,route_name in [('register','accounts:register'),('guest','guest_submit')]:
                        target=page.xpath('//a[@data-entry-action="'+action+'"]/@href')[0]
                        self.assertEqual(urlsplit(target).path,reverse(route_name))
                        self.assertEqual(parse_qs(urlsplit(target).query),{'service':[service.code]})
        self.assertEqual(Request.objects.count(),0)

    def test_account_heading_and_entry_structure_are_available_in_three_languages(self):
        for lang,heading in [('fr','Avec un compte'),('en','With an account'),('ar','باستخدام حساب')]:
            with self.subTest(language=lang):
                self.client.cookies[settings.LANGUAGE_COOKIE_NAME]=lang
                response=self.client.get(reverse('service_landing',args=['EGTP-IMT']))
                self.assertContains(response,heading)
                page=html.fromstring(response.content)
                self.assertEqual(page.xpath('//*[@data-access-mode]/@data-access-mode'),['account','guest'])
                self.assertEqual(page.get('dir'),'rtl' if lang=='ar' else 'ltr')

    def test_authenticated_users_keep_their_existing_role_based_path(self):
        service=Service.objects.get(code='EGTP-IMT')
        for role,target in [('REQUESTER',reverse('ibtikar:new',args=[service.code])),
                            ('CLIENT',reverse('dashboard:client')+'?service='+str(service.pk)),
                            ('PLATFORM_ADMIN',reverse('dashboard:router'))]:
            user=User.objects.create_user(username='entry-'+role,role=role,password=None)
            self.client.force_login(user)
            self.assertRedirects(self.client.get(reverse('service_landing',args=[service.code])),target,fetch_redirect_response=False)
            page=html.fromstring(self.client.get(reverse('service_detail',args=[service.code])).content)
            self.assertFalse(page.xpath('//*[@data-access-mode]'))
            self.assertEqual(page.xpath('//*[@data-service-entry="workspace"]/@href'),[reverse('service_landing',args=[service.code])])
        self.assertEqual(Request.objects.count(),0)

    def test_guest_channel_options_remain_unified(self):
        response=self.client.get(reverse('guest_submit'),{'service':'EGTP-IMT'})
        page=html.fromstring(response.content)
        self.assertEqual(page.xpath('//select[@name="channel"]/option/@value'),['GENOCLAB','IBTIKAR'])
        self.assertFalse(page.xpath('//a[@href="/ibtikar/"]'))
        self.assertEqual(Request.objects.count(),0)

    def test_direct_ibtikar_entry_routes_to_authorized_workspace(self):
        entry=reverse('ibtikar:index')
        guest=self.client.get(entry)
        self.assertRedirects(guest,reverse('guest_submit')+'?channel=IBTIKAR',fetch_redirect_response=False)
        service=self.client.get(entry,{'service':'EGTP-IMT'})
        self.assertRedirects(service,reverse('ibtikar:new',args=['EGTP-IMT']),fetch_redirect_response=False)
        self.assertEqual(self.client.get(entry,{'service':'UNKNOWN-SERVICE'}).status_code,404)

        admin=User.objects.create_user(username='ibtikar-entry-admin',role='PLATFORM_ADMIN',password=None)
        self.client.force_login(admin)
        workspace=self.client.get(entry)
        self.assertEqual(workspace.status_code,200)
        self.assertContains(workspace,'EGTP-IMT')

    def test_inactive_and_unknown_services_cannot_open_entry_pages(self):
        Service.objects.filter(code='EGTP-IMT').update(active=False)
        for route in ('service_landing','service_detail'):
            for code in ('EGTP-IMT','MISSING-SERVICE'):
                self.assertEqual(self.client.get(reverse(route,args=[code])).status_code,404)
