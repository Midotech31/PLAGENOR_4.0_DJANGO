import uuid as uuid_lib
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from datetime import datetime

from accounts.countries import COUNTRY_CHOICES
from core.models import Service, Request, RequestHistory
from core.ratelimit import rate_limit
from core.exceptions import PricingConfigurationError
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


def privacy(request):
    """Privacy / legal notice page. All text is CMS-editable (privacy_* keys)
    with sensible French defaults baked into the template."""
    return render(request, 'pages/privacy.html')


def export_my_data(request):
    """Personal-data export (data-access right): the requesting user downloads
    a JSON of their account fields + a summary of their own requests."""
    from django.contrib.auth.decorators import login_required as _lr
    from django.http import JsonResponse

    @_lr
    def _inner(req):
        u = req.user
        data = {
            'account': {
                'username': u.username, 'email': u.email,
                'first_name': u.first_name, 'last_name': u.last_name,
                'role': u.role, 'organization': u.organization,
                'organization_type': u.organization_type,
                'country': u.country, 'phone': u.phone,
                'wilaya': u.wilaya, 'gender': u.gender,
                'date_joined': u.date_joined.isoformat() if u.date_joined else None,
                'preferred_language': u.preferred_language,
                'two_factor_enabled': u.totp_enabled,
            },
            'requests': [
                {
                    'display_id': r.display_id, 'channel': r.channel,
                    'status': r.status, 'title': r.title,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                    'service_rating': r.service_rating,
                }
                for r in Request.objects.filter(requester=u).order_by('created_at')
            ],
        }
        resp = JsonResponse(data, json_dumps_params={'indent': 2, 'ensure_ascii': False})
        resp['Content-Disposition'] = 'attachment; filename="mes-donnees-plagenor.json"'
        return resp
    return _inner(request)


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
                # Backfill legacy report rows created before tokens were
                # assigned at upload time.  Without this, rendering the guest
                # download URL raises NoReverseMatch on completed requests.
                if tracked_request.report_file and not tracked_request.report_token:
                    tracked_request.report_token = uuid_lib.uuid4()
                    tracked_request.save(update_fields=['report_token'])
                history = tracked_request.history.select_related('actor').order_by('created_at')
    return render(request, 'pages/track.html', {
        'tracked_request': tracked_request,
        'history': history,
    })


def contact(request):
    return render(request, 'pages/contact.html')


def help_center(request):
    """Multilingual help center (FR/EN/AR), public.

    All copy is {% trans %}/{% blocktrans %} so it follows the active
    language + RTL automatically. When a user is logged in we pass their
    role so the template can highlight the guide that matters to them.
    """
    role = getattr(request.user, 'role', '') if request.user.is_authenticated else ''
    return render(request, 'pages/help.html', {'user_role': role})


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


@rate_limit('guest_submit', limit=10, window=3600)
def guest_submit(request):
    """Public guest submission form — no login required.

    Services for both channels are shown; the template filters the dropdown
    client-side based on the chosen channel. Server-side, we re-check that
    the chosen service is actually available on the chosen channel — the
    client filter is UX, not a security boundary.
    """
    services_qs = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'IBTIKAR', 'GENOCLAB'],
    ).order_by('code')

    if request.method == 'POST':
        guest_name = request.POST.get('guest_name', '').strip()
        guest_email = request.POST.get('guest_email', '').strip()
        guest_phone = request.POST.get('guest_phone', '').strip()
        organization = request.POST.get('organization', '').strip()
        organization_type = request.POST.get('organization_type', '').strip()
        # Whitelist against the model's declared choices — client-side selects
        # are advisory only; a crafted POST could store arbitrary strings.
        from accounts.models import User as _User
        _valid_org_types = {c for c, _ in _User.ORGANIZATION_TYPE_CHOICES}
        if organization_type not in _valid_org_types:
            organization_type = ''
        organization_type_other = request.POST.get('organization_type_other', '').strip()
        country = request.POST.get('country', '').strip()
        _valid_countries = {c for c, _ in COUNTRY_CHOICES}
        if country not in _valid_countries:
            country = ''
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
                'country_choices': COUNTRY_CHOICES,
            })

        service = Service.objects.filter(pk=service_id, active=True).first()
        if not service:
            messages.error(request, "Service invalide.")
            return render(request, 'pages/guest_submit.html', {
                'services': services_qs,
                'country_choices': COUNTRY_CHOICES,
            })

        # Re-check the service is actually available on the chosen channel
        # — the template's client-side filter is UX only; users can craft a
        # POST that bypasses it.
        if service.channel_availability not in ('BOTH', channel):
            messages.error(request, "Ce service n'est pas disponible sur le canal choisi.")
            return render(request, 'pages/guest_submit.html', {
                'services': services_qs,
                'country_choices': COUNTRY_CHOICES,
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
        if organization_type:
            requester_data['organization_type'] = organization_type
        if organization_type == 'autre' and organization_type_other:
            requester_data['organization_type_other'] = organization_type_other
        if country:
            requester_data['country'] = country

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

        # Use the canonical pricing resolver so guest submissions price the
        # same way as authenticated submissions (DB tiers → YAML → flat).
        from core.pricing import resolve_cost
        try:
            _price_result = resolve_cost(
                service, channel,
                sample_table=sample_table_data,
                service_params=service_params,
                urgency=urgency,
            )
        except PricingConfigurationError:
            messages.error(request, "La tarification de ce service est temporairement indisponible. Veuillez contacter l'administration.")
            return render(request, 'pages/guest_submit.html', {
                'services': services_qs,
                'country_choices': COUNTRY_CHOICES,
            })
        quote = _price_result['total']

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
        'country_choices': COUNTRY_CHOICES,
    })


def guest_ibtikar_code(request, token):
    """Guest submits their IBTIKAR-DGRSDT code via tracking page."""
    from django.contrib import messages as msg
    # The unguessable guest token is the authorization capability.  Using the
    # request primary key here allowed anyone who learned a request UUID to
    # alter its external IBTIKAR code without possessing the tracking token.
    req = get_object_or_404(
        Request, guest_token=token, submitted_as_guest=True,
    )
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
