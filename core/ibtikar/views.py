import json
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language, gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from core.exceptions import PricingConfigurationError
from core.service_eligibility import services_for
from core.ibtikar.forms import SchemaForm, cleaned_samples, make_sample_formset
from core.ibtikar.legacy import legacy_initial
from core.ibtikar.models import IbtikarAttachment, IbtikarSubmission
from core.ibtikar.schema import definitions, get_schema, label, projection, active_names, schema_for_service, active_data
from core.ibtikar.services import EDITABLE, save_staff, save_submission, serializable
from core.models import FinancialVisibility, Request, Service
from core.ratelimit import rate_limit


def user_actor(request):
    return request.user if request.user.is_authenticated and request.user.is_active else None


def may_read(user, req):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if req.requester_id == user.pk or user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'):
        return True
    if user.role == 'MEMBER':
        return bool((req.assigned_to_id and req.assigned_to.user_id == user.pk)
                    or req.informed_members.filter(user_id=user.pk).exists())
    return False


def get_request(request, pk=None, token=None):
    if token:
        return get_object_or_404(Request, guest_token=token, submitted_as_guest=True, channel='IBTIKAR')
    req = get_object_or_404(Request, pk=pk, channel='IBTIKAR')
    if not may_read(user_actor(request), req):
        raise Http404
    return req


def may_edit(request, req, token=None):
    if req.status not in EDITABLE:
        return False
    if token and req.submitted_as_guest and req.guest_token == token:
        return req.status in ('DRAFT', 'SUBMITTED')
    user = user_actor(request)
    return bool(user and (user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')
                         or req.requester_id == user.pk and req.status in ('DRAFT', 'SUBMITTED')))


def detail_url(req, token=None):
    return reverse('ibtikar:guest_detail', args=[token]) if token else reverse('ibtikar:detail', args=[req.pk])


