"""Tests for the money-critical core: pricing engine, the canonical cost
resolver, and the IBTIKAR budget check.

These guard the numbers that turn into real invoices (GENOCLAB) and the
virtual-budget gate (IBTIKAR). Run with ``python manage.py test core``.
"""
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.exceptions import (
    AuthorizationError, FinancialValidationError, InvalidTransitionError,
    PricingConfigurationError,
)
from core.financial import (
    check_ibtikar_budget, compute_invoice_totals, deduct_ibtikar_balance,
)
from core.models import Request, RequestHistory, Service
from core.pricing import calculate_price, resolve_cost
from core.state_machine import get_allowed_next_states
from core.workflow import check_role_permission, force_transition, transition
from core.uploads import validate_upload
from core.assignment import member_is_eligible


# ---------------------------------------------------------------------------
# calculate_price — pure pricing engine (no DB)
# ---------------------------------------------------------------------------
class CalculatePriceTests(SimpleTestCase):
    def _def(self, **pricing):
        base = {
            'model': 'per_sample_table_row_with_multiplier',
            'currency': 'DZD',
            'base_price': {'non_pathogenic': 1000, 'pathogenic': 2000},
            'multipliers': {'standard': 1, 'express': 2},
        }
        base.update(pricing)
        return {'service_code': 'X', 'pricing': base}

    def test_base_times_multiplier_times_samples(self):
        res = calculate_price(
            self._def(),
            {'analysis_mode': 'express'},
            sample_table=[{'a': 1}, {'a': 2}, {'a': 3}],
        )
        # 1000 (non_pathogenic) * 2 (express) * 3 samples
        self.assertEqual(res['unit_price'], 2000)
        self.assertEqual(res['number_of_units'], 3)
        self.assertEqual(res['total'], 6000)

    def test_pathogenic_selects_higher_base(self):
        res = calculate_price(
            self._def(),
            {'pathogenic': True, 'analysis_mode': 'standard'},
            sample_table=[{'a': 1}],
        )
        self.assertEqual(res['unit_price'], 2000)  # pathogenic base, x1
        self.assertEqual(res['total'], 2000)

    def test_unknown_multiplier_fails_closed(self):
        with self.assertRaises(PricingConfigurationError):
            calculate_price(
                self._def(),
                {'analysis_mode': 'does-not-exist'},
                sample_table=[{'a': 1}],
            )

    def test_per_sample_fixed_model(self):
        sdef = {'service_code': 'Y', 'pricing': {
            'model': 'per_sample_fixed', 'currency': 'DZD', 'unit_price': 500,
        }}
        res = calculate_price(sdef, {}, sample_table=[1, 2, 3, 4])
        self.assertEqual(res['total'], 2000)
        self.assertEqual(res['number_of_units'], 4)

    def test_raises_on_missing_definition(self):
        with self.assertRaises(ValueError):
            calculate_price(None, {}, [{'a': 1}])

    def test_raises_on_missing_pricing(self):
        with self.assertRaises(ValueError):
            calculate_price({'service_code': 'Z'}, {}, [{'a': 1}])

    def test_raises_on_unsupported_model(self):
        sdef = {'service_code': 'Z', 'pricing': {'model': 'bogus'}}
        with self.assertRaises(ValueError):
            calculate_price(sdef, {}, [{'a': 1}])

    def test_raises_on_empty_samples(self):
        with self.assertRaises(ValueError):
            calculate_price(self._def(), {}, sample_table=[])

    def test_malformed_numeric_price_fails_closed(self):
        with self.assertRaises(PricingConfigurationError):
            calculate_price(
                self._def(base_price={'non_pathogenic': 'not-a-price'}),
                {'analysis_mode': 'standard'}, [{'a': 1}],
            )


