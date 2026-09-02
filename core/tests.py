"""Tests for the money-critical core: pricing engine, the canonical cost
resolver, and the IBTIKAR budget check.

These guard the numbers that turn into real invoices (GENOCLAB) and the
virtual-budget gate (IBTIKAR). Run with ``python manage.py test core``.
"""
import base64
import uuid
from decimal import Decimal
from unittest.mock import call, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.utils import timezone

from core.exceptions import (
    AuthorizationError, BudgetExceededError, FinancialValidationError,
    InvalidTransitionError, PricingConfigurationError,
)
from core.financial import (
    approve_with_budget_override, archive_monthly_revenue,
    check_ibtikar_budget, compute_invoice_totals, deduct_ibtikar_balance,
    get_budget_dashboard, get_ibtikar_budget_used,
    get_ibtikar_budget_used_by_requester, get_ibtikar_virtual_revenue,
    get_revenue_summary,
)
from core.models import Invoice, Request, RequestHistory, Service, ServicePricing
from core.pricing import calculate_cost_from_db, calculate_price, resolve_cost
from core.state_machine import (
    GENOCLAB_TRANSITIONS, IBTIKAR_TRANSITIONS, get_all_states,
    get_allowed_next_states, get_graph, is_terminal,
    validate_genoclab_transition, validate_ibtikar_transition,
    validate_transition,
)
from core.workflow import (
    _auto_generate_documents, _create_notifications, _post_commit_transition,
    _send_transition_emails, check_role_permission, force_transition, transition,
)
from core.uploads import validate_upload
from core.assignment import member_is_eligible


