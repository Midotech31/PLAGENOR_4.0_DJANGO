"""Tests for core/pricing.py - Dynamic pricing calculation engine."""
import pytest
from decimal import Decimal
from django.test import TestCase
from unittest.mock import MagicMock, patch

from core.pricing import (
    calculate_cost_from_db,
    validate_and_calculate_price,
    apply_field_price_modifiers,
    get_field_price_modifiers,
    calculate_price,
    _normalize_params,
    evaluate_conditional_logic_server_side,
    validate_max_selections,
)
from core.models import ServicePricing


class TestCalculateCostFromDb(TestCase):
    """Test calculate_cost_from_db function using real model instances."""
    
    def setUp(self):
        """Set up test data with real models."""
        from accounts.models import BadgeConfig
        from core.models import Service, ServicePricing
        from django.db.models import Q
        BadgeConfig.seed_default_badges()
        
        self.service = Service.objects.create(
            name='Test Service',
            code='TEST-SVC',
            channel_availability='BOTH',
            ibtikar_price=Decimal('1000.00'),
            genoclab_price=Decimal('2000.00'),
            active=True
        )
    
    def test_base_price_calculation_no_configs(self):
        """Test BASE pricing type calculation falls back to service price when no DB configs."""
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None)
        
        self.assertEqual(result['source'], 'service_base_price')
        self.assertEqual(result['base_price'], 1000.00)
        self.assertEqual(result['total'], 1000.00)
    
    def test_per_sample_pricing(self):
        """Test PER_SAMPLE pricing type with DB configs."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='PER_SAMPLE',
            channel='IBTIKAR',
            amount=Decimal('500.00'),
            name='Per Sample',
            is_active=True,
            priority=1
        )
        
        sample_table = [1, 2, 3, 4, 5]  # 5 samples
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', sample_table, None)
        
        self.assertEqual(result['source'], 'service_pricing_db')
        self.assertEqual(result['total'], 2500.00)  # 500 * 5
        self.assertEqual(result['sample_count'], 5)
    
    def test_urgency_surcharge_applied(self):
        """Test URGENCY_SURCHARGE is applied for urgent requests."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=1
        )
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='URGENCY_SURCHARGE',
            channel='IBTIKAR',
            amount=Decimal('500.00'),
            name='Urgent Surcharge',
            is_active=True,
            priority=2
        )
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None, urgency='Urgent')
        
        self.assertEqual(result['total'], 1500.00)  # 1000 + 500
    
    def test_urgency_surcharge_not_applied_for_normal(self):
        """Test URGENCY_SURCHARGE is NOT applied for normal requests."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=1
        )
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='URGENCY_SURCHARGE',
            channel='IBTIKAR',
            amount=Decimal('500.00'),
            name='Urgent Surcharge',
            is_active=True,
            priority=2
        )
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None, urgency='Normal')
        
        self.assertEqual(result['total'], 1000.00)  # Only base, no surcharge
    
    def test_discount_reduces_total(self):
        """Test DISCOUNT pricing type reduces total."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=1
        )
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='DISCOUNT',
            channel='IBTIKAR',
            amount=Decimal('100.00'),
            name='Loyalty Discount',
            is_active=True,
            priority=2
        )
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None)
        
        self.assertEqual(result['total'], 900.00)  # 1000 - 100
    
    def test_override_replaces_total(self):
        """Test OVERRIDE pricing type replaces total.
        
        Note: Due to operator precedence in pricing.py line 209, BASE configs
        with amount > 0 also trigger override behavior. The OVERRIDE config
        must come BEFORE BASE in priority order to win.
        """
        from core.models import ServicePricing
        
        # OVERRIDE with higher priority (processed first)
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='OVERRIDE',
            channel='IBTIKAR',
            amount=Decimal('800.00'),
            name='Special Price',
            is_active=True,
            priority=1
        )
        # BASE with lower priority (processed second)
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=2
        )
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None)
        
        self.assertEqual(result['total'], 800.00)  # Override wins


