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
            # Count parameters in service_params
            if service_params:
                quantity = len([v for v in service_params.values() if v])
            config_total = config.amount * quantity
        elif config.pricing_type == 'URGENCY_SURCHARGE':
            if urgency in ['Urgent', 'Très urgent']:
                quantity = 1
                config_total = config.amount
        elif config.pricing_type == 'DISCOUNT':
            quantity = 1
            config_total = -config.amount  # Negative for discount
        
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
