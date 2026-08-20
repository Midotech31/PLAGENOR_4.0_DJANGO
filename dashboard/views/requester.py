import uuid
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back, redirect_to_detail, safe_int, safe_float, confirm_appointment_flow
from django.contrib import messages
from django.utils import timezone

from core.models import Service, Request
from core.services.ibtikar import submit_ibtikar_request, get_ibtikar_request_context
from core.financial import check_ibtikar_budget
from core.exceptions import PricingConfigurationError
from notifications.models import Notification


def requester_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'REQUESTER':
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@requester_required
def index(request):
    my_requests = Request.objects.filter(requester=request.user, channel='IBTIKAR')
    total = my_requests.count()
    active = my_requests.exclude(status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']).count()
    completed = my_requests.filter(status__in=['COMPLETED', 'CLOSED']).count()
    rejected = my_requests.filter(status='REJECTED').count()

    # Active requests
    active_requests = my_requests.exclude(
        status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']
    ).select_related('service', 'assigned_to__user').order_by('-created_at')

    # Archives
    archived = my_requests.filter(
        status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
    ).select_related('service').order_by('-updated_at')[:30]

    # Lazy backfill: any archived request with an uploaded report but
    # no report_token gets one now, so the archives table can route the
    # download through the gated /report/<token>/ view (the only path
    # that enforces the citation clause). Cheap — only fires for the
    # handful of legacy rows without a token.
    import uuid as _uuid
    for _req in archived:
        if _req.report_file and not _req.report_token:
            _req.report_token = _uuid.uuid4()
            _req.save(update_fields=['report_token'])

    # Available services for new request
    services = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'IBTIKAR']
    ).order_by('code')

    # Budget context from IBTIKAR service
    budget_context = get_ibtikar_request_context(request.user)

    # Notifications
    notifications = Notification.objects.filter(user=request.user, read=False).order_by('-created_at')[:10]

    context = {
        'total': total,
        'active': active,
        'completed': completed,
        'rejected': rejected,
        'active_requests': active_requests,
        'archived': archived,
        'services': services,
        'budget_context': budget_context,
        'notifications': notifications,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/requester/index.html', context)


@requester_required
def request_detail(request, pk):
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    # Lazy backfill: any uploaded report needs a report_token so the
    # download passes through the gated /report/<token>/ route + citation
    # clause. Older rows (created before the token was introduced)
    # otherwise fell back to the raw /media/ URL, bypassing the gate.
    if req.report_file and not req.report_token:
        import uuid as _uuid
        req.report_token = _uuid.uuid4()
        req.save(update_fields=['report_token'])
    from core.registry import get_service_def
    yaml_def = get_service_def(req.service.code) if req.service else None

    # Build parameter labels from YAML for better display
    param_labels = {}
    if yaml_def:
        for p in yaml_def.get('parameters', []):
            param_labels[p['name']] = p.get('label', p['name'])

    # Build display-ready parameters list: [(label, value), ...]
    params_display = []
    if req.service_params:
        for key, value in req.service_params.items():
            label = param_labels.get(key, key.replace('_', ' ').title())
            params_display.append((label, value))

    # Build sample table column labels
    sample_col_labels = {}
    if yaml_def:
        st = yaml_def.get('sample_table', {})
        for col in st.get('columns', []):
            sample_col_labels[col['name']] = col.get('label', col['name'])

    # Build display-ready sample headers
    sample_headers = []
    if req.sample_table and len(req.sample_table) > 0:
        for key in req.sample_table[0].keys():
            sample_headers.append(sample_col_labels.get(key, key.replace('_', ' ').title()))

    from core.models import Message
    messages_list = Message.objects.filter(
        request=req, to_user=request.user
    ).select_related('from_user').order_by('created_at')

    # Workflow history — same view as the analyst's, so the requester
    # can follow the progress of their own request step by step.
    history = req.history.select_related('actor').order_by('created_at')

    context = {
        'req': req,
        'params_display': params_display,
        'sample_headers': sample_headers,
        'messages_list': messages_list,
        'history': history,
        # Le RDV est « en attente » (donc à confirmer par le demandeur)
        # uniquement s'il a une date, n'est pas déjà confirmé, et que le
        # statut est encore au stade proposition/assignation.
        'appointment_pending': bool(
            req.appointment_date and not req.appointment_confirmed
            and req.status in ('APPOINTMENT_PROPOSED', 'ASSIGNED')
        ),
    }
    return render(request, 'dashboard/requester/request_detail.html', context)


@requester_required
def declare_ibtikar_balance(request):
    """Self-declared residual IBTIKAR balance.

    Stored on User (not on the request) so it persists across requests:
    once declared, every new request is sized against this number and
    every report-delivery deducts from it. The candidate can revise the
    figure at any time — the DGRSDT IBTIKAR budget is shared across
    multiple platforms, so the candidate is the only one who knows the
    true current residual.
    """
    if request.method != 'POST':
        return HttpResponseForbidden()
    from django.conf import settings as _s
    raw = request.POST.get('declared_balance', '').strip()
    try:
        declared = float(raw)
    except (TypeError, ValueError):
        messages.error(request, "Veuillez saisir un montant valide.")
        return redirect_back(request, 'dashboard:requester')

    hard_cap = float(_s.IBTIKAR_BUDGET_CAP)
    if declared < 0 or declared > hard_cap:
        messages.error(
            request,
            f"Le solde déclaré doit être compris entre 0 et {hard_cap:,.0f} DA.",
        )
        return redirect_back(request, 'dashboard:requester')

    request.user.ibtikar_declared_balance = declared
    request.user.ibtikar_balance_declared_at = timezone.now()
    request.user.save(update_fields=[
        'ibtikar_declared_balance', 'ibtikar_balance_declared_at',
    ])
    messages.success(
        request,
        f"Solde IBTIKAR mis à jour : {declared:,.0f} DA. Vous pouvez maintenant soumettre votre demande.",
    )
    return redirect_back(request, 'dashboard:requester')


@requester_required
def create_request(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service_id = request.POST.get('service_id')
    service = get_object_or_404(Service, pk=service_id, active=True)

    # Guard 1 — the requester must have declared a residual balance
    # before any submission. Without a declared value we cannot size or
    # cap-check a request, so reject the POST early with a clear redirect
    # back to the dashboard where the declaration card is shown.
    if request.user.ibtikar_declared_balance is None:
        messages.error(
            request,
            "Vous devez d'abord déclarer votre solde IBTIKAR résiduel "
            "avant de soumettre une demande.",
        )
        return redirect_back(request, 'dashboard:requester')
    declared = float(request.user.ibtikar_declared_balance)

    # Collect YAML parameter values
    service_params = {key.replace('param_', '', 1): val for key, val in request.POST.items() if key.startswith('param_')}
    sample_data = {}
    for key, val in request.POST.items():
        if key.startswith('sample_'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                sample_data.setdefault(parts[1], {})[parts[2]] = val
    sample_table_data = list(sample_data.values()) if sample_data else []

    # Resolve cost via the canonical pricing resolver (DB tiers → YAML →
    # flat). See core.pricing.resolve_cost for the precedence and rationale.
    from core.pricing import resolve_cost
    try:
        price_result = resolve_cost(
            service, 'IBTIKAR',
            sample_table=sample_table_data,
            service_params=service_params,
            urgency=request.POST.get('urgency', 'Normal'),
        )
    except PricingConfigurationError:
        messages.error(request, "La tarification de ce service doit être corrigée par un administrateur avant la soumission.")
        return redirect_back(request, 'dashboard:requester')
    budget_amount = price_result['total']

    # Budget guard — runs against the requester's DECLARED residual
    # balance (User.ibtikar_declared_balance), not a flat 200K. The
    # resolved cost is the basis; checking the flat service price would
    # let a multi-sample request slip past the cap.
    budget_check = check_ibtikar_budget(amount=budget_amount, requester=request.user)
    if budget_check['exceeded']:
        messages.error(
            request,
            f"Coût estimé ({budget_amount:,.0f} DA) supérieur à votre solde déclaré "
            f"({declared:,.0f} DA). Mettez à jour votre solde si vous avez vérifié "
            f"votre compte DGRSDT, ou contactez l'administrateur."
        )
        return redirect_back(request, 'dashboard:requester')

    # Use ibtikar service to submit
    req = submit_ibtikar_request(
        data={
            'title': request.POST.get('title', f"Demande {service.name}"),
            'description': request.POST.get('description', ''),
            'urgency': request.POST.get('urgency', 'Normal'),
            'service_id': str(service.pk),
            'budget_amount': budget_amount,
            'declared_ibtikar_balance': declared,
            'service_params': service_params,
            'sample_table': sample_table_data,
        },
        user=request.user,
    )
    messages.success(request, f"Demande {req.display_id} soumise avec succès.")
    return redirect_to_detail(request, req, 'dashboard:requester')


@requester_required
def confirm_receipt(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.receipt_confirmed = True
    req.receipt_confirmed_at = timezone.now()
    req.save(update_fields=['receipt_confirmed', 'receipt_confirmed_at'])
    # Transition SENT_TO_REQUESTER → COMPLETED
    if req.status == 'SENT_TO_REQUESTER':
        try:
            from core.workflow import transition
            from core.exceptions import InvalidTransitionError, AuthorizationError
            transition(req, 'COMPLETED', request.user, notes='Réception confirmée par le demandeur')
        except (InvalidTransitionError, AuthorizationError, ValueError):
            pass
    # Notify admin + analyst that report was downloaded/confirmed
    from accounts.models import User
    admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
    for admin in admins:
        Notification.objects.create(
            user=admin,
            message=f"{req.display_id}: Rapport téléchargé et réception confirmée par le demandeur.",
            request=req,
            notification_type='WORKFLOW',
        )
    if req.assigned_to:
        Notification.objects.create(
            user=req.assigned_to.user,
            message=f"{req.display_id}: Rapport téléchargé et réception confirmée par le demandeur.",
            request=req,
            notification_type='WORKFLOW',
        )
    messages.success(request, f"Réception confirmée pour {req.display_id}.")
    return redirect_to_detail(request, req, 'dashboard:requester')


@requester_required
def confirm_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    confirm_appointment_flow(request, req)
    return redirect_to_detail(request, req, 'dashboard:requester')


@requester_required
def suggest_alternative_date(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    alt_date = request.POST.get('alt_date', '')
    alt_note = request.POST.get('alt_note', '')
    if alt_date:
        from datetime import datetime as dt
        from core.models import RequestComment
        try:
            parsed_date = dt.strptime(alt_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Date invalide.")
            return redirect_to_detail(request, req, 'dashboard:requester')
        # Store the alternative date on the request
        req.alt_date_proposed = parsed_date
        req.alt_date_note = alt_note
        req.save(update_fields=['alt_date_proposed', 'alt_date_note'])
        # Also log as comment for audit trail
        RequestComment.objects.create(
            request=req, author=request.user,
            text=f"Date alternative proposée: {alt_date}. {alt_note}".strip(),
            step=req.status
        )
        # Notify the assigned analyst
        if req.assigned_to:
            Notification.objects.create(
                user=req.assigned_to.user,
                message=f"{req.display_id}: Date alternative proposée — {parsed_date.strftime('%d/%m/%Y')}",
                request=req,
                notification_type='WORKFLOW',
            )
        messages.success(request, f"Date alternative proposée: {parsed_date.strftime('%d/%m/%Y')}")
    return redirect_to_detail(request, req, 'dashboard:requester')


@requester_required
def submit_ibtikar_code(request, pk):
    """Requester submits their IBTIKAR-DGRSDT code."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    code = request.POST.get('ibtikar_code', '').strip()
    if not code:
        messages.error(request, "Veuillez saisir votre code IBTIKAR.")
        return redirect_to_detail(request, req, 'dashboard:requester')
    req.ibtikar_external_code = code
    req.save(update_fields=['ibtikar_external_code'])
    if req.status == 'IBTIKAR_SUBMISSION_PENDING':
        try:
            from core.workflow import transition
            from core.exceptions import InvalidTransitionError, AuthorizationError
            transition(req, 'IBTIKAR_CODE_SUBMITTED', request.user, notes=f'Code IBTIKAR: {code}')
        except (InvalidTransitionError, AuthorizationError, ValueError):
            pass
    messages.success(request, "Votre code IBTIKAR a été transmis au responsable de la plateforme.")
    return redirect_to_detail(request, req, 'dashboard:requester')


@requester_required
def rate_service(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    rating = safe_int(request.POST.get('rating'))
    if 1 <= rating <= 5:
        req.service_rating = rating
        req.rating_comment = request.POST.get('comment', '')
        req.rated_at = timezone.now()
        req.save(update_fields=['service_rating', 'rating_comment', 'rated_at'])
        messages.success(request, "Merci pour votre évaluation.")
    else:
        messages.error(request, "Veuillez sélectionner une note entre 1 et 5.")
    return redirect_to_detail(request, req, 'dashboard:requester')
