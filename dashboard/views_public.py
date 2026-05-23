import uuid as uuid_lib
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from datetime import datetime

from core.models import Service, Request, RequestHistory
from core.sequences import next_display_id
from dashboard.utils import safe_float

# Caps applied to guest-submitted payload — bound DB row size and rendered
# DOCX output (M3). Generous enough that no realistic submission is rejected.
MAX_GUEST_PARAMS = 200
MAX_GUEST_VALUE_LEN = 4096
MAX_GUEST_SAMPLE_ROWS = 200
MAX_GUEST_SAMPLE_COLS = 50


def home(request):
    services = Service.objects.filter(active=True)[:8]
    return render(request, 'pages/home.html', {'services': services})


def about(request):
    return render(request, 'pages/about.html')


def services(request):
    services = Service.objects.filter(active=True)
    return render(request, 'pages/services.html', {'services': services})


def track(request):
    """Public request tracking — UUID guest_token ONLY.

    The previous behaviour also matched the sequential ``display_id`` (e.g.
    ``GCL-2026-0001``) which let anonymous visitors enumerate the entire
    request stream. We now require the unguessable guest_token UUID issued
    in the confirmation email; ``display_id`` lookups are rejected.
    """
    tracked_request = None
    history = []
    q = request.GET.get('q', '').strip()
    if q:
        try:
            token = uuid_lib.UUID(q)
        except (ValueError, AttributeError):
            token = None
        if token is not None:
            tracked_request = Request.objects.filter(guest_token=token).first()
            if tracked_request:
                history = tracked_request.history.select_related('actor').order_by('created_at')
    return render(request, 'pages/track.html', {
        'tracked_request': tracked_request,
        'history': history,
    })


def contact(request):
    return render(request, 'pages/contact.html')


def service_detail(request, service_code):
    """Detailed service page showing full YAML definition."""
    from core.registry import get_service_def
    service = get_object_or_404(Service, code=service_code, active=True)
    yaml_def = get_service_def(service_code)
    return render(request, 'pages/service_detail.html', {
        'service': service,
        'yaml_def': yaml_def,
    })


def service_landing(request, service_code):
    """Landing page when a visitor clicks a service card."""
    service = get_object_or_404(Service, code=service_code, active=True)
    if request.user.is_authenticated:
        if request.user.role == 'REQUESTER':
            return redirect(f"{reverse('dashboard:requester')}?service={service.pk}")
        elif request.user.role == 'CLIENT':
            return redirect(f"{reverse('dashboard:client')}?service={service.pk}")
        else:
            return redirect('dashboard:router')
    return render(request, 'pages/service_landing.html', {'service': service})


