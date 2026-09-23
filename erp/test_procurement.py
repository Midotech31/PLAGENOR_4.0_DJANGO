from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from erp.models import CdcItem, ForecastObservation, ProcurementLine, PurchaseOrder, StockMovement
from erp.services.common import Conflict
from erp.services.procurement import (add_plan_article,approve_plan,create_plan,decide_plan_line,
    plan_to_cdc,plan_totals,refresh_forecast,submit_plan)
from erp.services.purchases import (cancel_order,confirm_order,create_order,receive_order_line,
    received_quantity,revise_delivery_date,save_order_line)
from erp.services.stock import reconcile_stock,reverse_stock
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class ProcurementChainTests(OperationFixtures,TestCase):
    def setUp(self):
        today=timezone.localdate()
        self.plan=create_plan(self.ops,reference='PLAN-TEST',year=today.year+1,title='Approvisionnement de recette',
            assignee=self.operator,allow_costs=True)
        self.line=add_plan_article(self.operator,self.plan.pk,expected=self.plan.version,article=self.article,lot_name='Consommables')
        self.plan.refresh_from_db()

    def decide(self,quantity=10):
        values={'retained_quantity':Decimal(quantity),'included':True,'lot_name':'Consommables','priority':'CRITICAL',
            'estimated_price':Decimal('100.00'),'tax_rate':Decimal('19'),'currency':'DZD',
            'price_source':'Devis fournisseur de recette','decision_reason':'Quantité vérifiée selon les besoins confirmés'}
        self.line=decide_plan_line(self.operator,self.line.pk,expected=self.plan.version,values=values)
        self.plan.refresh_from_db()
        return values

    def approve(self):
        self.decide()
        submit_plan(self.operator,self.plan.pk,expected=self.plan.version,reason='Préparation complète')
        self.plan.refresh_from_db()
        approve_plan(self.ops,self.plan.pk,expected=self.plan.version,reason='Quantités et budget validés')
        self.plan.refresh_from_db()

    def order(self):
        self.approve()
        order=create_order(self.ops,self.plan.pk,expected=self.plan.version,reference='PO-TEST',supplier=self.party,
            ordered_on=timezone.localdate(),expected_on=timezone.localdate()+timedelta(days=30))
        line=save_order_line(self.ops,order.pk,expected=order.version,plan_line=self.line,quantity=10,
            unit_price=Decimal('100'),tax_rate=Decimal('19'),currency='DZD')
        order.refresh_from_db()
        confirm_order(self.ops,order.pk,expected=order.version,reason='Commande institutionnelle confirmée')
        order.refresh_from_db()
        return order,line

    def receive_order(self,order,line,amount=4,**changes):
        data={'expected':order.version,'key':uuid.uuid4(),'amount':amount,'location':self.freezer,
            'lot_code':'SUPPLY-LOT','manufacturer_lot':'LOT-SUPPLIER','container_code':'SUPPLY-CONT',
            'received_on':timezone.localdate(),'condition':'Intact','expires_on':timezone.localdate()+timedelta(days=730)}
        data.update(changes)
        return receive_order_line(self.ops,line.pk,**data),data

    def test_forecast_snapshot_short_history_preserves_human_value_until_reconfirmed(self):
        self.decide()
        forecast=refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        self.assertEqual(forecast.result['model']['confidence'],'LOW')
        self.line.refresh_from_db()
        self.assertEqual(self.line.retained_quantity,10)
        self.assertIsNone(self.line.reviewed_at)
        self.assertIn('SHORT_HISTORY',forecast.result['warnings'])
        self.plan.refresh_from_db()
        with self.assertRaises(ValidationError):
            submit_plan(self.operator,self.plan.pk,expected=self.plan.version,reason='Revue manquante')
        with self.assertRaises(ValidationError):
            ForecastObservation.objects.filter(pk=forecast.pk).delete()

    def test_human_approval_and_financial_totals_are_exact(self):
        self.approve()
        self.assertEqual(self.plan.work.status,'APPROVED')
        totals=plan_totals(self.ops,self.plan)['currencies']['DZD']
        self.assertEqual((totals['net'],totals['tax'],totals['gross']),(1000,190,1190))
        self.assertEqual(totals['lots']['Consommables']['gross'],1190)
        with self.assertRaises(PermissionDenied):
            decide_plan_line(self.ops,self.line.pk,expected=self.plan.version,values={'retained_quantity':20})
        with self.assertRaises(PermissionDenied):
            approve_plan(self.operator,self.plan.pk,expected=self.plan.version,reason='Auto-approbation')

    def test_partial_receipt_and_retry_update_purchase_and_stock_once(self):
        order,line=self.order()
        link,data=self.receive_order(order,line)
        duplicate=receive_order_line(self.ops,line.pk,**data)
        self.assertEqual(link.pk,duplicate.pk)
        self.assertEqual(received_quantity(line),4)
        order.refresh_from_db()
        self.assertEqual(order.status,'PARTIAL')
        self.assertEqual(link.receipt.container.quantity,4)
        self.assertEqual(link.receipt.container.status,'PENDING')
        self.assertEqual(reconcile_stock(self.ops),[])
        with self.assertRaises(ValidationError):
            self.receive_order(order,line,amount=7,container_code='TOO-MUCH')
        completed,_=self.receive_order(order,line,amount=6,container_code='SUPPLY-CONT-2')
        order.refresh_from_db()
        self.assertEqual(order.status,'RECEIVED')
        self.assertEqual(received_quantity(line),10)
        self.assertEqual(StockMovement.objects.filter(kind='RECEIPT').count(),2)

    def test_receipt_reversal_restores_order_balance_without_deleting_history(self):
        order,line=self.order()
        link,_=self.receive_order(order,line,amount=10)
        order.refresh_from_db()
        self.assertEqual(order.status,'RECEIVED')
        reverse_stock(self.ops,link.receipt.movement_id,key=uuid.uuid4(),reason='Réception enregistrée sur le mauvais lot')
        order.refresh_from_db()
        self.assertEqual(order.status,'CONFIRMED')
        self.assertEqual(received_quantity(line),0)
        self.assertEqual(line.deliveries.count(),1)
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_plan_to_cdc_uses_approved_snapshot_not_current_catalogue(self):
        self.approve()
        approved_name=self.line.article_snapshot['name']
        self.article.name='Catalogue changé après validation'
        self.article.save(update_fields=['name'])
        dossier=plan_to_cdc(self.ops,self.plan.pk,expected=self.plan.version,reference='88/SME/SDFM/SG/ESSBO/2026',family='reagents',assignee=self.second)
        self.assertEqual(dossier.work.assignee_id,self.second.pk)
        self.assertEqual(dossier.lots.count(),1)
        item=CdcItem.objects.get(lot__dossier=dossier)
        self.assertEqual(item.designation,approved_name)
        self.assertEqual(item.quantity,10)
        self.assertEqual(item.estimated_price,100)
        self.assertEqual(item.tax_rate,19)
        self.assertFalse(dossier.data['consultation']['confirmed'])
        self.plan.refresh_from_db()
        self.assertEqual(plan_to_cdc(self.ops,self.plan.pk,expected=self.plan.version,
            reference=dossier.reference,family='reagents').pk,dossier.pk)

    def test_cost_and_assignment_permissions_do_not_expand(self):
        self.plan.work.allow_costs=False
        self.plan.work.save(update_fields=['allow_costs'])
        with self.assertRaises(PermissionDenied):
            self.decide()
        with self.assertRaises(PermissionDenied):
            refresh_forecast(self.second,self.line.pk,expected=self.plan.version)
        with self.assertRaises(PermissionDenied):
            plan_totals(self.operator,self.plan)
        with self.assertRaises(PermissionDenied):
            create_plan(self.operator,reference='NO',year=timezone.localdate().year,title='Interdit')

    def test_price_variance_requires_reason_and_cancellation_keeps_receipts(self):
        order,line=self.order()
        with self.assertRaises(ValidationError):
            self.receive_order(order,line,actual_unit_price=Decimal(110))
        link,_=self.receive_order(order,line,actual_unit_price=Decimal(110),variance_reason='Prix corrigé selon la facture')
        self.assertEqual(link.actual_unit_price,110)
        order.refresh_from_db()
        cancel_order(self.ops,order.pk,expected=order.version,reason='Solde non livré annulé')
        order.refresh_from_db()
        self.assertEqual(order.status,'CANCELLED')
        self.assertEqual(received_quantity(line),4)
        with self.assertRaises(ValidationError):
            self.receive_order(order,line,container_code='AFTER-CANCEL')


    def test_cancelled_partial_order_still_counts_delivered_items_against_plan(self):
        order,line=self.order()
        self.receive_order(order,line,amount=4)
        order.refresh_from_db()
        cancel_order(self.ops,order.pk,expected=order.version,reason='Solde annulé')
        order2=create_order(self.ops,self.plan.pk,expected=self.plan.version,reference='PO-REPLACE',supplier=self.party,
            ordered_on=timezone.localdate(),expected_on=timezone.localdate()+timedelta(days=30))
        with self.assertRaises(ValidationError):
            save_order_line(self.ops,order2.pk,expected=order2.version,plan_line=self.line,quantity=10,
                unit_price=Decimal(100),tax_rate=Decimal(19),currency='DZD')
        item=save_order_line(self.ops,order2.pk,expected=order2.version,plan_line=self.line,quantity=6,
            unit_price=Decimal(100),tax_rate=Decimal(19),currency='DZD')
        self.assertEqual(item.quantity,6)

    def test_receipt_reversal_retry_does_not_increment_order_version_twice(self):
        order,line=self.order()
        link,data=self.receive_order(order,line,amount=10)
        key=uuid.uuid4()
        first=reverse_stock(self.ops,link.receipt.movement_id,key=key,reason='Erreur de réception')
        order.refresh_from_db()
        version=order.version
        replay=reverse_stock(self.ops,link.receipt.movement_id,key=key,reason='Erreur de réception')
        self.assertEqual(replay.pk,first.pk)
        order.refresh_from_db()
        self.assertEqual(order.version,version)

    def test_old_physical_receipt_date_does_not_invent_recorded_consumption_history(self):
        self.receive(received_on=timezone.localdate()-timedelta(days=800))
        result=refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        self.assertEqual(result.result['model']['history_months'],0)
        self.assertEqual(result.result['model']['confidence'],'LOW')
        self.assertEqual(result.input_data['physical_usable'],'10.000000')

    def test_revised_overdue_delivery_is_eligible_only_after_new_date_confirmation(self):
        self.approve()
        today=timezone.localdate()
        order=create_order(self.ops,self.plan.pk,expected=self.plan.version,reference='PO-OVERDUE',supplier=self.party,
            ordered_on=today-timedelta(days=60),expected_on=today-timedelta(days=30))
        item=save_order_line(self.ops,order.pk,expected=order.version,plan_line=self.line,quantity=10,
            unit_price=Decimal(100),tax_rate=Decimal(19),currency='DZD')
        order.refresh_from_db()
        confirm_order(self.ops,order.pk,expected=order.version,reason='Commande existante reprise')
        order.refresh_from_db()
        second=create_plan(self.ops,reference='PLAN-REVIEW',year=today.year+1,title='Plan à actualiser',assignee=self.operator)
        line=add_plan_article(self.ops,second.pk,expected=second.version,article=self.article,lot_name='Fournitures')
        second.refresh_from_db()
        first=refresh_forecast(self.operator,line.pk,expected=second.version)
        self.assertIn('OVERDUE_DELIVERIES_EXCLUDED',first.result['warnings'])
        self.assertEqual(first.input_data['incoming'],[])
        revise_delivery_date(self.ops,order.pk,expected=order.version,expected_on=today+timedelta(days=20),reason='Nouvelle date écrite du fournisseur')
        second.refresh_from_db()
        updated=refresh_forecast(self.operator,line.pk,expected=second.version)
        self.assertEqual(updated.input_data['overdue_orders'],[])
        self.assertEqual(updated.input_data['incoming'][0]['quantity'],'10.000000')
        self.assertIn('FUTURE_RECEIPTS_REQUIRE_ACCEPTANCE_AND_EXPIRY_REVIEW',updated.result['warnings'])

    def test_per_purchase_unit_price_is_preserved_when_base_price_is_not_representable(self):
        from erp.services.catalog import save_conversion
        save_conversion(self.ops,self.article,{'unit':self.box,'factor':Decimal(3),'justification':'Trois unités par boîte'})
        self.article.purchase_unit=self.box
        self.article.save(update_fields=['purchase_unit'])
        alternate=create_plan(self.ops,reference='PRICE-PRECISION',year=timezone.localdate().year+1,title='Prix par boîte')
        line=add_plan_article(self.ops,alternate.pk,expected=alternate.version,article=self.article,lot_name='Boîtes')
        alternate.refresh_from_db()
        decide_plan_line(self.ops,line.pk,expected=alternate.version,values={'retained_quantity':Decimal(1),
            'estimated_price':Decimal(100),'tax_rate':Decimal(0),'price_source':'Prix par boîte',
            'decision_reason':'Un conditionnement validé'})
        alternate.refresh_from_db()
        submit_plan(self.ops,alternate.pk,expected=alternate.version,reason='Plan complet')
        alternate.refresh_from_db()
        approve_plan(self.ops,alternate.pk,expected=alternate.version,reason='Validé')
        alternate.refresh_from_db()
        order=create_order(self.ops,alternate.pk,expected=alternate.version,reference='PO-PRECISION',supplier=self.party,
            ordered_on=timezone.localdate(),expected_on=timezone.localdate())
        item=save_order_line(self.ops,order.pk,expected=order.version,plan_line=line,quantity=1,
            unit_price=Decimal(100),tax_rate=Decimal(0),currency='DZD')
        order.refresh_from_db()
        confirm_order(self.ops,order.pk,expected=order.version,reason='Commande validée')
        order.refresh_from_db()
        delivery,_=self.receive_order(order,item,amount=1)
        self.assertEqual(delivery.actual_unit_price,100)
        self.assertIsNone(delivery.receipt.unit_price)
        self.assertEqual(delivery.receipt.received_quantity,3)


    def test_forecast_uses_recorded_months_and_historical_locations_after_transfer(self):
        from datetime import datetime,time
        from unittest.mock import patch
        from erp.services.forecast_engine import month_after
        from erp.services.stock import remove_stock,transfer_stock
        from erp.services.storage import save_location
        today=timezone.localdate()
        first=month_after(today,-25)
        expiry=today+timedelta(days=1000)
        with patch('django.utils.timezone.now',return_value=timezone.make_aware(datetime.combine(first,time(12)))):
            container,_,_=self.receive(quantity=1000,expires_on=expiry)
        for index in range(1,25):
            recorded=month_after(first,index).replace(day=15)
            with patch('django.utils.timezone.now',return_value=timezone.make_aware(datetime.combine(recorded,time(12)))):
                remove_stock(self.ops,container.pk,key=uuid.uuid4(),amount=10,unit=self.unit,reason='Consommation mensuelle de recette')
        with patch('django.utils.timezone.now',return_value=timezone.make_aware(datetime.combine(recorded,time(13)))):
            remove_stock(self.ops,container.pk,key=uuid.uuid4(),amount=2,unit=self.unit,kind='LOSS',reason='Perte de recette documentée')
        self.plan.work.location=self.freezer
        self.plan.work.save(update_fields=['location'])
        observation=refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        self.assertEqual(observation.result['model']['history_months'],24)
        self.assertEqual(observation.result['model']['monthly_mean'],'10.000000')
        self.assertEqual(observation.input_data['historical_losses'],'2.000000')
        self.assertEqual(observation.result['model']['confidence'],'HIGH')
        destination=save_location(self.ops,{'code':'OTHER-STORAGE','name':'Autre stockage','kind':self.storage_kind,'parent':self.lab})
        transfer_stock(self.ops,container.pk,key=uuid.uuid4(),destination=destination,reason='Réorganisation après historique')
        self.plan.refresh_from_db()
        after=refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        self.assertEqual(after.result['model']['history_months'],24)
        self.assertEqual(after.result['model']['monthly_mean'],'10.000000')
        self.assertEqual(after.input_data['historical_losses'],'2.000000')
        self.assertEqual(after.input_data['physical_usable'],'0.000000')

    def test_forecast_credits_only_usable_reservations_for_included_confirmed_runs(self):
        from accounts.models import MemberProfile
        from core.models import Request,Service
        from erp.services.biobank import source_samples
        from erp.services.consumption import create_run,save_profile,save_rule,reserve_run,reservation_proposal
        from erp.services.stock import reserve_stock
        service=Service.objects.create(code='FORECAST-SERVICE',name='Service de recette')
        member,_=MemberProfile.objects.get_or_create(user=self.operator)
        request=Request.objects.create(service=service,requester=self.outsider,assigned_to=member,
            title='Activité prévue de recette',status='IN_PROGRESS',sample_table=[{'sample_code':'FC1'}])
        profile=save_profile(self.ops,{'code':'FC-RECIPE','name':'Nomenclature','service':service,
            'reference_samples':1,'protocol_reference':'SOP-RECETTE'})
        save_rule(self.ops,profile.pk,{'article':self.article,'quantity':Decimal(2),'unit':self.unit,'basis':'BATCH'},expected=profile.version)
        run=create_run(self.ops,request=request,profile=profile,code='FC-RUN',name='Analyse prévue',sample_count=1,
            planned_on=self.plan.starts_on,source_keys=[source_samples(self.ops,request)[0]['key']],committed=True,incremental_demand=True)
        container,_,_=self.receive(quantity=10,expires_on=self.plan.ends_on+timedelta(days=30))
        reserve_run(self.ops,run.pk,expected=run.version,key=uuid.uuid4(),allocations=reservation_proposal(self.ops,run)['allocations'],reason='Réservation planifiée')
        reserve_stock(self.ops,container.pk,key=uuid.uuid4(),amount=3,unit=self.unit,reference='Autre activité non comprise')
        result=refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        self.assertEqual(result.input_data['physical_usable'],'10.000000')
        self.assertEqual(result.input_data['reserved_total'],'5.000000')
        self.assertEqual(result.input_data['stock'][0]['quantity'],'7.000000')
        self.assertEqual(result.input_data['commitments'][0]['quantity'],'2.000000')
        self.assertEqual(result.result['projection']['covered_by_stock'],'2.000000')
        self.assertEqual(result.result['projection']['projected_end_balance'],'5.000000')

    def test_decision_exclusion_and_price_validation_are_not_silent(self):
        invalid=[{'decision_reason':''},{'retained_quantity':0,'decision_reason':'Quantité nulle'},
            {'retained_quantity':1,'decision_reason':'Devise invalide','currency':'€€€'},
            {'retained_quantity':1,'decision_reason':'Prix non documenté','estimated_price':Decimal(12),'price_source':''},
            {'retained_quantity':1,'decision_reason':'Champ interdit','version':99}]
        for values in invalid:
            with self.subTest(values=values),self.assertRaises(ValidationError):
                decide_plan_line(self.ops,self.line.pk,expected=self.plan.version,values=values)
        self.line.refresh_from_db()
        self.assertIsNone(self.line.retained_quantity)
        self.assertIsNone(self.line.reviewed_at)
        decide_plan_line(self.operator,self.line.pk,expected=self.plan.version,
            values={'included':False,'retained_quantity':0,'decision_reason':'Besoin reporté'})
        self.plan.refresh_from_db()
        with self.assertRaises(ValidationError):
            submit_plan(self.operator,self.plan.pk,expected=self.plan.version,reason='Plan entièrement exclu')

    def test_order_and_delivery_date_changes_reject_unjustified_or_stale_operations(self):
        order,line=self.order()
        with self.assertRaises(ValidationError):
            save_order_line(self.ops,order.pk,expected=order.version,plan_line=self.line,quantity=9,
                unit_price=Decimal(100),tax_rate=Decimal(19),currency='DZD')
        with self.assertRaises(ValidationError):
            revise_delivery_date(self.ops,order.pk,expected=order.version,expected_on=timezone.localdate(),reason='')
        with self.assertRaises(Conflict):
            cancel_order(self.ops,order.pk,expected=999,reason='Version dépassée')
        with self.assertRaises(ValidationError):
            cancel_order(self.ops,order.pk,expected=order.version,reason='')
        order.refresh_from_db()
        self.assertEqual(order.status,'CONFIRMED')

    def test_forecast_and_cdc_scope_and_plan_year_validation(self):
        with self.assertRaises(ValidationError):
            create_plan(self.ops,reference='PAST',year=timezone.localdate().year-1,title='Exercice passé')
        with self.assertRaises(ValidationError):
            plan_to_cdc(self.ops,self.plan.pk,expected=self.plan.version,reference='17/SME/SDFM/SG/ESSBO/2026',family='reagents')
        self.plan.work.category=self.other
        self.plan.work.save(update_fields=['category'])
        with self.assertRaises(PermissionDenied):
            refresh_forecast(self.operator,self.line.pk,expected=self.plan.version)
        with self.assertRaises(PermissionDenied):
            add_plan_article(self.operator,self.plan.pk,expected=self.plan.version,article=self.article,lot_name='Hors catégorie')

    def test_plan_http_rejects_stale_decisions_and_invalid_actions(self):
        from django.urls import reverse
        self.client.force_login(self.ops)
        route = reverse('erp:procurement-detail', args=[self.plan.pk])
        self.assertEqual(self.client.post(route, {'expected_version': self.plan.version,
            'reason': 'Action inconnue', 'action': 'unknown'}).status_code, 404)
        response = self.client.post(route, {'expected_version': self.plan.version,
            'reason': 'Revue manquante', 'action': 'submit'})
        self.assertEqual(response.status_code, 400)
        data = self.decide()
        data['expected_version'] = self.plan.version - 1
        response = self.client.post(reverse('erp:procurement-line', args=[self.line.pk]), data)
        self.assertEqual(response.status_code, 400)
        data['expected_version'] = self.plan.version
        self.assertEqual(self.client.post(reverse('erp:procurement-line', args=[self.line.pk]), data).status_code, 302)
        self.plan.refresh_from_db()
        cdc_data = {'expected_version': self.plan.version, 'family': 'reagents',
            'reference': '88/SME/SDFM/SG/ESSBO/2026'}
        self.assertEqual(self.client.post(reverse('erp:procurement-cdc', args=[self.plan.pk]), cdc_data).status_code, 400)
        create = {'reference': 'PLAN-TEST', 'title': 'Duplicated reference', 'year': timezone.localdate().year+1,
            'assignee': self.operator.pk, 'allow_costs': 'on', 'expected_version': 1}
        self.assertEqual(self.client.post(reverse('erp:procurement-create'), create).status_code, 400)

    def test_order_http_workflow_checks_versions_and_receipt_balance(self):
        from django.urls import reverse
        self.client.force_login(self.ops)
        self.approve()
        values = {'expected_version': self.plan.version-1, 'reference': 'HTTP-ORDER', 'supplier': self.party.pk,
            'ordered_on': timezone.localdate().isoformat(), 'expected_on': (timezone.localdate()+timedelta(days=30)).isoformat()}
        route = reverse('erp:order-create', args=[self.plan.pk])
        self.assertEqual(self.client.post(route, values).status_code, 400)
        values['expected_version'] = self.plan.version
        self.assertEqual(self.client.post(route, values).status_code, 302)
        order = PurchaseOrder.objects.get(reference='HTTP-ORDER')
        detail = reverse('erp:order-detail', args=[order.pk])
        action = {'expected_version': order.version, 'reason': 'Vérification', 'action': 'unknown'}
        self.assertEqual(self.client.post(detail, action).status_code, 404)
        action['action'] = 'confirm'
        self.assertEqual(self.client.post(detail, action).status_code, 400)
        line_data = {'expected_version': order.version+1, 'plan_line': self.line.pk,
            'quantity': '10', 'unit_price': '100', 'tax_rate': '19', 'currency': 'DZD'}
        self.assertEqual(self.client.post(reverse('erp:order-line-new', args=[order.pk]), line_data).status_code, 400)
        line_data['expected_version'] = order.version
        self.assertEqual(self.client.post(reverse('erp:order-line-new', args=[order.pk]), line_data).status_code, 302)
        order.refresh_from_db()
        line = order.lines.get()
        self.assertEqual(self.client.get(reverse('erp:order-line-edit', args=[order.pk, line.pk])).status_code, 200)
        action['expected_version'] = order.version
        self.assertEqual(self.client.post(detail, action).status_code, 302)
        order.refresh_from_db()
        date_data = {'expected_version': order.version+1, 'reason': 'Fournisseur consulté',
            'expected_on': (timezone.localdate()+timedelta(days=40)).isoformat()}
        date_route = reverse('erp:order-date', args=[order.pk])
        self.assertEqual(self.client.get(date_route).status_code, 200)
        self.assertEqual(self.client.post(date_route, date_data).status_code, 400)
        date_data['expected_version'] = order.version
        self.assertEqual(self.client.post(date_route, date_data).status_code, 302)
        order.refresh_from_db()
        receipt = {'expected_version': order.version, 'key': str(uuid.uuid4()), 'amount': '11',
            'location': self.freezer.pk, 'lot_code': 'HTTP-LOT', 'manufacturer_lot': 'MANUF',
            'container_code': 'HTTP-CONT', 'received_on': timezone.localdate().isoformat(), 'condition': 'Intact'}
        receipt_route = reverse('erp:order-receive', args=[line.pk])
        self.assertEqual(self.client.post(receipt_route, receipt).status_code, 400)
        self.assertFalse(StockMovement.objects.exists())
        receipt['amount'] = '10'
        self.assertEqual(self.client.post(receipt_route, receipt).status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, 'RECEIVED')
        self.assertEqual(received_quantity(line), 10)
        self.assertEqual(reconcile_stock(self.ops), [])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(receipt_route).status_code, 403)

    def test_purchase_document_access_uses_plan_scope_and_financial_permission(self):
        from erp.services.safety import attach_document, require_target, target_cost_access
        from erp.test_safety import pdf_bytes
        from erp.safety_forms import DocumentForm
        order, _ = self.order()
        self.assertEqual(require_target(self.ops, 'order', order.pk, write=True), order)
        self.assertTrue(target_cost_access(self.ops, 'order', order))
        self.assertEqual(require_target(self.operator, 'order', order.pk), order)
        with self.assertRaises(PermissionDenied):
            require_target(self.operator, 'order', order.pk, write=True)
        document = attach_document(self.ops, 'order', order.pk, title='Commande signée', kind='OTHER',
            filename='order.pdf', data=pdf_bytes('Commande signée'), source='Service des marchés')
        self.assertTrue(document.financial)
        form = DocumentForm(user=self.ops, target_kind='order', target=order)
        self.assertTrue(form.fields['financial'].disabled)
        self.assertTrue(form.fields['financial'].initial)
        self.assertIn(document.title, form.fields['supersedes'].label_from_instance(document))

    def test_plan_completion_and_supplier_guards_preserve_decisions(self):
        from unittest.mock import patch
        from erp.services.procurement import validate_plan
        with self.assertRaises(ValidationError):
            approve_plan(self.ops, self.plan.pk, expected=self.plan.version, reason='Pas soumis')
        self.decide()
        with self.assertRaises(ValidationError):
            submit_plan(self.operator, self.plan.pk, expected=self.plan.version, reason='')
        self.party.active = False
        self.party.save()
        with self.assertRaises(ValidationError):
            decide_plan_line(self.operator, self.line.pk, expected=self.plan.version,
                values={'supplier': self.party, 'decision_reason': 'Fournisseur désactivé'})
        ProcurementLine.objects.filter(pk=self.line.pk).update(estimated_price=None)
        with self.assertRaises(ValidationError):
            validate_plan(self.plan)
        with patch('erp.services.procurement.timezone.localdate', return_value=self.plan.ends_on+timedelta(days=1)):
            with self.assertRaises(ValidationError):
                refresh_forecast(self.ops, self.line.pk, expected=self.plan.version)
        with patch('erp.services.procurement.forecast_months', side_effect=ValueError('Historique invalide')):
            with self.assertRaisesMessage(ValidationError, 'Historique invalide'):
                refresh_forecast(self.ops, self.line.pk, expected=self.plan.version)
        self.assertFalse(ForecastObservation.objects.exists())

    def test_excluded_plan_lines_are_not_budgeted_or_copied_into_cdc(self):
        extra = add_plan_article(self.ops, self.plan.pk, expected=self.plan.version,
            article=self.liquid, lot_name='Non retenu')
        self.plan.refresh_from_db()
        decide_plan_line(self.ops, extra.pk, expected=self.plan.version,
            values={'included': False, 'decision_reason': 'Besoin différé'})
        self.plan.refresh_from_db()
        self.assertEqual(plan_totals(self.ops, self.plan)['incomplete_lines'], 1)
        self.approve()
        dossier = plan_to_cdc(self.ops, self.plan.pk, expected=self.plan.version,
            reference='89/SME/SDFM/SG/ESSBO/2026', family='reagents')
        self.assertEqual(CdcItem.objects.filter(lot__dossier=dossier).count(), 1)
        self.plan.refresh_from_db()
        with self.assertRaises(Conflict):
            plan_to_cdc(self.ops, self.plan.pk, expected=self.plan.version,
                reference='90/SME/SDFM/SG/ESSBO/2026', family='reagents')

    def test_order_rejects_unapproved_plan_inactive_supplier_future_date_and_bad_currency(self):
        values = {'expected': self.plan.version, 'reference': 'GUARD-ORDER', 'supplier': self.party,
            'ordered_on': timezone.localdate(), 'expected_on': timezone.localdate()+timedelta(days=30)}
        with self.assertRaises(ValidationError):
            create_order(self.ops, self.plan.pk, **values)
        self.approve()
        values['expected'] = self.plan.version
        self.party.active = False
        self.party.save()
        with self.assertRaises(ValidationError):
            create_order(self.ops, self.plan.pk, **values)
        self.party.active = True
        self.party.save()
        with self.assertRaises(ValidationError):
            create_order(self.ops, self.plan.pk, **dict(values, ordered_on=timezone.localdate()+timedelta(days=1)))
        order = create_order(self.ops, self.plan.pk, **values)
        with self.assertRaises(ValidationError):
            save_order_line(self.ops, order.pk, expected=order.version, plan_line=self.line, quantity=10,
                unit_price=100, tax_rate=19, currency='12!')
        foreign = ProcurementLine(pk=uuid.uuid4())
        with self.assertRaises(ValidationError):
            save_order_line(self.ops, order.pk, expected=order.version, plan_line=foreign, quantity=10,
                unit_price=100, tax_rate=19, currency='DZD')
        self.assertFalse(order.lines.exists())

    def test_category_scoped_forms_and_receipt_financial_permission(self):
        from erp.models import Capability
        from erp.procurement_forms import PlanArticleForm, OrderReceiptForm
        self.plan.work.category = self.category
        self.plan.work.save(update_fields=['category'])
        self.assertEqual(str(self.plan), self.plan.reference)
        self.assertEqual(list(PlanArticleForm(plan=self.plan).fields['article'].queryset), [self.article])
        order, line = self.order()
        self.assertEqual(str(order), order.reference)
        self.grant(Capability.RECEIVE_STOCK, category=self.category, location=self.freezer)
        self.assertNotIn('actual_unit_price', OrderReceiptForm(user=self.operator, line=line).fields)
        _, data = self.receive_order(order, line)
        with self.assertRaises(PermissionDenied):
            receive_order_line(self.operator, line.pk, **{**data, 'actual_unit_price': 100})
        with self.assertRaises(Conflict):
            receive_order_line(self.ops, line.pk, **{**data, 'variance_reason': 'Modification après réception'})
        self.assertEqual(received_quantity(line), 4)
        self.assertEqual(reconcile_stock(self.ops), [])