class UploadValidationTests(SimpleTestCase):
    def test_spoofed_pdf_is_rejected(self):
        upload = SimpleUploadedFile('invoice.pdf', b'<html>not pdf</html>', 'application/pdf')
        with self.assertRaises(ValidationError):
            validate_upload(upload, 'business_document')

    def test_valid_pdf_is_renamed_to_opaque_name(self):
        upload = SimpleUploadedFile('customer-name.pdf', b'%PDF-1.4\n%%EOF', 'application/pdf')
        validate_upload(upload, 'business_document')
        self.assertRegex(upload.name, r'^[0-9a-f]{32}\.pdf$')

    def test_mime_mismatch_is_rejected(self):
        upload = SimpleUploadedFile('invoice.pdf', b'%PDF-1.4\n%%EOF', 'text/html')
        with self.assertRaises(ValidationError):
            validate_upload(upload, 'business_document')

    def test_oversized_file_is_rejected(self):
        upload = SimpleUploadedFile('invoice.pdf', b'%PDF-' + b'x' * 100, 'application/pdf')
        with self.assertRaises(ValidationError):
            validate_upload(upload, 'business_document', max_bytes=10)


class AssignmentEligibilityTests(TestCase):
    def setUp(self):
        from accounts.models import User, MemberProfile, Technique
        self.user = User.objects.create_user(username='eligible-member', role='MEMBER')
        self.profile = self.user.member_profile
        self.profile.max_load = 2
        self.profile.save(update_fields=['max_load'])
        self.technique = Technique.objects.create(name='TEST_SERVICE')
        self.profile.techniques.add(self.technique)
        self.service = Service.objects.create(code='TEST_SERVICE', name='Test Service')

    def test_matching_available_member_is_eligible(self):
        self.assertTrue(member_is_eligible(self.profile, self.service))

    def test_capacity_and_active_account_are_enforced(self):
        self.profile.current_load = 2
        self.profile.save(update_fields=['current_load'])
        self.assertFalse(member_is_eligible(self.profile, self.service))
        self.profile.current_load = 0
        self.profile.save(update_fields=['current_load'])
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        self.assertFalse(member_is_eligible(self.profile, self.service))

    def test_nonmatching_technique_is_ineligible(self):
        self.technique.name = 'UNRELATED'
        self.technique.save(update_fields=['name'])
        self.assertFalse(member_is_eligible(self.profile, self.service))


# ---------------------------------------------------------------------------
# resolve_cost — canonical resolver, flat fallback (DB-backed Service)
# ---------------------------------------------------------------------------
class ResolveCostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # A code that is NOT one of the YAML registry services, so resolve_cost
        # falls through to the flat columns (no tiers, no pricing_data).
        cls.service = Service.objects.create(
            code='TEST_FLAT', name='Flat Test',
            channel_availability='BOTH',
            ibtikar_price=Decimal('1500'), genoclab_price=Decimal('3000'),
        )

    def test_no_service_fails_closed(self):
        with self.assertRaises(PricingConfigurationError):
            resolve_cost(None, 'GENOCLAB')

    def test_flat_ibtikar_uses_ibtikar_price_times_samples(self):
        res = resolve_cost(self.service, 'IBTIKAR', sample_table=[{'a': 1}, {'a': 2}])
        self.assertEqual(res['source'], 'flat')
        self.assertEqual(res['total'], 3000.0)  # 1500 * 2

    def test_flat_genoclab_uses_genoclab_price_times_samples(self):
        res = resolve_cost(self.service, 'GENOCLAB', sample_table=[{'a': 1}, {'a': 2}, {'a': 3}])
        self.assertEqual(res['total'], 9000.0)  # 3000 * 3

    def test_empty_sample_table_bills_one(self):
        res = resolve_cost(self.service, 'GENOCLAB', sample_table=[])
        self.assertEqual(res['total'], 3000.0)  # max(1, 0) * 3000

    def test_invalid_channel_fails_closed(self):
        with self.assertRaises(PricingConfigurationError):
            resolve_cost(self.service, 'XYZ', sample_table=[{'a': 1}])


