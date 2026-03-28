"""API endpoint that returns HTML form fragment for a service's YAML-defined parameters."""
from django.http import HttpResponse
from django.template.loader import render_to_string
from core.registry import get_service_def


def service_form_fragment(request, service_code):
    """Return rendered HTML for a service's YAML parameters + sample table."""
    definition = get_service_def(service_code)
    if not definition:
        return HttpResponse('<p class="text-muted">Service non trouvé.</p>')

    parameters = definition.get('parameters', [])
    sample_table = definition.get('sample_table', {})
    pricing = definition.get('pricing', {})

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
        'service_code': service_code,
        'db_fields': db_fields,
    })
    return HttpResponse(html)
