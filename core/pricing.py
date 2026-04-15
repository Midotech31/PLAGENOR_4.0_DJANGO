"""
Pricing engine for PLAGENOR 4.0.

Workflow map (high-level):
- Recalculate every request price server-side from ServicePricing + dynamic field modifiers.
- Sanitize conditional form fields and enforce max selections before pricing.
- Keep audit-friendly mismatch details when submitted client price differs.
"""

# core/pricing.py — PLAGENOR 4.0 Pricing Engine
# Generic pricing dispatcher driven by ServicePricing database model.

from __future__ import annotations

import logging
from decimal import Decimal
from django.db import models

logger = logging.getLogger('plagenor.pricing')

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
    Price calculation with proper order of operations:
    
    CORRECT ORDER:
    1. Per-sample supplements (e.g., pathogen supplement) added to base
    2. Multiply by number of samples
    3. Apply analysis mode multiplier (e.g., Triplicata ×2.6)
    
    Formula: (Base + Supplements) × Sample_Count × Multiplier = Total
    
    Example: (2500 + 1500) × 5 × 2.8 = 56,000 DA
    """
    n = len(samples)
    if n <= 0:
        raise ValueError("At least one sample is required")

    params = _normalize_params(params)

    base_prices = pricing.get('base_price', {})
    multipliers = pricing.get('multipliers', {})

    # Step 1: Determine base price per sample
    pathogenic = bool(params.get('pathogenic', False))
    base_key = 'pathogenic' if pathogenic else 'non_pathogenic'
    base_price = int(base_prices.get(base_key, base_prices.get('default', 0)))

    # Step 2: Calculate per-sample supplements (BEFORE sample count and multiplier)
    per_sample_supplements = 0
    supplements_breakdown = []
    
    # Check for supplement fields in params (these add to per-sample price)
    # Common supplement field names: 'pathogen_supplement', 'isolate_supplement', etc.
    supplement_fields = [
        'pathogen_supplement', 'isolate_supplement', 'supplement',
        'pathogenic_supplement', 'urgent_supplement'
    ]
    
    for field_name in supplement_fields:
        if field_name in params and params[field_name]:
            try:
                supplement_value = float(params[field_name])
                if supplement_value > 0:
                    per_sample_supplements += supplement_value
                    supplements_breakdown.append({
                        'field': field_name,
                        'amount': supplement_value,
                    })
            except (ValueError, TypeError):
                pass
    
    # Also check for boolean fields that indicate supplements
    # e.g., 'is_pathogen' = True might add a fixed supplement
    if params.get('is_pathogen') or params.get('pathogenic_isolate'):
        # Look up supplement amount from pricing config
        pathogen_supplement = pricing.get('pathogen_supplement', 0)
        if pathogen_supplement > 0:
            per_sample_supplements += float(pathogen_supplement)
            supplements_breakdown.append({
                'field': 'pathogenic_isolate',
                'amount': float(pathogen_supplement),
            })

    # Step 3: Calculate per-sample total (base + supplements)
    per_sample_total = base_price + per_sample_supplements

    # Step 4: Determine analysis mode multiplier
    mult_key = (
        params.get('analysis_mode') or params.get('qc_level')
        or params.get('sequencing_mode') or params.get('drying_level')
        or params.get('primer_type')
    )

    if not mult_key and multipliers:
        mult_key = list(multipliers.keys())[0]

    multiplier = float(multipliers.get(mult_key, 1)) if mult_key else 1.0

    # Step 5: Calculate final total
    # Order: (Base + Supplements) × Sample_Count × Multiplier
    subtotal_before_multiplier = per_sample_total * n
    total = int(subtotal_before_multiplier * multiplier)

    return {
        'pricing_model': 'per_sample_table_row_with_multiplier',
        'number_of_units': n,
        'base_price': base_price,
        'per_sample_supplements': per_sample_supplements,
        'per_sample_total': per_sample_total,
        'unit_price': int(per_sample_total * multiplier),  # Display price per sample after all calcs
        'total': total,
        'currency': currency,
        'breakdown': {
            'base_price': base_price,
            'per_sample_supplements': per_sample_supplements,
            'supplements_breakdown': supplements_breakdown,
            'per_sample_total': per_sample_total,
            'sample_count': n,
            'subtotal_before_multiplier': subtotal_before_multiplier,
            'multiplier_key': mult_key,
            'multiplier': multiplier,
            'pathogenic': pathogenic,
            'rows_billed': n,
            'calculation_formula': f'({base_price} + {per_sample_supplements}) × {n} × {multiplier} = {total}',
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
    
    CORRECT PRICING ORDER:
    1. Extract per-sample supplements from form fields (additions to base price per sample)
    2. Calculate: (Base Price + Per-Sample Supplements) × Sample Count
    3. Apply analysis mode multipliers (e.g., Triplicata ×2.6)
    4. Apply total-level modifiers (surcharges, discounts to final total)
    
    Example: (2500 + 1500) × 5 × 2.8 = 56,000 DA
             │     │      │   │
             │     │      │   └── Analysis multiplier (from option_pricing)
             │     │      └────── Sample count
             │     └───────────── Per-sample supplement (pathogen)
             └─────────────────── Base price per sample
    
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
    
    sample_count = len([s for s in sample_table if s]) if sample_table else 0
    
    # Step 1: Extract per-sample supplements from form fields
    # These are added to the base price BEFORE sample count and multiplier
    per_sample_supplements = Decimal('0')
    supplements_breakdown = []
    
    if service_params:
        # Look for fields with per-sample price modifiers
        from core.models import ServiceFormField
        per_sample_fields = service.form_fields.filter(
            affects_pricing=True,
            price_modifier_type='add',
            price_modifier_scope='per_sample',
        ).filter(
            models.Q(channel='BOTH') | models.Q(channel=channel)
        )
        
        for field in per_sample_fields:
            field_value = service_params.get(field.name) or service_params.get(f'param_{field.name}')
            if field_value:
                # Check if this field should apply (boolean fields)
                should_apply = False
                if field.field_type in ['boolean', 'checkbox']:
                    should_apply = bool(field_value)
                elif field.field_type in ['select', 'multiselect', 'dropdown']:
                    choices = field.get_choices() or []
                    if isinstance(field_value, list):
                        should_apply = any(str(v) in choices for v in field_value)
                    else:
                        should_apply = str(field_value) in choices
                else:
                    should_apply = bool(field_value)
                
                if should_apply and field.price_modifier_value:
                    supplement = Decimal(str(field.price_modifier_value))
                    per_sample_supplements += supplement
                    supplements_breakdown.append({
                        'field': field.name,
                        'label': field.get_label(),
                        'amount': float(supplement),
                    })
    
    # Get active pricing configs for this service
    pricing_configs = service.pricing_configs.filter(
        is_active=True
    ).filter(
        models.Q(channel=channel) | models.Q(channel='BOTH')
    ).order_by('priority', 'pk')
    
    if not pricing_configs.exists():
        # Fall back to service's base price with per-sample supplements
        base_price = service.ibtikar_price if channel == 'IBTIKAR' else service.genoclab_price
        per_sample_total = Decimal(str(base_price)) + per_sample_supplements
        total = per_sample_total * sample_count
        
        breakdown = [{
            'name': 'Prix de base',
            'type': 'BASE',
            'amount': float(base_price),
            'quantity': sample_count,
            'subtotal': float(base_price) * sample_count,
        }]
        
        if per_sample_supplements > 0:
            breakdown.append({
                'name': 'Suppléments par échantillon',
                'type': 'PER_SAMPLE_SUPPLEMENT',
                'amount': float(per_sample_supplements),
                'quantity': sample_count,
                'subtotal': float(per_sample_supplements) * sample_count,
                'details': supplements_breakdown,
            })
        
        return {
            'source': 'service_base_price',
            'base_price': float(base_price),
            'per_sample_supplements': float(per_sample_supplements),
            'per_sample_total': float(per_sample_total),
            'sample_count': sample_count,
            'total': float(total),
            'breakdown': breakdown,
        }
    
    breakdown = []
    total = Decimal('0')
    base_per_sample = Decimal('0')
    override_applied = False
    has_per_sample_config = pricing_configs.filter(pricing_type='PER_SAMPLE').exists()

    for config in pricing_configs:
        quantity = 1
        config_total = Decimal('0')

        if config.pricing_type == 'OVERRIDE':
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

        if override_applied:
            continue

        if config.pricing_type == 'BASE':
            base_per_sample = Decimal(str(config.amount))
            quantity = sample_count if sample_count > 0 else 1
            config_total = base_per_sample * quantity
            total += config_total
        elif config.pricing_type == 'PER_SAMPLE':
            quantity = sample_count
            config_total = Decimal(str(config.amount)) * quantity
            total += config_total
        elif config.pricing_type == 'PER_PARAMETER':
            if service_params:
                quantity = len([v for v in service_params.values() if v])
            config_total = Decimal(str(config.amount)) * quantity
            total += config_total
        elif config.pricing_type == 'URGENCY_SURCHARGE':
            if urgency in ['Urgent', 'Très urgent']:
                config_total = Decimal(str(config.amount))
                total += config_total
        elif config.pricing_type == 'DISCOUNT':
            config_total = -Decimal(str(config.amount))
            total += config_total

        breakdown.append({
            'name': config.name,
            'type': config.pricing_type,
            'amount': float(config.amount),
            'quantity': quantity,
            'subtotal': float(config_total),
        })

    if not override_applied and per_sample_supplements > 0:
        if sample_count > 0:
            supplements_total = per_sample_supplements * sample_count
            total += supplements_total
            breakdown.append({
                'name': 'Suppléments par échantillon',
                'type': 'PER_SAMPLE_SUPPLEMENT',
                'amount': float(per_sample_supplements),
                'quantity': sample_count,
                'subtotal': float(supplements_total),
                'details': supplements_breakdown,
            })

    if not override_applied and not pricing_configs.exists():
        pass

    if not override_applied and total == Decimal('0') and has_per_sample_config and sample_count == 0:
        total = Decimal('0')
    
    return {
        'source': 'service_pricing_db',
        'pricing_configs_used': pricing_configs.count(),
        'base_per_sample': float(base_per_sample),
        'per_sample_supplements': float(per_sample_supplements),
        'per_sample_total': float(base_per_sample + per_sample_supplements),
        'sample_count': sample_count,
        'total': float(total),
        'breakdown': breakdown,
        'calculation_formula': f'({base_per_sample} + {per_sample_supplements}) × {sample_count} = {total}',
    }


def get_field_price_modifiers(service, channel='BOTH', scope='total'):
    """
    Get form fields that affect pricing for a service.
    
    Args:
        service: Service model instance
        channel: 'IBTIKAR', 'GENOCLAB', or 'BOTH'
        scope: 'per_sample' or 'total' - which scope of modifiers to return
    
    Returns list of fields with pricing modifier info. Includes fields that have:
    1. Field-level modifiers: affects_pricing=True with price_modifier_type in ['add', 'set', 'multiply']
    2. Option-level pricing: non-empty option_pricing JSON dict (for per-option multipliers)
    
    Both types are needed because apply_field_price_modifiers() handles both:
    - option_pricing dict → per-option multipliers (e.g. Duplicata=×2, Triplicata=×3)
    - price_modifier_value → field-level modifiers (surcharges, overrides, multipliers)
    """
    from core.models import ServiceFormField
    from django.db.models import Q
    
    fields = service.form_fields.filter(
        Q(affects_pricing=True, price_modifier_type__in=['add', 'set', 'multiply'])
        | Q(option_pricing__len__gt=0)
    ).filter(
        Q(channel='BOTH') | Q(channel=channel)
    )
    
    # Filter by scope if specified
    if scope == 'per_sample':
        fields = fields.filter(price_modifier_scope='per_sample')
    elif scope == 'total':
        # Total scope includes: fields with total scope OR fields without scope set (default)
        # Also include option_pricing fields (multipliers are always total scope)
        fields = fields.filter(
            Q(price_modifier_scope='total') 
            | Q(price_modifier_scope='') 
            | Q(price_modifier_scope__isnull=True)
            | Q(option_pricing__len__gt=0)  # option_pricing multipliers are always total scope
        )
    
    return list(fields)


def apply_field_price_modifiers(base_cost, service_params, modifier_fields):
    """
    Apply field-level price modifiers to a base cost.
    
    Supports two pricing modes:
    1. Field-level modifier: If field.affects_pricing=True and price_modifier_type is set,
       apply the modifier when the field is filled/selected.
    2. Option-level pricing: If field.option_pricing dict is set, look up the selected
       option's value in the dict and apply it (typically as multiply modifier).
       Example: {"Duplicata": 2, "Triplicata": 3} means Duplicata ×2, Triplicata ×3
    
    PRICING ORDER (mathematical precedence):
    1. First: Apply all ADD operations (surcharges, supplements)
    2. Second: Apply all MULTIPLY operations (multipliers)
    3. SET operations override the total completely
    
    This ensures: (Base + Additions) × Multipliers = Final Price
    
    Args:
        base_cost: Decimal or float base cost
        service_params: Dict of selected field values (keys are field.name prefixed with 'param_')
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
    
    # Collect all modifiers first to apply in correct order
    add_modifiers = []      # Will be applied first
    multiply_modifiers = [] # Will be applied second
    set_modifiers = []      # Override completely
    
    for field in modifier_fields:
        # Get field value from service_params (key format: field.name)
        # service_params may have keys like 'param_fieldname' or just 'fieldname'
        field_value = service_params.get(field.name)
        if not field_value:
            # Try with param_ prefix
            field_value = service_params.get(f'param_{field.name}')
        
        # Check if this field's value triggers a price modifier
        if not field_value:
            continue
        
        # Handle option_pricing: Look up selected option's value from option_pricing dict
        # This allows per-option multipliers like Duplicata=×2, Triplicata=×3
        option_pricing = getattr(field, 'option_pricing', None) or {}
        if option_pricing and isinstance(option_pricing, dict) and option_pricing:
            # Normalize field_value for lookup
            selected_options = []
            if isinstance(field_value, list):
                selected_options = [str(v) for v in field_value]
            else:
                selected_options = [str(field_value)]
            
            # Check each selected option against option_pricing dict
            for opt_value in selected_options:
                if opt_value in option_pricing:
                    opt_price = option_pricing[opt_value]
                    try:
                        opt_multiplier = Decimal(str(opt_price))
                        if opt_multiplier > 0:
                            # Store as multiply modifier (to be applied after additions)
                            multiply_modifiers.append({
                                'field': field.name,
                                'label': field.get_label(),
                                'type': 'option_multiply',
                                'option': opt_value,
                                'value': float(opt_multiplier),
                                'decimal_value': opt_multiplier,
                            })
                            # Add warning if available
                            if field.condition_note_fr or field.condition_note_en:
                                warnings.append({
                                    'field': field.name,
                                    'note_fr': field.condition_note_fr,
                                    'note_en': field.condition_note_en,
                                })
                    except (ValueError, TypeError):
                        pass
        
        # Handle field-level price_modifier (legacy behavior)
        # This applies when field.affects_pricing=True and price_modifier_type is set
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
        
        # Store modifiers for later application in correct order
        if modifier_type == 'add':
            add_modifiers.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'add',
                'value': float(modifier_value),
                'decimal_value': modifier_value,
            })
        elif modifier_type == 'set':
            set_modifiers.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'set',
                'value': float(modifier_value),
                'decimal_value': modifier_value,
            })
        elif modifier_type == 'multiply':
            multiply_modifiers.append({
                'field': field.name,
                'label': field.get_label(),
                'type': 'multiply',
                'value': float(modifier_value),
                'decimal_value': modifier_value,
            })
        
        # Add warning message
        if field.condition_note_fr or field.condition_note_en:
            warnings.append({
                'field': field.name,
                'note_fr': field.condition_note_fr,
                'note_en': field.condition_note_en,
            })
    
    # Apply modifiers in correct mathematical order:
    # 1. SET (override completely)
    # 2. ADD (surcharges/supplements)
    # 3. MULTIPLY (multipliers)
    
    for mod in set_modifiers:
        total = mod['decimal_value']
        modifiers_applied.append(mod)
    
    for mod in add_modifiers:
        total += mod['decimal_value']
        modifiers_applied.append(mod)
    
    for mod in multiply_modifiers:
        total *= mod['decimal_value']
        modifiers_applied.append(mod)
    
    return {
        'total': float(total),
        'warnings': warnings,
        'modifiers_applied': modifiers_applied,
    }