# ---------------------------------------------------------------------------
# check_ibtikar_budget — the virtual budget gate
# ---------------------------------------------------------------------------
class IbtikarBudgetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.User = User

    def _requester(self, declared):
        return self.User.objects.create(
            username=f'req-{declared}', role='REQUESTER',
            ibtikar_declared_balance=declared,
        )

    def test_undeclared_balance_blocks_submission(self):
        req = self._requester(None)
        res = check_ibtikar_budget(5000, requester=req)
        self.assertTrue(res['exceeded'])
        self.assertTrue(res['needs_declaration'])
        self.assertIsNone(res['declared'])

    def test_amount_within_declared_balance_is_allowed(self):
        req = self._requester(Decimal('50000'))
        res = check_ibtikar_budget(20000, requester=req)
        self.assertFalse(res['exceeded'])
        self.assertEqual(res['remaining'], 30000)
        self.assertFalse(res['needs_declaration'])

    def test_amount_over_declared_balance_is_blocked(self):
        req = self._requester(Decimal('10000'))
        res = check_ibtikar_budget(15000, requester=req)
        self.assertTrue(res['exceeded'])
        self.assertEqual(res['remaining'], 0.0)

    def test_cap_comes_from_settings(self):
        req = self._requester(Decimal('10000'))
        res = check_ibtikar_budget(1000, requester=req)
        self.assertEqual(res['cap'], settings.IBTIKAR_BUDGET_CAP)


# ---------------------------------------------------------------------------
# Invoice / quote totals — HT -> VAT -> TTC (GENOCLAB real money)
# ---------------------------------------------------------------------------
class InvoiceTotalsTests(SimpleTestCase):
    def test_basic_vat_19_percent(self):
        t = compute_invoice_totals([{'total': 10000}], vat_rate=0.19)
        self.assertEqual(t['subtotal_ht'], 10000)
        self.assertEqual(t['vat_amount'], 1900.0)
        self.assertEqual(t['total_ttc'], 11900.0)

    def test_multiple_lines_plus_fees(self):
        t = compute_invoice_totals(
            [{'total': 5000}, {'total': 2500}],
            admin_fees=1000, report_fees=500, vat_rate=0.19,
        )
        # HT = 7500; before tax = 7500 + 1000 + 500 = 9000
        self.assertEqual(t['subtotal_before_tax'], 9000)
        self.assertEqual(t['vat_amount'], 1710.0)  # 9000 * 0.19
        self.assertEqual(t['total_ttc'], 10710.0)

    def test_zero_vat(self):
        t = compute_invoice_totals([{'total': 3000}], vat_rate=0)
        self.assertEqual(t['vat_amount'], 0.0)
        self.assertEqual(t['total_ttc'], 3000.0)

    def test_rounding_to_two_decimals(self):
        # 333.33 * 0.19 = 63.3327 -> rounds to 63.33
        t = compute_invoice_totals([{'total': 333.33}], vat_rate=0.19)
        self.assertEqual(t['vat_amount'], 63.33)
        self.assertEqual(t['total_ttc'], 396.66)

    def test_empty_lines_is_zero(self):
        t = compute_invoice_totals([], vat_rate=0.19)
        self.assertEqual(t['total_ttc'], 0.0)

    def test_half_up_rounding(self):
        # 0.25 * 0.5 = 0.125 -> ROUND_HALF_UP gives 0.13 (Python round() would
        # banker's-round to 0.12). Decimal arithmetic makes this deterministic.
        t = compute_invoice_totals([{'total': 0.25}], vat_rate=0.5)
        self.assertEqual(t['vat_amount'], 0.13)
        self.assertEqual(t['total_ttc'], 0.38)

    def test_returns_json_safe_floats(self):
        import json
        t = compute_invoice_totals([{'total': 1500}], vat_rate=0.19)
        json.dumps(t)  # must not raise (stored in Request.quote_detail JSONField)
        self.assertIsInstance(t['total_ttc'], float)

    def test_rejects_malformed_line_total_instead_of_zero(self):
        with self.assertRaises(FinancialValidationError):
            compute_invoice_totals([{'total': 'not-a-number'}])

    def test_rejects_negative_and_nonfinite_money(self):
        for value in ('-0.01', 'NaN', 'Infinity', '-Infinity'):
            with self.subTest(value=value):
                with self.assertRaises(FinancialValidationError):
                    compute_invoice_totals([{'total': value}])

    def test_rejects_vat_above_one(self):
        with self.assertRaises(FinancialValidationError):
            compute_invoice_totals([{'total': 100}], vat_rate='1.01')

    def test_rejects_negative_optional_fee(self):
        with self.assertRaises(FinancialValidationError):
            compute_invoice_totals([{'total': 100}], admin_fees='-1')


