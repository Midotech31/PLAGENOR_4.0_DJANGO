"""Tests for the money-critical core: pricing engine, the canonical cost
resolver, and the IBTIKAR budget check.

These guard the numbers that turn into real invoices (GENOCLAB) and the
virtual-budget gate (IBTIKAR). Run with ``python manage.py test core``.
"""
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.financial import check_ibtikar_budget
from core.models import Service
from core.pricing import calculate_price, resolve_cost


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
