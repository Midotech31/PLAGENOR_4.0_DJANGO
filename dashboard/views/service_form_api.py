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
        return HttpResponse('<p class="text-muted">Service non trouvé.</p>')

    parameters = definition.get('parameters', [])
    sample_table = definition.get('sample_table', {})
    pricing = definition.get('pricing', {}) or {}

    # Also load DB-defined custom fields if ServiceFormField model exists
    db_fields = []
    try:
        from core.models import Service, ServiceFormField
        svc = Service.objects.filter(code=service_code).first()
        if svc:
            db_fields = list(svc.custom_fields.all().values('name', 'label', 'field_type', 'options', 'required'))
    except Exception:
        pass

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
