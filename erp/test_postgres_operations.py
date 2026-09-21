from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from erp.models import BiologicalSample, CdcGeneration, SampleEvent, StockContainer, StockEntry, StockMovement
from erp.services.biobank import receive_sample, reconcile_biobank
from erp.services.cdc import create_dossier
from erp.services.stock import receive_stock, reconcile_stock, remove_stock
from erp.services.storage import save_location
from erp.test_operations import OperationFixtures
from erp.tests import fixtures


class PostgreSQLOperationalTests(OperationFixtures, TransactionTestCase):
    def setUp(self):
        for name, value in fixtures().items():
            if name != 'User':
                setattr(self, name, value)
        self.ops = get_user_model().objects.create_user(username='pg-ops', role='PLATFORM_ADMIN')

    def race(self, operations):
        barrier = Barrier(len(operations))
        def execute(operation):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                value = operation()
                return ('saved', str(value.pk))
            except (ValidationError, IntegrityError):
                return ('rejected', '')
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            futures = [pool.submit(execute, operation) for operation in operations]
            return [future.result(timeout=45) for future in futures]

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_consumptions_cannot_overdraw_one_container(self):
        container, _, _ = self.receive(quantity=10)
        results = self.race([lambda: remove_stock(self.admin, container.pk, key=uuid.uuid4(),
            amount=7, unit=self.unit, reason='Consommation simultanée') for _ in range(2)])
        self.assertCountEqual([result[0] for result in results], ['saved', 'rejected'])
        container.refresh_from_db()
        self.assertEqual(container.quantity, 3)
        self.assertEqual(StockMovement.objects.filter(kind='CONSUMPTION').count(), 1)
        self.assertEqual(reconcile_stock(self.admin), [])

    @skipUnlessDBFeature('has_select_for_update')
    def test_duplicate_receipt_retry_creates_exactly_one_ledger_operation(self):
        _, _, values = self.receive('BASE')
        values = {**values, 'key': uuid.uuid4(), 'lot_code': 'PG-LOT',
            'manufacturer_lot': 'PG-MFG', 'container_code': 'PG-CONT'}
        results = self.race([lambda: receive_stock(self.admin, **values) for _ in range(2)])
        self.assertEqual([result[0] for result in results], ['saved', 'saved'])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(StockContainer.objects.filter(code='PG-CONT').count(), 1)
        self.assertEqual(StockMovement.objects.filter(key=values['key']).count(), 1)
        self.assertEqual(reconcile_stock(self.admin), [])

    @skipUnlessDBFeature('has_select_for_update')
    def test_two_samples_cannot_occupy_the_same_position(self):
        box = save_location(self.admin, {'code': 'PG-BOX', 'name': 'Boîte de recette',
            'kind': self.storage_kind, 'parent': self.freezer, 'grid_rows': 1, 'grid_columns': 1})
        position = box.positions.get()
        def receive(code):
            return receive_sample(self.admin, key=uuid.uuid4(), code=code, amount=20, unit=self.ul,
                location=box, position=position, received_on=timezone.localdate(), reason='Réception de recette')
        results = self.race([lambda: receive('PG-S1'), lambda: receive('PG-S2')])
        self.assertCountEqual([result[0] for result in results], ['saved', 'rejected'])
        self.assertEqual(BiologicalSample.objects.filter(position=position).count(), 1)
        self.assertEqual(SampleEvent.objects.filter(kind='RECEIPT').count(), 1)
        self.assertEqual(reconcile_biobank(self.admin), [])

    @skipUnlessDBFeature('has_select_for_update')
    def test_sql_blocks_operational_history_changes_and_nonfinite_stock(self):
        container, move, _ = self.receive()
        entry = move.entries.get()
        statements = [
            ('UPDATE erp_stockmovement SET reason = %s WHERE id = %s', ['tamper', move.pk]),
            ('DELETE FROM erp_stockentry WHERE id = %s', [entry.pk]),
            ('UPDATE erp_stockreceipt SET condition = %s WHERE id = %s', ['tamper', move.receipt.pk]),
            ("UPDATE erp_stockcontainer SET quantity = 'NaN' WHERE id = %s", [container.pk]),
            ('UPDATE erp_stockcontainer SET reserved = %s WHERE id = %s', [11, container.pk]),
        ]
        for statement, parameters in statements:
            with self.subTest(statement=statement), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, parameters)
        container.refresh_from_db()
        self.assertEqual((container.quantity, container.reserved), (10, 0))
        self.assertEqual(reconcile_stock(self.admin), [])

    @skipUnlessDBFeature('has_select_for_update')
    def test_sql_prevents_historical_cdc_revision_mutation(self):
        dossier = create_dossier(self.ops, family='equipment', reference='72/SME/SDFM/SG/ESSBO/2026',
            title='Dossier de recette PostgreSQL', assignee=self.operator)
        revision = dossier.revisions.get()
        for sql in ('UPDATE erp_cdcrevision SET reason = %s WHERE id = %s',
                    'DELETE FROM erp_cdcrevision WHERE reason <> %s AND id = %s'):
            with self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, ['tamper', revision.pk])
        revision.refresh_from_db()
        self.assertEqual(revision.reason, '')


    @skipUnlessDBFeature('has_select_for_update')
    def test_simultaneous_resource_bookings_have_only_one_winner(self):
        from datetime import timedelta
        from erp.models import ActivitySchedule, WorkItem
        from erp.services.planning import create_activity, save_resource
        resource=save_resource(self.ops,{'code':'PG-SCHED','name':'Instrument de test','kind':'EQUIPMENT'})
        start=timezone.now()+timedelta(days=1)
        def book(member):
            return create_activity(self.ops,key=uuid.uuid4(),kind='CONTROL',title='Créneau concurrent',assignee=member,
                starts_at=start,ends_at=start+timedelta(hours=1),resources=[resource])
        result=self.race([lambda:book(self.operator),lambda:book(self.ops)])
        self.assertCountEqual([value[0] for value in result],['saved','rejected'])
        self.assertEqual(ActivitySchedule.objects.count(),1)
        self.assertEqual(WorkItem.objects.count(),1)

    @skipUnlessDBFeature('has_select_for_update')
    def test_competing_dependencies_cannot_introduce_a_cycle(self):
        from erp.models import ActivityDependency
        from erp.services.work import create_work
        from erp.services.planning import set_dependencies
        first=create_work(self.ops,kind='CONTROL',title='Premier contrôle',assignee=self.operator)
        second=create_work(self.ops,kind='CONTROL',title='Second contrôle',assignee=self.ops)
        result=self.race([
            lambda:set_dependencies(self.ops,first.pk,expected=first.version,prerequisites=[second],reason='Ordre proposé'),
            lambda:set_dependencies(self.ops,second.pk,expected=second.version,prerequisites=[first],reason='Ordre concurrent')])
        self.assertCountEqual([value[0] for value in result],['saved','rejected'])
        self.assertEqual(ActivityDependency.objects.count(),1)
