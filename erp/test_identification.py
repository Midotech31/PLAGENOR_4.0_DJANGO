from io import BytesIO
import uuid
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from erp.identification import identity,identity_scope,target_url,TOKEN
from erp.models import Capability
from erp.services.biobank import receive_sample
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],SECURE_SSL_REDIRECT=False,
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class IdentificationTests(OperationFixtures,TestCase):
    def setUp(self):
        self.container,self.receipt,_=self.receive()

    def test_internal_tokens_redirect_only_to_scoped_application_records(self):
        self.client.force_login(self.ops)
        for kind,obj in [('article',self.article),('container',self.container),('lot',self.container.lot),('location',self.freezer)]:
            with self.subTest(kind=kind):
                token='PLAGENOR|'+kind+'|'+str(obj.pk)
                self.assertIsNotNone(TOKEN.fullmatch(token))
                response=self.client.get(reverse('erp:identify'),{'q':token})
                self.assertEqual(response.status_code,302)
                self.assertEqual(response['Location'],target_url(self.ops,kind,obj))
                label=self.client.get(reverse('erp:label',args=[kind,obj.pk]))
                self.assertEqual(label.status_code,200)
                qr=self.client.get(reverse('erp:qr-image',args=[kind,obj.pk]))
                self.assertEqual(qr.status_code,200)
                self.assertEqual(qr['Content-Type'],'image/png')
                image=Image.open(BytesIO(qr.content))
                image.verify()
        self.assertEqual(self.client.get(reverse('erp:identify'),{'q':'https://untrusted.invalid/'}).status_code,200)
        self.assertEqual(self.client.get(reverse('erp:identify'),{'q':'PLAGENOR|unknown|'+str(self.article.pk)}).status_code,404)

    def test_manual_codes_and_vendor_barcodes_are_searchable_without_scope_leakage(self):
        self.container.lot.barcode='GS1-DOCUMENTED-CODE'
        self.container.lot.save(update_fields=['barcode'])
        self.client.force_login(self.ops)
        self.assertContains(self.client.get(reverse('erp:identify'),{'q':self.container.code}),self.container.code)
        self.assertContains(self.client.get(reverse('erp:identify'),{'q':'GS1-DOCUMENTED-CODE'}),self.container.lot.code)
        self.assertEqual(self.client.get(reverse('erp:identify-target',args=['container',self.container.pk])).status_code,302)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:identify')).status_code,403)
        self.assertEqual(self.client.get(reverse('erp:qr-image',args=['container',self.container.pk])).status_code,404)

    def test_stock_only_member_can_scan_location_and_article_without_extra_catalogue_access(self):
        self.grant(Capability.VIEW_STOCK,category=self.category,location=self.freezer)
        self.client.force_login(self.operator)
        self.assertEqual(identity(self.operator,'article',self.article.pk),self.article)
        article_url=target_url(self.operator,'article',self.article)
        self.assertTrue(article_url.startswith(reverse('erp:stock-list')))
        location_url=target_url(self.operator,'location',self.lab)
        self.assertIn('location=',location_url)
        self.assertContains(self.client.get(location_url),self.container.code)
        with self.assertRaises(Http404):
            identity(self.operator,'article',self.liquid.pk)
        with self.assertRaises(Http404):
            identity(self.operator,'container','not-a-uuid')
        with self.assertRaises(Http404):
            identity_scope(self.operator,'unknown')

    def test_sample_labels_include_only_internal_identity_and_print_copy_count_is_bounded(self):
        sample=receive_sample(self.ops,key=uuid.uuid4(),code='SAMPLE-PRIVATE-CODE',amount=10,unit=self.ul,
            location=self.freezer,received_on=timezone.localdate(),reason='Réception échantillon')
        self.grant(Capability.VIEW_BIOBANK,location=self.freezer)
        self.client.force_login(self.operator)
        url=reverse('erp:label',args=['sample',sample.pk])
        response=self.client.get(url,{'copies':6})
        self.assertEqual(response.status_code,200)
        html=response.content.decode()
        self.assertEqual(html.count('class="resource-label"'),6)
        self.assertEqual(response.context['code'],sample.code)
        self.assertNotIn('matrix',response.context.flatten() if hasattr(response.context,'flatten') else {})
        for value in (0,101,'invalid'):
            self.assertEqual(self.client.get(url,{'copies':value}).status_code,404)
        self.assertEqual(target_url(self.operator,'sample',sample),reverse('erp:sample-detail',args=[sample.pk]))
        self.assertTrue(target_url(self.operator,'location',self.freezer).startswith(reverse('erp:storage-maps')))