def guest_submit(request):
    """Public guest submission form — no login required."""
    services_qs = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'GENOCLAB']
    ).order_by('code')

    if request.method == 'POST':
        guest_name = request.POST.get('guest_name', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        organization = request.POST.get('organization', '').strip()
        channel = request.POST.get('channel', 'GENOCLAB').strip()
        if channel not in ('IBTIKAR', 'GENOCLAB'):
            channel = 'GENOCLAB'
        service_id = request.POST.get('service_id', '')
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        urgency = request.POST.get('urgency', 'Normal')

        if not guest_name or not guest_email or not service_id:
            messages.error(request, "Veuillez remplir tous les champs obligatoires.")
            return render(request, 'pages/guest_submit.html', {
                'services': services_qs,
            })

        service = Service.objects.filter(pk=service_id, active=True).first()
        if not service:
            messages.error(request, "Service invalide.")
            return render(request, 'pages/guest_submit.html', {
                'services': services_qs,
            })

        # Generate display_id atomically (race-free) — guest GCL shares the
        # same sequence as registered GCL submissions; guest IBT has its own.
        year = datetime.now().year
        prefix = 'IBT' if channel == 'IBTIKAR' else 'GCL'
        display_id = next_display_id(
            prefix, year,
            initial_value_fn=lambda: Request.objects.filter(
                channel=channel, created_at__year=year,
                display_id__startswith=f'{prefix}-{year}-',
            ).count(),
        )
        guest_token = uuid_lib.uuid4()

        # Collect YAML parameter values — capped to prevent unbounded POST
        # payloads from bloating the row or downstream DOCX rendering.
        service_params = {}
        for key, val in request.POST.items():
            if not key.startswith('param_'):
                continue
            if len(service_params) >= MAX_GUEST_PARAMS:
                break
            service_params[key.replace('param_', '', 1)] = (val or '')[:MAX_GUEST_VALUE_LEN]

        # Collect sample table data with row/column caps.
        sample_data = {}
        for key, val in request.POST.items():
            if not key.startswith('sample_'):
                continue
            parts = key.split('_', 2)
            if len(parts) != 3:
                continue
            row_idx, col_name = parts[1], parts[2]
            row = sample_data.get(row_idx)
            if row is None:
                if len(sample_data) >= MAX_GUEST_SAMPLE_ROWS:
                    continue
                row = sample_data.setdefault(row_idx, {})
            if len(row) >= MAX_GUEST_SAMPLE_COLS:
                continue
            row[col_name] = (val or '')[:MAX_GUEST_VALUE_LEN]
        sample_table_data = list(sample_data.values()) if sample_data else []

        requester_data = {}
        if organization:
            requester_data['organization'] = organization

        # IBTIKAR-specific fields
        ibtikar_id = ''
        declared_balance = 0
        if channel == 'IBTIKAR':
            ibtikar_id = request.POST.get('ibtikar_id', '').strip()
            declared_balance = safe_float(request.POST.get('declared_balance'))
            if ibtikar_id:
                requester_data['ibtikar_id'] = ibtikar_id
            if declared_balance:
                requester_data['declared_ibtikar_balance'] = declared_balance

        quote = service.ibtikar_price if channel == 'IBTIKAR' else service.genoclab_price

        req = Request.objects.create(
            display_id=display_id,
            title=title or f"Demande {service.name}",
            description=description,
            channel=channel,
            status='REQUEST_CREATED',
            urgency=urgency,
            service=service,
            quote_amount=quote,
            submitted_as_guest=True,
            guest_token=guest_token,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            service_params=service_params,
            sample_table=sample_table_data,
            requester_data=requester_data,
        )

        RequestHistory.objects.create(
            request=req,
            from_status='',
            to_status='REQUEST_CREATED',
        )

        # Send email with tracking code
        try:
            from notifications.emails import notify_guest_tracking_code, notify_submission_confirmation
            notify_guest_tracking_code(req)
            notify_submission_confirmation(req)
        except Exception:
            pass

        return render(request, 'pages/guest_submit_success.html', {
            'req': req,
            'guest_token': guest_token,
        })

    return render(request, 'pages/guest_submit.html', {
        'services': services_qs,
    })


def guest_ibtikar_code(request, pk):
    """Guest submits their IBTIKAR-DGRSDT code via tracking page."""
    from django.contrib import messages as msg
    req = get_object_or_404(Request, pk=pk, submitted_as_guest=True)
    if request.method != 'POST':
        return redirect('track')
    code = request.POST.get('ibtikar_code', '').strip()
    if not code:
        msg.error(request, "Veuillez saisir votre code IBTIKAR.")
        return redirect(f"{reverse('track')}?q={req.guest_token}")
    req.ibtikar_external_code = code
    req.save(update_fields=['ibtikar_external_code'])
    if req.status == 'IBTIKAR_SUBMISSION_PENDING':
        try:
            from core.workflow import transition
            transition(req, 'IBTIKAR_CODE_SUBMITTED', None, notes=f'Code IBTIKAR (guest): {code}', force=True)
        except Exception:
            pass
    msg.success(request, "Votre code IBTIKAR a été transmis au responsable de la plateforme.")
    return redirect(f"{reverse('track')}?q={req.guest_token}")


def switch_language(request):
    """Switch language and redirect back. The `next` parameter is validated
    against the request host so this endpoint cannot be turned into an
    open-redirect link in a phishing email."""
    from django.utils import translation
    from django.conf import settings
    from django.http import HttpResponseRedirect
    from django.utils.http import url_has_allowed_host_and_scheme

    lang = request.POST.get('language', 'fr')
    next_url = request.POST.get('next', '/')
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = '/'

    if lang in dict(settings.LANGUAGES):
        translation.activate(lang)
        response = HttpResponseRedirect(next_url)
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=365*24*60*60)
        # Persist for authenticated users so PreferredLanguageMiddleware keeps
        # honouring this choice on subsequent requests (the cookie alone is
        # ignored for logged-in users by design).
        if request.user.is_authenticated:
            try:
                request.user.preferred_language = lang
                request.user.save(update_fields=['preferred_language'])
            except Exception:
                pass
        return response

    return HttpResponseRedirect(next_url)
