from django.utils.translation import gettext as _
from django.http import QueryDict
from django.shortcuts import redirect

from core.ibtikar.legacy import mapped_values
from core.ibtikar.schema import schema_for_service
from core.ibtikar.views import profile_initial
from core.ibtikar.services import serializable


def open_legacy_submission(request, service):
    schema = schema_for_service(service)
    params = {key[6:]: request.POST.getlist(key) if len(request.POST.getlist(key)) > 1 else value
              for key, value in request.POST.items() if key.startswith('param_')}
    rows = {}
    for key, value in request.POST.items():
        if key.startswith('sample_') and len(key.split('_', 2)) == 3:
            prefix, index, name = key.split('_', 2)
            rows.setdefault(index, {})[name] = value
    applicant = profile_initial(request.user if request.user.is_authenticated else None)
    for key, dest in [('guest_name', 'full_name'), ('guest_email', 'email'), ('guest_phone', 'phone'),
                      ('organization', 'institution'), ('title', 'project_title'),
                      ('declared_balance', 'declared_balance'), ('ibtikar_id', 'ibtikar_id')]:
        if request.POST.get(key):
            applicant[dest] = request.POST[key]
    applicant.update(mapped_values(schema['applicant'], params))
    imported = {'applicant': applicant, 'parameters': mapped_values(schema['parameters'], params),
                'samples': [mapped_values(schema['samples'], value) for value in rows.values()],
                'legacy_data': {'requester_data': applicant, 'service_params': params, 'sample_table': list(rows.values())}}
    if len(str(imported)) > 500000:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(_('La demande dépasse la taille technique autorisée.'))
    request.session['ibtikar_import_' + service.code] = serializable(imported)
    return redirect('ibtikar:new', code=service.code)