def visible_prices(request):
    user = user_actor(request)
    return bool(user and user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE', 'MEMBER')) or FinancialVisibility.estimates_visible()


def index(request):
    services = services_for('IBTIKAR').order_by('code')
    own = Request.objects.filter(requester=request.user, channel='IBTIKAR').select_related('service')[:100] if request.user.is_authenticated else []
    return render(request, 'ibtikar/index.html', {'services': services, 'own_requests': own})


def profile_initial(user):
    if not user:
        return {}
    initial = {'full_name': user.get_full_name(), 'institution': user.organization,
               'laboratory': user.laboratory, 'email': user.email, 'phone': user.phone,
               'supervisor': user.supervisor, 'supervisor_email': user.supervisor_email,
               'ibtikar_id': user.ibtikar_id, 'declared_balance': user.ibtikar_declared_balance}
    return {k: v for k, v in initial.items() if v is not None and v != ''}


def form_context(schema, app_form, param_form, formset, upload_form, **extra):
    return {'schema': schema, 'schema_title': label(schema['title'], get_language() or 'fr'),
            'applicant_form': app_form, 'parameter_form': param_form,
            'sample_formset': formset, 'upload_form': upload_form,
            'form_rules': schema.get('rules', []),
            'notices': [label(x, get_language() or 'fr') for x in schema.get('notices', [])], **extra}


@never_cache
@rate_limit('ibtikar_form_save', limit=30, window=3600)
def editor(request, code=None, pk=None, token=None):
    actor = user_actor(request)
    req = get_request(request, pk, token) if pk or token else None
    if req and not may_edit(request, req, token):
        return HttpResponseForbidden(_('Cette demande est en lecture seule à ce stade.'))
    if not req and actor and actor.role not in ('REQUESTER', 'CLIENT', 'SUPER_ADMIN', 'PLATFORM_ADMIN'):
        return HttpResponseForbidden()
    service = req.service if req else get_object_or_404(services_for('IBTIKAR'), code=code)
    if service is None:
        raise Http404
    current = IbtikarSubmission.objects.filter(request=req).first() if req else None
    schema = current.schema if current else schema_for_service(service)
    if not schema:
        raise Http404
    legacy = legacy_initial(req, schema) if req and not current else None
    imported = request.session.get('ibtikar_import_' + service.code) if not req else None
    initial = ({'applicant': current.applicant, 'parameters': current.parameters, 'samples': current.samples}
               if current else legacy or imported or {'applicant': profile_initial(actor), 'parameters': {}, 'samples': []})
    existing = {x.field_name: x for x in current.attachments.filter(active=True)} if current else {}
    draft = request.method == 'POST' and request.POST.get('action') == 'draft'
    bound = request.POST if request.method == 'POST' else None
    app_form = SchemaForm(bound, initial=initial['applicant'], prefix='applicant',
                          specs=schema['applicant'], require_complete=not draft)
    param_form = SchemaForm(bound, initial=initial['parameters'], prefix='parameters',
                            specs=schema['parameters'], require_complete=not draft)
    parameter_values = active_data(schema, 'parameters', initial['parameters'])
    if bound is not None:
        param_form.is_valid()
        parameter_values = active_data(schema, 'parameters', param_form.cleaned_data)
    formset = make_sample_formset(schema, bound, initial['samples'], parameter_values, require_complete=not draft)
    sample_values = initial['samples']
    if bound is not None:
        formset.is_valid()
        sample_values = cleaned_samples(formset)
    upload_form = SchemaForm(bound, request.FILES if bound is not None else None,
                             specs=schema['attachments'], prefix='attachments',
                             parameters=parameter_values, samples=[active_data(schema, 'samples', row, parameter_values) for row in sample_values],
                             existing_files=existing, require_complete=not draft)
    errors = []
    if bound is not None:
        valid = app_form.is_valid() & param_form.is_valid() & formset.is_valid() & upload_form.is_valid()
        if not sample_values and not draft:
            errors.append(_('Ajoutez au moins un échantillon ou une amorce.'))
            valid = False
        if req and draft and req.status != 'DRAFT':
            errors.append(_('Une demande déjà soumise doit être enregistrée comme révision, pas comme brouillon.'))
            valid = False
        try:
            revision = int(request.POST.get('revision', '0'))
        except ValueError:
            revision = -1
        if valid:
            try:
                saved = save_submission(service=service, schema=schema,
                    applicant=app_form.cleaned_data, parameters=param_form.cleaned_data,
                    samples=sample_values, files=upload_form.cleaned_data, actor=actor,
                    req=req, revision=revision, draft=draft,
                    legacy_data=legacy['legacy_data'] if legacy else imported.get('legacy_data') if imported else None)
            except (ValidationError, PricingConfigurationError) as exc:
                errors.extend(exc.messages if isinstance(exc, ValidationError) else [str(exc)])
            else:
                request.session.pop('ibtikar_import_' + service.code, None)
                messages.success(request, _('Le formulaire a été enregistré sans modifier les champs non applicables.'))
                guest_token = token or (saved.request.guest_token if not actor else None)
                return redirect(detail_url(saved.request, guest_token))
    existing_rows = [{'field': label(next(x['label'] for x in schema['attachments'] if x['name'] == key), get_language() or 'fr'),
                      'name': file.original_name, 'url': reverse('ibtikar:attachment', args=[file.pk]) + (f'?access={token}' if token else '')}
                     for key, file in existing.items() if any(x['name'] == key for x in schema['attachments'])]
    context = form_context(schema, app_form, param_form, formset, upload_form,
        req=req, revision=current.revision if current else 0, errors=errors,
        existing_attachments=existing_rows, legacy=bool(legacy or imported),
        allow_draft=not req or req.status == 'DRAFT', prices_visible=visible_prices(request),
        estimate_url=reverse('ibtikar:estimate', args=[service.code]) + (('?request=' + str(req.pk) + ('&access=' + str(token) if token else '')) if req else ''))
    return render(request, 'ibtikar/editor.html', context, status=400 if bound is not None else 200)


@never_cache
def detail(request, pk=None, token=None):
    req = get_request(request, pk, token)
    current = IbtikarSubmission.objects.filter(request=req).first()
    user = user_actor(request)
    if current:
        project = projection(current.schema, current.applicant, current.parameters,
                             current.samples, current.staff, get_language() or 'fr')
        if not visible_prices(request):
            project['staff'] = [row for row in project['staff'] if row['name'] not in ('validated_price', 'price_justification')]
        active = active_names(current.schema['attachments'], {}, current.parameters, [active_data(current.schema, 'samples', row, current.parameters) for row in current.samples])
        attachments = [{'label': label(spec['label'], get_language() or 'fr'), 'name': file.original_name,
                        'url': reverse('ibtikar:attachment', args=[file.pk]) + (f'?access={token}' if token else '')}
                       for spec in current.schema['attachments'] if spec['name'] in active
                       for file in current.attachments.filter(field_name=spec['name'], active=True)]
    else:
        project = None
        attachments = []
    return render(request, 'ibtikar/detail.html', {
        'req': req, 'submission': current, 'projection': project, 'attachments': attachments,
        'can_edit': may_edit(request, req, token),
        'edit_url': reverse('ibtikar:guest_edit', args=[token]) if token else reverse('ibtikar:edit', args=[req.pk]),
        'document_url': reverse('documents:guest_ibtikar_form', args=[token]) if token else reverse('documents:ibtikar_form', args=[req.pk]),
        'can_staff': bool(req.status not in ('COMPLETED', 'CLOSED', 'ARCHIVED', 'REJECTED') and user and (user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')
                          or user.role == 'MEMBER' and req.assigned_to_id and req.assigned_to.user_id == user.pk)),
        'prices_visible': visible_prices(request), 'guest_token': token,
        'operations_url': (reverse('track') + '?q=' + str(token)) if token else (reverse('dashboard:requester_request_detail', args=[req.pk]) if user and user.role == 'REQUESTER' else reverse('dashboard:admin_request_detail', args=[req.pk]) if user and user.role in ('SUPER_ADMIN','PLATFORM_ADMIN') else reverse('dashboard:router')),
        'code_url': reverse('ibtikar:guest_code', args=[token]) if token else reverse('ibtikar:code', args=[req.pk]),
        'can_code': req.status in ('IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED') and (bool(token) or bool(user and req.requester_id == user.pk)),
    })


@never_cache
def staff_editor(request, pk):
    req = get_request(request, pk)
    current = get_object_or_404(IbtikarSubmission, request=req)
    user = user_actor(request)
    allowed = user and (user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN') or
                       user.role == 'MEMBER' and req.assigned_to_id and req.assigned_to.user_id == user.pk)
    if not allowed:
        return HttpResponseForbidden()
    specs = current.schema['staff']
    if user.role == 'MEMBER':
        specs = [s for s in specs if s['name'] not in ('validated_price', 'price_justification',
                  'administrative_validation', 'head_visa', 'director_visa')]
    form = SchemaForm(request.POST if request.method == 'POST' else None,
                      prefix='staff', specs=specs, initial=current.staff)
    errors = []
    if request.method == 'POST' and form.is_valid():
        try:
            save_staff(current.pk, form.cleaned_data, user, int(request.POST.get('revision', '0')))
        except (ValidationError, ValueError) as exc:
            errors.extend(exc.messages if isinstance(exc, ValidationError) else [str(exc)])
        else:
            return redirect('ibtikar:detail', pk=req.pk)
    return render(request, 'ibtikar/staff.html', {'req': req, 'form': form,
                   'revision': current.revision, 'errors': errors, 'estimate': current.estimate},
                   status=400 if request.method == 'POST' else 200)


@never_cache
def attachment(request, pk):
    obj = get_object_or_404(IbtikarAttachment.objects.select_related('submission__request'), pk=pk)
    req = obj.submission.request
    access = request.GET.get('access', '')
    guest_access = bool(req.submitted_as_guest and req.guest_token and access == str(req.guest_token))
    if not guest_access and not may_read(user_actor(request), req):
        raise Http404
    try:
        response = FileResponse(obj.file.open('rb'), as_attachment=True, filename=obj.original_name)
    except (FileNotFoundError, OSError):
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@require_POST
@never_cache
@rate_limit('ibtikar_estimate', limit=120, window=300)
def estimate(request, code):
    if not visible_prices(request):
        return JsonResponse({'visible': False})
    service = get_object_or_404(services_for('IBTIKAR'), code=code)
    schema = schema_for_service(service)
    if request.GET.get('request'):
        try:
            req = get_request(request, pk=request.GET['request'], token=request.GET.get('access'))
        except (ValidationError, ValueError):
            raise Http404
        if req.service_id != service.pk:
            raise Http404
        current = IbtikarSubmission.objects.filter(request=req).first()
        schema = current.schema if current else schema
    if not schema:
        raise Http404
    params = SchemaForm(request.POST, specs=schema['parameters'], prefix='parameters')
    params.is_valid()
    rows = make_sample_formset(schema, request.POST, parameters=active_data(schema, 'parameters', params.cleaned_data))
    if not params.is_valid() or not rows.is_valid():
        return JsonResponse({'visible': True, 'status': 'incomplete', 'total': None})
    from core.pricing import resolve_cost
    try:
        result = resolve_cost(service, 'IBTIKAR', cleaned_samples(rows),
                              {**params.cleaned_data, '_ibtikar_schema': schema['version']}, ibtikar_schema=schema)
    except PricingConfigurationError:
        return JsonResponse({'visible': True, 'status': 'pending', 'total': None})
    return JsonResponse({'visible': True, 'status': result['status'],
                         'total': str(result['total']) if result['total'] is not None else None,
                         'currency': 'DZD'})


@require_POST
@never_cache
@rate_limit('ibtikar_reference', limit=20, window=3600)
def submit_code(request, pk=None, token=None):
    from core.ibtikar.services import record_code
    req = get_request(request, pk, token)
    actor = None if token else user_actor(request)
    if not token and (not actor or req.requester_id != actor.pk):
        raise Http404
    try:
        record_code(req, request.POST.get('ibtikar_code', '').strip(), actor, guest_token=token)
    except ValidationError as exc:
        messages.error(request, ' '.join(exc.messages))
    return redirect(detail_url(req, token))
