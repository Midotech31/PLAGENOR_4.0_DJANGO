# core/pricing.py — PLAGENOR 4.0 Pricing Engine
# Generic pricing dispatcher driven by YAML service registry.

from __future__ import annotations

from django.db import models

MULTIPLIER_KEY_MAP = {
    'nombre_echantillons': 'nombre_echantillons',
    'sample_count': 'nombre_echantillons',
    'nb_echantillons': 'nombre_echantillons',
    'nb_samples': 'nombre_echantillons',
    'nombre_de_genes': 'nombre_de_genes',
    'gene_count': 'nombre_de_genes',
    'nb_genes': 'nombre_de_genes',
}


def _normalize_params(params: dict) -> dict:
    """Normalize parameter names using MULTIPLIER_KEY_MAP."""
    normalized = {}
    for k, v in params.items():
        canonical = MULTIPLIER_KEY_MAP.get(k, k)
        normalized[canonical] = v
    return normalized


def calculate_price(service_def: dict, service_params: dict, sample_table: list) -> dict:
    """
    Calculate price based on registry-defined pricing model.
    Returns: {pricing_model, number_of_units, unit_price, total, currency, breakdown}
    """
    if not service_def:
        raise ValueError("Service definition is missing")

    pricing = service_def.get('pricing')
    if not pricing:
        raise ValueError(f"Service {service_def.get('service_code')} has no pricing definition")

    model = pricing.get('model')
    currency = pricing.get('currency', 'DZD')

    if not model:
        raise ValueError("Pricing model not defined in registry")

    if not isinstance(sample_table, list):
        raise ValueError("Sample table must be a list")

    if model == 'per_sample_table_row_with_multiplier':
        return _price_per_row_with_multiplier(pricing, service_params or {}, sample_table, currency)

    if model == 'per_sample_fixed':
        return _price_per_sample_fixed(pricing, sample_table, currency)

    raise ValueError(f"Unsupported pricing model: {model}")


def _price_per_row_with_multiplier(pricing: dict, params: dict, samples: list, currency: str) -> dict:
    """
    Price = base_price × multiplier × number_of_samples
    base_price depends on pathogenic status, multiplier on analysis_mode/qc_level.
    """
    n = len(samples)
    if n <= 0:
        raise ValueError("At least one sample is required")

    params = _normalize_params(params)

    base_prices = pricing.get('base_price', {})
    multipliers = pricing.get('multipliers', {})

    # Determine base price
    pathogenic = bool(params.get('pathogenic', False))
    base_key = 'pathogenic' if pathogenic else 'non_pathogenic'
    base_price = int(base_prices.get(base_key, base_prices.get('default', 0)))

    # Determine multiplier key
    mult_key = (
        params.get('analysis_mode') or params.get('qc_level')
        or params.get('sequencing_mode') or params.get('drying_level')
        or params.get('primer_type')
    )

    if not mult_key and multipliers:
        mult_key = list(multipliers.keys())[0]

    multiplier = float(multipliers.get(mult_key, 1)) if mult_key else 1.0
    unit_price = int(base_price * multiplier)
    total = unit_price * n

    return {
        'pricing_model': 'per_sample_table_row_with_multiplier',
        'number_of_units': n,
        'unit_price': unit_price,
        'total': total,
        'currency': currency,
        'breakdown': {
            'base_price': base_price,
            'multiplier_key': mult_key,
            'multiplier': multiplier,
            'pathogenic': pathogenic,
            'rows_billed': n,
        },
    }


def _price_per_sample_fixed(pricing: dict, samples: list, currency: str) -> dict:
    """Fixed price per sample."""
    n = len(samples)
    if n <= 0:
        raise ValueError("At least one sample is required")

    unit_price = int(pricing.get('unit_price', 0))
    total = unit_price * n

    return {
        'pricing_model': 'per_sample_fixed',
        'number_of_units': n,
        'unit_price': unit_price,
        'total': total,
        'currency': currency,
        'breakdown': {'rows_billed': n},
    }


def format_price(amount: float, currency: str = 'DZD') -> str:
    """Format a price for display."""
    return f"{amount:,.0f} {currency}"


