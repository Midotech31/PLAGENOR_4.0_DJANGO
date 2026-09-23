"""Inventory authorization and snapshot boundaries preserve stock ledger integrity."""
import uuid
from django.core.exceptions import ValidationError
from django.test import TestCase

from erp.models import InventoryCampaign, StockMovement, WorkItem
from erp.services.common import Conflict
from erp.services.inventory import (approve_inventory, count_inventory, create_inventory,
    recount_inventory, submit_inventory)
from erp.services.stock import reconcile_stock, transfer_stock
from erp.test_operations import OperationFixtures


class InventoryContracts(OperationFixtures, TestCase):
    def test_empty_scope_rolls_back_campaign_and_work(self):
        self.receive()
        with self.assertRaises(ValidationError):
            create_inventory(self.ops, title='Périmètre vide', category=self.other, assignee=self.operator)
        self.assertFalse(InventoryCampaign.objects.exists())
        self.assertFalse(WorkItem.objects.exists())

    def test_count_rejects_container_that_moved_outside_snapshot(self):
        container, _, _ = self.receive()
        campaign = create_inventory(self.ops, title='Comptage', location=self.freezer, assignee=self.operator)
        line = campaign.lines.get()
        from erp.services.storage import save_location
        destination = save_location(self.ops, {'code': 'INVENTORY-DEST', 'name': 'Autre stockage',
            'kind': self.storage_kind, 'parent': self.lab})
        transfer_stock(self.ops, container.pk, key=uuid.uuid4(), destination=destination, reason='Déplacement')
        container.refresh_from_db()
        with self.assertRaises(ValidationError):
            count_inventory(self.operator, line.pk, expected=line.version,
                container_version=container.version, amount=10)
        line.refresh_from_db()
        self.assertIsNone(line.counted_quantity)
        self.assertEqual(reconcile_stock(self.ops), [])

    def test_recount_and_approval_require_submitted_campaign_and_valid_lines(self):
        container, _, _ = self.receive()
        campaign = create_inventory(self.ops, title='Comptage', category=self.category, assignee=self.operator)
        line = campaign.lines.get()
        for action in ('recount', 'approve'):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                if action == 'recount':
                    recount_inventory(self.ops, campaign.pk, expected=campaign.work.version,
                        line_ids=[line.pk], reason='Recomptage')
                else:
                    approve_inventory(self.ops, campaign.pk, expected=campaign.work.version,
                        key=uuid.uuid4(), reason='Validation')
        count_inventory(self.operator, line.pk, expected=line.version, container_version=container.version, amount=9)
        campaign.work.refresh_from_db()
        submit_inventory(self.operator, campaign.pk, expected=campaign.work.version, reason='Comptage terminé')
        campaign.work.refresh_from_db()
        for identities in ([], [uuid.uuid4()], [line.pk, uuid.uuid4()]):
            with self.subTest(identities=identities), self.assertRaises(ValidationError):
                recount_inventory(self.ops, campaign.pk, expected=campaign.work.version,
                    line_ids=identities, reason='Recomptage')
        approved = approve_inventory(self.ops, campaign.pk, expected=campaign.work.version,
            key=uuid.uuid4(), reason='Validation')
        with self.assertRaises(Conflict):
            approve_inventory(self.ops, campaign.pk, expected=campaign.work.version,
                key=uuid.uuid4(), reason='Validation')
        self.assertEqual(StockMovement.objects.filter(kind='INVENTORY').count(), 1)
        container.refresh_from_db()
        self.assertEqual(container.quantity, 9)
        self.assertEqual(reconcile_stock(self.ops), [])