# ---------------------------------------------------------------------------
# Workflow state machine + role permissions
# ---------------------------------------------------------------------------
class WorkflowTransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.admin = User.objects.create(username='wf-admin', role='SUPER_ADMIN')
        cls.platform = User.objects.create(username='wf-plat', role='PLATFORM_ADMIN')
        cls.client_user = User.objects.create(username='wf-client', role='CLIENT')

    def _req(self, channel='GENOCLAB', status='REQUEST_CREATED'):
        return Request.objects.create(channel=channel, status=status)

    # --- pure validation helpers ---
    def test_allowed_next_states_genoclab_start(self):
        nxt = get_allowed_next_states('GENOCLAB', 'REQUEST_CREATED')
        self.assertEqual(nxt, {'QUOTE_DRAFT', 'REJECTED'})

    def test_unknown_channel_raises(self):
        with self.assertRaises(InvalidTransitionError):
            get_allowed_next_states('NOPE', 'REQUEST_CREATED')

    def test_super_admin_bypasses_role_check(self):
        req = self._req()
        self.assertTrue(check_role_permission(req, 'QUOTE_DRAFT', self.admin))

    def test_wrong_role_denied(self):
        req = self._req()
        # CLIENT may not move REQUEST_CREATED -> QUOTE_DRAFT (admins only)
        self.assertFalse(check_role_permission(req, 'QUOTE_DRAFT', self.client_user))

    def test_unknown_edge_denied_fail_closed(self):
        req = self._req()
        self.assertFalse(check_role_permission(req, 'COMPLETED', self.platform))

    # --- transition() behaviour ---
    def test_valid_transition_updates_status_and_history(self):
        req = self._req()
        transition(req, 'QUOTE_DRAFT', self.platform, notes='ok')
        req.refresh_from_db()
        self.assertEqual(req.status, 'QUOTE_DRAFT')
        h = RequestHistory.objects.filter(request=req, to_status='QUOTE_DRAFT').first()
        self.assertIsNotNone(h)
        self.assertEqual(h.from_status, 'REQUEST_CREATED')
        self.assertFalse(h.forced)

    def test_invalid_target_raises(self):
        req = self._req()
        with self.assertRaises(InvalidTransitionError):
            transition(req, 'COMPLETED', self.platform)
        req.refresh_from_db()
        self.assertEqual(req.status, 'REQUEST_CREATED')  # unchanged

    def test_wrong_role_raises_authorization_error(self):
        req = self._req()
        with self.assertRaises(AuthorizationError):
            transition(req, 'QUOTE_DRAFT', self.client_user)

    def test_force_transition_bypasses_graph(self):
        req = self._req()
        force_transition(req, 'COMPLETED', self.admin, notes='manual override')
        req.refresh_from_db()
        self.assertEqual(req.status, 'COMPLETED')
        h = RequestHistory.objects.filter(request=req, to_status='COMPLETED').first()
        self.assertTrue(h.forced)

    def test_force_transition_unknown_status_raises(self):
        req = self._req()
        with self.assertRaises(InvalidTransitionError):
            force_transition(req, 'NOT_A_STATUS', self.admin)