def validate_and_calculate_price(service, channel, sample_table, service_params, urgency='Normal', submitted_price=None):
    """
    Server-side price validation and recalculation.
    
    This function ALWAYS recalculates the price server-side and compares
    with any submitted (client-provided) price. The server-calculated price
    is the authoritative price and will be stored regardless of what
    the client submitted.
    
    SECURITY: This function evaluates conditional logic server-side to prevent
    manipulation where a user bypasses JS and submits data for hidden fields.
    
    Args:
        service: Service model instance
        channel: 'IBTIKAR' or 'GENOCLAB'
        sample_table: List of sample dicts
        service_params: Dict of service parameters
        urgency: Urgency level ('Normal', 'Urgent', 'Très urgent')
        submitted_price: Optional price submitted by client (for logging)
    
    Returns:
        dict with:
            - server_price: The authoritative server-calculated price
            - submitted_price: The price submitted by client (if any)
            - mismatch_detected: Boolean indicating if prices differed
            - mismatch_amount: Absolute difference if mismatch
            - cost_result: Full cost calculation breakdown
            - modifier_result: Field price modifiers applied
            - manipulation_detected: Boolean if hidden field manipulation was detected
            - hidden_fields_rejected: List of hidden fields that were rejected
    """
    result = {
        'server_price': 0.0,
        'submitted_price': float(submitted_price) if submitted_price else None,
        'mismatch_detected': False,
        'mismatch_amount': 0.0,
        'mismatch_percentage': 0.0,
        'cost_result': None,
        'modifier_result': None,
        'price_source': 'service_pricing_db',
        'logged': False,
        'manipulation_detected': False,
        'hidden_fields_rejected': [],
        'warnings': [],
    }
    
    # SECURITY STEP 0: Sanitize service_params
    # Evaluate conditional logic server-side to filter out hidden fields
    if service_params:
        conditional_result = evaluate_conditional_logic_server_side(service, service_params, channel)
        result['manipulation_detected'] = conditional_result['manipulation_detected']
        result['hidden_fields_rejected'] = conditional_result['hidden_fields_submitted']
        result['warnings'].extend(conditional_result['warnings'])
        
        # Use sanitized params for all calculations
        service_params = conditional_result['sanitized_params']
        
        # Validate max_selections constraints
        max_selections_result = validate_max_selections(service, service_params, channel)
        if not max_selections_result['valid']:
            result['warnings'].append(
                f'Max selections exceeded: {max_selections_result["violations"]}'
            )
            # Use sanitized params (with truncated selections)
            service_params = max_selections_result['sanitized_params']
    
    # Step 1: Calculate base cost from ServicePricing database
    cost_result = calculate_cost_from_db(
        service=service,
        channel=channel,
        sample_table=sample_table,
        service_params=service_params,
        urgency=urgency,
    )
    result['cost_result'] = cost_result
    result['price_source'] = cost_result.get('source', 'unknown')
    server_price = Decimal(str(cost_result.get('total', 0)))
    
    # Step 2: Apply field-level price modifiers (only TOTAL scope modifiers)
    # Per-sample modifiers are already applied in calculate_cost_from_db
    modifier_fields = get_field_price_modifiers(service, channel, scope='total')
    if modifier_fields and service_params:
        modifier_result = apply_field_price_modifiers(server_price, service_params, modifier_fields)
        result['modifier_result'] = modifier_result
        server_price = Decimal(str(modifier_result.get('total', 0)))
    
    result['server_price'] = float(server_price)
    
    # Step 3: Compare with submitted price if provided
    if submitted_price is not None:
        submitted_decimal = Decimal(str(submitted_price))
        if submitted_decimal != server_price:
            result['mismatch_detected'] = True
            result['mismatch_amount'] = float(abs(server_price - submitted_decimal))
            if server_price > 0:
                result['mismatch_percentage'] = float(abs(server_price - submitted_decimal) / server_price * 100)
            
            # Log the potential manipulation attempt
            _log_price_mismatch(
                service_code=service.code if service else 'UNKNOWN',
                channel=channel,
                submitted_price=float(submitted_decimal),
                server_price=float(server_price),
                mismatch_amount=result['mismatch_amount'],
                sample_count=len(sample_table) if sample_table else 0,
                service_params=service_params,
            )
            result['logged'] = True
    
    return result


