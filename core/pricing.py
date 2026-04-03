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
        # OVERRIDE type always replaces total and prevents other configs
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
            continue  # Always skip OVERRIDE after processing
        
        # After OVERRIDE is applied, skip all other configs
        if override_applied:
            continue
        
        # BASE with positive amount sets the base total (allows modifiers to apply)
        if config.pricing_type == 'BASE' and config.amount > 0:
            total = Decimal(str(config.amount))
            breakdown.append({
                'name': config.name,
                'type': config.pricing_type,
                'amount': float(config.amount),
                'quantity': quantity,
                'subtotal': float(config_total),
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
    
    # Step 2: Apply field-level price modifiers
    modifier_fields = get_field_price_modifiers(service, channel)
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
            should_show = False
            
            for rule in field.conditional_logic:
                trigger_field_name = rule.get('trigger_field')
                trigger_value = rule.get('trigger_value')
                actions = rule.get('actions', [])
                
                # Check if this rule's trigger condition is met
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
                            pass
            
            # Update visibility
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