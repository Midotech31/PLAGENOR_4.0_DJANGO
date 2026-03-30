import uuid as uuid_lib
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from datetime import datetime

from core.models import Service, Request, RequestHistory


def home(request):
    services = Service.objects.filter(active=True)[:8]
    return render(request, 'pages/home.html', {'services': services})


def about(request):
    return render(request, 'pages/about.html')


def services(request):
    services = Service.objects.filter(active=True)
    return render(request, 'pages/services.html', {'services': services})


def track(request):
    tracked_request = None
    history = []
    q = request.GET.get('q', '').strip()
    if q:
        tracked_request = Request.objects.filter(display_id__iexact=q).first()
        if not tracked_request:
            try:
                token = uuid_lib.UUID(q)
                tracked_request = Request.objects.filter(guest_token=token).first()
            except (ValueError, AttributeError):
                pass
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

        # Generate display_id
        year = datetime.now().year
        prefix = 'IBT' if channel == 'IBTIKAR' else 'GCL'
        count = Request.objects.filter(channel=channel, created_at__year=year).count() + 1
        display_id = f"{prefix}-{year}-{count:04d}"
        guest_token = uuid_lib.uuid4()

        # Collect YAML parameter values
        service_params = {key.replace('param_', '', 1): val for key, val in request.POST.items() if key.startswith('param_')}
        # Collect sample table data
        sample_data = {}
        for key, val in request.POST.items():
            if key.startswith('sample_'):
                parts = key.split('_', 2)
                if len(parts) == 3:
                    row_idx, col_name = parts[1], parts[2]
                    sample_data.setdefault(row_idx, {})[col_name] = val
        sample_table_data = list(sample_data.values()) if sample_data else []

        requester_data = {}
        if organization:
            requester_data['organization'] = organization

        # IBTIKAR-specific fields
        ibtikar_id = ''
        declared_balance = 0
        if channel == 'IBTIKAR':
            ibtikar_id = request.POST.get('ibtikar_id', '').strip()
            declared_balance = float(request.POST.get('declared_balance', 0) or 0)
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
        return redirect(f"{reverse('track')}?q={req.display_id}")
    req.ibtikar_external_code = code
    req.save(update_fields=['ibtikar_external_code'])
    if req.status == 'IBTIKAR_SUBMISSION_PENDING':
        try:
            from core.workflow import transition
            transition(req, 'IBTIKAR_CODE_SUBMITTED', None, notes=f'Code IBTIKAR (guest): {code}', force=True)
        except Exception:
            pass
    msg.success(request, "Votre code IBTIKAR a été transmis au responsable de la plateforme.")
    return redirect(f"{reverse('track')}?q={req.display_id}")


def switch_language(request):
    """Switch language and redirect back."""
    from django.utils import translation
    from django.conf import settings
    from django.http import HttpResponseRedirect
    
    lang = request.POST.get('language', 'fr')
    next_url = request.POST.get('next', '/')
    
    if lang in dict(settings.LANGUAGES):
        translation.activate(lang)
        response = HttpResponseRedirect(next_url)
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang, max_age=365*24*60*60)
        return response
    
    return redirect(next_url)