def _log_price_mismatch(service_code, channel, submitted_price, server_price, mismatch_amount, sample_count, service_params):
    """
    Log price mismatch events for security audit.
    
    This helps detect:
    1. Accidental calculation errors on the client side
    2. Intentional price manipulation attempts via DevTools
    3. Pricing configuration bugs
    """
    mismatch_ratio = abs(server_price - submitted_price) / server_price * 100 if server_price > 0 else 0
    
    # Determine severity
    if mismatch_ratio > 50:
        severity = 'CRITICAL'
    elif mismatch_ratio > 20:
        severity = 'HIGH'
    elif mismatch_ratio > 5:
        severity = 'MEDIUM'
    else:
        severity = 'LOW'
    
    logger.warning(
        f"PRICE_MISMATCH [{severity}] Service={service_code} Channel={channel} "
        f"Submitted={submitted_price:,.2f} DA Server={server_price:,.2f} DA "
        f"Diff={mismatch_amount:,.2f} DA ({mismatch_ratio:.1f}%) "
        f"Samples={sample_count} Params={len(service_params) if service_params else 0}",
        extra={
            'event_type': 'PRICE_MISMATCH',
            'severity': severity,
            'service_code': service_code,
            'channel': channel,
            'submitted_price': submitted_price,
            'server_price': server_price,
            'mismatch_amount': mismatch_amount,
            'mismatch_percentage': mismatch_ratio,
            'sample_count': sample_count,
            'service_params_keys': list(service_params.keys()) if service_params else [],
        }
    )


