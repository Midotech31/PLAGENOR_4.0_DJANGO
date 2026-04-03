"""Tests for conditional logic in forms and pricing."""
from django.test import TestCase
from unittest.mock import MagicMock, patch

from core.pricing import apply_field_price_modifiers


class TestServiceFormFieldConditionalLogic(TestCase):
    """Test ServiceFormField conditional logic functionality."""
    
    def test_conditional_logic_json_field(self):
        """Test conditional_logic JSONField can store rules."""
        from core.models import ServiceFormField
        
        field = ServiceFormField(
            name='premium_option',
            field_type='select',
            conditional_logic=[
                {
                    'trigger_field': 'service_type',
                    'trigger_value': 'premium',
                    'actions': ['show', 'make_required']
                }
            ]
        )
        
        self.assertEqual(len(field.conditional_logic), 1)
        self.assertEqual(field.conditional_logic[0]['trigger_field'], 'service_type')
    
    def test_conditional_logic_show_action(self):
        """Test 'show' action in conditional logic."""
        from core.models import ServiceFormField
        
        field = ServiceFormField(
            name='rush_delivery',
            field_type='boolean',
            conditional_logic=[
                {
                    'trigger_field': 'service_type',
                    'trigger_value': 'express',
                    'actions': ['show']
                }
            ]
        )
        
        actions = field.conditional_logic[0]['actions']
        self.assertIn('show', actions)
    
    def test_multiple_conditional_rules(self):
        """Test multiple conditional rules on a field."""
        from core.models import ServiceFormField
        
        field = ServiceFormField(
            name='advanced_options',
            field_type='multiselect',
            conditional_logic=[
                {
                    'trigger_field': 'service_type',
                    'trigger_value': 'premium',
                    'actions': ['show']
                },
                {
                    'trigger_field': 'member_level',
                    'trigger_value': 'gold',
                    'actions': ['show']
                }
            ]
        )
        
        self.assertEqual(len(field.conditional_logic), 2)


class TestOptionPricing(TestCase):
    """Test option-level pricing for multi-select fields."""
    
    def test_option_pricing_json_field(self):
        """Test option_pricing JSONField can store per-option prices."""
        from core.models import ServiceFormField
        
        field = ServiceFormField(
            name='addons',
            field_type='multiselect',
            option_pricing={
                'premium_support': 500,
                'priority_queue': 300,
                'extended_warranty': 200,
            }
        )
        
        self.assertEqual(field.option_pricing['premium_support'], 500)
        self.assertEqual(field.option_pricing['priority_queue'], 300)


class TestConditionalPricing(TestCase):
    """Test conditional pricing behavior."""
    
    def test_hidden_field_excluded_from_pricing(self):
        """Test hidden fields are excluded from price calculation."""
        hidden_field = MagicMock()
        hidden_field.name = 'hidden_option'
        hidden_field.field_type = 'select'
        hidden_field.price_modifier_type = 'add'
        hidden_field.price_modifier_value = 500
        hidden_field.get_choices.return_value = ['hidden_option']
        hidden_field.get_label.return_value = 'Hidden'
        
        result = apply_field_price_modifiers(
            base_cost=1000,
            service_params={'hidden_option': 'selected'},
            modifier_fields=[hidden_field]
        )
        
        self.assertEqual(result['total'], 1000)
        self.assertEqual(len(result['modifiers_applied']), 0)
    
    def test_visible_field_included_in_pricing(self):
        """Test visible fields are included in price calculation."""
        visible_field = MagicMock()
        visible_field.name = 'visible_option'
        visible_field.field_type = 'boolean'
        visible_field.price_modifier_type = 'add'
        visible_field.price_modifier_value = 200
        visible_field.get_choices.return_value = []
        visible_field.get_label.return_value = 'Visible'
        
        result = apply_field_price_modifiers(
            base_cost=1000,
            service_params={'visible_option': True},
            modifier_fields=[visible_field]
        )
        
        self.assertEqual(result['total'], 1200)
        self.assertEqual(len(result['modifiers_applied']), 1)
    
    def test_field_modifier_activation_and_revert(self):
        """Test price modifier activation based on field selection."""
        field = MagicMock()
        field.name = 'express_service'
        field.field_type = 'boolean'
        field.price_modifier_type = 'multiply'
        field.price_modifier_value = 1.5
        field.get_choices.return_value = []
        field.get_label.return_value = 'Express'
        
        result_without = apply_field_price_modifiers(
            base_cost=1000,
            service_params={'express_service': False},
            modifier_fields=[field]
        )
        
        result_with = apply_field_price_modifiers(
            base_cost=1000,
            service_params={'express_service': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result_without['total'], 1000)
        self.assertEqual(result_with['total'], 1500)
    
    def test_multiply_modifier(self):
        """Test multiply price modifier."""
        field = MagicMock()
        field.name = 'rush_order'
        field.field_type = 'boolean'
        field.price_modifier_type = 'multiply'
        field.price_modifier_value = 1.5
        field.get_choices.return_value = []
        field.get_label.return_value = 'Rush Order'
        
        result = apply_field_price_modifiers(
            base_cost=100.00,
            service_params={'rush_order': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 150.00)
    
    def test_set_modifier(self):
        """Test set price modifier."""
        field = MagicMock()
        field.name = 'flat_rate'
        field.field_type = 'boolean'
        field.price_modifier_type = 'set'
        field.price_modifier_value = 750.00
        field.get_choices.return_value = []
        field.get_label.return_value = 'Flat Rate'
        
        result = apply_field_price_modifiers(
            base_cost=500.00,
            service_params={'flat_rate': True},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 750.00)
    
    def test_modifier_not_applied_when_field_not_selected(self):
        """Test modifier is not applied when field value doesn't match."""
        field = MagicMock()
        field.name = 'premium_option'
        field.field_type = 'select'
        field.price_modifier_type = 'add'
        field.price_modifier_value = 100.00
        field.get_choices.return_value = ['premium_option']
        field.get_label.return_value = 'Premium Option'
        
        result = apply_field_price_modifiers(
            base_cost=500.00,
            service_params={'premium_option': 'not_selected'},
            modifier_fields=[field]
        )
        
        self.assertEqual(result['total'], 500.00)
        self.assertEqual(len(result['modifiers_applied']), 0)
