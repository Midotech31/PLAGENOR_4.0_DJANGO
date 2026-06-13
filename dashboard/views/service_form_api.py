"""API endpoint that returns HTML form fragment for a service's YAML-defined parameters."""
import json
from django.http import HttpResponse
from django.template.loader import render_to_string
from core.registry import get_service_def


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

    # Also load DB-defined custom fields. A SuperAdmin can define a whole
    # service's form here: fields tagged ``parameter`` become questions
    # (db_fields, serialized with their variable-pricing / conditional-logic
    # config), fields tagged ``sample_column`` become extra columns of the
    # per-sample table — so a brand-new service with no YAML still renders a
    # complete online form and a complete generated document.
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
        pass

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

    html = render_to_string('includes/service_form_fields.html', {
        'parameters': parameters,
        'sample_table': sample_table,
        'pricing': pricing,
        # ``data-pricing`` attribute on the cost-estimate box needs valid
        # JSON (not a Python dict repr) for ``JSON.parse`` to consume.
        'pricing_json': json.dumps(pricing, ensure_ascii=False),
        'service_code': service_code,
        'db_fields': db_fields,
    })
    return HttpResponse(html)