def evaluate_conditional_logic_server_side(service, service_params, channel='BOTH'):
    """
    Server-side evaluation of conditional logic rules.
    
    This function mirrors the JavaScript evaluateConditionalLogic() to determine
    which fields SHOULD be visible based on conditional_logic rules.
    
    IMPORTANT: This prevents manipulation where a user bypasses JS and submits
    data for fields that should be hidden.
    
    Args:
        service: Service model instance
        service_params: Dict of submitted field values
        channel: 'IBTIKAR', 'GENOCLAB', or 'BOTH'
    
    Returns:
        dict with:
            - sanitized_params: Only includes values for visible fields
            - hidden_fields_submitted: List of fields that were submitted but should be hidden
            - manipulation_detected: Boolean if any hidden fields were submitted
            - warnings: List of warning messages
    """
    from core.models import ServiceFormField
    
    result = {
        'sanitized_params': {},
        'hidden_fields_submitted': [],
        'manipulation_detected': False,
        'warnings': [],
    }
    
    if not service_params:
        return result
    
    # Get all form fields for this service and channel
    all_fields = service.form_fields.filter(
        models.Q(channel=channel) | models.Q(channel='BOTH')
    )
    
    # Build a map of field name -> field object
    field_map = {f.name: f for f in all_fields}
    
    # Build initial visibility state - fields with no conditional_logic are always visible
    # For multiselect checkboxes, always include the field itself
    visible_fields = set()
    for field in all_fields:
        if not field.conditional_logic or len(field.conditional_logic) == 0:
            visible_fields.add(field.name)
    
    # Iteratively evaluate conditional logic (max 10 iterations like JS)
    max_iterations = 10
    for iteration in range(max_iterations):
        changed = False
        
        for field in all_fields:
            if not field.conditional_logic or len(field.conditional_logic) == 0:
                continue
            if field.name in visible_fields:
                continue  # Already visible
            
            # Evaluate each condition rule
            # Fields with ONLY 'activate_price_modifier' actions are always visible
            # (the modifier activates when conditions are met, but field is still visible)
            should_show = None  # None = not determined by show/hide actions
            has_show_hide_action = False
            
            for rule in field.conditional_logic:
                trigger_field_name = rule.get('trigger_field')
                trigger_value = rule.get('trigger_value')
                actions = rule.get('actions', [])
                
                # Check if this is a visibility action
                action_types = set(actions)
                if 'show' in action_types or 'hide' in action_types:
                    has_show_hide_action = True
                
                # Skip if trigger field doesn't exist
                if trigger_field_name not in field_map:
                    continue
                
                trigger_field = field_map[trigger_field_name]
                trigger_param_value = service_params.get(trigger_field_name)
                
                # Handle different field types
                condition_met = False
                
                if trigger_field.field_type in ['checkbox', 'boolean']:
                    # Boolean fields: value is 'true' or truthy when checked
                    if trigger_param_value in ['true', True, 'on']:
                        if str(trigger_value).lower() in ['true', '1', 'yes']:
                            condition_met = True
                elif trigger_field.field_type in ['multiselect']:
                    # Multi-select: value is a list of selected options
                    if isinstance(trigger_param_value, list):
                        if trigger_value in trigger_param_value:
                            condition_met = True
                    elif trigger_param_value:  # Might be comma-separated string
                        selected = [v.strip() for v in str(trigger_param_value).split(',')]
                        if trigger_value in selected:
                            condition_met = True
                else:
                    # Select, dropdown, text, etc.
                    if str(trigger_param_value) == str(trigger_value):
                        condition_met = True
                
                # Apply actions
                if condition_met:
                    for action in actions:
                        if action == 'show':
                            should_show = True
                        elif action == 'hide':
                            should_show = False
                            break  # Hide takes precedence for this rule
                        elif action == 'activate_price_modifier':
                            # This field affects pricing when trigger condition is met
                            # Field remains visible - this is handled in pricing logic
                            pass
            
            # Update visibility
            # If field has no show/hide actions (only activate_price_modifier), it's visible
            if not has_show_hide_action:
                should_show = True
            
            if should_show and field.name not in visible_fields:
                visible_fields.add(field.name)
                changed = True
        
        if not changed:
            break
    
    # Build sanitized params - only include values for visible fields
    for field_name, value in service_params.items():
        if field_name in visible_fields:
            result['sanitized_params'][field_name] = value
        else:
            # Field is hidden but user submitted data - potential manipulation
            if value and value not in ['', None, [], {}]:
                result['hidden_fields_submitted'].append(field_name)
                result['manipulation_detected'] = True
    
    # Log manipulation attempts
    if result['manipulation_detected']:
        logger.warning(
            f"SECURITY [HIDDEN_FIELD_MANIPULATION] Service={service.code} Channel={channel} "
            f"Hidden fields submitted: {result['hidden_fields_submitted']}",
            extra={
                'event_type': 'HIDDEN_FIELD_MANIPULATION',
                'severity': 'HIGH',
                'service_code': service.code,
                'channel': channel,
                'hidden_fields_submitted': result['hidden_fields_submitted'],
                'total_submitted_fields': len(service_params),
                'visible_fields': list(visible_fields),
            }
        )
        result['warnings'].append(
            f'Rejected {len(result["hidden_fields_submitted"])} hidden field(s): {", ".join(result["hidden_fields_submitted"])}'
        )
    
    return result


