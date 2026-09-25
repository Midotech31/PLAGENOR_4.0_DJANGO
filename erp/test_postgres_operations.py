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
    def test_concurrent_cdc_workbook_confirmation_creates_one_revision(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from erp.services.cdc_exchange import export_workbook, preview_workbook, apply_workbook
        dossier = create_dossier(self.ops, family='equipment', reference='73/SME/SDFM/SG/ESSBO/2026',
            title='Confirmation Excel concurrente', assignee=self.operator)
        preview = preview_workbook(self.ops, dossier.pk, expected=dossier.version,
            upload=SimpleUploadedFile('lots.xlsx', export_workbook(self.ops, dossier)),
            mode='merge', reason='Import confirmé simultanément')
        results = self.race([lambda: apply_workbook(self.ops, preview.pk) for _ in range(2)])
        self.assertEqual([result[0] for result in results], ['saved', 'saved'])
        self.assertEqual(results[0][1], results[1][1])
        dossier.refresh_from_db()
        self.assertEqual(dossier.revision_number, 2)
        self.assertEqual(dossier.revisions.count(), 2)

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
    def test_new_cdc_and_procurement_history_is_sql_immutable(self):
        from erp.models import CdcItem, CdcReviewDecision, ProcurementCdcItemLink
        from erp.services.cdc import (create_clause_revision, review_dossier, save_clause,
            save_cdc_item)
        from erp.services.procurement import plan_from_cdc

        dossier = create_dossier(self.ops, family='reagents',
            reference='78/SME/SDFM/SG/ESSBO/2026', title='Historique CDC SQL',
            assignee=self.operator)
        CdcItem.objects.filter(lot__dossier=dossier).update(active=False)
        dossier.refresh_from_db()
        lot = dossier.lots.first()
        save_cdc_item(self.ops, lot.pk, expected=dossier.version,
            values={'quantity': Decimal('4')}, article=self.article,
            purchase_unit=self.unit, reason='Besoin structuré')
        dossier.refresh_from_db()

        plan = plan_from_cdc(self.ops, dossier.pk, expected=dossier.version,
            plan_reference='PG-CDC-HISTORY', year=timezone.localdate().year,
            reason='Déficit confirmé')
        provenance = ProcurementCdcItemLink.objects.get(line__plan=plan)

        clause = save_clause(self.ops, values={'code':'PG.CLAUSE','name':'Clause PG',
            'name_en':'','name_ar':'','title':'Clause PostgreSQL','active':True},
            reason='Référentiel PostgreSQL')
        clause_revision = create_clause_revision(self.ops, clause,
            text_fr='Texte immuable', source_reference='Source PostgreSQL', activate=True)

        dossier.work.status = 'SUBMITTED'
        dossier.work.save(update_fields=['status'])
        decision = review_dossier(self.ops, dossier.pk, expected=dossier.version,
            stage=CdcReviewDecision.Stage.TECHNICAL,
            outcome=CdcReviewDecision.Outcome.APPROVED, comment='Revue SQL')

        statements = [
            ('UPDATE erp_procurementcdcitemlink SET reason=%s WHERE id=%s',
                ['tamper', provenance.pk]),
            ('UPDATE erp_cdcclauserevision SET status=%s WHERE id=%s',
                ['RETIRED', clause_revision.pk]),
            ('DELETE FROM erp_cdcreviewdecision WHERE id=%s', [decision.pk]),
        ]
        for sql, args in statements:
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, args)

        provenance.refresh_from_db()
        clause_revision.refresh_from_db()
        self.assertEqual(provenance.reason, 'Déficit confirmé')
        self.assertEqual(clause_revision.status, 'ACTIVE')
        self.assertTrue(CdcReviewDecision.objects.filter(pk=decision.pk).exists())


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


    def procurement_order(self):
        from datetime import timedelta
        from erp.services.procurement import create_plan,add_plan_article,decide_plan_line,submit_plan,approve_plan
        from erp.services.purchases import create_order,save_order_line,confirm_order
        today=timezone.localdate()
        plan=create_plan(self.ops,reference='PG-PLAN',year=today.year+1,title='Approvisionnement de recette',assignee=self.operator,allow_costs=True)
        line=add_plan_article(self.ops,plan.pk,expected=plan.version,article=self.article,lot_name='Lot de recette')
        plan.refresh_from_db()
        decide_plan_line(self.ops,line.pk,expected=plan.version,values={'retained_quantity':Decimal(10),
            'estimated_price':Decimal(100),'tax_rate':Decimal(19),'currency':'DZD',
            'price_source':'Devis de recette','decision_reason':'Besoins contrôlés'})
        plan.refresh_from_db()
        submit_plan(self.operator,plan.pk,expected=plan.version,reason='Plan préparé')
        plan.refresh_from_db()
        approve_plan(self.ops,plan.pk,expected=plan.version,reason='Plan validé')
        plan.refresh_from_db()
        order=create_order(self.ops,plan.pk,expected=plan.version,reference='PG-ORDER',supplier=self.party,
            ordered_on=today,expected_on=today+timedelta(days=10))
        item=save_order_line(self.ops,order.pk,expected=order.version,plan_line=line,quantity=10,
            unit_price=Decimal(100),tax_rate=Decimal(19),currency='DZD')
        order.refresh_from_db()
        confirm_order(self.ops,order.pk,expected=order.version,reason='Commande documentée')
        order.refresh_from_db()
        return plan,line,order,item

    @skipUnlessDBFeature('has_select_for_update')
    def test_competing_partial_deliveries_cannot_exceed_ordered_quantity(self):
        from erp.services.purchases import receive_order_line,received_quantity
        plan,line,order,item=self.procurement_order()
        def deliver(code):
            return receive_order_line(self.ops,item.pk,expected=order.version,key=uuid.uuid4(),amount=7,
                location=self.freezer,lot_code='PG-L-'+code,manufacturer_lot='PG-M-'+code,
                container_code='PG-C-'+code,received_on=timezone.localdate(),condition='Intact')
        result=self.race([lambda:deliver('A'),lambda:deliver('B')])
        self.assertCountEqual([value[0] for value in result],['saved','rejected'])
        self.assertEqual(received_quantity(item),7)
        self.assertEqual(StockMovement.objects.filter(kind='RECEIPT').count(),1)
        self.assertEqual(reconcile_stock(self.ops),[])

    @skipUnlessDBFeature('has_select_for_update')
    def test_duplicate_purchase_delivery_has_one_receipt_and_one_balance_change(self):
        from erp.services.purchases import receive_order_line,received_quantity
        plan,line,order,item=self.procurement_order()
        params={'expected':order.version,'key':uuid.uuid4(),'amount':10,'location':self.freezer,
            'lot_code':'PG-REPLAY-L','manufacturer_lot':'PG-REPLAY-M','container_code':'PG-REPLAY-C',
            'received_on':timezone.localdate(),'condition':'Intact'}
        result=self.race([lambda:receive_order_line(self.ops,item.pk,**params) for count in range(2)])
        self.assertEqual([value[0] for value in result],['saved','saved'])
        self.assertEqual(result[0][1],result[1][1])
        self.assertEqual(received_quantity(item),10)
        self.assertEqual(StockMovement.objects.filter(kind='RECEIPT').count(),1)
        self.assertEqual(reconcile_stock(self.ops),[])

    @skipUnlessDBFeature('has_select_for_update')
    def test_approved_plan_order_and_revisions_are_immutable_even_through_sql(self):
        plan,line,order,item=self.procurement_order()
        statements=[
            ('UPDATE erp_procurementline SET retained_quantity=11 WHERE id=%s',[line.pk]),
            ('DELETE FROM erp_procurementline WHERE id=%s',[line.pk]),
            ('UPDATE erp_purchaseorderline SET quantity=11 WHERE id=%s',[item.pk]),
            ('DELETE FROM erp_purchaseorderline WHERE id=%s',[item.pk]),
            ('UPDATE erp_procurementplan SET approved_revision_id=NULL WHERE id=%s',[plan.pk]),
            ('DELETE FROM erp_procurementrevision WHERE id=%s',[plan.approved_revision_id]),
        ]
        for sql,args in statements:
            with self.subTest(sql=sql),self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql,args)
        line.refresh_from_db()
        self.assertEqual(line.retained_quantity,10)
        item.refresh_from_db()
        self.assertEqual(item.quantity,10)

    @skipUnlessDBFeature('has_select_for_update')
    def test_procurement_rejects_nonfinite_quantities_prices_and_factors_in_database(self):
        from erp.services.procurement import create_plan,add_plan_article
        plan=create_plan(self.ops,reference='PG-FINITE',year=timezone.localdate().year+1,title='Contrôle numérique')
        line=add_plan_article(self.ops,plan.pk,expected=plan.version,article=self.article,lot_name='Lot')
        for column in ('retained_quantity','proposed_quantity','estimated_price','purchase_factor','tax_rate'):
            with self.subTest(column=column),self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('UPDATE erp_procurementline SET '+column+"='NaN' WHERE id=%s",[line.pk])


    @skipUnlessDBFeature('has_select_for_update')
    def test_competing_transfers_reject_second_stale_physical_location(self):
        from erp.services.stock import transfer_stock
        container,_,_=self.receive()
        first=save_location(self.ops,{'code':'PG-DEST-1','name':'Destination une','kind':self.storage_kind,'parent':self.lab})
        second=save_location(self.ops,{'code':'PG-DEST-2','name':'Destination deux','kind':self.storage_kind,'parent':self.lab})
        result=self.race([lambda:transfer_stock(self.ops,container.pk,key=uuid.uuid4(),destination=first,
            expected=container.version,reason='Déplacement un'),
            lambda:transfer_stock(self.ops,container.pk,key=uuid.uuid4(),destination=second,
            expected=container.version,reason='Déplacement deux')])
        self.assertCountEqual([row[0] for row in result],['saved','rejected'])
        self.assertEqual(StockMovement.objects.filter(kind='TRANSFER').count(),1)
        self.assertEqual(reconcile_stock(self.ops),[])

    @skipUnlessDBFeature('has_select_for_update')
    def test_competing_confirmations_of_one_import_apply_only_once(self):
        from erp.models import ImportBatch
        from erp.services.bulk_imports import preview_import,apply_import
        from erp.test_imports import csv_file
        data=csv_file([{'article_code':self.article.code,'location_code':self.freezer.code,'lot_code':'PG-IMPORT-L',
            'manufacturer_lot':'PG-IMPORT-M','container_code':'PG-IMPORT-C','amount':'10','unit_code':self.unit.code,
            'received_on':timezone.localdate().isoformat(),'condition':'Intact'}])
        batch=preview_import(self.ops,key=uuid.uuid4(),kind='INITIAL',filename='stock.csv',data=data,reason='Reprise contrôlée')
        self.assertFalse(StockMovement.objects.exists())
        result=self.race([lambda:apply_import(self.ops,batch.pk,expected=batch.version,confirmed=True) for count in range(2)])
        self.assertEqual([row[0] for row in result],['saved','saved'])
        self.assertEqual(result[0][1],result[1][1])
        self.assertEqual(StockMovement.objects.filter(kind='INITIAL').count(),1)
        self.assertEqual(StockContainer.objects.get().quantity,10)
        for sql in ("UPDATE erp_importbatch SET payload='[]'::jsonb WHERE id=%s",'DELETE FROM erp_importbatch WHERE id=%s'):
            with self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql,[batch.pk])
        self.assertEqual(reconcile_stock(self.ops),[])

    @skipUnlessDBFeature('has_select_for_update')
    def test_document_and_alert_evidence_cannot_be_modified_through_sql(self):
        from datetime import timedelta
        from erp.services.alerts import acknowledge,collect_alerts,send_digest
        from erp.services.safety import attach_document
        from erp.services.work import create_work
        from erp.test_safety import pdf_bytes
        document=attach_document(self.ops,'article',self.article.pk,title='Preuve de recette',kind='CERTIFICATE',
            filename='preuve.pdf',data=pdf_bytes(),source='Document synthétique de test')
        work=create_work(self.ops,kind='CONTROL',title='Contrôle en retard',assignee=self.operator,
            due_on=timezone.localdate()-timedelta(days=1))
        row=collect_alerts(self.ops)['alerts'][0]
        acknowledgement=acknowledge(self.ops,row['signature'],reason='Action documentée')
        digest=send_digest(self.ops)
        statements=[('UPDATE erp_resourcedocument SET content=%s WHERE id=%s',[b'tamper',document.pk]),
            ('DELETE FROM erp_resourcedocument WHERE id=%s',[document.pk]),
            ('UPDATE erp_alertacknowledgement SET reason=%s WHERE id=%s',['tamper',acknowledgement.pk]),
            ('DELETE FROM erp_alertdigest WHERE id=%s',[digest.pk])]
        for sql,values in statements:
            with self.subTest(sql=sql),self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql,values)
