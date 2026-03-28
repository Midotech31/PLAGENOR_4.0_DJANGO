import uuid as uuid_lib
from django.shortcuts import render, redirect
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
    q = request.GET.get('q', '').strip()
    if q:
        tracked_request = Request.objects.filter(display_id__iexact=q).first()
        if not tracked_request:
            try:
                token = uuid_lib.UUID(q)
                tracked_request = Request.objects.filter(guest_token=token).first()
            except (ValueError, AttributeError):
                pass
    return render(request, 'pages/track.html', {'tracked_request': tracked_request})


def contact(request):
    return render(request, 'pages/contact.html')


def guest_submit(request):
    """Public guest submission form — no login required."""
    services_qs = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'GENOCLAB']
    ).order_by('code')

    if request.method == 'POST':
        guest_name = request.POST.get('guest_name', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
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
        count = Request.objects.filter(channel='GENOCLAB', created_at__year=year).count() + 1
        display_id = f"GCL-{year}-{count:04d}"
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

        req = Request.objects.create(
            display_id=display_id,
            title=title or f"Demande {service.name}",
            description=description,
            channel='GENOCLAB',
            status='REQUEST_CREATED',
            urgency=urgency,
            service=service,
            quote_amount=service.genoclab_price,
            submitted_as_guest=True,
            guest_token=guest_token,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            service_params=service_params,
            sample_table=sample_table_data,
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
