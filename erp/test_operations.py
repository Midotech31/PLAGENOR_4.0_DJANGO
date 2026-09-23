from datetime import date, timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from erp.models import (Capability, CdcDossier, InventoryLine, StockContainer, StockEntry,
    StockLot, StockMovement, StockReservation, WorkComment, WorkItem)
from erp.permissions import has_access, operational_scope
from erp.services.access import save_grant
from erp.services.cdc import create_dossier, document_data, save_cdc_item
from erp.services.common import Conflict
from erp.services.inventory import (approve_inventory, count_inventory, create_inventory,
                                   recount_inventory, submit_inventory)
from erp.services.stock import (control_container, control_lot, fefo, is_usable, open_container,
    receive_stock, reconcile_stock, release_stock, remove_stock, reserve_stock, reverse_stock,
    stock_quantity, transfer_stock)
from erp.services.work import (comment_work, create_work, delegate_work, transition_work,
                              work_allowed, work_scope)
from erp.tests import fixtures
from notifications.models import Notification


class OperationFixtures:
    @classmethod
    def setUpTestData(cls):
        for name, value in fixtures().items():
            if name != 'User':
                setattr(cls, name, value)
        cls.ops = get_user_model().objects.create_user(username='erp-ops', role='PLATFORM_ADMIN')
        cls.second = get_user_model().objects.create_user(username='erp-other-member', role='MEMBER')

    def grant(self, capability, user=None, **scope):
        return save_grant(self.admin, {'user': user or self.operator, 'capability': capability, **scope})

    def receive(self, suffix='1', quantity=10, accepted=True, **changes):
        values = {'key': uuid.uuid4(), 'article': self.article, 'location': self.freezer,
            'manufacturer_lot': 'M-' + suffix, 'lot_code': 'LOT-' + suffix,
            'container_code': 'CONT-' + suffix, 'amount': Decimal(quantity), 'unit': self.unit,
            'received_on': timezone.localdate(), 'condition': 'Emballage intact',
            'expires_on': timezone.localdate() + timedelta(days=100), 'supplier': self.party}
        values.update(changes)
        move = receive_stock(self.admin, **values)
        container = move.receipt.container
        if accepted:
            container = control_container(self.admin, container.pk, expected=container.version,
                status=StockLot.Status.AVAILABLE, reason='Contrôle documentaire et physique conforme')
        return container, move, values


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                   SECURE_SSL_REDIRECT=False,
                   STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class WorkAndStockTests(OperationFixtures, TestCase):
    def test_admin_ops_delegates_cdc_without_global_rights_and_can_revoke(self):
        task = create_work(self.ops, kind='CDC', title='Préparer le CDC annuel', assignee=self.operator,
                           due_on=timezone.localdate() + timedelta(days=7))
        self.assertTrue(has_access(self.operator))
        self.assertTrue(work_allowed(self.operator, task, edit=True))
        self.assertFalse(work_allowed(self.operator, task, costs=True))
        self.assertEqual(work_scope(self.operator).get().pk, task.pk)
        self.assertFalse(work_scope(self.outsider).exists())
        self.assertFalse(work_allowed(self.outsider, task))
        self.assertEqual(Notification.objects.filter(user=self.operator).count(), 1)
        with self.assertRaises(PermissionDenied):
            delegate_work(self.operator, task.pk, expected=task.version, assignee=self.second)
        with self.assertRaises(ValidationError):
            transition_work(self.operator, task.pk, expected=task.version, state='SUBMITTED')
        with self.assertRaises(PermissionDenied):
            transition_work(self.operator, task.pk, expected=task.version, state='APPROVED')
        task = delegate_work(self.ops, task.pk, expected=task.version, assignee=self.second,
                             allow_costs=True, reason='Répartition de la charge')
        self.assertFalse(work_allowed(self.operator, task))
        self.assertTrue(work_allowed(self.second, task, costs=True))
        self.assertFalse(work_scope(self.operator).exists())
        with self.assertRaises(PermissionDenied):
            comment_work(self.operator, task.pk, 'Ancien membre')
        task = delegate_work(self.ops, task.pk, expected=task.version, assignee=None, reason='Retrait temporaire')
        self.assertEqual(task.status, 'DRAFT')
        self.assertFalse(task.allow_costs)
        self.assertFalse(work_scope(self.second).exists())

    def test_invalid_assignees_versions_cost_scope_and_work_transitions(self):
        with self.assertRaises(PermissionDenied):
            create_work(self.operator, kind='CONTROL', title='Interdit')
        with self.assertRaises(ValidationError):
            create_work(self.ops, kind='CONTROL', title='Contrôle', assignee=self.outsider)
        with self.assertRaises(ValidationError):
            create_work(self.ops, kind='INVENTORY', title='Inventaire', allow_costs=True)
        task = create_work(self.ops, kind='CONTROL', title='Vérifier les péremptions')
        self.assertEqual(str(task), task.title)
        with self.assertRaises(Conflict):
            delegate_work(self.ops, task.pk, expected=99, assignee=self.operator)
        task = delegate_work(self.ops, task.pk, expected=task.version, assignee=self.operator)
        with self.assertRaises(ValidationError):
            delegate_work(self.ops, task.pk, expected=task.version, assignee=self.second)
        with self.assertRaises(ValidationError):
            delegate_work(self.ops, task.pk, expected=task.version, assignee=self.operator, allow_costs=True)
        task = transition_work(self.operator, task.pk, expected=task.version, state='IN_PROGRESS')
        for state, reason in [('SUBMITTED', ''), ('DRAFT', ''), ('APPROVED', '')]:
            with self.subTest(state=state), self.assertRaises((PermissionDenied, ValidationError)):
                transition_work(self.operator, task.pk, expected=task.version, state=state, reason=reason)
        task = transition_work(self.operator, task.pk, expected=task.version, state='SUBMITTED', reason='Contrôle terminé')
        with self.assertRaises(ValidationError):
            transition_work(self.ops, task.pk, expected=task.version, state='CHANGES_REQUESTED')
        task = transition_work(self.ops, task.pk, expected=task.version, state='CHANGES_REQUESTED', reason='Vérifier le second congélateur')
        task = transition_work(self.operator, task.pk, expected=task.version, state='SUBMITTED', reason='Vérification complétée')
        task = transition_work(self.ops, task.pk, expected=task.version, state='APPROVED')
        self.assertEqual(task.approved_by, self.ops)
        with self.assertRaises(ValidationError):
            delegate_work(self.ops, task.pk, expected=task.version, assignee=self.operator)
        with self.assertRaises(ValidationError):
            transition_work(self.ops, task.pk, expected=task.version, state='CANCELLED', reason='Clôturé')
        self.assertGreaterEqual(task.comments.count(), 3)
        with self.assertRaises(ValidationError):
            task.comments.update(body='Réécriture')
        for invalid in ('', ' ' * 3, 'x' * 10001):
            with self.assertRaises(ValidationError):
                comment_work(self.ops, task.pk, invalid)
        comment = comment_work(self.operator, task.pk, 'Document archivé')
        self.assertEqual(comment.body, 'Document archivé')
        task2 = create_work(self.ops, kind='RECEIPT', title='Contrôle', assignee=self.operator)
        task2 = transition_work(self.ops, task2.pk, expected=task2.version, state='CANCELLED', reason='Commande annulée')
        self.assertFalse(work_allowed(self.operator, task2))

    def test_receipt_quarantine_acceptance_and_idempotence(self):
        container, move, values = self.receive(accepted=False)
        self.assertFalse(is_usable(container))
        self.assertEqual(container.quantity, 10)
        self.assertEqual(receive_stock(self.admin, **values).pk, move.pk)
        self.assertEqual(StockContainer.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        with self.assertRaises(Conflict):
            receive_stock(self.admin, **{**values, 'amount': Decimal(11)})
        with self.assertRaises(ValidationError):
            remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=1, unit=self.unit)
        container = control_container(self.admin, container.pk, expected=container.version,
            status='AVAILABLE', reason='Accepté')
        self.assertTrue(is_usable(container))
        self.assertEqual(reconcile_stock(self.admin), [])
        for model in (StockMovement, StockEntry):
            with self.assertRaises(ValidationError):
                model.objects.all().delete()
        with self.assertRaises(ValidationError):
            move.reason = 'Altération'
            move.save()

    def test_failed_receipt_rolls_back_everything(self):
        container, move, values = self.receive()
        baseline = (StockContainer.objects.count(), StockLot.objects.count(), StockMovement.objects.count())
        invalid = [{'condition': ''}, {'received_on': timezone.localdate() + timedelta(days=1)},
                   {'ordered_on': timezone.localdate() + timedelta(days=1)}, {'amount': 0},
                   {'amount': 'NaN'}, {'amount': '0.0000001'}, {'unit': self.ml}, {'location': self.lab},
                   {'manufactured_on': timezone.localdate() + timedelta(days=1)}, {'key': 'bad'}]
        for i, changes in enumerate(invalid):
            data = {**values, 'key': uuid.uuid4(), 'lot_code': 'BAD-' + str(i), 'manufacturer_lot': 'BAD-' + str(i),
                    'container_code': 'BAD-' + str(i), **changes}
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                receive_stock(self.admin, **data)
            self.assertEqual((StockContainer.objects.count(), StockLot.objects.count(), StockMovement.objects.count()), baseline)
        with self.assertRaises(PermissionDenied):
            receive_stock(self.operator, **{**values, 'key': uuid.uuid4()})
        self.party.active = False
        self.party.save()
        with self.assertRaises(ValidationError):
            receive_stock(self.admin, **{**values, 'key': uuid.uuid4(), 'container_code': 'BAD-INACTIVE'})

    def test_existing_lot_has_distinct_container_controls_and_immutable_metadata(self):
        first, move, values = self.receive()
        other = receive_stock(self.admin, **{**values, 'key': uuid.uuid4(), 'container_code': 'CONT-2', 'cold_chain_ok': False}).receipt.container
        self.assertEqual(other.status, 'QUARANTINE')
        self.assertEqual(StockLot.objects.count(), 1)
        self.assertTrue(is_usable(first))
        self.assertFalse(is_usable(other))
        with self.assertRaises(ValidationError):
            receive_stock(self.admin, **{**values, 'key': uuid.uuid4(), 'container_code': 'CONT-3', 'expires_on': None})

    def test_available_reserved_balances_and_release_retry(self):
        container, _, _ = self.receive()
        reservation = reserve_stock(self.admin, container.pk, key=uuid.uuid4(), amount=7, unit=self.unit, reference='Run planifié')
        container.refresh_from_db()
        self.assertEqual(container.reserved, 7)
        with self.assertRaises(ValidationError):
            remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=4, unit=self.unit)
        consumed = remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=5, unit=self.unit, reservation=reservation)
        reservation.refresh_from_db()
        self.assertEqual(reservation.remaining, 2)
        key = uuid.uuid4()
        release = release_stock(self.admin, reservation.pk, key=key, reason='Fin du run')
        self.assertEqual(release_stock(self.admin, reservation.pk, key=key, reason='Fin du run').pk, release.pk)
        with self.assertRaises(ValidationError):
            release_stock(self.admin, reservation.pk, key=uuid.uuid4(), reason='Déjà libéré')
        container.refresh_from_db()
        self.assertEqual((container.quantity, container.reserved), (5, 0))
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_fefo_after_opening_expiry_and_lot_recall(self):
        first, _, _ = self.receive('1', expires_on=timezone.localdate() + timedelta(days=30))
        second, _, _ = self.receive('2', expires_on=timezone.localdate() + timedelta(days=60))
        self.assertEqual(fefo(self.admin, self.article).first().pk, first.pk)
        with self.assertRaises(ValidationError):
            remove_stock(self.admin, second.pk, key=uuid.uuid4(), amount=1, unit=self.unit)
        remove_stock(self.admin, second.pk, key=uuid.uuid4(), amount=1, unit=self.unit, reason='Lot réservé à ce protocole')
        self.article.after_open_days = 10
        self.article.save()
        first.refresh_from_db()
        first = open_container(self.admin, first.pk, expected=first.version, opened_on=timezone.localdate())
        self.assertEqual(first.use_by, timezone.localdate() + timedelta(days=10))
        self.assertEqual(first.stability_days, 10)
        with self.assertRaises(ValidationError):
            open_container(self.admin, first.pk, expected=first.version, opened_on=timezone.localdate())
        lot = first.lot
        control_lot(self.admin, lot.pk, expected=lot.version, status='RECALLED', reason='Rappel fabricant')
        self.assertFalse(is_usable(first))
        with self.assertRaises(ValidationError):
            control_container(self.admin, first.pk, expected=first.version, status='AVAILABLE', reason='Essai interdit')
        expired, _, _ = self.receive('3', accepted=False, expires_on=timezone.localdate() - timedelta(days=1))
        with self.assertRaises(ValidationError):
            control_container(self.admin, expired.pk, expected=expired.version, status='AVAILABLE', reason='Expiré')
        remove_stock(self.admin, expired.pk, key=uuid.uuid4(), amount=10, unit=self.unit, kind='EXPIRY', reason='Péremption')
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_transfers_preserve_containers_reservations_and_opening(self):
        from erp.services.storage import save_location
        destination = save_location(self.admin, {'code': 'F2', 'name': 'Second congélateur', 'kind': self.storage_kind, 'parent': self.lab})
        container, _, _ = self.receive()
        reservation = reserve_stock(self.admin, container.pk, key=uuid.uuid4(), amount=3, unit=self.unit, reference='Analyse')
        key = uuid.uuid4()
        move = transfer_stock(self.admin, container.pk, key=key, destination=destination, reason='Réorganisation')
        self.assertEqual(transfer_stock(self.admin, container.pk, key=key, destination=destination, reason='Réorganisation').pk, move.pk)
        container.refresh_from_db()
        self.assertEqual((container.location_id, container.quantity, container.reserved), (destination.pk, 10, 3))
        self.assertEqual(move.entries.count(), 2)
        transfer_stock(self.admin, container.pk, key=uuid.uuid4(), destination=self.freezer,
            amount=4, unit=self.unit, destination_code='SPLIT', reason='Division')
        target = StockContainer.objects.get(code='SPLIT')
        self.assertEqual(target.quantity, 4)
        self.assertEqual(target.status, container.status)
        with self.assertRaises(ValidationError):
            transfer_stock(self.admin, container.pk, key=uuid.uuid4(), destination=self.freezer,
                amount=4, unit=self.unit, destination_code='SPLIT2', reason='Réservé')
        self.assertFalse(StockContainer.objects.filter(code='SPLIT2').exists())
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_reversal_restores_and_rejects_later_activity(self):
        container, receipt, _ = self.receive()
        consumption = remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=3, unit=self.unit)
        key = uuid.uuid4()
        correction = reverse_stock(self.ops, consumption.pk, key=key, reason='Erreur de quantité')
        self.assertEqual(reverse_stock(self.ops, consumption.pk, key=key, reason='Erreur de quantité').pk, correction.pk)
        container.refresh_from_db()
        self.assertEqual(container.quantity, 10)
        with self.assertRaises(ValidationError):
            reverse_stock(self.ops, receipt.pk, key=uuid.uuid4(), reason='Activité ultérieure')
        with self.assertRaises(PermissionDenied):
            reverse_stock(self.operator, consumption.pk, key=uuid.uuid4(), reason='Interdit')
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_stock_control_and_opening_reject_invalid_physical_states(self):
        container, _, _ = self.receive()
        with self.assertRaises(ValidationError):
            control_container(self.admin, container.pk, expected=container.version,
                status='DESTROYED', reason='Contrôle demandé avant destruction')
        with self.assertRaises(ValidationError):
            control_lot(self.admin, container.lot_id, expected=container.lot.version,
                status='DESTROYED', reason='Lot encore en stock')
        with self.assertRaises(ValidationError):
            control_lot(self.admin, container.lot_id, expected=container.lot.version,
                status='UNKNOWN', reason='État non prévu')
        with self.assertRaises(ValidationError):
            open_container(self.admin, container.pk, expected=container.version,
                opened_on=timezone.localdate()-timedelta(days=1))
        quarantined, _, _ = self.receive('Q', accepted=False)
        with self.assertRaises(ValidationError):
            open_container(self.admin, quarantined.pk, expected=quarantined.version,
                opened_on=timezone.localdate())
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_reserved_consumption_reversal_restores_both_ledgers_once(self):
        container, _, _ = self.receive()
        reservation = reserve_stock(self.admin, container.pk, key=uuid.uuid4(), amount=4,
            unit=self.unit, reference='Analyse annulée')
        consumed = remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=2,
            unit=self.unit, reservation=reservation)
        reservation.refresh_from_db()
        self.assertEqual(reservation.remaining, 2)
        correction = reverse_stock(self.ops, consumed.pk, key=uuid.uuid4(), reason='Analyse non réalisée')
        container.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual((container.quantity, container.reserved, reservation.remaining), (10, 4, 4))
        with self.assertRaises(Conflict):
            reverse_stock(self.ops, consumed.pk, key=uuid.uuid4(), reason='Deuxième correction interdite')
        with self.assertRaises(ValidationError):
            reverse_stock(self.ops, reservation.movement_id, key=uuid.uuid4(),
                reason='Réservation corrigée hors de sa procédure')
        self.assertEqual(correction.reverses_id, consumed.pk)
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_stock_outflows_and_transfers_reject_unjustified_or_unsafe_changes(self):
        from erp.services.storage import save_location
        destination = save_location(self.admin, {'code':'F-DEST','name':'Autre stockage',
            'kind':self.storage_kind,'parent':self.lab})
        container, _, _ = self.receive()
        with self.assertRaises(ValidationError):
            remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=1, unit=self.unit,
                kind=StockMovement.Kind.TRANSFER, reason='Type invalide pour une sortie')
        with self.assertRaises(ValidationError):
            remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=1, unit=self.unit,
                kind=StockMovement.Kind.LOSS, reason='')
        with self.assertRaises(ValidationError):
            reserve_stock(self.admin, container.pk, key=uuid.uuid4(), amount=1,
                unit=self.unit, reference='')
        with self.assertRaises(ValidationError):
            transfer_stock(self.admin, container.pk, key=uuid.uuid4(), destination=self.freezer,
                reason='Même emplacement')
        with self.assertRaises(ValidationError):
            transfer_stock(self.admin, container.pk, key=uuid.uuid4(), destination=destination,
                amount=11, unit=self.unit, destination_code='EXCESS', reason='Trop de stock')
        with self.assertRaises(ValidationError):
            transfer_stock(self.admin, container.pk, key=uuid.uuid4(), destination=destination,
                amount=1, unit=self.unit, reason='Division sans code')
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_scoped_permissions_are_intersections_and_costs_are_separate(self):
        container, _, values = self.receive()
        self.grant(Capability.RECEIVE_STOCK, category=self.category, location=self.freezer)
        self.grant(Capability.CONSUME_STOCK, category=self.category, location=self.freezer)
        self.assertEqual(list(operational_scope(StockContainer.objects.all(), self.operator)), [container])
        self.assertFalse(operational_scope(StockContainer.objects.all(), self.outsider).exists())
        self.assertEqual(operational_scope(StockContainer.objects.all(), self.admin).count(), 1)
        with self.assertRaises(PermissionDenied):
            receive_stock(self.operator, **{**values, 'key': uuid.uuid4(), 'container_code': 'COST', 'unit_price': 10})
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:stock-list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('erp:stock-detail', args=[container.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('erp:stock-action', args=[container.pk, 'control'])).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:stock-list')).status_code, 403)

    def test_blind_inventory_assignment_recount_and_ledger_adjustment(self):
        container, _, _ = self.receive()
        campaign = create_inventory(self.ops, title='Inventaire F80', assignee=self.operator, location=self.freezer, blind=True)
        line = campaign.lines.get()
        self.client.force_login(self.operator)
        response = self.client.get(reverse('erp:inventory-detail', args=[campaign.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['reveal'])
        self.assertNotContains(response, 'Théorique au comptage')
        with self.assertRaises(ValidationError):
            submit_inventory(self.operator, campaign.pk, expected=campaign.work.version)
        line = count_inventory(self.operator, line.pk, expected=line.version, container_version=container.version, amount=8, note='Comptage direct')
        campaign.work.refresh_from_db()
        submit_inventory(self.operator, campaign.pk, expected=campaign.work.version)
        campaign.work.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            approve_inventory(self.operator, campaign.pk, expected=campaign.work.version, key=uuid.uuid4(), reason='Auto-validation interdite')
        recount_inventory(self.ops, campaign.pk, expected=campaign.work.version, line_ids=[str(line.pk)], reason='Confirmer l’écart')
        line.refresh_from_db()
        self.assertTrue(line.needs_recount)
        count_inventory(self.operator, line.pk, expected=line.version, container_version=container.version, amount=9)
        campaign.work.refresh_from_db()
        submit_inventory(self.operator, campaign.pk, expected=campaign.work.version)
        campaign.work.refresh_from_db()
        key = uuid.uuid4()
        adjustment = approve_inventory(self.ops, campaign.pk, expected=campaign.work.version, key=key, reason='Écart confirmé et validé')
        self.assertEqual(approve_inventory(self.ops, campaign.pk, expected=campaign.work.version, key=key, reason='Écart confirmé et validé').pk, adjustment.pk)
        container.refresh_from_db()
        self.assertEqual(container.quantity, 9)
        self.assertEqual(adjustment.entries.get().quantity_delta, -1)
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_inventory_rejects_stale_counts_and_reserved_underflow(self):
        container, _, _ = self.receive()
        campaign = create_inventory(self.ops, title='Contrôle', assignee=self.operator)
        line = campaign.lines.get()
        count_inventory(self.operator, line.pk, expected=line.version, container_version=container.version, amount=7)
        campaign.work.refresh_from_db()
        submit_inventory(self.operator, campaign.pk, expected=campaign.work.version)
        remove_stock(self.admin, container.pk, key=uuid.uuid4(), amount=1, unit=self.unit)
        campaign.work.refresh_from_db()
        with self.assertRaises(Conflict):
            approve_inventory(self.ops, campaign.pk, expected=campaign.work.version, key=uuid.uuid4(), reason='Stock modifié')
        self.assertFalse(campaign.lines.get().campaign.adjustment_id)
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_native_cdc_creation_uses_existing_accounts_and_retains_source_catalogue(self):
        dossier = create_dossier(self.ops, family='equipment', reference='18/SME/SDFM/SG/ESSBO/2026',
            title='Équipements de la plateforme', assignee=self.operator, allow_costs=False)
        self.assertEqual(dossier.work.assignee_id, self.operator.pk)
        self.assertEqual(dossier.lots.count(), 2)
        self.assertEqual(sum(lot.items.count() for lot in dossier.lots.all()), 23)
        first = dossier.lots.first().items.first()
        old_revision = dossier.revisions.first()
        revision = save_cdc_item(self.operator, first.lot_id, expected=dossier.version, pk=first.pk,
            article=self.article, purchase_unit=self.unit, values={'quantity': 4})
        first.refresh_from_db()
        self.assertEqual(first.article_id, self.article.pk)
        self.assertEqual(first.base_factor, 1)
        self.assertEqual(first.designation, self.article.name)
        self.assertNotEqual(revision.sha256, old_revision.sha256)
        self.assertNotEqual(old_revision.data['lot_catalog']['lots'][0]['items'][0]['designation'], self.article.name)
        dossier.refresh_from_db()
        with self.assertRaises(PermissionDenied):
            save_cdc_item(self.operator, first.lot_id, expected=dossier.version, pk=first.pk,
                values={'estimated_price': Decimal(100), 'tax_rate': Decimal(0), 'price_source': 'Devis fournisseur'})
        with self.assertRaises(ValidationError):
            old_revision.delete()