def calculate_cost_from_db(service, channel, sample_table=None, service_params=None, urgency='Normal'):
    """
    Calculate cost based on ServicePricing configurations from database.
    
    Args:
        service: Service model instance
        channel: 'IBTIKAR' or 'GENOCLAB'
        sample_table: List of sample dicts (optional)
        service_params: Dict of service parameters (optional)
        urgency: Urgency level for surcharge calculation
    
    Returns:
        dict with cost breakdown and total
    """
    from decimal import Decimal
    
    if not service:
        return {'error': 'Service is required', 'total': 0}
    
    # Get active pricing configs for this service
    pricing_configs = service.pricing_configs.filter(
        is_active=True
    ).filter(
        models.Q(channel=channel) | models.Q(channel='BOTH')
    ).order_by('priority', 'pk')
    
    if not pricing_configs.exists():
        # Fall back to service's base price
        base_price = service.ibtikar_price if channel == 'IBTIKAR' else service.genoclab_price
        sample_count = len([s for s in sample_table if s]) if sample_table else 1
        total = float(base_price) * sample_count
        return {
            'source': 'service_base_price',
            'base_price': float(base_price),
            'sample_count': sample_count,
            'total': total,
            'breakdown': [{
                'name': 'Prix de base',
                'type': 'BASE',
                'amount': float(base_price),
                'quantity': sample_count,
                'subtotal': total,
            }],
        }
    
    breakdown = []
    total = Decimal('0')
    sample_count = len([s for s in sample_table if s]) if sample_table else 0
    
    # First pass: calculate base costs from pricing configs
    override_applied = False
    for config in pricing_configs:
        config_total = Decimal('0')
        quantity = 1
        
        if config.pricing_type == 'BASE':
            quantity = sample_count if sample_count > 0 else 1
            config_total = config.amount * quantity
        elif config.pricing_type == 'PER_SAMPLE':
            quantity = sample_count
            config_total = config.amount * quantity
        elif config.pricing_type == 'PER_PARAMETER':
            if service_params:
                quantity = len([v for v in service_params.values() if v])
            config_total = config.amount * quantity
        elif config.pricing_type == 'URGENCY_SURCHARGE':
            if urgency in ['Urgent', 'Très urgent']:
                quantity = 1
                config_total = config.amount
        elif config.pricing_type == 'DISCOUNT':
            quantity = 1
            config_total = -config.amount
        
        # Check for override type (set)
        if config.pricing_type == 'OVERRIDE' or config.pricing_type == 'BASE' and config.amount > 0:
            # This is a total override, don't add to existing
            if not override_applied:
                total = Decimal(str(config.amount))
                override_applied = True
                breakdown.append({
                    'name': config.name,
                    'type': config.pricing_type,
                    'amount': float(config.amount),
                    'quantity': 1,
                    'subtotal': float(config.amount),
                    'is_override': True,
                })
                continue
        
        total += config_total
        breakdown.append({
            'name': config.name,
            'type': config.pricing_type,
            'amount': float(config.amount),
            'quantity': quantity,
            'subtotal': float(config_total),
        })
    
    return {
        'source': 'service_pricing_db',
        'pricing_configs_used': pricing_configs.count(),
        'sample_count': sample_count,
        'total': float(total),
        'breakdown': breakdown,
    }


def get_field_price_modifiers(service, channel='BOTH'):
    """
    Get all form fields that affect pricing for a service.
    
    Returns list of fields with pricing modifier info.
    """
    from core.models import ServiceFormField
    
    fields = service.form_fields.filter(
        affects_pricing=True,
        price_modifier_type__in=['add', 'set', 'multiply']
    ).filter(
        models.Q(channel='BOTH') | models.Q(channel=channel)
    )
    
    return list(fields)


def apply_field_price_modifiers(base_cost, service_params, modifier_fields):
    """
    Apply field-level price modifiers to a base cost.
    
    Args:
        base_cost: Decimal or float base cost
        service_params: Dict of selected field values
        modifier_fields: QuerySet of ServiceFormField with pricing modifiers
    
    Returns:
        dict with modified total and warnings
    """
    from decimal import Decimal
    
    if not modifier_fields or not service_params:
        return {'total': float(base_cost), 'warnings': [], 'modifiers_applied': []}
    
    total = Decimal(str(base_cost))
    warnings = []
    modifiers_applied = []
    
    for field in modifier_fields:
        field_value = service_params.get(field.name)
        
        # Check if this field's value triggers a price modifier
        if not field_value:
            continue
        
        # For boolean fields, any truthy value triggers
        # For select/multiselect, check if value is in options
        should_apply = False
        
        if field.field_type in ['boolean', 'checkbox']:
            should_apply = bool(field_value)
        elif field.field_type in ['select', 'multiselect', 'dropdown']:
            # Check if selected value triggers modifier
            choices = field.get_choices() or []
            if isinstance(field_value, list):
                should_apply = any(str(v) in choices for v in field_value)
            else:
                should_apply = str(field_value) in choices
        else:
            # For text/number fields, apply if has value
            should_apply = bool(field_value)
        
        if not should_apply or not field.price_modifier_value:
            continue
        
        modifier_value = Decimal(str(field.price_modifier_value))
        modifier_type = field.price_modifier_type
        
        if modifier_type == 'add':
            total += modifier_value
            modifiers_applied.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'add',
                'value': float(modifier_value),
            })
        elif modifier_type == 'set':
            total = modifier_value
            modifiers_applied.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'set',
                'value': float(modifier_value),
            })
        elif modifier_type == 'multiply':
            total *= modifier_value
            modifiers_applied.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'multiply',
                'value': float(modifier_value),
            })
        
        # Add warning message
        if field.condition_note_fr or field.condition_note_en:
            warnings.append({
                'field': field.name,
                'note_fr': field.condition_note_fr,
                'note_en': field.condition_note_en,
            })
    
    return {
        'total': float(total),
        'warnings': warnings,
        'modifiers_applied': modifiers_applied,
    }