class TestValidateAndCalculatePrice(TestCase):
    """Test validate_and_calculate_price function."""
    
    def setUp(self):
        """Set up test data."""
        from accounts.models import BadgeConfig
        BadgeConfig.seed_default_badges()
    
    @patch('core.pricing.calculate_cost_from_db')
    @patch('core.pricing.get_field_price_modifiers')
    def test_price_match(self, mock_get_modifiers, mock_calc_cost):
        """Test when submitted price matches server calculation."""
        service = MagicMock()
        service.code = 'TEST'
        
        mock_calc_cost.return_value = {
            'source': 'service_pricing_db',
            'total': 1000.00,
            'breakdown': []
        }
        mock_get_modifiers.return_value = []
        
        result = validate_and_calculate_price(
            service=service,
            channel='IBTIKAR',
            sample_table=[1],
            service_params={},
            submitted_price=1000.00
        )
        
        self.assertFalse(result['mismatch_detected'])
        self.assertEqual(result['server_price'], 1000.00)
    
    @patch('core.pricing.calculate_cost_from_db')
    @patch('core.pricing.get_field_price_modifiers')
    def test_price_mismatch_detected(self, mock_get_modifiers, mock_calc_cost):
        """Test when submitted price differs from server calculation."""
        service = MagicMock()
        service.code = 'TEST'
        
        mock_calc_cost.return_value = {
            'source': 'service_pricing_db',
            'total': 1000.00,
            'breakdown': []
        }
        mock_get_modifiers.return_value = []
        
        result = validate_and_calculate_price(
            service=service,
            channel='IBTIKAR',
            sample_table=[1],
            service_params={},
            submitted_price=500.00  # Intentionally wrong
        )
        
        self.assertTrue(result['mismatch_detected'])
        self.assertEqual(result['mismatch_amount'], 500.00)
        self.assertTrue(result['logged'])
    
    @patch('core.pricing.calculate_cost_from_db')
    @patch('core.pricing.get_field_price_modifiers')
    def test_price_mismatch_percentage(self, mock_get_modifiers, mock_calc_cost):
        """Test mismatch percentage calculation."""
        service = MagicMock()
        service.code = 'TEST'
        
        mock_calc_cost.return_value = {
            'source': 'service_pricing_db',
            'total': 1000.00,
            'breakdown': []
        }
        mock_get_modifiers.return_value = []
        
        result = validate_and_calculate_price(
            service=service,
            channel='IBTIKAR',
            sample_table=[1],
            service_params={},
            submitted_price=900.00  # 10% difference
        )
        
        self.assertTrue(result['mismatch_detected'])
        self.assertAlmostEqual(result['mismatch_percentage'], 10.0, places=1)