# ---------------------------------------------------------------------------
# End-to-end pipeline walks — drive each channel through its full happy path
# with role-appropriate actors, proving the state machine + role matrix +
# key side effects (IBTIKAR budget deduction) all hold together.
# ---------------------------------------------------------------------------
class EndToEndPipelineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User, MemberProfile
        cls.admin = User.objects.create(username='e2e-admin', role='PLATFORM_ADMIN')
        cls.finance = User.objects.create(username='e2e-fin', role='FINANCE')
        cls.analyst_user = User.objects.create(username='e2e-analyst', role='MEMBER')
        cls.analyst = MemberProfile.objects.get(user=cls.analyst_user)

    def _step(self, req, to, actor):
        transition(req, to, actor, notes=f'e2e→{to}')
        req.refresh_from_db()
        self.assertEqual(req.status, to)

    def test_ibtikar_full_pipeline_deducts_budget(self):
        from accounts.models import User
        requester = User.objects.create(
            username='e2e-req', role='REQUESTER',
            ibtikar_declared_balance=Decimal('100000'))
        req = Request.objects.create(
            channel='IBTIKAR', status='DRAFT', requester=requester,
            assigned_to=self.analyst, budget_amount=Decimal('40000'))

        self._step(req, 'SUBMITTED', requester)
        self._step(req, 'VALIDATION_PEDAGOGIQUE', self.admin)
        self._step(req, 'VALIDATION_FINANCE', self.admin)
        self._step(req, 'PLATFORM_NOTE_GENERATED', self.finance)
        self._step(req, 'IBTIKAR_SUBMISSION_PENDING', self.admin)
        self._step(req, 'IBTIKAR_CODE_SUBMITTED', requester)
        self._step(req, 'ASSIGNED', self.admin)
        self._step(req, 'APPOINTMENT_PROPOSED', self.analyst_user)
        self._step(req, 'APPOINTMENT_CONFIRMED', requester)
        self._step(req, 'SAMPLE_RECEIVED', self.analyst_user)
        self._step(req, 'ANALYSIS_STARTED', self.analyst_user)
        self._step(req, 'ANALYSIS_FINISHED', self.analyst_user)
        self._step(req, 'REPORT_UPLOADED', self.analyst_user)
        self._step(req, 'REPORT_VALIDATED', self.admin)
        self._step(req, 'SENT_TO_REQUESTER', self.admin)
        self._step(req, 'COMPLETED', requester)

        # Budget deducted exactly once on COMPLETED.
        requester.refresh_from_db()
        self.assertEqual(float(requester.ibtikar_declared_balance), 60000.0)

        # History records every step (16 transitions).
        self.assertEqual(RequestHistory.objects.filter(request=req).count(), 16)

        self._step(req, 'CLOSED', self.admin)  # terminal

    def test_genoclab_full_pipeline(self):
        from accounts.models import User
        client = User.objects.create(username='e2e-client', role='CLIENT')
        req = Request.objects.create(
            channel='GENOCLAB', status='REQUEST_CREATED', requester=client,
            assigned_to=self.analyst, quote_amount=Decimal('50000'))

        self._step(req, 'QUOTE_DRAFT', self.admin)
        self._step(req, 'QUOTE_SENT', self.admin)
        self._step(req, 'QUOTE_VALIDATED_BY_CLIENT', client)
        self._step(req, 'ORDER_UPLOADED', client)
        self._step(req, 'INVOICE_GENERATED', self.finance)
        self._step(req, 'ASSIGNED', self.admin)
        self._step(req, 'APPOINTMENT_PROPOSED', self.analyst_user)
        self._step(req, 'APPOINTMENT_CONFIRMED', client)
        self._step(req, 'SAMPLE_RECEIVED', self.analyst_user)
        self._step(req, 'ANALYSIS_STARTED', self.analyst_user)
        self._step(req, 'ANALYSIS_FINISHED', self.analyst_user)
        self._step(req, 'PAYMENT_PENDING', self.admin)
        self._step(req, 'PAYMENT_PROOF_UPLOADED', client)
        req.payment_verified_at = timezone.now()
        req.payment_verified_by = self.finance
        req.payment_verification_note = 'Proof matched to the bank receipt.'
        req.save(update_fields=[
            'payment_verified_at', 'payment_verified_by',
            'payment_verification_note',
        ])
        self._step(req, 'PAYMENT_CONFIRMED', self.finance)
        self._step(req, 'REPORT_UPLOADED', self.analyst_user)
        self._step(req, 'REPORT_VALIDATED', self.admin)
        self._step(req, 'SENT_TO_CLIENT', self.admin)
        self._step(req, 'COMPLETED', client)
        self._step(req, 'ARCHIVED', self.admin)  # terminal

    def test_genoclab_client_cannot_self_validate_finance_step(self):
        # A CLIENT must NOT be able to drive the finance/invoice transition.
        from accounts.models import User
        client = User.objects.create(username='e2e-client2', role='CLIENT')
        req = Request.objects.create(
            channel='GENOCLAB', status='ORDER_UPLOADED', requester=client)
        with self.assertRaises(AuthorizationError):
            transition(req, 'INVOICE_GENERATED', client)

    def test_client_uploads_proof_but_finance_confirms_payment(self):
        from accounts.models import User
        client = User.objects.create(username='payment-client', role='CLIENT')
        req = Request.objects.create(
            channel='GENOCLAB', status='PAYMENT_PENDING', requester=client)

        transition(req, 'PAYMENT_PROOF_UPLOADED', client)
        req.refresh_from_db()
        self.assertEqual(req.status, 'PAYMENT_PROOF_UPLOADED')

        with self.assertRaises(AuthorizationError):
            transition(req, 'PAYMENT_CONFIRMED', client)

        req.payment_verified_at = timezone.now()
        req.payment_verified_by = self.finance
        req.payment_verification_note = 'Proof matched to the bank receipt.'
        req.save(update_fields=[
            'payment_verified_at', 'payment_verified_by',
            'payment_verification_note',
        ])
        transition(req, 'PAYMENT_CONFIRMED', self.finance)
        req.refresh_from_db()
        self.assertEqual(req.status, 'PAYMENT_CONFIRMED')
        self.assertEqual(req.payment_verified_by, self.finance)

    def test_payment_confirmation_requires_verification_audit(self):
        req = Request.objects.create(
            channel='GENOCLAB', status='PAYMENT_PROOF_UPLOADED')
        with self.assertRaises(InvalidTransitionError):
            transition(req, 'PAYMENT_CONFIRMED', self.finance)


