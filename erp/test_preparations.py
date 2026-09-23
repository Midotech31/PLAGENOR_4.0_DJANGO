from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied,ValidationError
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone

from erp.models import InternalPreparation,StockContainer,StockMovement
from erp.services.preparations import prepare_stock
from erp.services.stock import reconcile_stock,reserve_stock
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],SECURE_SSL_REDIRECT=False,
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PreparationTests(OperationFixtures,TestCase):
    def setUp(self):
        self.source,_,_=self.receive(quantity=100,article=self.liquid,unit=self.ml)

    def values(self):
        return {'key':uuid.uuid4(),'article':self.liquid,'location':self.freezer,'lot_code':'PREP-LOT',
            'container_code':'PREP-CONT','amount':25,'unit':self.ml,'prepared_on':timezone.localdate(),
            'expires_on':timezone.localdate()+timedelta(days=30),'protocol_reference':'SOP de préparation vérifiée',
            'reason':'Préparation de recette documentée','ingredients':[{'container':self.source,'amount':10,'unit':self.ml}]}

    def test_atomic_preparation_keeps_sources_and_balances_and_retry_is_exact(self):
        values=self.values()
        first=prepare_stock(self.ops,**values)
        replay=prepare_stock(self.ops,**values)
        self.assertEqual(first.pk,replay.pk)
        self.source.refresh_from_db()
        self.assertEqual(self.source.quantity,90)
        target=first.output_lot.containers.get()
        self.assertEqual(target.quantity,25)
        self.assertEqual(target.status,'PENDING')
        self.assertEqual(first.output_lot.origin,'PREPARATION')
        self.assertEqual(first.sources[0]['container'],str(self.source.pk))
        self.assertEqual(first.sources[0]['manufacturer_lot'],self.source.lot.manufacturer_lot)
        self.assertEqual(first.sources[0]['amount'],'10.000000')
        self.assertEqual(first.movement.entries.count(),2)
        self.assertEqual(reconcile_stock(self.ops),[])
        with self.assertRaises(ValidationError):
            first.delete()

    def test_invalid_or_reserved_sources_never_create_partial_output(self):
        reserve_stock(self.ops,self.source.pk,key=uuid.uuid4(),amount=95,unit=self.ml,reference='Série déjà réservée')
        with self.assertRaises(ValidationError):
            prepare_stock(self.ops,**self.values())
        self.assertEqual(StockContainer.objects.count(),1)
        self.assertFalse(InternalPreparation.objects.exists())
        self.assertFalse(StockMovement.objects.filter(kind='PREPARATION').exists())
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_invalid_inputs_dates_quantity_concentration_and_permissions(self):
        values=self.values()
        changes=[{'ingredients':[]},{'ingredients':values['ingredients']*2},{'protocol_reference':''},
            {'reason':''},{'prepared_on':timezone.localdate()+timedelta(days=1)},
            {'expires_on':timezone.localdate()-timedelta(days=1)},{'amount':0},
            {'concentration_value':Decimal(10)}]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                prepare_stock(self.ops,**{**values,**change})
        self.assertEqual(StockContainer.objects.count(),1)
        with self.assertRaises(PermissionDenied):
            prepare_stock(self.operator,**values)

    def test_native_preparation_page_and_form_save(self):
        self.client.force_login(self.ops)
        url=reverse('erp:preparation-create')
        self.assertEqual(self.client.get(url).status_code,200)
        data={'key':str(uuid.uuid4()),'article':self.liquid.pk,'location':self.freezer.pk,'lot_code':'FORM-LOT',
            'container_code':'FORM-CONT','amount':'20','unit':self.ml.pk,'prepared_on':timezone.localdate().isoformat(),
            'protocol_reference':'SOP-01','reason':'Préparation au laboratoire','sources-TOTAL_FORMS':'2','sources-INITIAL_FORMS':'0',
            'sources-MIN_NUM_FORMS':'1','sources-MAX_NUM_FORMS':'50','sources-0-container':self.source.pk,
            'sources-0-amount':'5','sources-0-unit':self.ml.pk}
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        prepared=InternalPreparation.objects.get()
        self.assertEqual(self.client.get(reverse('erp:preparation-detail',args=[prepared.pk])).status_code,200)
        self.assertContains(self.client.get(reverse('erp:stock-detail',args=[prepared.output_lot.containers.get().pk])),'Voir le protocole et les lots sources')
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_preparation_detail_uses_integer_identity_and_enforces_read_scope(self):
        from django.urls import resolve
        from erp.models import Capability
        prepared=prepare_stock(self.ops,**self.values())
        url=reverse('erp:preparation-detail',args=[prepared.pk])
        self.assertIsInstance(prepared.pk,int)
        self.assertEqual(resolve(url).kwargs['pk'],prepared.pk)
        self.assertIsInstance(resolve(url).kwargs['pk'],int)
        self.client.force_login(self.ops)
        self.assertContains(self.client.get(url),prepared.protocol_reference)
        self.assertEqual(self.client.post(url,{}).status_code,405)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code,404)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(url).status_code,404)
        self.grant(Capability.VIEW_STOCK,category=self.liquid.category,location=self.freezer)
        self.assertContains(self.client.get(url),prepared.protocol_reference)
        self.assertEqual(self.client.get(reverse('erp:preparation-detail',args=[0])).status_code,404)
        self.assertEqual(self.client.get('/erp/preparations/'+str(uuid.uuid4())+'/').status_code,404)
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_http_preparation_overdraw_rolls_back_output_and_consumption(self):
        self.client.force_login(self.ops)
        data = {'key': uuid.uuid4(), 'article': self.liquid.pk, 'location': self.freezer.pk,
            'lot_code': 'OVERDRAW-LOT', 'container_code': 'OVERDRAW-CONT', 'amount': '20', 'unit': self.ml.pk,
            'prepared_on': timezone.localdate().isoformat(), 'protocol_reference': 'SOP-01', 'reason': 'Préparation',
            'sources-TOTAL_FORMS': '1', 'sources-INITIAL_FORMS': '0', 'sources-MIN_NUM_FORMS': '1',
            'sources-MAX_NUM_FORMS': '50', 'sources-0-container': self.source.pk,
            'sources-0-amount': '101', 'sources-0-unit': self.ml.pk}
        response = self.client.post(reverse('erp:preparation-create'), data)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertFalse(InternalPreparation.objects.exists())
        self.source.refresh_from_db()
        self.assertEqual(self.source.quantity, 100)
        self.assertEqual(reconcile_stock(self.ops), [])

    def test_preparation_date_cannot_precede_source_manufacturing(self):
        values = self.values()
        self.source.lot.manufactured_on = timezone.localdate()
        self.source.lot.save(update_fields=['manufactured_on'])
        values['prepared_on'] = timezone.localdate() - timedelta(days=1)
        with self.assertRaisesRegex(ValidationError, 'postérieur'):
            prepare_stock(self.ops, **values)
        self.assertFalse(InternalPreparation.objects.exists())
        self.source.refresh_from_db()
        self.assertEqual(self.source.quantity, 100)