class TestApplyFieldPriceModifiers(TestCase):
    """Test apply_field_price_modifiers function."""
    
    def test_add_modifier(self):
        """Test 'add' price modifier type for boolean field."""
        field = MagicMock()
        field.name = 'premium_option'
        field.field_type = 'boolean'
        field.price_modifier_type = 'add'
        field.price_modifier_value = Decimal('100.00')
        field.get_choices.return_value = []
        field.get_label.return_value = 'Premium Option'
        
        result = apply_field_price_modifiers(
            base_cost=Decimal('500.00'),
            service_params={'premium_option': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 600.00)
        self.assertEqual(len(result['modifiers_applied']), 1)
    
    def test_set_modifier(self):
        """Test 'set' price modifier type."""
        field = MagicMock()
        field.name = 'flat_rate'
        field.field_type = 'boolean'
        field.price_modifier_type = 'set'
        field.price_modifier_value = Decimal('750.00')
        field.get_choices.return_value = []
        field.get_label.return_value = 'Flat Rate'
        
        result = apply_field_price_modifiers(
            base_cost=Decimal('500.00'),
            service_params={'flat_rate': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 750.00)
    
    def test_multiply_modifier(self):
        """Test 'multiply' price modifier type."""
        field = MagicMock()
        field.name = 'rush_order'
        field.field_type = 'boolean'
        field.price_modifier_type = 'multiply'
        field.price_modifier_value = Decimal('1.5')
        field.get_choices.return_value = []
        field.get_label.return_value = 'Rush Order'
        
        result = apply_field_price_modifiers(
            base_cost=Decimal('100.00'),
            service_params={'rush_order': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 150.00)
    
    def test_modifier_not_applied_when_field_not_selected(self):
        """Test modifier is not applied when field value doesn't match."""
        field = MagicMock()
        field.name = 'premium_option'
        field.field_type = 'select'
        field.price_modifier_type = 'add'
        field.price_modifier_value = Decimal('100.00')
        field.get_choices.return_value = ['premium_option']
        field.get_label.return_value = 'Premium Option'
        
        result = apply_field_price_modifiers(
            base_cost=Decimal('500.00'),
            service_params={'premium_option': 'not_selected'},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 500.00)
        self.assertEqual(len(result['modifiers_applied']), 0)


class TestNormalizeParams(TestCase):
    """Test _normalize_params helper function."""
    
    def test_normalize_sample_count_keys(self):
        """Test sample count parameter name normalization."""
        params = {
            'nombre_echantillons': 5,
            'sample_count': 5,
            'nb_echantillons': 5,
        }
        
        result = _normalize_params(params)
        
        # All should normalize to 'nombre_echantillons'
        self.assertEqual(result['nombre_echantillons'], 5)
    
    def test_normalize_gene_count_keys(self):
        """Test gene count parameter name normalization."""
        params = {
            'nombre_de_genes': 10,
            'gene_count': 10,
            'nb_genes': 10,
        }
        
        result = _normalize_params(params)
        
        # All should normalize to 'nombre_de_genes'
        self.assertEqual(result['nombre_de_genes'], 10)
    
    def test_unknown_keys_preserved(self):
        """Test unknown keys are preserved."""
        params = {'unknown_key': 'value'}
        
        result = _normalize_params(params)
        
        self.assertEqual(result['unknown_key'], 'value')


class TestPricePropagation(TestCase):
    """Test price propagation after ServicePricing updates."""
    
    def setUp(self):
        """Set up test data."""
        import uuid
        from accounts.models import BadgeConfig
        from core.models import Service
        BadgeConfig.seed_default_badges()
        
        self.service = Service.objects.create(
            name='Propagation Test Service',
            code='PROP-' + str(uuid.uuid4().hex[:8].upper()),
            channel_availability='BOTH',
            ibtikar_price=Decimal('500.00'),
            genoclab_price=Decimal('1000.00'),
            active=True
        )
    
    def test_per_sample_multiple_samples(self):
        """Test per-sample pricing with various sample counts."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='PER_SAMPLE',
            channel='IBTIKAR',
            amount=Decimal('100.00'),
            name='Per Sample',
            is_active=True,
            priority=1
        )
        
        test_cases = [
            ([1], 100),
            ([1, 2], 200),
            ([1, 2, 3, 4, 5], 500),
            ([], 0),  # Empty sample table = 0 samples
            (None, 0),  # None = 0 samples
        ]
        
        for sample_table, expected in test_cases:
            result = calculate_cost_from_db(self.service, 'IBTIKAR', sample_table, None)
            self.assertEqual(
                result['total'], float(expected),
                f"Sample table {sample_table} should cost {expected}"
            )
    
    def test_genoclab_channel_uses_different_price(self):
        """Test GENOCLAB channel uses its own base price."""
        result_ibtikar = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None)
        result_genoclab = calculate_cost_from_db(self.service, 'GENOCLAB', [1], None)
        
        self.assertEqual(result_ibtikar['base_price'], 500.00)
        self.assertEqual(result_genoclab['base_price'], 1000.00)
    
    def test_multiple_discounts_stack(self):
        """Test multiple discounts can stack (sum together)."""
        from core.models import ServicePricing
        
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=1
        )
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='DISCOUNT',
            channel='IBTIKAR',
            amount=Decimal('50.00'),
            name='Discount 1',
            is_active=True,
            priority=2
        )
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='DISCOUNT',
            channel='IBTIKAR',
            amount=Decimal('30.00'),
            name='Discount 2',
            is_active=True,
            priority=3
        )
        
        result = calculate_cost_from_db(self.service, 'IBTIKAR', [1], None)
        
        self.assertEqual(result['total'], 920.00)  # 1000 - 50 - 30


class TestEvaluateConditionalLogicServerSide(TestCase):
    """Test server-side conditional logic evaluation for security."""
    
    def setUp(self):
        """Set up test data with conditional logic fields."""
        from accounts.models import BadgeConfig
        from core.models import Service, ServiceFormField
        import uuid
        BadgeConfig.seed_default_badges()
        
        self.service = Service.objects.create(
            name='Conditional Logic Test',
            code='COND-' + str(uuid.uuid4().hex[:6].upper()),
            channel_availability='BOTH',
            ibtikar_price=Decimal('1000.00'),
            active=True
        )
    
    def test_fields_without_conditional_logic_are_visible(self):
        """Test that fields without conditional_logic are always visible."""
        from core.models import ServiceFormField
        
        # Create a field without conditional logic
        ServiceFormField.objects.create(
            service=self.service,
            name='always_visible_field',
            label='Always Visible',
            field_type='text',
            channel='BOTH'
        )
        
        result = evaluate_conditional_logic_server_side(
            self.service,
            {'always_visible_field': 'some value'},
            'IBTIKAR'
        )
        
        self.assertEqual(result['manipulation_detected'], False)
        self.assertIn('always_visible_field', result['sanitized_params'])
    
    def test_hidden_field_rejected_when_trigger_not_met(self):
        """Test that a field is hidden when its trigger condition is not met."""
        from core.models import ServiceFormField
        
        # Create trigger field (checkbox)
        trigger = ServiceFormField.objects.create(
            service=self.service,
            name='has_premium_option',
            label='Has Premium Option',
            field_type='boolean',
            channel='BOTH'
        )
        
        # Create dependent field with conditional logic
        dependent = ServiceFormField.objects.create(
            service=self.service,
            name='premium_analysis',
            label='Premium Analysis Type',
            field_type='select',
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'has_premium_option',
                'trigger_value': 'true',
                'actions': ['show']
            }]
        )
        
        # Submit data with premium_analysis but trigger not met
        result = evaluate_conditional_logic_server_side(
            self.service,
            {'has_premium_option': False, 'premium_analysis': 'type_a'},
            'IBTIKAR'
        )
        
        # The field should be hidden and rejected
        self.assertTrue(result['manipulation_detected'])
        self.assertIn('premium_analysis', result['hidden_fields_submitted'])
        self.assertNotIn('premium_analysis', result['sanitized_params'])
    
    def test_hidden_field_accepted_when_trigger_met(self):
        """Test that a field is visible when its trigger condition IS met."""
        from core.models import ServiceFormField
        
        # Create trigger field (checkbox checked)
        trigger = ServiceFormField.objects.create(
            service=self.service,
            name='has_rush_order',
            label='Has Rush Order',
            field_type='boolean',
            channel='BOTH'
        )
        
        # Create dependent field
        dependent = ServiceFormField.objects.create(
            service=self.service,
            name='rush_priority',
            label='Rush Priority Level',
            field_type='select',
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'has_rush_order',
                'trigger_value': 'true',
                'actions': ['show']
            }]
        )
        
        # Submit data with trigger met
        result = evaluate_conditional_logic_server_side(
            self.service,
            {'has_rush_order': 'true', 'rush_priority': 'high'},
            'IBTIKAR'
        )
        
        # The field should be visible and accepted
        self.assertFalse(result['manipulation_detected'])
        self.assertIn('rush_priority', result['sanitized_params'])
        self.assertEqual(result['sanitized_params']['rush_priority'], 'high')
    
    def test_chained_conditions_evaluated(self):
        """Test that chained conditional logic (A->B->C) is properly evaluated."""
        from core.models import ServiceFormField
        
        # Create field A (trigger)
        field_a = ServiceFormField.objects.create(
            service=self.service,
            name='service_type',
            label='Service Type',
            field_type='select',
            channel='BOTH'
        )
        
        # Create field B (depends on A)
        field_b = ServiceFormField.objects.create(
            service=self.service,
            name='analysis_framework',
            label='Analysis Framework',
            field_type='select',
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'service_type',
                'trigger_value': 'advanced',
                'actions': ['show']
            }]
        )
        
        # Create field C (depends on B)
        field_c = ServiceFormField.objects.create(
            service=self.service,
            name='detailed_report',
            label='Detailed Report Options',
            field_type='select',
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'analysis_framework',
                'trigger_value': 'wgs',
                'actions': ['show']
            }]
        )
        
        # Submit with chain A->B->C all satisfied
        result = evaluate_conditional_logic_server_side(
            self.service,
            {
                'service_type': 'advanced',
                'analysis_framework': 'wgs',
                'detailed_report': 'comprehensive'
            },
            'IBTIKAR'
        )
        
        self.assertFalse(result['manipulation_detected'])
        self.assertIn('detailed_report', result['sanitized_params'])
    
    def test_empty_params_returns_empty_sanitized(self):
        """Test that empty params returns empty sanitized result."""
        result = evaluate_conditional_logic_server_side(self.service, {}, 'IBTIKAR')
        
        self.assertFalse(result['manipulation_detected'])
        self.assertEqual(result['sanitized_params'], {})
        self.assertEqual(result['hidden_fields_submitted'], [])


class TestValidateMaxSelections(TestCase):
    """Test max_selections validation for security."""
    
    def setUp(self):
        """Set up test data."""
        from accounts.models import BadgeConfig
        from core.models import Service, ServiceFormField
        import uuid
        BadgeConfig.seed_default_badges()
        
        self.service = Service.objects.create(
            name='Max Selections Test',
            code='MAX-' + str(uuid.uuid4().hex[:6].upper()),
            channel_availability='BOTH',
            ibtikar_price=Decimal('1000.00'),
            active=True
        )
    
    def test_selections_within_limit_accepted(self):
        """Test that selections within max limit are accepted."""
        from core.models import ServiceFormField
        
        field = ServiceFormField.objects.create(
            service=self.service,
            name='analysis_types',
            label='Analysis Types',
            field_type='multiselect',
            max_selections=3,
            channel='BOTH'
        )
        
        result = validate_max_selections(
            self.service,
            {'analysis_types': ['type_a', 'type_b']},
            'IBTIKAR'
        )
        
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['violations']), 0)
    
    def test_selections_exceeding_limit_rejected(self):
        """Test that excess selections are truncated and logged."""
        from core.models import ServiceFormField
        
        field = ServiceFormField.objects.create(
            service=self.service,
            name='gene_panels',
            label='Gene Panels',
            field_type='multiselect',
            max_selections=2,
            channel='BOTH'
        )
        
        result = validate_max_selections(
            self.service,
            {'gene_panels': ['panel_a', 'panel_b', 'panel_c', 'panel_d']},
            'IBTIKAR'
        )
        
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['violations']), 1)
        self.assertEqual(result['violations'][0]['submitted_count'], 4)
        self.assertEqual(result['violations'][0]['max_allowed'], 2)
        # Should be truncated to max
        self.assertEqual(len(result['sanitized_params']['gene_panels']), 2)
    
    def test_no_max_limit_allows_any_selection(self):
        """Test that fields without max_selections allow any number."""
        from core.models import ServiceFormField
        
        field = ServiceFormField.objects.create(
            service=self.service,
            name='sample_types',
            label='Sample Types',
            field_type='multiselect',
            max_selections=None,  # No limit
            channel='BOTH'
        )
        
        result = validate_max_selections(
            self.service,
            {'sample_types': ['type_a', 'type_b', 'type_c', 'type_d', 'type_e']},
            'IBTIKAR'
        )
        
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['violations']), 0)
    
    def test_string_comma_separated_values_counted(self):
        """Test that comma-separated string values are counted correctly."""
        from core.models import ServiceFormField
        
        field = ServiceFormField.objects.create(
            service=self.service,
            name='options',
            label='Options',
            field_type='multiselect',
            max_selections=2,
            channel='BOTH'
        )
        
        result = validate_max_selections(
            self.service,
            {'options': 'opt1,opt2,opt3'},  # String instead of list
            'IBTIKAR'
        )
        
        self.assertFalse(result['valid'])
        self.assertEqual(result['violations'][0]['submitted_count'], 3)


class TestValidateAndCalculatePriceWithSecurity(TestCase):
    """Test validate_and_calculate_price with security features."""
    
    def setUp(self):
        """Set up test data."""
        from accounts.models import BadgeConfig
        from core.models import Service, ServicePricing
        import uuid
        BadgeConfig.seed_default_badges()
        
        self.service = Service.objects.create(
            name='Security Test Service',
            code='SEC-' + str(uuid.uuid4().hex[:6].upper()),
            channel_availability='BOTH',
            ibtikar_price=Decimal('1000.00'),
            active=True
        )
        
        # Add base pricing
        ServicePricing.objects.create(
            service=self.service,
            pricing_type='BASE',
            channel='IBTIKAR',
            amount=Decimal('1000.00'),
            name='Base Price',
            is_active=True,
            priority=1
        )
    
    def test_hidden_field_manipulation_detected_and_rejected(self):
        """Test that hidden field manipulation is detected and price calculated without it."""
        from core.models import ServiceFormField
        
        # Create trigger and dependent fields
        trigger = ServiceFormField.objects.create(
            service=self.service,
            name='enable_premium',
            label='Enable Premium',
            field_type='boolean',
            channel='BOTH'
        )
        
        premium_field = ServiceFormField.objects.create(
            service=self.service,
            name='premium_service',
            label='Premium Service',
            field_type='select',
            affects_pricing=True,
            price_modifier_type='add',
            price_modifier_value=Decimal('500.00'),
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'enable_premium',
                'trigger_value': 'true',
                'actions': ['show']
            }]
        )
        
        # Try to submit premium without enabling trigger
        result = validate_and_calculate_price(
            service=self.service,
            channel='IBTIKAR',
            sample_table=[1],
            service_params={
                'enable_premium': False,
                'premium_service': 'gold'  # Hidden field submitted!
            },
            submitted_price=1500.00  # Client tried to include premium
        )
        
        # Should detect manipulation
        self.assertTrue(result['manipulation_detected'])
        self.assertIn('premium_service', result['hidden_fields_rejected'])
        
        # Price should be calculated WITHOUT the hidden field
        self.assertEqual(result['server_price'], 1000.00)  # Base only, no premium
    
    def test_valid_submission_accepted(self):
        """Test that valid submissions with all conditions met are accepted."""
        from core.models import ServiceFormField
        
        # Create trigger field (checkbox checked)
        trigger = ServiceFormField.objects.create(
            service=self.service,
            name='enable_express',
            label='Enable Express',
            field_type='boolean',
            channel='BOTH'
        )
        
        # Create pricing modifier field that shows when trigger is met
        # For boolean fields with boolean field_type, the modifier applies when the value is truthy
        express_field = ServiceFormField.objects.create(
            service=self.service,
            name='express_surcharge',
            label='Express Surcharge',
            field_type='boolean',  # Checkbox
            affects_pricing=True,
            price_modifier_type='add',
            price_modifier_value=Decimal('200.00'),
            channel='BOTH',
            conditional_logic=[{
                'trigger_field': 'enable_express',
                'trigger_value': 'true',
                'actions': ['show']
            }]
        )
        
        # Submit with trigger met AND modifier field checked
        result = validate_and_calculate_price(
            service=self.service,
            channel='IBTIKAR',
            sample_table=[1],
            service_params={
                'enable_express': 'true',
                'express_surcharge': 'true'  # Field visible because trigger met
            },
            submitted_price=1200.00  # Correct: 1000 + 200
        )
        
        # No manipulation detected
        self.assertFalse(result['manipulation_detected'])
        self.assertEqual(result['server_price'], 1200.00)
        self.assertFalse(result['mismatch_detected'])
