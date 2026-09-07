"""API endpoint that returns HTML form fragment for a service's YAML-defined parameters."""
import logging
import json
from copy import deepcopy
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from core.registry import get_service_def
from core.ratelimit import rate_limit


logger = logging.getLogger(__name__)


def service_form_fragment(request, service_code):
    """Return rendered HTML for a service's YAML parameters + sample table.

    Pricing is now included in the response so the IBTIKAR / GENOCLAB
    requester sees a live cost estimate. The previous "hide pricing from
    anonymous visitors" stance broke the same form for authenticated
    requesters who routed through this endpoint, leaving the cost-estimate
    box hidden and the budget guard silent. YAML pricing tables are in
    the repo anyway and aren't secret.
    """
    definition = get_service_def(service_code)
    if not definition:
        # No YAML registry entry — this is fine for a service a SuperAdmin
        # created from scratch. Its entire form (questions + sample columns)
        # comes from the DB ``custom_fields`` loaded below. Only bail if the
        # service itself doesn't exist.
        from core.models import Service as _Service
        if not _Service.objects.filter(code=service_code).exists():
            return HttpResponse('<p class="text-muted">Service non trouvé.</p>')
        definition = {}

    definition = deepcopy(definition)
    parameters = definition.get('parameters', [])
    # Copy so we can augment without mutating the cached registry dict.
    sample_table = dict(definition.get('sample_table', {}) or {})
    # The template hides a parameter when its name is also a sample-table
    # column (``param.name not in sample_table.column_names``). The registry
    # only carries ``columns``; without an explicit ``column_names`` list the
    # lookup resolves to '' and Django evaluates ``name not in ''`` as False,
    # silently hiding EVERY Section-4 question. Compute the list here.
    sample_table['column_names'] = [
        c.get('name') for c in (sample_table.get('columns') or []) if c.get('name')
    ]
    pricing = definition.get('pricing', {}) or {}

    # SuperAdmin-edited pricing_data (Service.pricing_data) takes precedence
    # over the YAML pricing block — reagent/consumable cost changes the admin
    # makes in the UI must be the ones the requester sees and the engine bills.
    db_pdata = {}
    try:
        from core.models import Service as _Svc
        _svc = _Svc.objects.filter(code=service_code).first()
        if _svc and isinstance(_svc.pricing_data, dict) and _svc.pricing_data.get('multipliers'):
            db_pdata = _svc.pricing_data
    except Exception:
        logger.exception("Unable to load DB pricing for service=%s", service_code)
        db_pdata = {}
    if db_pdata.get('base_price') or db_pdata.get('multipliers'):
        # Surface the override to the cost calculator as if it were the YAML.
        pricing = {
            **pricing,
            'base_price': db_pdata.get('base_price', pricing.get('base_price', {})),
            'multipliers': db_pdata.get('multipliers', pricing.get('multipliers', {})),
            'model': pricing.get('model', 'per_sample_table_row_with_multiplier'),
        }

    # Bridge: when pricing defines a ``multipliers`` table (e.g.
    # {Simple: 1, Duplicate: 2, Triplicate: 3} on a per_sample_table_row_with
    # _multiplier model), inject that map as ``option_pricing`` on the param
    # whose options match — the cost calculator only sees per-field
    # data-option-pricing attributes, never the global pricing block,
    # so without this bridge Duplicate/Triplicate were silently ignored at
    # cost-estimate time.
    yaml_multipliers = (pricing or {}).get('multipliers') if isinstance(pricing, dict) else None
    if isinstance(yaml_multipliers, dict) and yaml_multipliers:
        # Compare as strings: YAML option values can be ints (e.g. duration
        # 1/2/3) while the multiplier keys are strings ("1"/"2"/"3") — a raw
        # set intersection would miss them (int 1 != str "1").
        mult_by_str = {str(k): v for k, v in yaml_multipliers.items()}
        mult_str_keys = set(mult_by_str.keys())
        # Don't mutate the cached registry parameter dicts.
        parameters = [dict(p) for p in parameters]
        for p in parameters:
            opts = p.get('options') or []
            if not opts:
                continue
            opt_strs = {str(o) for o in opts}
            # Match the param whose options are the multiplier keys (covers
            # analysis_mode, qc_level, sequencing_mode, drying_level,
            # primer_type, duration_units_24h… in the EGTP YAML registry).
            if opt_strs & mult_str_keys and not p.get('option_pricing'):
                # Key the option_pricing by the ACTUAL option value the form
                # posts (str), so the JS lookup matches the selected value.
                p['option_pricing'] = {
                    str(o): mult_by_str[str(o)]
                    for o in opts if str(o) in mult_by_str
                }

    # Also load DB-defined custom fields. A SuperAdmin can define a whole
    # service's form here: fields tagged ``parameter`` become questions
    # (db_fields, serialized with their variable-pricing / conditional-logic
    # config), fields tagged ``sample_column`` become extra columns of the
    # per-sample table — so a brand-new service with no YAML still renders a
    # complete online form and a complete generated document.
    svc = None
    db_fields = []
    db_columns = []
    try:
        from core.models import Service, ServiceFormField
        svc = Service.objects.filter(code=service_code).first()
        if svc:
            for f in svc.custom_fields.all().order_by('sort_order', 'pk'):
                if getattr(f, 'field_category', 'parameter') == 'sample_column':
                    db_columns.append({
                        'name': f.name,
                        'label': f.label,
                        'type': 'enum' if f.field_type == 'enum' else (
                            'number' if f.field_type == 'number' else 'string'),
                        'options': f.options or [],
                        'required': f.required,
                    })
                else:
                    db_fields.append({
                        'name': f.name,
                        'label': f.label,
                        'field_type': f.field_type,
                        'options': f.options or [],
                        'required': f.required,
                        'pricing_info': f.pricing_info,
                        'option_pricing': f.option_pricing or {},
                        'conditional_logic': f.conditional_logic or [],
                    })
    except Exception:
        logger.exception("Unable to load DB form fields for service=%s", service_code)

    # Merge admin-defined sample columns into the (possibly empty) YAML table.
    if db_columns:
        existing = {c.get('name') for c in (sample_table.get('columns') or [])}
        merged = list(sample_table.get('columns') or [])
        for col in db_columns:
            if col['name'] not in existing:
                merged.append(col)
        sample_table['enabled'] = True
        sample_table.setdefault('min_rows', 1)
        sample_table['columns'] = merged
        sample_table['column_names'] = [c.get('name') for c in merged if c.get('name')]

    from core.financial_visibility import estimates_visible
    show_estimates = bool(getattr(request.user, 'is_admin', False)) or estimates_visible(service=svc)
    if not show_estimates:
        pricing = {}
        for field in parameters + db_fields + sample_table.get('columns', []):
            field.pop('pricing_info', None)
            field.pop('option_pricing', None)

    html = render_to_string('includes/service_form_fields.html', {
        'show_estimates': show_estimates,
        'parameters': parameters,
        'sample_table': sample_table,
        'pricing': pricing,
        # ``data-pricing`` attribute on the cost-estimate box needs valid
        # JSON (not a Python dict repr) for ``JSON.parse`` to consume.
        'pricing_json': json.dumps(pricing, ensure_ascii=False),
        'service_code': service_code,
        'estimate_channel': request.GET.get('channel', 'GENOCLAB'),
        'db_fields': db_fields,
    })
    response = HttpResponse(html)
    response['Cache-Control'] = 'private, no-store'
    return response