# ---------------------------------------------------------------------------
# Bilan (configurable activity report) engine
# ---------------------------------------------------------------------------
class BilanEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        svc = Service.objects.create(code='B_SVC', name='Bilan Svc')
        u = User.objects.create(username='bilan-req', role='REQUESTER')
        for i, ch in enumerate(['IBTIKAR', 'GENOCLAB', 'IBTIKAR']):
            Request.objects.create(
                channel=ch, status='COMPLETED', service=svc, requester=u,
                display_id=f'BIL-{i}', budget_amount=Decimal('1000'))

    def test_available_sections_nonempty(self):
        from core.bilan import available_sections
        secs = available_sections()
        self.assertTrue(secs)
        self.assertTrue(all(len(s) == 2 for s in secs))

    def test_build_bilan_returns_kpis_and_sections(self):
        from core.bilan import build_bilan
        result = build_bilan(filters={}, sections=['channel'])
        self.assertIn('kpis', result)
        self.assertIn('sections', result)
        self.assertTrue(len(result['sections']) >= 1)
        # The channel section should tally our 3 requests.
        channel_section = result['sections'][0]
        self.assertIn('rows', channel_section)

    def test_build_bilan_defaults_when_no_sections(self):
        from core.bilan import build_bilan
        result = build_bilan(filters={}, sections=None)
        self.assertTrue(len(result['sections']) >= 1)


