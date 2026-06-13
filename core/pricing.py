# core/pricing.py — PLAGENOR 4.0 Pricing Engine
# Generic pricing dispatcher driven by YAML service registry.

from __future__ import annotations

import logging

from django.db import models

logger = logging.getLogger('plagenor.pricing')


def _coerce_int(value, default=0, key=''):
    """Coerce a YAML registry value to int; log + fall back on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        if value not in (None, ''):
            logger.warning(
                "pricing: cannot coerce %r to int at %s; using %s",
                value, key or '?', default,
            )
        return default


def _coerce_float(value, default=0.0, key=''):
    """Coerce a YAML registry value to float; log + fall back on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        if value not in (None, ''):
            logger.warning(
                "pricing: cannot coerce %r to float at %s; using %s",
                value, key or '?', default,
            )
        return default

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

    # Determine base price — defensive coercion in case the registry value
    # is mistyped (e.g. quoted "1000" with a thousand-separator).
    pathogenic = bool(params.get('pathogenic', False))
    base_key = 'pathogenic' if pathogenic else 'non_pathogenic'
    base_price = _coerce_int(
        base_prices.get(base_key, base_prices.get('default', 0)),
        default=0, key=f"base_price/{base_key}",
    )

    # Determine multiplier key
    mult_key = (
        params.get('analysis_mode') or params.get('qc_level')
        or params.get('sequencing_mode') or params.get('drying_level')
        or params.get('primer_type')
    )

    if not mult_key and multipliers:
        mult_key = list(multipliers.keys())[0]

    # Multiplier defaults to 1.0 (no effect) — never 0 — so a typo never
    # silently zeroes out a quote.
    multiplier = (
        _coerce_float(multipliers.get(mult_key, 1), default=1.0,
                      key=f"multiplier/{mult_key}")
        if mult_key else 1.0
    )
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

    unit_price = _coerce_int(pricing.get('unit_price', 0), default=0, key="unit_price")
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


# ============================================================================
# CANONICAL COST RESOLVER  ===  the single source of truth for "how much?"
# ============================================================================
#
# Three pricing sources coexist in the codebase:
#
#   1. ``ServicePricing`` tiers (DB, editable in the SuperAdmin service-edit
#      page). These are what an operator authors when they configure
#      per-sample prices, urgency surcharges, volume discounts, etc.
#
#   2. ``services_registry/<code>.yaml`` (the YAML registry consumed by
#      ``calculate_price``). Older path. Defines per-multiplier pricing for
#      9 IBTIKAR services. Still authoritative for those nine since their
#      YAML descriptions encode logic that doesn't yet exist as tiers.
#
#   3. ``Service.ibtikar_price`` / ``Service.genoclab_price`` (flat columns).
#      The last-resort fallback. Charges this amount per *sample* (not
#      flat per request) so a GENOCLAB submission with 10 samples doesn't
#      get billed the same as one with 1 sample.
#
# Precedence — fail UP, never silently DOWN:
#
#   * If any active ServicePricing tier exists for (service, channel), the
#     DB tiers WIN. They reflect a deliberate operator decision and must
#     not be silently overridden by older YAML or flat columns.
#   * Otherwise, if a YAML registry definition exists for this service
#     code, use ``calculate_price`` against it.
#   * Otherwise, use the flat column × sample count.
#
# Every public submission path (IBTIKAR requester, GENOCLAB client, guest
# submission) calls ``resolve_cost`` so the answer is identical regardless
# of who's clicking.
# ============================================================================