class ManagementCommandCoverageTests(TestCase):
    """Smoke-test operational commands without touching an external database."""

    @override_settings(DEBUG=True)
    def test_account_notification_revenue_and_demo_seed_commands(self):
        from django.core.management import call_command
        from accounts.models import User
        from notifications.models import Notification

        call_command('seed_accounts', quiet=True, verbosity=0)
        self.assertTrue(User.objects.filter(username='admin', role='SUPER_ADMIN').exists())
        # Re-running covers the refresh/idempotency path.
        call_command('seed_accounts', quiet=False, verbosity=0)
        call_command('seed_notifications', verbosity=0)
        call_command('seed_notifications', verbosity=0)
        self.assertTrue(Notification.objects.exists())
        call_command('archive_revenue', month=1, year=2026, verbosity=0)

        Service.objects.create(
            code='DEMO-COVER', name='Demo coverage', active=True,
            channel_availability='IBTIKAR', ibtikar_price=Decimal('5000'),
        )
        call_command(
            'seed_demo_request', service='DEMO-COVER', status='ASSIGNED',
            balance=180000, verbosity=0,
        )
        call_command(
            'seed_demo_request', service='missing-code', status='REPORT_UPLOADED',
            balance=170000, verbosity=0,
        )
        self.assertEqual(Request.objects.filter(display_id__startswith='IBT-DEMO-').count(), 1)

    def test_demo_seed_commands_refuse_non_debug_environments(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with override_settings(DEBUG=False):
            with self.assertRaisesRegex(CommandError, 'seed_accounts is disabled'):
                call_command('seed_accounts', quiet=True, verbosity=0)
            with self.assertRaisesRegex(CommandError, 'seed_demo_request is disabled'):
                call_command('seed_demo_request', verbosity=0)

    def test_backup_restore_commands_success_and_errors(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from pathlib import Path
        import tempfile

        temp_dir = Path(tempfile.mkdtemp(prefix='plagenor-command-tests-'))
        backup = temp_dir / 'backup.sqlite3'
        backup.write_bytes(b'SQLite format 3')
        with patch('core.management.commands.backup_db.perform_backup', return_value=backup):
            call_command('backup_db', keep=2, verbosity=0)
        with patch('core.management.commands.backup_db.perform_backup', side_effect=RuntimeError('failed')):
            with self.assertRaises(CommandError):
                call_command('backup_db', verbosity=0)
        with self.assertRaises(CommandError):
            call_command('restore_db', input=str(temp_dir / 'missing.sqlite3'), verbosity=0)
        with patch('core.management.commands.restore_db.perform_restore') as restore:
            call_command('restore_db', input=str(backup), verbosity=0)
            restore.assert_called_once_with(backup)
        with patch('core.management.commands.restore_db.perform_restore', side_effect=RuntimeError('failed')):
            with self.assertRaises(CommandError):
                call_command('restore_db', input=str(backup), verbosity=0)

    def test_programmatic_template_builders_create_valid_docx_files(self):
        from django.core.management import call_command
        from pathlib import Path
        import tempfile
        import documents.build_default_templates as builders

        temp_dir = Path(tempfile.mkdtemp(prefix='plagenor-template-builders-'))
        with patch.object(builders, 'TEMPLATE_DIR', temp_dir):
            paths = builders.build_all()
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(path.exists() for path in paths))
            # Existing files exercise the one-time backup behavior.
            builders.build_all()
            self.assertTrue((temp_dir / 'quote_template.bak.docx').exists())

        fake_base = temp_dir / 'project'
        with self.settings(BASE_DIR=fake_base):
            call_command('create_docx_templates', verbosity=0)
        output = fake_base / 'documents' / 'docx_templates'
        self.assertEqual(len(list(output.glob('*.docx'))), 4)

    def test_demo_seed_schema_helpers_cover_typed_fields(self):
        from core.management.commands.seed_demo_request import Command

        service = Service.objects.create(
            code='SCHEMA-COVER', name='Schema coverage', active=True,
            channel_availability='IBTIKAR', ibtikar_price=Decimal('10'))
        definition = {
            'parameters': [
                {'name': 'enabled', 'type': 'boolean'},
                {'name': 'mode', 'type': 'choice', 'options': ['fast', 'slow']},
                {'name': 'comment', 'type': 'string'},
                {'type': 'string'},
            ],
            'sample_table': {'columns': [
                {'name': 'sample_code', 'type': 'string', 'label': 'Code'},
                {'name': 'replicates', 'type': 'integer', 'label': 'Replicates'},
                {'name': 'matrix', 'type': 'choice', 'options': ['soil', 'water']},
                {'name': 'description', 'type': 'string', 'label': 'Description'},
                {'type': 'string'},
            ]},
        }
        with patch('core.registry.get_service_def', return_value=definition):
            params, rows = Command()._build_service_aware_samples(service, count=2)
        self.assertFalse(params['enabled'])
        self.assertEqual(params['mode'], 'fast')
        self.assertEqual(rows[0]['replicates'], '1')
        self.assertEqual(rows[1]['matrix'], 'soil')


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


class DynamicPricingTests(TestCase):
    def setUp(self):
        self.service = Service.objects.create(
            code='DYNAMIC_PRICE_TEST', name='Dynamic pricing test',
            channel_availability='BOTH', ibtikar_price=Decimal('120'),
            genoclab_price=Decimal('240'),
        )

    def _tier(self, pricing_type, amount, priority):
        return ServicePricing.objects.create(
            service=self.service, channel='BOTH', name=pricing_type,
            pricing_type=pricing_type, amount=Decimal(amount),
            priority=priority,
        )

    def test_no_tiers_uses_channel_base_price_per_nonempty_sample(self):
        result = calculate_cost_from_db(
            self.service, 'GENOCLAB', [{}, {'id': 1}, {'id': 2}])
        self.assertEqual(result['source'], 'service_base_price')
        self.assertEqual(result['sample_count'], 2)
        self.assertEqual(result['total'], 480.0)

    def test_tier_stack_applies_quantities_urgency_and_discount(self):
        self._tier('BASE', '100', 1)
        self._tier('PER_SAMPLE', '10', 2)
        self._tier('PER_PARAMETER', '5', 3)
        self._tier('URGENCY_SURCHARGE', '20', 4)
        self._tier('DISCOUNT', '50', 5)
        result = calculate_cost_from_db(
            self.service, 'GENOCLAB',
            sample_table=[{'id': 1}, {'id': 2}],
            service_params={'a': 'yes', 'b': '', 'c': 1},
            urgency='Urgent',
        )
        self.assertEqual(result['source'], 'service_pricing_db')
        self.assertEqual(result['total'], 200.0)
        self.assertEqual(result['pricing_configs_used'], 5)

    def test_nonurgent_surcharge_is_zero_and_discount_clamps_at_zero(self):
        self._tier('URGENCY_SURCHARGE', '20', 1)
        self._tier('DISCOUNT', '50', 2)
        result = calculate_cost_from_db(
            self.service, 'GENOCLAB', sample_table=[{'id': 1}],
            urgency='Normal',
        )
        self.assertEqual(result['total'], 0.0)

    def test_override_replaces_all_other_tiers(self):
        self._tier('BASE', '100', 1)
        self._tier('OVERRIDE', '777', 2)
        result = calculate_cost_from_db(
            self.service, 'IBTIKAR', sample_table=[{'id': 1}, {'id': 2}])
        self.assertEqual(result['source'], 'service_pricing_db_override')
        self.assertEqual(result['total'], 777.0)

    def test_missing_service_returns_explicit_error(self):
        result = calculate_cost_from_db(None, 'GENOCLAB')
        self.assertEqual(result, {'error': 'Service is required', 'total': 0})


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


class FinancialReportingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.requester = User.objects.create_user(
            username='financial-report-requester', role='REQUESTER')
        cls.super_admin = User.objects.create_user(
            username='financial-report-admin', role='SUPER_ADMIN')
        cls.member = User.objects.create_user(
            username='financial-report-member', role='MEMBER')
        cls.active_request = Request.objects.create(
            display_id='FIN-REPORT-1', title='Counted request',
            channel='IBTIKAR', status='COMPLETED', requester=cls.requester,
            budget_amount=Decimal('1250'),
        )
        Request.objects.create(
            display_id='FIN-REPORT-2', title='Rejected request',
            channel='IBTIKAR', status='REJECTED', requester=cls.requester,
            budget_amount=Decimal('9000'),
        )
        Invoice.objects.create(
            invoice_number='FIN-INV-1', client=cls.requester,
            total_ttc=Decimal('2380'), subtotal_ht=Decimal('2000'),
            vat_amount=Decimal('380'), created_by=cls.super_admin,
        )

    def test_revenue_queries_keep_channels_and_rejections_separate(self):
        year = timezone.now().year
        virtual = get_ibtikar_virtual_revenue(year)
        self.assertEqual(virtual, {
            'total': 1250.0, 'count': 1, 'students': 1,
        })
        self.assertEqual(
            get_ibtikar_budget_used_by_requester(self.requester.pk, year),
            1250.0,
        )
        self.assertEqual(get_ibtikar_budget_used(year), 1250.0)
        self.assertEqual(get_revenue_summary(), {'total': 2380.0, 'count': 1})

    def test_monthly_archive_is_idempotent_and_dashboard_is_symmetric(self):
        now = timezone.now()
        first = archive_monthly_revenue(now.month, now.year)
        second = archive_monthly_revenue(now.month, now.year)
        self.assertEqual({row['channel'] for row in first}, {'IBTIKAR', 'GENOCLAB'})
        self.assertTrue(all(row['created'] for row in first))
        self.assertTrue(all(not row['created'] for row in second))
        dashboard = get_budget_dashboard()
        self.assertEqual(dashboard['ibtikar']['total'], 1250.0)
        self.assertEqual(dashboard['genoclab']['total'], 2380.0)

    def test_budget_override_requires_super_admin_and_justification(self):
        with self.assertRaises(BudgetExceededError):
            approve_with_budget_override(
                self.active_request, self.member, 100, 'Valid justification')
        with self.assertRaises(BudgetExceededError):
            approve_with_budget_override(
                self.active_request, self.super_admin, 100, 'short')
        result = approve_with_budget_override(
            self.active_request, self.super_admin, 100,
            'Documented institutional exception',
        )
        self.assertTrue(result['approved'])
        self.assertTrue(result['override'])

# ---------------------------------------------------------------------------
# Workflow state machine + role permissions
# ---------------------------------------------------------------------------
class StateMachineContractTests(SimpleTestCase):
    def test_channel_graphs_and_state_listing_are_authoritative(self):
        self.assertIs(get_graph('IBTIKAR'), IBTIKAR_TRANSITIONS)
        self.assertIs(get_graph('GENOCLAB'), GENOCLAB_TRANSITIONS)
        self.assertEqual(get_all_states('IBTIKAR'), list(IBTIKAR_TRANSITIONS))
        self.assertEqual(get_all_states('GENOCLAB'), list(GENOCLAB_TRANSITIONS))

    def test_channel_specific_validators_accept_declared_edges(self):
        self.assertTrue(validate_ibtikar_transition('DRAFT', 'SUBMITTED'))
        self.assertTrue(validate_genoclab_transition(
            'PAYMENT_PENDING', 'PAYMENT_PROOF_UPLOADED'))

    def test_invalid_and_terminal_transitions_fail_closed(self):
        with self.assertRaises(InvalidTransitionError):
            validate_transition('GENOCLAB', 'PAYMENT_PENDING', 'PAYMENT_CONFIRMED')
        with self.assertRaises(InvalidTransitionError):
            validate_transition('IBTIKAR', 'CLOSED', 'SUBMITTED')
        self.assertTrue(is_terminal('IBTIKAR', 'CLOSED'))
        self.assertTrue(is_terminal('GENOCLAB', 'ARCHIVED'))
        self.assertFalse(is_terminal('GENOCLAB', 'REQUEST_CREATED'))


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

    def test_noncritical_side_effects_are_deferred_until_commit(self):
        req = self._req()
        with patch('core.workflow._post_commit_transition') as side_effects:
            with self.captureOnCommitCallbacks(execute=True):
                transition(req, 'QUOTE_DRAFT', self.platform)
                side_effects.assert_not_called()
            side_effects.assert_called_once()


class WorkflowSideEffectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        cls.requester = User.objects.create_user(
            username='side-requester', email='requester@example.test',
            role='CLIENT')
        cls.member_user = User.objects.create_user(
            username='side-member', email='member@example.test', role='MEMBER')
        cls.admin = User.objects.create_user(
            username='side-admin', email='admin@example.test',
            role='PLATFORM_ADMIN')
        cls.request = Request.objects.create(
            display_id='SIDE-1', title='Side effects', channel='GENOCLAB',
            status='ASSIGNED', requester=cls.requester,
            assigned_to=cls.member_user.member_profile,
        )

    def test_post_commit_dispatches_audit_email_notification_and_documents(self):
        with (
            patch('core.workflow.log_workflow_transition') as audit,
            patch('core.workflow._send_transition_emails') as emails,
            patch('core.workflow._create_notifications') as notifications,
            patch('core.workflow._auto_generate_documents') as documents,
        ):
            _post_commit_transition(
                self.request, 'REQUEST_CREATED', 'QUOTE_DRAFT',
                self.admin, 'reviewed', False,
            )
        audit.assert_called_once()
        emails.assert_called_once()
        notifications.assert_called_once()
        documents.assert_called_once()

    def test_notification_recipients_follow_visibility_rules(self):
        from notifications.models import Notification
        _create_notifications(self.request, 'ASSIGNED')
        recipients = set(Notification.objects.values_list('user_id', flat=True))
        self.assertEqual(recipients, {
            self.requester.pk, self.member_user.pk,
        })
        Notification.objects.all().delete()
        _create_notifications(self.request, 'REQUEST_CREATED')
        recipients = set(Notification.objects.values_list('user_id', flat=True))
        self.assertEqual(recipients, {self.admin.pk})

    def test_email_router_selects_dedicated_and_milestone_templates(self):
        from notifications import emails
        with (
            patch.object(emails, 'notify_assignment') as assignment,
            patch.object(emails, 'notify_appointment') as appointment,
            patch.object(emails, 'notify_report_delivery') as delivery,
            patch.object(emails, 'notify_status_change') as status_change,
        ):
            _send_transition_emails(self.request, 'INVOICE_GENERATED', 'ASSIGNED')
            _send_transition_emails(
                self.request, 'ASSIGNED', 'APPOINTMENT_PROPOSED')
            _send_transition_emails(
                self.request, 'REPORT_VALIDATED', 'SENT_TO_CLIENT')
        assignment.assert_called_once_with(
            self.request, self.member_user.member_profile)
        appointment.assert_called_once_with(self.request)
        delivery.assert_called_once_with(self.request)
        self.assertEqual(status_change.call_count, 2)
        status_change.assert_has_calls([
            call(self.request, 'ASSIGNED', 'APPOINTMENT_PROPOSED'),
            call(self.request, 'REPORT_VALIDATED', 'SENT_TO_CLIENT'),
        ])

    def test_document_hooks_are_explicit_and_channel_safe(self):
        from documents import generators
        ibtikar = Request.objects.create(
            display_id='SIDE-IBT-1', title='IBTIKAR documents',
            channel='IBTIKAR', status='SUBMITTED')
        with (
            patch.object(generators, 'generate_ibtikar_form') as ibtikar_form,
            patch.object(generators, 'generate_platform_note') as platform_note,
            patch.object(generators, 'generate_reception_form') as reception,
        ):
            _auto_generate_documents(ibtikar, 'SUBMITTED')
            _auto_generate_documents(self.request, 'SUBMITTED')
            _auto_generate_documents(ibtikar, 'PLATFORM_NOTE_GENERATED')
            _auto_generate_documents(self.request, 'SAMPLE_RECEIVED')
            _auto_generate_documents(self.request, 'QUOTE_DRAFT')
        ibtikar_form.assert_called_once_with(ibtikar)
        platform_note.assert_called_once_with(ibtikar)
        reception.assert_called_once_with(self.request)


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


class DatabaseBackupPrimitiveTests(SimpleTestCase):
    """Exercise backup/restore without touching the configured test DB."""

    def _database(self, engine, name='db', **extra):
        return {'default': {'ENGINE': engine, 'NAME': name, **extra}}

    def test_engine_detection_and_unsupported_backend(self):
        from core import db_backup

        for engine, expected in (
            ('django.db.backends.sqlite3', 'sqlite'),
            ('django.db.backends.postgresql', 'postgres'),
        ):
            with patch.object(db_backup.settings, 'DATABASES', self._database(engine)):
                self.assertEqual(db_backup._engine_name(), expected)
        with patch.object(db_backup.settings, 'DATABASES', self._database('django.db.backends.mysql')):
            with self.assertRaisesRegex(RuntimeError, 'Unsupported database engine'):
                db_backup._engine_name()

    def test_sqlite_backup_is_valid_copy_and_prunes_old_files(self):
        import sqlite3
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from core import db_backup

        with TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'live.db'
            conn = sqlite3.connect(source)
            conn.execute('CREATE TABLE evidence (id INTEGER PRIMARY KEY)')
            conn.commit()
            conn.close()
            backup_dir = root / 'data' / 'backups'
            backup_dir.mkdir(parents=True)
            for idx in range(3):
                old = backup_dir / f'plagenor_20000101_00000{idx}.db'
                old.write_bytes(b'old')

            with self.settings(BASE_DIR=root), patch.object(
                db_backup.settings, 'DATABASES',
                self._database('django.db.backends.sqlite3', str(source)),
            ):
                result = db_backup.perform_backup(keep=2)

            self.assertTrue(result.exists())
            self.assertEqual(result.read_bytes(), source.read_bytes())
            self.assertEqual(len(list(backup_dir.glob('plagenor_*.db'))), 2)

    def test_sqlite_backup_rejects_missing_database(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from core import db_backup

        with TemporaryDirectory() as td:
            root = Path(td)
            with self.settings(BASE_DIR=root), patch.object(
                db_backup.settings, 'DATABASES',
                self._database('django.db.backends.sqlite3', str(root / 'missing.db')),
            ):
                with self.assertRaises(FileNotFoundError):
                    db_backup.perform_backup()

    def test_postgres_backup_builds_safe_command_and_password_environment(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from core import db_backup

        database = self._database(
            'django.db.backends.postgresql', 'plagenor', HOST='db.local',
            PORT='5433', USER='backup_user', PASSWORD='secret',
        )
        with TemporaryDirectory() as td, self.settings(BASE_DIR=Path(td)), patch.object(
            db_backup.settings, 'DATABASES', database,
        ), patch(
            'core.db_backup.subprocess.run',
            return_value=SimpleNamespace(returncode=0, stderr=''),
        ) as run:
            result = db_backup.perform_backup()

        command = run.call_args.args[0]
        self.assertEqual(command[0], 'pg_dump')
        self.assertIn('--format=custom', command)
        self.assertIn('plagenor', command)
        self.assertEqual(run.call_args.kwargs['env']['PGPASSWORD'], 'secret')
        self.assertTrue(str(result).endswith('.dump'))

    def test_postgres_backup_failure_removes_partial_dump(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from core import db_backup

        with TemporaryDirectory() as td:
            root = Path(td)

            def fail_dump(command, **kwargs):
                Path(command[command.index('--file') + 1]).write_bytes(b'partial')
                return SimpleNamespace(returncode=1, stderr='permission denied')

            with self.settings(BASE_DIR=root), patch.object(
                db_backup.settings, 'DATABASES',
                self._database('django.db.backends.postgresql', 'plagenor'),
            ), patch('core.db_backup.subprocess.run', side_effect=fail_dump):
                with self.assertRaisesRegex(RuntimeError, 'permission denied'):
                    db_backup.perform_backup()
            self.assertFalse(list((root / 'data' / 'backups').glob('*.dump')))

    def test_sqlite_restore_validates_then_preserves_previous_database(self):
        import sqlite3
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from core import db_backup

        def make_db(path, value):
            connection = sqlite3.connect(path)
            connection.execute('CREATE TABLE marker (value TEXT)')
            connection.execute('INSERT INTO marker VALUES (?)', (value,))
            connection.commit()
            connection.close()

        with TemporaryDirectory() as td:
            root = Path(td)
            live = root / 'live.db'
            incoming = root / 'incoming.db'
            make_db(live, 'old')
            make_db(incoming, 'new')
            with patch.object(
                db_backup.settings, 'DATABASES',
                self._database('django.db.backends.sqlite3', str(live)),
            ):
                db_backup.perform_restore(incoming)

            connection = sqlite3.connect(live)
            self.assertEqual(connection.execute('SELECT value FROM marker').fetchone()[0], 'new')
            connection.close()
            self.assertTrue((root / 'live.pre_restore.db').exists())
            self.assertFalse(incoming.exists())

    def test_invalid_sqlite_restore_is_rejected_before_mutation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from core import db_backup

        with TemporaryDirectory() as td:
            root = Path(td)
            live = root / 'live.db'
            incoming = root / 'invalid.db'
            live.write_bytes(b'original')
            incoming.write_bytes(b'not sqlite')
            with patch.object(
                db_backup.settings, 'DATABASES',
                self._database('django.db.backends.sqlite3', str(live)),
            ):
                with self.assertRaisesRegex(ValueError, 'SQLite invalide'):
                    db_backup.perform_restore(incoming)
            self.assertEqual(live.read_bytes(), b'original')

    def test_postgres_dump_validation_and_restore_contract(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from core import db_backup

        database = self._database(
            'django.db.backends.postgresql', 'plagenor', HOST='db.local',
            USER='restore_user', PASSWORD='secret',
        )
        with TemporaryDirectory() as td:
            dump = Path(td) / 'backup.dump'
            dump.write_bytes(b'custom dump placeholder')
            calls = [SimpleNamespace(returncode=0, stderr=''), SimpleNamespace(returncode=0, stderr='')]
            with patch.object(db_backup.settings, 'DATABASES', database), patch(
                'core.db_backup.subprocess.run', side_effect=calls,
            ) as run:
                db_backup.perform_restore(dump)

        self.assertEqual(run.call_args_list[0].args[0][:2], ['pg_restore', '--list'])
        restore_command = run.call_args_list[1].args[0]
        self.assertIn('--clean', restore_command)
        self.assertIn('--if-exists', restore_command)
        self.assertEqual(run.call_args_list[1].kwargs['env']['PGPASSWORD'], 'secret')

    def test_postgres_validation_reports_missing_tool_and_invalid_dump(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from core import db_backup

        with TemporaryDirectory() as td:
            dump = Path(td) / 'bad.dump'
            dump.write_bytes(b'bad')
            with patch('core.db_backup.subprocess.run', side_effect=FileNotFoundError):
                with self.assertRaisesRegex(ValueError, 'pg_restore introuvable'):
                    db_backup._validate_pg_dump(dump)
            with patch(
                'core.db_backup.subprocess.run',
                return_value=SimpleNamespace(returncode=1, stderr='invalid archive'),
            ):
                with self.assertRaisesRegex(ValueError, 'invalid archive'):
                    db_backup._validate_pg_dump(dump)


class StatisticsScopeAndAggregationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import User

        cls.requester = User.objects.create_user(
            username='stats-requester', password='x', role='REQUESTER',
            wilaya='16', organization='CNRDPA', gender='F',
        )
        cls.client_user = User.objects.create_user(
            username='stats-genoclab-client', password='x', role='CLIENT',
            wilaya='31', organization='ESSBO', gender='M',
        )
        cls.analyst = User.objects.create_user(
            username='stats-scope-analyst', password='x', role='MEMBER')
        cls.other_analyst = User.objects.create_user(
            username='stats-scope-other', password='x', role='MEMBER')
        cls.finance = User.objects.create_user(
            username='stats-finance', password='x', role='FINANCE')
        cls.admin = User.objects.create_user(
            username='stats-platform-admin', password='x', role='PLATFORM_ADMIN')
        cls.service = Service.objects.create(
            code='STATS-SVC', name='Statistical service')

        cls.completed = Request.objects.create(
            display_id='IBT-STATS-001', title='Completed IBTIKAR',
            channel='IBTIKAR', status='COMPLETED', requester=cls.requester,
            assigned_to=cls.analyst.member_profile, service=cls.service,
            budget_amount=Decimal('1200.00'),
            service_params={'analysis_frame': 'Research'},
        )
        cls.in_progress = Request.objects.create(
            display_id='GCL-STATS-001', title='Active GENOCLAB',
            channel='GENOCLAB', status='REQUEST_CREATED', requester=cls.client_user,
            assigned_to=cls.other_analyst.member_profile, service=cls.service,
            quote_amount=Decimal('2300.00'),
            service_params={'analysis_frame': 'Teaching'},
        )
        cls.rejected = Request.objects.create(
            display_id='IBT-STATS-002', title='Rejected IBTIKAR',
            channel='IBTIKAR', status='REJECTED', requester=cls.requester,
            assigned_to=cls.other_analyst.member_profile, service=None,
            budget_amount=Decimal('500.00'), service_params={},
        )

    def test_headline_kpis_and_full_filter_matrix(self):
        from core.stats import headline_kpis

        all_kpis = headline_kpis()
        self.assertEqual(all_kpis['total'], 3)
        self.assertEqual(all_kpis['completed'], 1)
        self.assertEqual(all_kpis['rejected'], 1)
        self.assertEqual(all_kpis['in_progress'], 1)
        self.assertEqual(all_kpis['completion_rate'], 33.3)
        self.assertEqual(all_kpis['ibtikar_virtual_revenue'], 1700.0)
        self.assertEqual(all_kpis['genoclab_revenue'], 2300.0)

        filtered = headline_kpis(
            channel='IBTIKAR', service_code='STATS-SVC', status=['COMPLETED'],
            wilaya='16', organization='cnrdpa', gender='F',
            analysis_frame='Research', requester_id=self.requester.pk,
        )
        self.assertEqual(filtered['total'], 1)
        self.assertEqual(filtered['completed'], 1)

    def test_all_breakdown_dimensions_and_monthly_trend(self):
        from core.stats import (
            breakdown_by_analysis_frame, breakdown_by_gender,
            breakdown_by_organization, breakdown_by_service,
            breakdown_by_status, breakdown_by_wilaya, monthly_trend,
        )

        self.assertEqual(sum(r['count'] for r in breakdown_by_status()), 3)
        service_rows = breakdown_by_service()
        service = next(r for r in service_rows if r['key'] == 'STATS-SVC')
        self.assertEqual(service['count'], 2)
        self.assertEqual(service['ibtikar_total'], 1200.0)
        self.assertEqual(service['genoclab_total'], 2300.0)
        self.assertIn('Alger', {r['label'] for r in breakdown_by_wilaya()})
        self.assertIn('CNRDPA', {r['key'] for r in breakdown_by_organization()})
        self.assertIn('Femme', {r['label'] for r in breakdown_by_gender()})
        frames = {r['key']: r['count'] for r in breakdown_by_analysis_frame()}
        self.assertEqual(frames, {'Research': 1, 'Teaching': 1, '—': 1})
        self.assertEqual(sum(r['count'] for r in monthly_trend()), 3)

    def test_role_scopes_never_cross_tenants_or_assignments(self):
        from core.stats import stats_for_user

        requester = stats_for_user(self.requester)
        client = stats_for_user(self.client_user)
        analyst = stats_for_user(self.analyst)
        other = stats_for_user(self.other_analyst)
        finance = stats_for_user(self.finance)
        admin = stats_for_user(self.admin)

        self.assertEqual((requester['scope'], requester['kpis']['total']), ('personal', 2))
        self.assertEqual((client['scope'], client['kpis']['total']), ('personal', 1))
        self.assertEqual((analyst['scope'], analyst['kpis']['total']), ('analyst', 1))
        self.assertEqual((other['scope'], other['kpis']['total']), ('analyst', 2))
        self.assertEqual((finance['scope'], finance['kpis']['total']), ('finance', 3))
        self.assertEqual((admin['scope'], admin['kpis']['total']), ('admin', 3))
        self.assertIn('by_wilaya', admin)
        self.assertNotIn('by_wilaya', requester)

    def test_member_without_profile_fails_closed_to_empty_scope(self):
        from accounts.models import MemberProfile, User
        from core.stats import stats_for_user

        broken = User.objects.create_user(
            username='stats-member-no-profile', password='x', role='MEMBER')
        MemberProfile.objects.filter(user=broken).delete()
        self.assertEqual(stats_for_user(broken)['kpis']['total'], 0)


class QrCodeUtilityContractTests(SimpleTestCase):
    def test_generated_qr_is_a_real_png_data_url(self):
        from core.qrcode_utils import generate_qr_base64, generate_qr_data_url

        encoded = generate_qr_base64('https://example.invalid/track/?q=token')
        self.assertTrue(base64.b64decode(encoded).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(
            generate_qr_data_url('safe-data').startswith('data:image/png;base64,'))

    def test_tracking_helpers_use_canonical_query_string_routes(self):
        from types import SimpleNamespace
        from core.qrcode_utils import (
            generate_ibtikar_id_qr, generate_reception_qr,
            generate_request_tracking_qr,
        )

        token = uuid.uuid4()
        request_obj = SimpleNamespace(guest_token=token)
        expected = f'https://plagenor.invalid/track/?q={token}'
        for helper in (
            generate_request_tracking_qr, generate_ibtikar_id_qr,
            generate_reception_qr,
        ):
            with self.subTest(helper=helper.__name__), patch(
                'core.qrcode_utils.generate_qr_data_url', return_value='qr',
            ) as generate:
                self.assertEqual(helper(request_obj, 'https://plagenor.invalid'), 'qr')
                generate.assert_called_once_with(expected)

    def test_report_and_missing_token_contracts(self):
        from types import SimpleNamespace
        from core.qrcode_utils import (
            generate_ibtikar_id_qr, generate_reception_qr, generate_report_qr,
            generate_request_tracking_qr, get_tracking_info,
        )

        empty = SimpleNamespace(
            display_id='NO-TOKEN', guest_token=None, report_token=None)
        self.assertIsNone(generate_request_tracking_qr(empty))
        self.assertIsNone(generate_ibtikar_id_qr(empty))
        self.assertIsNone(generate_reception_qr(empty))
        self.assertIsNone(generate_report_qr(empty))
        self.assertEqual(get_tracking_info(empty), {
            'display_id': 'NO-TOKEN', 'guest_token': None, 'report_token': None,
            'has_tracking_qr': False, 'has_report_qr': False,
        })

        guest_token, report_token = uuid.uuid4(), uuid.uuid4()
        complete = SimpleNamespace(
            display_id='WITH-TOKENS', guest_token=guest_token,
            report_token=report_token,
        )
        with patch('core.qrcode_utils.generate_qr_data_url', side_effect=lambda url: f'qr:{url}'):
            info = get_tracking_info(complete)
            report = generate_report_qr(complete, 'https://plagenor.invalid')
        self.assertEqual(info['tracking_url'], f'/track/?q={guest_token}')
        self.assertEqual(info['report_url'], f'/report/{report_token}/')
        self.assertTrue(info['has_tracking_qr'])
        self.assertTrue(info['has_report_qr'])
        self.assertEqual(
            report, f'qr:https://plagenor.invalid/report/{report_token}/')


class QRCodeCompatibilityTests(SimpleTestCase):
    """Exercise the QR generation contract across qrcode major upgrades."""

    def test_tracking_qr_is_a_valid_png_data_url(self):
        import base64
        import io
        from PIL import Image
        from core.qrcode_utils import generate_qr_data_url

        encoded = generate_qr_data_url(
            '/track/?q=00000000-0000-0000-0000-000000000001')
        self.assertTrue(encoded.startswith('data:image/png;base64,'))
        payload = base64.b64decode(encoded.split(',', 1)[1], validate=True)
        self.assertTrue(payload.startswith(b'\x89PNG\r\n\x1a\n'))
        image = Image.open(io.BytesIO(payload))
        image.verify()
        self.assertEqual(image.format, 'PNG')

    def test_request_qr_variants_preserve_canonical_urls(self):
        import uuid
        from types import SimpleNamespace
        from unittest.mock import patch
        from core.qrcode_utils import (
            generate_ibtikar_id_qr, generate_reception_qr,
            generate_report_qr, generate_request_tracking_qr,
        )

        request_obj = SimpleNamespace(
            guest_token=uuid.UUID('00000000-0000-0000-0000-000000000001'),
            report_token=uuid.UUID('00000000-0000-0000-0000-000000000002'),
        )
        with patch('core.qrcode_utils.generate_qr_data_url',
                   side_effect=lambda value: value):
            expected_tracking = (
                'https://plagenor.example.test/track/'
                '?q=00000000-0000-0000-0000-000000000001'
            )
            self.assertEqual(
                generate_request_tracking_qr(
                    request_obj, 'https://plagenor.example.test'),
                expected_tracking,
            )
            self.assertEqual(
                generate_ibtikar_id_qr(
                    request_obj, 'https://plagenor.example.test'),
                expected_tracking,
            )
            self.assertEqual(
                generate_reception_qr(
                    request_obj, 'https://plagenor.example.test'),
                expected_tracking,
            )
            self.assertEqual(
                generate_report_qr(
                    request_obj, 'https://plagenor.example.test'),
                'https://plagenor.example.test/report/'
                '00000000-0000-0000-0000-000000000002/',
            )
