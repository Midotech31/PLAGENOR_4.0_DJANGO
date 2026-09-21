from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp.models import AnalysisRun, RunAllocation, RunConsumption, StockMovement, StockReservation
from erp.services.biobank import receive_sample, reconcile_biobank, source_samples
from erp.services.consumption import (calculate_requirements, cancel_run, close_request_resources,
    confirm_run, create_run, reservation_proposal, reserve_run, save_profile, save_rule)
from erp.services.stock import reconcile_stock, reserve_stock
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConsumptionIntegrationTests(OperationFixtures, TestCase):
    def setUp(self):
        self.service = Service.objects.create(code='TEST-RUN', name='Prestation de recette')
        member, _ = MemberProfile.objects.get_or_create(user=self.operator)
        self.req = Request.objects.create(requester=self.outsider, assigned_to=member,
            service=self.service, title='Demande analytique de recette', status='IN_PROGRESS',
            sample_table=[{'sample_code': 'TEST-SOURCE-1', 'quantity': '50', 'quantity_unit': 'µL'}])
        self.profile = save_profile(self.ops, {'code': 'BOM-TEST', 'name': 'Nomenclature de recette',
            'service': self.service, 'reference_samples': 1, 'protocol_reference': 'SOP-TEST-01'})
        self.rule = save_rule(self.ops, self.profile.pk, {'article': self.article, 'quantity': Decimal(2),
            'unit': self.unit, 'basis': 'PROPORTIONAL'}, expected=self.profile.version)
        self.profile.refresh_from_db()
        self.container, _, _ = self.receive(quantity=20)

    def make_run(self, name='RUN-1', samples=()):
        source_keys = [] if samples else [source_samples(self.admin, self.req)[0]['key']]
        return create_run(self.ops, request=self.req, profile=self.profile, code=name,
            name='Série documentée', sample_count=1, planned_on=timezone.localdate(),
            source_keys=source_keys, samples=samples)

    def test_profile_arithmetic_and_role_restrictions(self):
        requirements = calculate_requirements(self.profile, 3)
        self.assertEqual(requirements[0]['quantity'], 6)
        self.assertEqual(requirements[0]['calculation'][0]['conversion_factor'], '1')
        with self.assertRaises(PermissionDenied):
            save_profile(self.operator, {'code': 'NO', 'name': 'Interdit'})
        with self.assertRaises(ValidationError):
            save_profile(self.ops, {'created_at': timezone.now()})
        with self.assertRaises(ValidationError):
            calculate_requirements(self.profile, 0)
        self.profile = save_profile(self.ops, {'reference_samples': 3}, pk=self.profile.pk,
            expected=self.profile.version)
        fractional = calculate_requirements(self.profile, 1)[0]
        self.assertEqual(fractional['quantity'], Decimal('0.666667'))
        save_rule(self.ops, self.profile.pk, {'article': self.article, 'quantity': Decimal(1),
            'unit': self.unit, 'basis': 'BATCH'}, expected=self.profile.version)
        self.profile.refresh_from_db()
        self.assertEqual(calculate_requirements(self.profile, 4)[0]['quantity'], Decimal('4.666667'))

    def test_run_reservation_actual_confirmation_and_request_trace(self):
        run = self.make_run()
        proposal = reservation_proposal(self.ops, run)
        self.assertEqual(proposal['shortages'], [])
        self.assertEqual(len(proposal['allocations']), 1)
        reserve_key = uuid.uuid4()
        operation = reserve_run(self.ops, run.pk, expected=run.version, key=reserve_key,
            allocations=proposal['allocations'], reason='Préparation de la série')
        self.assertEqual(reserve_run(self.ops, run.pk, expected=run.version, key=reserve_key,
            allocations=proposal['allocations'], reason='Préparation de la série').pk, operation.pk)
        run.refresh_from_db()
        allocation = RunAllocation.objects.get(requirement__run=run)
        self.assertEqual(allocation.reservation.remaining, 2)
        key = uuid.uuid4()
        confirmed = confirm_run(self.ops, run.pk, expected=run.version, key=key,
            actuals={str(allocation.pk): '1.5'}, reason='Consommation réelle relevée', confirmed=True)
        self.assertEqual(confirm_run(self.ops, run.pk, expected=run.version, key=key,
            actuals={str(allocation.pk): '1.5'}, reason='Consommation réelle relevée', confirmed=True).pk, confirmed.pk)
        run.refresh_from_db()
        self.container.refresh_from_db()
        self.assertEqual(run.status, 'COMPLETED')
        self.assertEqual((self.container.quantity, self.container.reserved), (Decimal('18.5'), 0))
        consumed = RunConsumption.objects.get(run=run)
        self.assertEqual(consumed.movement.request_id, self.req.pk)
        self.assertEqual(run.inputs.get().source_key, source_samples(self.admin, self.req)[0]['key'])
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_request_to_stored_sample_run_consumption_conserves_both_ledgers(self):
        source = source_samples(self.ops, self.req)[0]
        sample = receive_sample(self.ops, key=uuid.uuid4(), code='STORED-RUN', amount=50, unit=self.ul,
            location=self.freezer, received_on=timezone.localdate(), reason='Réception pour analyse',
            request=self.req, source_key=source['key'], source_fingerprint=source['fingerprint'])
        run = self.make_run(samples=[sample])
        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=reservation_proposal(self.ops, run)['allocations'], reason='Analyse prévue')
        run.refresh_from_db()
        allocation = RunAllocation.objects.get(requirement__run=run)
        input_record = run.inputs.get()
        confirm_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            actuals={str(allocation.pk): '2'}, biological_quantities={str(input_record.pk): '5'},
            reason='Analyse terminée et quantités confirmées', confirmed=True)
        sample.refresh_from_db()
        self.assertEqual(sample.remaining_quantity, 45)
        self.assertEqual(sample.events.filter(kind='CONSUMPTION', request=self.req).count(), 1)
        self.assertEqual(reconcile_biobank(self.admin), [])
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_invalid_actual_quantities_roll_back_and_cancel_releases_reservations(self):
        run = self.make_run()
        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=reservation_proposal(self.ops, run)['allocations'], reason='Planification')
        run.refresh_from_db()
        allocation = RunAllocation.objects.get(requirement__run=run)
        for actuals, confirmed in (({}, True), ({str(allocation.pk): '3'}, True),
                                   ({str(allocation.pk): '0'}, True), ({str(allocation.pk): '2'}, False)):
            with self.subTest(actuals=actuals), self.assertRaises(ValidationError):
                confirm_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                    actuals=actuals, reason='Contrôle des valeurs', confirmed=confirmed)
        self.assertEqual(RunConsumption.objects.count(), 0)
        self.assertEqual(self.container.entries.filter(movement__kind='CONSUMPTION').count(), 0)
        key = uuid.uuid4()
        cancelled = cancel_run(self.ops, run.pk, expected=run.version, key=key, reason='Série annulée')
        self.assertEqual(cancel_run(self.ops, run.pk, expected=run.version, key=key, reason='Série annulée').pk, cancelled.pk)
        self.container.refresh_from_db()
        self.assertEqual((self.container.quantity, self.container.reserved), (20, 0))
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_request_closure_releases_all_reservations_without_changing_physical_stock(self):
        run = self.make_run()
        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=reservation_proposal(self.ops, run)['allocations'], reason='Préparation')
        reserve_stock(self.ops, self.container.pk, key=uuid.uuid4(), amount=3,
            unit=self.unit, reference='Réservation complémentaire', request=self.req)
        with self.assertRaises(ValidationError):
            close_request_resources(self.ops, self.req, 'Pas encore clôturée')
        self.req.archived = True
        self.req.save(update_fields=['archived'])
        close_request_resources(self.ops, self.req, 'Demande archivée')
        close_request_resources(self.ops, self.req, 'Nouvel appel de clôture')
        run.refresh_from_db()
        self.container.refresh_from_db()
        self.assertEqual(run.status, 'CANCELLED')
        self.assertEqual((self.container.quantity, self.container.reserved), (20, 0))
        self.assertFalse(StockReservation.objects.filter(request=self.req, remaining__gt=0).exists())
        self.assertEqual(reconcile_stock(self.admin), [])