# ---------------------------------------------------------------------------
# ensure_superuser + seed commands (management commands smoke)
# ---------------------------------------------------------------------------
class ManagementCommandTests(TestCase):
    def test_ensure_superuser_creates_from_env(self):
        import os
        from django.core.management import call_command
        from accounts.models import User
        os.environ['DJANGO_SUPERUSER_USERNAME'] = 'seed-admin'
        os.environ['DJANGO_SUPERUSER_PASSWORD'] = 'S3cret!pass9'
        os.environ['DJANGO_SUPERUSER_EMAIL'] = 'admin@essbo.dz'
        try:
            call_command('ensure_superuser')
            u = User.objects.get(username='seed-admin')
            self.assertTrue(u.is_superuser)
            self.assertEqual(u.role, 'SUPER_ADMIN')
            # Idempotent: a second run must not error or duplicate.
            call_command('ensure_superuser')
            self.assertEqual(User.objects.filter(username='seed-admin').count(), 1)
        finally:
            for k in ('DJANGO_SUPERUSER_USERNAME', 'DJANGO_SUPERUSER_PASSWORD',
                      'DJANGO_SUPERUSER_EMAIL'):
                os.environ.pop(k, None)

    def test_ensure_superuser_noop_without_env(self):
        from django.core.management import call_command
        from accounts.models import User
        before = User.objects.count()
        call_command('ensure_superuser')  # no env → skip, no error
        self.assertEqual(User.objects.count(), before)

    def test_seed_services_and_content_run(self):
        from django.core.management import call_command
        call_command('seed_services')
        call_command('seed_content')
        self.assertTrue(Service.objects.exists())


# ---------------------------------------------------------------------------
# IBTIKAR balance deduction (unit + end-to-end on COMPLETED)
# ---------------------------------------------------------------------------
class IbtikarDeductionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.User = User
        cls.admin = User.objects.create(username='ded-admin', role='SUPER_ADMIN')

    def test_deduct_reduces_declared_balance(self):
        u = self.User.objects.create(
            username='ded1', role='REQUESTER',
            ibtikar_declared_balance=Decimal('50000'))
        res = deduct_ibtikar_balance(u, 12000, reason='x')
        u.refresh_from_db()
        self.assertEqual(res['remaining'], 38000.0)
        self.assertEqual(float(u.ibtikar_declared_balance), 38000.0)

    def test_deduct_floors_at_zero(self):
        u = self.User.objects.create(
            username='ded2', role='REQUESTER',
            ibtikar_declared_balance=Decimal('5000'))
        deduct_ibtikar_balance(u, 9000, reason='x')
        u.refresh_from_db()
        self.assertEqual(float(u.ibtikar_declared_balance), 0.0)

    def test_deduct_skips_when_no_declared_balance(self):
        u = self.User.objects.create(username='ded3', role='REQUESTER',
                                     ibtikar_declared_balance=None)
        res = deduct_ibtikar_balance(u, 1000, reason='x')
        self.assertTrue(res['skipped'])

    def test_budget_is_deducted_only_once_on_replay(self):
        """Regression: an admin forcing the request back and the requester
        confirming again must NOT debit the budget a second time."""
        u = self.User.objects.create(
            username='ded-replay', role='REQUESTER',
            ibtikar_declared_balance=Decimal('100000'))
        req = Request.objects.create(
            channel='IBTIKAR', status='SENT_TO_REQUESTER', requester=u,
            budget_amount=Decimal('30000'), display_id='DED-REPLAY-1')

        transition(req, 'COMPLETED', u)
        u.refresh_from_db()
        self.assertEqual(float(u.ibtikar_declared_balance), 70000.0)
        req.refresh_from_db()
        self.assertTrue(req.budget_deducted)

        # Replay the completion.
        force_transition(req, 'SENT_TO_REQUESTER', self.admin, notes='fix')
        transition(req, 'COMPLETED', u)
        u.refresh_from_db()
        self.assertEqual(float(u.ibtikar_declared_balance), 70000.0,
                         "le budget a été déduit deux fois")

    def test_completing_ibtikar_request_deducts_budget(self):
        """End-to-end: SENT_TO_REQUESTER -> COMPLETED on IBTIKAR deducts the
        resolved cost from the requester's declared balance."""
        u = self.User.objects.create(
            username='ded-flow', role='REQUESTER',
            ibtikar_declared_balance=Decimal('100000'))
        req = Request.objects.create(
            channel='IBTIKAR', status='SENT_TO_REQUESTER',
            requester=u, budget_amount=Decimal('30000'))
        transition(req, 'COMPLETED', self.admin, notes='receipt confirmed')
        req.refresh_from_db()
        u.refresh_from_db()
        self.assertEqual(req.status, 'COMPLETED')
        self.assertEqual(float(u.ibtikar_declared_balance), 70000.0)