@require_POST
@rate_limit('financial_estimate', limit=120, window=60)
def estimate(request, service_code):
    """Use the submission resolver for browser estimates; never accept a price."""
    from core.models import Service
    from core.financial_visibility import estimates_visible
    from core.pricing import resolve_cost
    from core.exceptions import PricingConfigurationError
    service = get_object_or_404(Service, code=service_code, active=True)
    channel = request.POST.get('channel', 'GENOCLAB')
    if channel not in ('IBTIKAR', 'GENOCLAB') or service.channel_availability not in ('BOTH', channel):
        return JsonResponse({'error': 'Invalid channel'}, status=400)
    if not estimates_visible(service=service):
        response = JsonResponse({'visible': False})
    else:
        params = {k[6:]: v for k,v in request.POST.items() if k.startswith('param_')}
        samples = {}
        for key, value in request.POST.items():
            if key.startswith('sample_'):
                parts = key.split('_', 2)
                if len(parts) == 3:
                    samples.setdefault(parts[1], {})[parts[2]] = value
        if len(samples) > 500:
            return JsonResponse({'error': 'Too many samples'}, status=400)
        try:
            result = resolve_cost(service, channel, sample_table=list(samples.values()), service_params=params,
                                  urgency=request.POST.get('urgency','Normal'))
            response = JsonResponse({'visible': True, 'total': str(result['total']), 'currency': 'DZD'})
        except PricingConfigurationError:
            response = JsonResponse({'visible': False, 'unavailable': True})
    response['Cache-Control'] = 'private, no-store'
    return response
