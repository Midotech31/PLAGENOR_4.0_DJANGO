"""Tests for the money-critical core: pricing engine, the canonical cost
resolver, and the IBTIKAR budget check.

These guard the numbers that turn into real invoices (GENOCLAB) and the
virtual-budget gate (IBTIKAR). Run with ``python manage.py test core``.
"""
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.exceptions import AuthorizationError, InvalidTransitionError
from core.financial import check_ibtikar_budget, compute_invoice_totals
from core.models import Request, RequestHistory, Service
from core.pricing import calculate_price, resolve_cost
from core.state_machine import get_allowed_next_states
from core.workflow import check_role_permission, force_transition, transition


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

    def test_missing_multiplier_key_defaults_to_one(self):
        # An unknown analysis_mode must never zero out the quote.
        res = calculate_price(
            self._def(),
            {'analysis_mode': 'does-not-exist'},
            sample_table=[{'a': 1}],
        )
        self.assertEqual(res['unit_price'], 1000)  # base * 1.0

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

    def test_no_service_returns_zero(self):
        res = resolve_cost(None, 'GENOCLAB')
        self.assertEqual(res['total'], 0.0)
        self.assertEqual(res['source'], 'no_service')

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

    def test_invalid_channel_is_normalised(self):
        # An unknown channel not starting with 'g' -> treated as IBTIKAR.
        res = resolve_cost(self.service, 'XYZ', sample_table=[{'a': 1}])
        self.assertEqual(res['total'], 1500.0)

    def test_invalid_channel_starting_with_g_is_genoclab(self):
        # ...while one starting with 'g' -> GENOCLAB (documents the rule).
        res = resolve_cost(self.service, 'garbage', sample_table=[{'a': 1}])
        self.assertEqual(res['total'], 3000.0)


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
