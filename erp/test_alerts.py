from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
import uuid

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.management import call_command,CommandError
from django.test import TestCase,override_settings
from django.urls import reverse
from django.utils import timezone

from erp.models import AlertAcknowledgement,AlertDigest,AlertPolicy,Capability,Location,StockContainer,WorkItem
from erp.services.alerts import acknowledge,collect_alerts,policy,save_policy,send_digest
from erp.services.biobank import receive_sample,reserve_position
from erp.services.cold_storage import record_temperature
from erp.services.common import Conflict
from erp.services.stock import control_lot,is_usable,remove_stock
from erp.services.storage import save_location
from erp.services.work import create_work
from erp.test_operations import OperationFixtures
from notifications.models import Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],SECURE_SSL_REDIRECT=False,
    STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
        'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AlertTests(OperationFixtures,TestCase):
    def kinds(self,user=None):
        return {row['kind'] for row in collect_alerts(user or self.ops)['alerts']}

    def test_policy_read_does_not_write_and_edits_are_validated_and_versioned(self):
        self.assertFalse(AlertPolicy.objects.exists())
        default=policy()
        self.assertEqual(default.expiry_days,[180,90,60,30,7])
        self.assertFalse(AlertPolicy.objects.exists())
        selected=save_policy(self.ops,{'expiry_days':[30,7,30],'dormant_days':90},expected=default.version)
        self.assertEqual(selected.expiry_days,[30,7])
        with self.assertRaises(Conflict):
            save_policy(self.ops,{'dormant_days':100},expected=999)
        with self.assertRaises(PermissionDenied):
            save_policy(self.operator,{'dormant_days':100},expected=selected.version)
        for change in ({'expiry_days':[]},{'expiry_days':[True]},{'expiry_days':[0]},{'expiry_days':[3661]},
            {'dormant_days':0},{'receipt_pending_days':366},{'occupancy_percent':0},{'overstock_multiplier':0},{'key':'changed'}):
            with self.subTest(change=change),self.assertRaises(ValidationError):
                save_policy(self.ops,change,expected=selected.version)
        selected.refresh_from_db()
        self.assertEqual(selected.dormant_days,90)

    def test_reference_without_ledger_is_not_reported_as_recorded_stockout(self):
        self.article.criticality='CRITICAL'
        self.article.save(update_fields=['criticality'])
        result=collect_alerts(self.ops)
        self.assertEqual([row['kind'] for row in result['alerts']],['UNINITIALIZED'])
        self.assertEqual(result['counts']['total'],1)
        self.assertNotIn('UNAVAILABLE',self.kinds())

    def test_stock_thresholds_are_computed_only_for_complete_authorized_scope(self):
        self.article.minimum_stock=12
        self.article.save(update_fields=['minimum_stock'])
        container,_,_=self.receive(expires_on=timezone.localdate()+timedelta(days=1000))
        self.assertIn('LOW_STOCK',self.kinds())
        self.grant(Capability.VIEW_STOCK,location=self.freezer,category=self.category)
        partial=collect_alerts(self.operator)
        self.assertFalse(partial['platform_thresholds_available'])
        self.assertNotIn('LOW_STOCK',{row['kind'] for row in partial['alerts']})
        self.grant(Capability.VIEW_STOCK,category=self.category)
        self.assertIn('LOW_STOCK',self.kinds(self.operator))
        self.article.minimum_stock=0
        self.article.reorder_point=10
        self.article.save(update_fields=['minimum_stock','reorder_point'])
        self.assertIn('REORDER',self.kinds())
        self.article.reorder_point=0
        self.article.target_stock=4
        self.article.save(update_fields=['reorder_point','target_stock'])
        self.assertIn('OVERSTOCK',self.kinds())
        remove_stock(self.ops,container.pk,key=uuid.uuid4(),amount=10,unit=self.unit,reason='Consommation de recette')
        self.assertIn('UNAVAILABLE',self.kinds())
        self.assertNotIn('OVERSTOCK',self.kinds())

    def test_expiry_buckets_after_opening_recall_and_control_are_distinct(self):
        soon,_,_=self.receive('SOON',expires_on=timezone.localdate()+timedelta(days=5))
        late,_,_=self.receive('EXPIRED',accepted=False,expires_on=timezone.localdate()-timedelta(days=1))
        recalled,_,_=self.receive('RECALL',expires_on=timezone.localdate()+timedelta(days=1000))
        control_lot(self.ops,recalled.lot_id,expected=recalled.lot.version,status='RECALLED',reason='Rappel fabricant de recette')
        save_policy(self.ops,{'receipt_pending_days':0},expected=1)
        rows=collect_alerts(self.ops)['alerts']
        kinds={row['kind'] for row in rows}
        self.assertTrue({'EXPIRY_SOON','EXPIRED','RECALL','RECEIPT_CONTROL'}<=kinds)
        soon_alert=next(row for row in rows if row['kind']=='EXPIRY_SOON')
        self.assertEqual(soon_alert['data']['values']['window'],7)
        self.assertIn('5 jours',soon_alert['message'])
        self.assertEqual(rows[0]['severity'],'CRITICAL')

    def test_dormancy_uses_recorded_history_and_does_not_invent_absence_before_intake(self):
        today=timezone.now()
        with patch('django.utils.timezone.now',return_value=today-timedelta(days=200)):
            self.receive(expires_on=(today+timedelta(days=900)).date())
        self.assertIn('DORMANT',self.kinds())
        container=StockContainer.objects.get()
        remove_stock(self.ops,container.pk,key=uuid.uuid4(),amount=1,unit=self.unit,reason='Reprise de consommation')
        self.assertNotIn('DORMANT',self.kinds())

    def test_storage_incident_and_occupied_grid_generate_scoped_alerts(self):
        box=save_location(self.ops,{'code':'ALERT-BOX','name':'Boîte de contrôle','kind':self.storage_kind,
            'parent':self.freezer,'grid_rows':1,'grid_columns':1})
        receive_sample(self.ops,key=uuid.uuid4(),code='ALERT-SAMPLE',amount=10,unit=self.ul,
            location=box,position=box.positions.get(),received_on=timezone.localdate(),reason='Stockage de recette')
        record_temperature(self.ops,location=self.freezer,measured_at=timezone.now(),value=-60)
        rows=collect_alerts(self.ops)['alerts']
        self.assertTrue({'STORAGE_INCIDENT','OCCUPANCY'}<={row['kind'] for row in rows})
        self.assertNotIn('OCCUPANCY',self.kinds(self.operator))
        self.grant(Capability.VIEW_BIOBANK,location=self.freezer)
        self.assertIn('OCCUPANCY',self.kinds(self.operator))
        self.assertIn('STORAGE_INCIDENT',self.kinds(self.operator))

    def test_overdue_task_and_acknowledgement_keep_risk_visible_and_create_only_one_followup(self):
        work=create_work(self.ops,kind='INVENTORY',title='Inventaire à terminer',assignee=self.operator,
            due_on=timezone.localdate()-timedelta(days=1),location=self.freezer,priority='URGENT')
        alert=next(row for row in collect_alerts(self.ops)['alerts'] if row['kind']=='TASK_OVERDUE')
        first=acknowledge(self.ops,alert['signature'],reason='Vérification confiée à un membre',assignee=self.second)
        second=acknowledge(self.ops,alert['signature'],reason='Vérification confiée à un membre',assignee=self.second)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(WorkItem.objects.filter(assignee=self.second).count(),1)
        visible=next(row for row in collect_alerts(self.ops)['alerts'] if row['signature']==alert['signature'])
        self.assertEqual(visible['acknowledgement'].pk,first.pk)
        with self.assertRaises(PermissionDenied):
            acknowledge(self.operator,alert['signature'],reason='Délégation non autorisée',assignee=self.second)
        acknowledged=acknowledge(self.operator,alert['signature'],reason='Comptage en cours')
        self.assertIsNone(acknowledged.work_id)
        work.due_on=timezone.localdate()+timedelta(days=1)
        work.save(update_fields=['due_on'])
        with self.assertRaises(Conflict):
            acknowledge(self.operator,alert['signature'],reason='Ancienne alerte')
        with self.assertRaises(ValidationError):
            first.delete()

    def test_digest_is_daily_deduplicated_grouped_and_optional(self):
        self.receive(expires_on=timezone.localdate()+timedelta(days=2))
        first=send_digest(self.ops)
        self.assertIsNotNone(first)
        again=send_digest(self.ops)
        self.assertEqual(first.pk,again.pk)
        self.assertEqual(AlertDigest.objects.filter(user=self.ops).count(),1)
        self.assertEqual(Notification.objects.filter(user=self.ops,notification_type='SYSTEM').count(),1)
        self.assertEqual(first.notification.link_url,reverse('erp:alerts'))
        self.assertEqual(send_digest(self.operator),None)
        save_policy(self.ops,{'digest_enabled':False},expected=1)
        self.assertIsNone(send_digest(self.ops,day=timezone.localdate()+timedelta(days=1)))
        with self.assertRaises(PermissionDenied):
            send_digest(self.outsider)
        output=StringIO()
        call_command('send_erp_alert_digest',username=self.ops.username,stdout=output)
        self.assertIn('0',output.getvalue())
        with self.assertRaises(CommandError):
            call_command('send_erp_alert_digest',username='unknown-user',stdout=StringIO())

    def test_inactive_storage_ancestor_excludes_stock_and_cannot_be_silently_deactivated(self):
        container,_,_=self.receive()
        with self.assertRaises(ValidationError):
            save_location(self.ops,{'active':False},pk=self.lab.pk,expected=self.lab.version)
        Location.objects.filter(pk=self.lab.pk).update(active=False)
        self.assertFalse(is_usable(container))
        self.assertIn('UNAVAILABLE',self.kinds())

    def test_native_alert_views_filters_policy_and_action_permissions(self):
        self.receive(expires_on=timezone.localdate()+timedelta(days=2))
        self.client.force_login(self.ops)
        response=self.client.get(reverse('erp:alerts'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Alertes et contrôles prioritaires')
        self.assertEqual(self.client.get(reverse('erp:alerts'),{'severity':'HIGH','state':'new'}).status_code,200)
        alert=collect_alerts(self.ops)['alerts'][0]
        url=reverse('erp:alert-action',args=[alert['signature']])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'reason':'Dossier examiné'}).status_code,302)
        self.assertEqual(self.client.get(reverse('erp:alert-policy')).status_code,200)
        data={'expected_version':1,'expiry_days':'60, 30, 7','dormant_days':120,'receipt_pending_days':2,
            'occupancy_percent':'90','overstock_multiplier':'2','digest_enabled':'on'}
        self.assertEqual(self.client.post(reverse('erp:alert-policy'),data).status_code,302)
        invalid=self.client.post(reverse('erp:alert-policy'),{**data,'expiry_days':'bad'})
        self.assertEqual(invalid.status_code,400)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:alerts')).status_code,403)
        self.assertEqual(self.client.get(reverse('erp:alert-policy')).status_code,403)
        with self.assertRaises(PermissionDenied):
            collect_alerts(AnonymousUser())
