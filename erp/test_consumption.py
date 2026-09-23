from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp.models import AnalysisRun, RunAllocation, RunConsumption, StockMovement, StockReservation
from erp.consumption_forms import RunConfirmForm, RunCreateForm, RunReserveForm
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

    def test_run_creation_form_limits_profiles_samples_and_management_flags(self):
        manager_form = RunCreateForm(user=self.ops, request=self.req)
        operator_form = RunCreateForm(user=self.operator, request=self.req)
        self.assertEqual(list(manager_form.fields['profile'].queryset), [self.profile])
        self.assertEqual(manager_form.fields['source_keys'].choices[0][0],
            source_samples(self.ops, self.req)[0]['key'])
        self.assertIn('committed', manager_form.fields)
        self.assertIn('incremental_demand', manager_form.fields)
        self.assertNotIn('committed', operator_form.fields)
        self.assertNotIn('incremental_demand', operator_form.fields)
        self.assertEqual(list(manager_form.fields['samples'].queryset), [])
        source = source_samples(self.ops, self.req)[0]
        sample = receive_sample(self.ops, key=uuid.uuid4(), code='FORM-SAMPLE', amount=10, unit=self.ul,
            location=self.freezer, received_on=timezone.localdate(), reason='Réception pour la série',
            request=self.req, source_key=source['key'], source_fingerprint=source['fingerprint'])
        refreshed = RunCreateForm(user=self.ops, request=self.req)
        self.assertEqual(list(refreshed.fields['samples'].queryset), [sample])
        self.assertIn(sample.code, refreshed.fields['samples'].label_from_instance(sample))

    def test_reservation_and_confirmation_forms_follow_real_allocations(self):
        run = self.make_run()
        reservation_form = RunReserveForm(user=self.ops, run=run)
        requirement = run.requirements.get()
        self.assertEqual(list(reservation_form.fields['requirement'].queryset), [requirement])
        self.assertEqual(list(reservation_form.fields['container'].queryset), [self.container])
        self.assertIn(str(requirement.article),
            reservation_form.fields['requirement'].label_from_instance(requirement))
        self.assertIn(self.container.code,
            reservation_form.fields['container'].label_from_instance(self.container))
        self.assertEqual(RunConfirmForm(run=run).actual_fields, {})
        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=reservation_proposal(self.ops, run)['allocations'], reason='Série préparée')
        run.refresh_from_db()
        allocation = RunAllocation.objects.get(requirement__run=run)
        form = RunConfirmForm(run=run)
        amount_name = form.actual_fields[str(allocation.pk)]
        self.assertEqual(form.fields[amount_name].initial, allocation.reservation.remaining)
        self.assertEqual(form.fields[amount_name].max_value, allocation.reservation.remaining)
        self.assertEqual(len(form.groups), 3)
        self.assertEqual(form.biological_fields, {})
        source = source_samples(self.ops, self.req)[0]
        sample = receive_sample(self.ops, key=uuid.uuid4(), code='BIOLOGY-FORM', amount=10, unit=self.ul,
            location=self.freezer, received_on=timezone.localdate(), reason='Réception de contrôle',
            request=self.req, source_key=source['key'], source_fingerprint=source['fingerprint'])
        biological_run = self.make_run(name='RUN-BIO-FORM', samples=[sample])
        biological_input = biological_run.inputs.get()
        biological_form = RunConfirmForm(run=biological_run)
        biological_name = biological_form.biological_fields[str(biological_input.pk)]
        self.assertEqual(biological_form.fields[biological_name].initial, 0)
        self.assertIn(sample.code, biological_form.fields[biological_name].label)

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

    def test_profile_rules_and_source_selection_guards(self):
        updated = save_rule(self.ops, self.profile.pk, {'quantity': Decimal(3)},
            expected=self.profile.version, pk=self.rule.pk)
        self.assertEqual(updated.version, self.rule.version + 1)
        self.profile.refresh_from_db()
        self.profile.active = False
        with self.assertRaises(ValidationError):
            calculate_requirements(self.profile, 1)
        self.profile.active = True
        self.article.active = False
        self.article.save()
        with self.assertRaises(ValidationError):
            calculate_requirements(self.profile, 1)
        self.article.active = True
        self.article.save()
        source = source_samples(self.ops, self.req)[0]
        sample = receive_sample(self.ops, key=uuid.uuid4(), code='SELECTION-GUARD', amount=10,
            unit=self.ul, location=self.freezer, received_on=timezone.localdate(), reason='Réception',
            request=self.req, source_key=source['key'], source_fingerprint=source['fingerprint'])
        for keys, samples in [([source['key'], source['key']], []), (['unknown'], []),
                              ([], []), ([source['key']], [sample]), ([], [sample, sample])]:
            with self.subTest(keys=keys, samples=samples), self.assertRaises(ValidationError):
                create_run(self.ops, request=self.req, profile=self.profile, code='INVALID', name='Invalid',
                    sample_count=1, planned_on=timezone.localdate(), source_keys=keys, samples=samples)
        self.assertFalse(AnalysisRun.objects.exists())
        sample.status = 'DESTROYED'
        sample.save()
        with self.assertRaises(ValidationError):
            self.make_run(samples=[sample])
        self.profile.service = Service.objects.create(code='OTHER-RUN', name='Autre prestation')
        self.profile.save()
        with self.assertRaises(ValidationError):
            self.make_run()

    def test_malformed_reservations_are_atomic_and_keys_cannot_be_reused(self):
        from erp.services.common import Conflict
        run = self.make_run()
        proposal = reservation_proposal(self.ops, run)['allocations']
        invalid = [[], ['invalid'], [{'container': str(self.container.pk)}],
            [dict(proposal[0], requirement=str(uuid.uuid4()))], [proposal[0], proposal[0]]]
        for allocations in invalid:
            with self.subTest(allocations=allocations), self.assertRaises(ValidationError):
                reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                    allocations=allocations, reason='Contrôle des allocations')
            self.container.refresh_from_db()
            self.assertEqual(self.container.reserved, 0)
            self.assertFalse(RunAllocation.objects.exists())
        key = uuid.uuid4()
        reserve_run(self.ops, run.pk, expected=run.version, key=key,
            allocations=proposal, reason='Réservation valide')
        with self.assertRaises(Conflict):
            reserve_run(self.ops, run.pk, expected=run.version, key=key,
                allocations=proposal, reason='Autre opération')
        self.assertEqual(RunAllocation.objects.count(), 1)
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_confirmation_rejects_foreign_biology_and_changed_source(self):
        from erp.services.common import Conflict
        run = self.make_run()
        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=reservation_proposal(self.ops, run)['allocations'], reason='Préparation')
        run.refresh_from_db()
        allocation = RunAllocation.objects.get(requirement__run=run)
        actuals = {str(allocation.pk): '2'}
        with self.assertRaises(ValidationError):
            confirm_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(), actuals=actuals,
                biological_quantities={str(uuid.uuid4()): '1'}, reason='Analyse', confirmed=True)
        self.req.sample_table = [{'sample_code': 'SOURCE-CHANGED', 'quantity': '50', 'quantity_unit': 'µL'}]
        self.req.save()
        with self.assertRaises(Conflict):
            confirm_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(), actuals=actuals,
                reason='Analyse', confirmed=True)
        self.container.refresh_from_db()
        self.assertEqual((self.container.quantity, self.container.reserved), (20, 2))
        self.assertFalse(RunConsumption.objects.exists())
        cancel_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(), reason='Source modifiée')
        run.refresh_from_db()
        with self.assertRaises(ValidationError):
            reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
                allocations=[], reason='Déjà annulée')
        with self.assertRaises(ValidationError):
            cancel_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(), reason='Déjà annulée')
        self.assertEqual(reconcile_stock(self.admin), [])

    def test_shortage_and_request_closure_require_authenticated_actor(self):
        from django.contrib.auth.models import AnonymousUser
        run = self.make_run()
        self.container.quantity = 1
        self.container.save()
        proposal = reservation_proposal(self.ops, run)
        self.assertEqual(Decimal(proposal['shortages'][0]['quantity']), 1)
        self.req.archived = True
        self.req.save()
        for actor in [None, AnonymousUser()]:
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                close_request_resources(actor, self.req, 'Clôture')
        run.refresh_from_db()
        self.assertEqual(run.status, 'PLANNED')

    def test_linked_planning_rechecks_run_identity_status_and_input_completeness(self):
        from erp.services.planning import create_activity, readiness
        from erp.services.work import transition_work
        run = self.make_run()
        start, end = timezone.now(), timezone.now()+timedelta(hours=1)
        values = {'key': uuid.uuid4(), 'kind': 'CONTROL', 'title': 'Analyse planifiée', 'assignee': self.ops,
            'starts_at': start, 'ends_at': end, 'run': run}
        with self.assertRaises(ValidationError):
            create_activity(self.ops, **values)
        other = Request.objects.create(display_id='REQ-OTHER-PLAN', requester=self.outsider, service=self.service,
            title='Autre demande', status='IN_PROGRESS')
        values['kind'] = 'ANALYSIS'
        with self.assertRaises(ValidationError):
            create_activity(self.ops, **dict(values, request=other))
        schedule = create_activity(self.ops, **values)
        with self.assertRaises(ValidationError):
            transition_work(self.ops, schedule.work_id, expected=schedule.work.version,
                state='SUBMITTED', reason='Pas démarrée')
        for state, word in [('CANCELLED', 'annulée'), ('COMPLETED', 'confirmées')]:
            AnalysisRun.objects.filter(pk=run.pk).update(status=state)
            issues = readiness(self.ops, schedule.work)['issues']
            self.assertTrue(any(word in str(issue) for issue in issues), issues)
        # A legacy/incomplete run must never be presented as ready for execution.
        legacy = AnalysisRun.objects.create(code='LEGACY-NO-INPUT', name='Série incomplète', request=self.req,
            profile=self.profile, sample_count=1, planned_on=timezone.localdate(), created_by=self.ops)
        missing = create_activity(self.ops, **dict(values, key=uuid.uuid4(), run=legacy,
            starts_at=end, ends_at=end+timedelta(hours=1)))
        issues = readiness(self.ops, missing.work)['issues']
        self.assertTrue(any('Aucun échantillon' in str(issue) for issue in issues), issues)

    def test_request_links_refuse_unassigned_and_closed_writes(self):
        from erp.services.links import lock_request, request_scope, require_request
        self.assertFalse(request_scope(self.outsider).exists())
        with self.assertRaises(PermissionDenied):
            lock_request(self.second, self.req)
        self.req.archived = True
        self.req.save()
        with self.assertRaises(ValidationError):
            require_request(self.ops, self.req)
        with self.assertRaises(ValidationError):
            lock_request(self.ops, self.req)
        self.assertEqual(lock_request(self.ops, self.req, allow_closed=True), self.req)

    @override_settings(SECURE_SSL_REDIRECT=False, STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
    def test_reservation_page_prefill_and_external_user_restrictions(self):
        from django.urls import reverse
        run = self.make_run()
        self.client.force_login(self.ops)
        response = self.client.get(reverse('erp:run-operation', args=[run.pk, 'reserve']), {
            'requirement': run.requirements.get().pk, 'container': self.container.pk, 'amount': '2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['amount'], '2')
        self.client.force_login(self.outsider)
        for route in [reverse('erp:profile-list'), reverse('erp:profile-detail', args=[self.profile.pk]),
                      reverse('erp:work-list'), reverse('erp:preparation-create')]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 403)