def resolve_cost(
    service,
    channel: str,
    sample_table=None,
    service_params=None,
    urgency: str = 'Normal',
):
    """Resolve the canonical cost for a request submission.

    Returns ``{'total': float, 'source': str, 'breakdown': [...]}``.
    ``source`` is one of ``'db_tiers'`` / ``'yaml_registry'`` / ``'flat'``
    so the caller can surface which path was taken — useful when an admin
    is debugging "why is my discount tier not firing?".

    Never raises on bad input; falls back to the flat path and logs.
    """
    sample_table = sample_table or []
    service_params = service_params or {}
    if not service:
        return {'total': 0.0, 'source': 'no_service', 'breakdown': []}
    if channel not in ('IBTIKAR', 'GENOCLAB'):
        channel = 'GENOCLAB' if channel.lower().startswith('g') else 'IBTIKAR'

    # 1) DB tiers — what the SuperAdmin actually configured
    try:
        has_tiers = service.pricing_configs.filter(
            is_active=True,
        ).filter(
            models.Q(channel=channel) | models.Q(channel='BOTH')
        ).exists()
    except Exception:
        has_tiers = False

    if has_tiers:
        result = calculate_cost_from_db(
            service, channel,
            sample_table=sample_table,
            service_params=service_params,
            urgency=urgency,
        )
        result['source'] = 'db_tiers'
        return result

    # 2a) DB pricing_data — SuperAdmin-edited base price + multipliers
    #     Same shape as a YAML ``pricing`` block, so the existing
    #     ``calculate_price`` engine consumes it unchanged. This is the lever
    #     for reagent/consumable cost variations: the SuperAdmin edits the
    #     numbers in the UI and the next quote/estimate uses them, without
    #     touching the YAML on disk.
    pdata = getattr(service, 'pricing_data', None) or {}
    db_pricing_block = None
    if isinstance(pdata, dict) and pdata.get('base_price') and pdata.get('multipliers'):
        db_pricing_block = {
            'model': 'per_sample_table_row_with_multiplier',
            'currency': pdata.get('currency', 'DZD'),
            'base_price': pdata.get('base_price') or {},
            'multipliers': pdata.get('multipliers') or {},
        }

    # 2b) YAML registry — for the legacy 9 IBTIKAR services (fallback when
    #     pricing_data hasn't been authored yet).
    try:
        from core.registry import get_service_def
        yaml_def = get_service_def(service.code)
    except Exception:
        yaml_def = None

    # If the SuperAdmin has authored pricing_data, that overrides the YAML
    # pricing block while keeping the rest of the YAML definition (so
    # ``calculate_price`` still sees ``service_code`` etc.).
    if db_pricing_block and sample_table:
        synthetic_def = dict(yaml_def or {})
        synthetic_def['pricing'] = db_pricing_block
        try:
            db_result = calculate_price(synthetic_def, service_params, sample_table)
            return {
                'total': float(db_result.get('total', 0)),
                'source': 'service_pricing_data',
                'breakdown': [{
                    'name': 'DB-authored base × multiplier × samples',
                    'type': db_result.get('pricing_model', 'db'),
                    'amount': float(db_result.get('unit_price', 0)),
                    'quantity': db_result.get('number_of_units', 0),
                    'subtotal': float(db_result.get('total', 0)),
                }],
                'yaml_breakdown': db_result.get('breakdown', {}),
                'currency': db_result.get('currency', 'DZD'),
            }
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "resolve_cost: pricing_data calculate_price failed for %s (%s); "
                "falling through to YAML/flat",
                service.code, exc,
            )

    if yaml_def and yaml_def.get('pricing') and sample_table:
        try:
            yaml_result = calculate_price(yaml_def, service_params, sample_table)
            return {
                'total': float(yaml_result.get('total', 0)),
                'source': 'yaml_registry',
                'breakdown': [{
                    'name': 'YAML pricing',
                    'type': yaml_result.get('pricing_model', 'yaml'),
                    'amount': float(yaml_result.get('unit_price', 0)),
                    'quantity': yaml_result.get('number_of_units', 0),
                    'subtotal': float(yaml_result.get('total', 0)),
                }],
                'yaml_breakdown': yaml_result.get('breakdown', {}),
                'currency': yaml_result.get('currency', 'DZD'),
            }
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "resolve_cost: YAML calculate_price failed for %s (%s); "
                "falling through to flat",
                service.code, exc,
            )

    # 3) Flat per-sample fallback — never per-request, so GENOCLAB billing
    #    actually scales with sample count.
    flat = service.ibtikar_price if channel == 'IBTIKAR' else service.genoclab_price
    flat = float(flat or 0)
    sample_count = max(1, len([s for s in sample_table if s]))
    total = flat * sample_count
    return {
        'total': total,
        'source': 'flat',
        'breakdown': [{
            'name': 'Prix forfaitaire (par échantillon)',
            'type': 'FLAT',
            'amount': flat,
            'quantity': sample_count,
            'subtotal': total,
        }],
    }


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
            if urgency in ('Urgent', 'Très urgent'):
                quantity = 1
                config_total = config.amount
        elif config.pricing_type == 'DISCOUNT':
            quantity = 1
            # DISCOUNT amount is conventionally stored NEGATIVE in the DB
            # (matches the "Remise volume −500" pattern in the seed fixtures);
            # but if an operator typed a positive number we treat it as a
            # subtraction so the math is intuitive either way.
            config_total = -abs(config.amount)

        total += config_total
        breakdown.append({
            'name': config.name,
            'type': config.pricing_type,
            'amount': float(config.amount),
            'quantity': quantity,
            'subtotal': float(config_total),
        })

    # Clamp at zero — a stack of discounts can't produce a negative bill.
    if total < 0:
        total = Decimal('0')

    return {
        'source': 'service_pricing_db',
        'pricing_configs_used': pricing_configs.count(),
        'sample_count': sample_count,
        'total': float(total),
        'breakdown': breakdown,
    }
