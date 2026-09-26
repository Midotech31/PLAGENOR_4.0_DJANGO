from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from erp.models import (
    EquipmentInventorySource, LegacyInventoryRecord, PlanningResource,
)


@skipUnlessDBFeature('has_select_for_update')
class InventorySourcePostgreSQLIntegrityTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='inventory-pg-admin',
            password='x',
            role='SUPER_ADMIN',
            is_staff=True,
            is_superuser=True,
        )
        self.resource = PlanningResource.objects.create(
            code='INVPG-EQ',
            name='Équipement de contrôle',
            kind=PlanningResource.Kind.EQUIPMENT,
        )
        self.source = LegacyInventoryRecord.objects.create(
            source_key='INV26:PG:SOURCE',
            source_file='Laboratory Inventory List 01.docx',
            source_section='Salle 01',
            source_row='2',
            kind=LegacyInventoryRecord.Kind.EQUIPMENT,
            fingerprint='a' * 64,
            raw_data={'Equipment Name': 'Équipement de contrôle'},
            resolution=LegacyInventoryRecord.Resolution.IMPORTED,
            entity_type='erp.planningresource',
            entity_id=self.resource.pk,
        )
        self.evidence = EquipmentInventorySource.objects.create(
            resource=self.resource,
            source_record=self.source,
            source_designation='Équipement de contrôle',
            model='Model A',
            reference='REF-A',
            source_serial_number='SER-A',
            source_quantity=1,
            source_file=self.source.source_file,
            source_row=self.source.source_row,
            source_room='01',
            source_fingerprint=self.source.fingerprint,
        )

    def _blocked(self, sql, params):
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, params)

    def test_equipment_source_evidence_is_sql_immutable(self):
        self._blocked(
            'UPDATE erp_equipmentinventorysource SET model = %s WHERE id = %s',
            ['tampered', str(self.evidence.pk)],
        )
        self._blocked(
            'DELETE FROM erp_equipmentinventorysource WHERE id = %s',
            [str(self.evidence.pk)],
        )
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.model, 'Model A')
        self.assertTrue(
            EquipmentInventorySource.objects.filter(pk=self.evidence.pk).exists()
        )

    def test_legacy_raw_source_is_immutable_but_review_state_is_editable(self):
        self._blocked(
            'UPDATE erp_legacyinventoryrecord SET fingerprint = %s WHERE id = %s',
            ['b' * 64, str(self.source.pk)],
        )
        self._blocked(
            'UPDATE erp_legacyinventoryrecord SET raw_data = %s::jsonb WHERE id = %s',
            ['{}', str(self.source.pk)],
        )
        self._blocked(
            'DELETE FROM erp_legacyinventoryrecord WHERE id = %s',
            [str(self.source.pk)],
        )

        LegacyInventoryRecord.objects.filter(pk=self.source.pk).update(
            review_status=LegacyInventoryRecord.ReviewStatus.CONFIRMED,
            review_note='Contrôle humain documenté.',
            reviewed_by=self.user,
        )
        self.source.refresh_from_db()
        self.assertEqual(
            self.source.review_status,
            LegacyInventoryRecord.ReviewStatus.CONFIRMED,
        )
        self.assertEqual(self.source.fingerprint, 'a' * 64)
        self.assertEqual(
            self.source.raw_data,
            {'Equipment Name': 'Équipement de contrôle'},
        )
