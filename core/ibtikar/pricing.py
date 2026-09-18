from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from core.exceptions import PricingConfigurationError
from core.ibtikar.schema import get_schema, active_data, schema_for_service


def amount(value):
    try:
        value = Decimal(str(value))
    except Exception as exc:
        raise PricingConfigurationError('Invalid tariff amount') from exc
    if not value.is_finite() or value < 0:
        raise PricingConfigurationError('Invalid tariff amount')
    return value


def resolve_schema_cost(service, channel, samples, parameters, urgency='Normal', schema=None):
    from core.registry import get_service_def
    schema = schema or schema_for_service(service)
    if channel != 'IBTIKAR' or not schema:
        raise PricingConfigurationError('Unknown IBTIKAR form')
    parameters = active_data(schema, 'parameters', parameters)
    samples = [active_data(schema, 'samples', row, parameters) for row in samples]
    if not samples:
        return {'total': None, 'known_subtotal': '0', 'source': 'pending_review',
                'status': 'pending', 'reasons': ['samples_required'], 'breakdown': [], 'currency': 'DZD'}
    today = timezone.localdate()
    configured = service.pricing_configs.filter(Q(channel=channel) | Q(channel='BOTH'))
    effective = configured.filter(is_active=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=today)).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=today)).order_by('priority', 'pk')
    applicable_overrides = [x for x in effective if x.pricing_type == 'OVERRIDE'
                           and x.min_quantity <= len(samples)
                           and (x.max_quantity is None or len(samples) <= x.max_quantity)
                           and x.min_amount is None and x.max_amount is None]
    if applicable_overrides:
        value = amount(applicable_overrides[-1].amount)
        return {'total': value, 'known_subtotal': str(value), 'source': 'db_override',
                'status': 'calculated', 'reasons': [], 'currency': 'DZD',
                'breakdown': [{'name': applicable_overrides[-1].name, 'quantity': 1, 'subtotal': str(value)}]}
    source = (get_service_def(service.code) or {}).get('pricing', {})
    override = service.pricing_data or {}
    if not isinstance(override, dict):
        raise PricingConfigurationError('Invalid pricing configuration')
    current = override.get('ibtikar', {})
    if current and not isinstance(current, dict):
        raise PricingConfigurationError('Invalid IBTIKAR pricing configuration')
    pricing = {**source, **current}
    reasons = []
    if any(f.get('configured_field') and f.get('price_sensitive') and any(values.get(f['name']) not in (None, '', [], 'no', False) for values in ([parameters] if group == 'parameters' else samples)) for group in ('parameters', 'samples') for f in schema[group]):
        reasons.append('administrator_option_tariff_requires_review')
    if configured.exists():
        reasons.append('configured_tariffs_require_option_review')
    if override and not current:
        reasons.append('legacy_pricing_configuration_requires_review')
    if urgency != 'Normal':
        reasons.append('urgency_price_requires_review')
    lines = []
    code = service.code
    base = (pricing.get('base_price') or {}).get('non_pathogenic')
    multipliers = pricing.get('multipliers', {})
    n = len(samples)

    def add(name, rate, quantity=1):
        if rate is None:
            reasons.append(name + '_price_not_configured')
            return
        subtotal = amount(rate) * quantity
        lines.append({'name': name, 'quantity': quantity, 'unit_price': str(amount(rate)), 'subtotal': str(subtotal)})

    def factor(name, key):
        values = pricing.get(name, {})
        if key not in values:
            reasons.append(name + '_' + str(key) + '_not_configured')
            return None
        return amount(values[key])

    if code == 'EGTP-IMT':
        for i, row in enumerate(samples, 1):
            risk = 'pathogenic' if row.get('risk_status') in ('pathogenic', 'clinical') or row.get('origin') == 'clinical' else 'standard'
            rates = pricing.get('imt_rates', {}).get(risk, {})
            add('maldi_' + str(i), rates.get(row.get('analysis_mode')))
            if row.get('maldi_target') == 'disposable':
                add('disposable_target_' + str(i), pricing.get('disposable_target_price'))
            if row.get('fresh_culture') == 'no':
                for operation in row.get('preparation') or []:
                    add('preparation_' + operation + '_' + str(i), pricing.get('preparation_prices', {}).get(operation))
    elif code == 'EGTP-SeqS':
        direction = {'forward': 'Forward', 'reverse': 'Reverse', 'both': 'Forward + Reverse'}.get(parameters.get('sequencing_mode'))
        multiplier = factor('multipliers', direction)
        purity = parameters.get('submitted_type')
        if purity in ('bigdye', 'other'):
            reasons.append('submitted_material_requires_review')
        elif purity not in ('purified_pcr', 'unpurified_pcr'):
            reasons.append('submitted_material_missing')
        if base is not None and multiplier is not None:
            price = amount(base) * multiplier
            if purity == 'unpurified_pcr':
                cleanup = factor('multipliers', 'Non-purified')
                price = price * cleanup if cleanup is not None else price
            add('sanger', price, n)
    elif code == 'EGTP-Seq02':
        direction = {'forward': 'F', 'reverse': 'F', 'both': 'F+R'}.get(parameters.get('sequencing_mode'))
        multiplier = factor('multipliers', direction)
        if parameters.get('extraction_method') != 'classical':
            reasons.append('extraction_kit_price_requires_review')
        if parameters.get('pcr_kit') != 'DreamTaq':
            reasons.append('pcr_kit_price_requires_review')
        if set(parameters.get('qc_methods') or []) != {'spectrophotometry'}:
            reasons.append('quality_control_price_requires_review')
        if base is not None and multiplier is not None:
            add('sequencing_identification', amount(base) * multiplier, n)
    elif code == 'EGTP-PCR':
        methods = set(parameters.get('qc_methods') or [])
        mode = 'None' if methods == {'none'} else 'Gel' if methods == {'gel'} else 'ScanDrop + Gel' if methods == {'spectrophotometry', 'gel'} else None
        if parameters.get('pcr_kit') != 'Standard Taq':
            reasons.append('pcr_kit_price_requires_review')
        multiplier = factor('multipliers', mode)
        if parameters.get('product_recovery') == 'yes' and amount(parameters.get('product_volume_ul') or 0) not in (25, 50):
            reasons.append('requested_volume_price_requires_review')
        if base is not None and multiplier is not None:
            add('pcr', amount(base) * multiplier, n)
    elif code == 'EGTP-CAN':
        if set(parameters.get('qc_methods') or []) != {'fluorimetry', 'gel'}:
            reasons.append('quality_control_scope_requires_review')
        add('nucleic_acid_qc', pricing.get('unit_price'), n)
    elif code == 'EGTP-PS':
        pairs = defaultdict(list)
        for row in samples:
            pairs[row.get('pair_code')].append(row)
        for key, pair in pairs.items():
            if len(pair) != 2 or {r.get('direction') for r in pair} != {'forward', 'reverse'}:
                reasons.append('incomplete_primer_pair_' + str(key))
                continue
            length = max(len(str(r.get('sequence') or '')) for r in pair)
            category = 'up_to_25_nt' if 0 < length <= 25 else 'from_26_to_30_nt' if length <= 30 else 'from_31_to_40_nt' if length <= 40 else None
            multiplier = factor('multipliers', category)
            if base is not None and multiplier is not None:
                add('primer_pair_' + str(key), amount(base) * multiplier)
        if parameters.get('purification_method') not in ('', None, 'butanol'):
            reasons.append('purification_price_requires_review')
        if parameters.get('delivery_format') == 'solution' and amount(parameters.get('concentration_um', '0')) != 1:
            reasons.append('delivery_concentration_requires_review')
    elif code == 'EGTP-Illumina-Microbial-WGS':
        depth = {'standard': 'Standard', 'high': 'High'}.get(parameters.get('sequencing_depth'))
        multiplier = factor('multipliers', depth)
        if base is not None and multiplier is not None:
            add('microbial_wgs', amount(base) * multiplier, n)
    elif code == 'EGTP-Lyoph':
        duration = parameters.get('duration_units_24h')
        multiplier = factor('multipliers', str(duration))
        if base is not None and multiplier is not None:
            add('freeze_drying', amount(base) * multiplier, n)
        reasons.append('container_solvent_thermal_compatibility_review')
    else:
        add('custom_scope', pricing.get('unit_price'), n)
        reasons.append('service_scope_requires_review')
    if not lines:
        reasons.append('tariff_not_determined')
    total = sum((Decimal(x['subtotal']) for x in lines), Decimal('0')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {'total': total if not reasons else None, 'known_subtotal': str(total),
            'source': 'configured_ibtikar_tariff' if current else 'registry_ibtikar_tariff',
            'status': 'pending' if reasons else 'calculated', 'currency': 'DZD',
            'reasons': sorted(set(reasons)), 'breakdown': lines}
