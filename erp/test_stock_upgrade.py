"""Exercise the actual additive upgrade on populated legacy stock tables."""
from datetime import timedelta
from decimal import Decimal
import uuid
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone


class ScientificStockUpgradeTests(TransactionTestCase):
    def test_legacy_identifiers_quantities_references_and_immutable_history_survive(self):
        executor = MigrationExecutor(connection)
        target = executor.loader.graph.leaf_nodes('erp')
        source = [('erp', '0029_cdcreusepreview')]
        executor.migrate(source)
        try:
            apps = executor.loader.project_state(source).apps
            def model(name):
                return apps.get_model('erp', name)
            actor = get_user_model().objects.create_user(username='legacy-stock-upgrade', role='PLATFORM_ADMIN')
            unit = model('Unit').objects.create(code='OLD-UNIT', name='Unité historique', dimension='COUNT', factor=1)
            category = model('Category').objects.create(code='OLD-CAT', name='Catégorie historique')
            party = model('Party').objects.create(code='OLD-PARTY', name='Fabricant historique', is_manufacturer=True, is_supplier=True)
            kind = model('LocationType').objects.create(code='OLD-KIND', name='Stockage', can_store=True)
            location = model('Location').objects.create(code='OLD-LOCATION', name='Laboratoire', kind=kind)
            article = model('Article').objects.create(code='OLD-ARTICLE', name='Réactif historique', category=category,
                base_unit=unit, manufacturer=party, manufacturer_reference='OLD-MF-00012', catalog_reference='OLD-CAT-00123', preferred_supplier=party)
            day = timezone.localdate() - timedelta(days=30)
            lot = model('StockLot').objects.create(code='OLD-LOT', name='Lot historique', article=article,
                manufacturer_lot='BATCH-0012', serial_number='SN-00012', status='AVAILABLE')
            container = model('StockContainer').objects.create(code='OLD-CONTAINER', name='Contenant historique',
                lot=lot, location=location, quantity=Decimal('10.125'), reserved=Decimal('.125'), status='AVAILABLE')
            snapshot = {'article': 'OLD-ARTICLE', 'manufacturer_reference': 'OLD-MF-00012', 'legacy': ['préserver', '00012']}
            movement = model('StockMovement').objects.create(key=uuid.uuid4(), payload_hash='a' * 64,
                kind='RECEIPT', actor_id=actor.pk, reason='Réception historique', snapshot=snapshot)
            entry = model('StockEntry').objects.create(movement=movement, container=container, location=location,
                quantity_delta=Decimal('10.125'), reserved_delta=Decimal('.125'), snapshot=snapshot)
            receipt = model('StockReceipt').objects.create(movement=movement, container=container,
                supplier=party, order_reference='BC-HISTORIQUE', received_on=day,
                received_quantity=Decimal('10.125'), condition='Intact', unit_price=Decimal('12.50'), currency='DZD')
            identifiers = [obj.pk for obj in (article, lot, container, movement, entry, receipt)]
            if connection.vendor == 'postgresql':
                from django.core.files.storage import FileSystemStorage
                from scripts.production_stock_upgrade import migrate_safely
                with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'RENDER_GIT_COMMIT': 'a' * 40}):
                    backup = {'backup_object': 'database_backups/ci-only.dump.fernet', 'plaintext_bytes': 1024}
                    evidence = migrate_safely(backup=lambda: backup, storage=FileSystemStorage(location=directory))
                    self.assertEqual(evidence['status'], 'verified')
                    self.assertEqual(evidence['tables']['erp.stockcontainer']['rows'], 1)
            else:
                MigrationExecutor(connection).migrate(target)
            from erp.models import Article, StockContainer, StockEntry, StockLot, StockMovement, StockReceipt
            from erp.services.stock import fefo, reconcile_stock
            from erp.services.stock_reporting import entry_balances
            from erp.services.stock_exports import stock_table
            objects = [cls.objects.get(pk=pk) for cls, pk in zip(
                (Article, StockLot, StockContainer, StockMovement, StockEntry, StockReceipt), identifiers)]
            self.assertEqual([obj.pk for obj in objects], identifiers)
            self.assertEqual((objects[0].catalog_reference, objects[0].manufacturer_reference), ('OLD-CAT-00123', 'OLD-MF-00012'))
            self.assertEqual((objects[2].quantity, objects[2].reserved), (Decimal('10.125'), Decimal('.125')))
            self.assertEqual(objects[3].snapshot, snapshot)
            self.assertEqual(objects[4].snapshot, snapshot)
            self.assertEqual(objects[5].order_reference, 'BC-HISTORIQUE')
            self.assertEqual(objects[5].delivery_reference, '')
            self.assertIsNone(objects[2].fifo_received_on)
            self.assertEqual(fefo(actor, objects[0]).get().fifo_date, day)
            self.assertEqual(stock_table(StockContainer.objects.select_related('lot__article__base_unit', 'location'))[1][0][18], day)
            self.assertEqual(entry_balances([objects[4]])[0].physical_after, Decimal('10.125'))
            self.assertEqual(reconcile_stock(actor), [])
        finally:
            MigrationExecutor(connection).migrate(target)

    def test_normal_and_already_upgraded_startups_use_the_regular_migration_command(self):
        from scripts.production_stock_upgrade import migrate_safely
        with patch('scripts.production_stock_upgrade.call_command') as command:
            self.assertIsNone(migrate_safely())
        command.assert_called_once_with('migrate', interactive=False)

    @skipUnlessDBFeature('has_select_for_update')
    def test_backup_failure_refuses_upgrade_and_rolls_back(self):
        from django.db.migrations.recorder import MigrationRecorder
        from scripts.production_stock_upgrade import migrate_safely, UPGRADE
        executor = MigrationExecutor(connection)
        target = executor.loader.graph.leaf_nodes('erp')
        executor.migrate([('erp', '0029_cdcreusepreview')])
        try:
            def failed_backup():
                raise RuntimeError('Synthetic backup failure')
            with patch.dict('os.environ', {'RENDER_GIT_COMMIT': 'b' * 40}), self.assertRaisesMessage(RuntimeError, 'Synthetic backup failure'):
                migrate_safely(backup=failed_backup)
            self.assertNotIn(UPGRADE, MigrationRecorder(connection).applied_migrations())
        finally:
            MigrationExecutor(connection).migrate(target)

    @skipUnlessDBFeature('has_select_for_update')
    def test_failed_preservation_check_rolls_back_schema_and_migration_records(self):
        from django.db.migrations.recorder import MigrationRecorder
        from scripts.production_stock_upgrade import migrate_safely, UPGRADE
        executor = MigrationExecutor(connection)
        target = executor.loader.graph.leaf_nodes('erp')
        executor.migrate([('erp', '0029_cdcreusepreview')])
        try:
            backup = {'backup_object': 'database_backups/ci-only.dump.fernet', 'plaintext_bytes': 1024}
            with patch.dict('os.environ', {'RENDER_GIT_COMMIT': 'c' * 40}), patch(
                    'scripts.production_stock_upgrade.manifest', side_effect=[{}, {'changed': True}]), self.assertRaisesMessage(
                    RuntimeError, 'Existing ERP data changed'):
                migrate_safely(backup=lambda: backup)
            self.assertNotIn(UPGRADE, MigrationRecorder(connection).applied_migrations())
        finally:
            MigrationExecutor(connection).migrate(target)
