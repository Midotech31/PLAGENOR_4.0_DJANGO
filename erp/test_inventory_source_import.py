from io import StringIO
import csv
import uuid

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from erp.models import Article, Category, LocationType, StockContainer, StockReceipt, Unit
from erp.services.bulk_imports import apply_import, preview_import
from erp.test_operations import OperationFixtures


def _csv(rows):
    stream = StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=';')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class RichInventoryImportTests(OperationFixtures, TestCase):
    def _preview(self, kind, rows):
        return preview_import(
            self.ops,
            key=uuid.uuid4(),
            kind=kind,
            filename='inventaire.csv',
            data=_csv(rows),
            reason='Reprise contrôlée de l’inventaire PLAGENOR 2026',
        )

    def test_catalogue_and_initial_stock_preserve_inventory_evidence(self):
        catalog = {
            'code': 'INV-EQUIP-TEST',
            'name': 'Équipement documenté',
            'category_code': self.category.code,
            'base_unit_code': self.unit.code,
            'catalog_reference': 'CAT-2026-01',
            'manufacturer_reference': 'REF-ABC',
            'grade': 'Inventaire historique',
            'format': 'Modèle X',
            'storage_instructions': 'Salle documentée dans la source.',
            'specifications': 'Source : inventaire institutionnel 2026.',
        }
        batch = self._preview('CATALOG', [catalog])
        self.assertTrue(batch.report['valid'], batch.report)
        apply_import(self.ops, batch.pk, expected=batch.version, confirmed=True)
        article = Article.objects.get(code='INV-EQUIP-TEST')
        self.assertEqual(article.catalog_reference, 'CAT-2026-01')
        self.assertEqual(article.manufacturer_reference, 'REF-ABC')
        self.assertEqual(article.grade, 'Inventaire historique')
        self.assertEqual(article.format, 'Modèle X')
        self.assertIn('Salle', article.storage_instructions)

        initial = {
            'article_code': article.code,
            'location_code': self.freezer.code,
            'lot_code': 'INV-EQ-LOT',
            'manufacturer_lot': 'PLAGENOR-2026',
            'container_code': 'INV-EQ-CONT',
            'amount': '1',
            'unit_code': self.unit.code,
            'received_on': timezone.localdate().isoformat(),
            'condition': 'Inventaire existant — état à confirmer',
            'serial_number': 'SN-2026-001',
            'barcode': 'ASSET-2026-001',
            'control_notes': 'Source exacte conservée pour rapprochement.',
        }
        batch = self._preview('INITIAL', [initial])
        self.assertTrue(batch.report['valid'], batch.report)
        apply_import(self.ops, batch.pk, expected=batch.version, confirmed=True)
        container = StockContainer.objects.select_related('lot').get(code='INV-EQ-CONT')
        self.assertEqual(container.lot.serial_number, 'SN-2026-001')
        self.assertEqual(container.lot.barcode, 'ASSET-2026-001')
        self.assertEqual(
            StockReceipt.objects.get(container=container).control_notes,
            'Source exacte conservée pour rapprochement.',
        )


    def test_inventory_reference_bootstrap_is_previewable_and_idempotent(self):
        self.assertFalse(Unit.objects.filter(code='PACK').exists())
        call_command('bootstrap_inventory_references', actor=self.ops.username)
        self.assertFalse(Unit.objects.filter(code='PACK').exists())

        call_command('bootstrap_inventory_references', actor=self.ops.username, apply=True)
        self.assertEqual(Unit.objects.get(code='G').factor, Unit.objects.get(code='ML').factor)
        self.assertEqual(str(Unit.objects.get(code='G').factor), '0.001000000')
        self.assertTrue(Category.objects.filter(code='EQUIPMENT').exists())
        self.assertTrue(Category.objects.filter(code='CHEMICALS').exists())
        self.assertTrue(Category.objects.filter(code='CONSUMABLES').exists())
        self.assertTrue(Category.objects.filter(code='REAGENTS').exists())
        self.assertTrue(LocationType.objects.filter(code='PLAGENOR_ROOM', can_store=True).exists())

        counts = (Unit.objects.count(), Category.objects.count(), LocationType.objects.count())
        call_command('bootstrap_inventory_references', actor=self.ops.username, apply=True)
        self.assertEqual(counts, (Unit.objects.count(), Category.objects.count(), LocationType.objects.count()))

    def test_equipment_inventory_view_reuses_stock_entities(self):
        call_command('bootstrap_inventory_references', actor=self.ops.username, apply=True)
        catalog = {
            'code': 'EQ-VIEW-TEST',
            'name': 'Séquenceur de test',
            'category_code': 'EQUIPMENT',
            'base_unit_code': 'PIECE',
            'catalog_reference': 'REF-VIEW',
            'format': 'Model View',
        }
        batch = self._preview('CATALOG', [catalog])
        self.assertTrue(batch.report['valid'], batch.report)
        apply_import(self.ops, batch.pk, expected=batch.version, confirmed=True)
        initial = {
            'article_code': 'EQ-VIEW-TEST',
            'location_code': self.freezer.code,
            'lot_code': 'EQ-VIEW-LOT',
            'manufacturer_lot': 'INVENTAIRE-2026',
            'container_code': 'EQ-VIEW-CONT',
            'amount': '1',
            'unit_code': 'PIECE',
            'received_on': timezone.localdate().isoformat(),
            'condition': 'Inventaire existant — état non documenté',
            'serial_number': 'SERIAL-VIEW-001',
        }
        batch = self._preview('INITIAL', [initial])
        self.assertTrue(batch.report['valid'], batch.report)
        apply_import(self.ops, batch.pk, expected=batch.version, confirmed=True)

        self.client.force_login(self.ops)
        response = self.client.get('/erp/equipment/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Séquenceur de test')
        self.assertContains(response, 'Model View')
        self.assertContains(response, 'SERIAL-VIEW-001')