def validate_max_selections(service, service_params, channel='BOTH'):
    """
    Validate that multi-select fields don't exceed max_selections limit.
    
    Args:
        service: Service model instance
        service_params: Dict of submitted field values
        channel: 'IBTIKAR', 'GENOCLAB', or 'BOTH'
    
    Returns:
        dict with:
            - valid: Boolean if all selections are within limits
            - violations: List of {field_name, submitted_count, max_allowed} dicts
            - sanitized_params: Params with excess selections truncated
    """
    from core.models import ServiceFormField
    
    result = {
        'valid': True,
        'violations': [],
        'sanitized_params': dict(service_params),
    }
    
    if not service_params:
        return result
    
    # Get multiselect fields with max_selections constraint
    constrained_fields = service.form_fields.filter(
        field_type='multiselect',
        max_selections__isnull=False,
        max_selections__gt=0
    ).filter(
        models.Q(channel=channel) | models.Q(channel='BOTH')
    )
    
    for field in constrained_fields:
        field_value = service_params.get(field.name)
        if not field_value:
            continue
        
        # Parse the selected values
        if isinstance(field_value, list):
            selected_count = len(field_value)
        elif isinstance(field_value, str) and field_value:
            selected_count = len([v for v in field_value.split(',') if v.strip()])
        else:
            continue
        
        max_allowed = field.max_selections
        
        if selected_count > max_allowed:
            result['valid'] = False
            result['violations'].append({
                'field_name': field.name,
                'field_label': field.get_label(),
                'submitted_count': selected_count,
                'max_allowed': max_allowed,
            })
            
            # Truncate to max allowed
            if isinstance(field_value, list):
                result['sanitized_params'][field.name] = field_value[:max_allowed]
            elif isinstance(field_value, str):
                values = [v.strip() for v in field_value.split(',') if v.strip()]
                result['sanitized_params'][field.name] = ','.join(values[:max_allowed])
            
            logger.warning(
                f"SECURITY [MAX_SELECTIONS_EXCEEDED] Service={service.code} "
                f"Field={field.name} Submitted={selected_count} Max={max_allowed}",
                extra={
                    'event_type': 'MAX_SELECTIONS_EXCEEDED',
                    'severity': 'MEDIUM',
                    'service_code': service.code,
                    'field_name': field.name,
                    'submitted_count': selected_count,
                    'max_allowed': max_allowed,
                }
            )
    
    return result