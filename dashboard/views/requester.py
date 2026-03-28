import uuid
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.utils import timezone

from core.models import Service, Request
from core.services.ibtikar import submit_ibtikar_request, get_ibtikar_request_context
from core.financial import check_ibtikar_budget
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

    context = {
        'req': req,
        'params_display': params_display,
        'sample_headers': sample_headers,
    }
    return render(request, 'dashboard/requester/request_detail.html', context)


@requester_required
def create_request(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service_id = request.POST.get('service_id')
    service = get_object_or_404(Service, pk=service_id, active=True)

    # Declared balance validation
    declared = float(request.POST.get('declared_balance', 0))
    if declared < 0 or declared > 200000:
        messages.error(request, "Le solde IBTIKAR déclaré doit être entre 0 et 200 000 DA.")
        return redirect_back(request, 'dashboard:requester')
    if service.ibtikar_price and float(service.ibtikar_price) > declared:
        messages.warning(request, f"Attention: le coût estimé ({service.ibtikar_price} DA) dépasse votre solde déclaré ({declared:,.0f} DA).")

    # Budget check before submission
    budget_check = check_ibtikar_budget(amount=service.ibtikar_price, requester=request.user)
    if budget_check['exceeded']:
        messages.error(
            request,
            f"Budget IBTIKAR dépassé: {budget_check['projected']:,.0f} / {budget_check['cap']:,.0f} DZD. "
            f"Reste: {budget_check['remaining']:,.0f} DZD."
        )
        return redirect_back(request, 'dashboard:requester')

    # Collect YAML parameter values
    service_params = {key.replace('param_', '', 1): val for key, val in request.POST.items() if key.startswith('param_')}
    sample_data = {}
    for key, val in request.POST.items():
        if key.startswith('sample_'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                sample_data.setdefault(parts[1], {})[parts[2]] = val
    sample_table_data = list(sample_data.values()) if sample_data else []

    # Calculate cost from YAML pricing if available
    from core.pricing import calculate_price
    from core.registry import get_service_def
    yaml_def = get_service_def(service.code)
    if yaml_def and sample_table_data:
        try:
            price_result = calculate_price(yaml_def, service_params, sample_table_data)
            budget_amount = price_result.get('total', float(service.ibtikar_price))
        except (ValueError, KeyError):
            budget_amount = float(service.ibtikar_price)
    else:
        budget_amount = float(service.ibtikar_price)

    # Use ibtikar service to submit
    req = submit_ibtikar_request(
        data={
            'title': request.POST.get('title', f"Demande {service.name}"),
            'description': request.POST.get('description', ''),
            'urgency': request.POST.get('urgency', 'Normal'),
            'service_id': str(service.pk),
            'budget_amount': budget_amount,
            'declared_ibtikar_balance': float(request.POST.get('declared_balance', 0)),
            'service_params': service_params,
            'sample_table': sample_table_data,
        },
        user=request.user,
    )
    messages.success(request, f"Demande {req.display_id} soumise avec succès.")
    return redirect_back(request, 'dashboard:requester')


@requester_required
def confirm_receipt(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.receipt_confirmed = True
    req.receipt_confirmed_at = timezone.now()
    req.save(update_fields=['receipt_confirmed', 'receipt_confirmed_at'])
    messages.success(request, f"Réception confirmée pour {req.display_id}.")
    return redirect_back(request, 'dashboard:requester')


@requester_required
def confirm_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.appointment_confirmed = True
    req.appointment_confirmed_at = timezone.now()
    req.save(update_fields=['appointment_confirmed', 'appointment_confirmed_at'])
    try:
        from core.workflow import transition
        from core.exceptions import InvalidTransitionError, AuthorizationError
        transition(req, 'APPOINTMENT_CONFIRMED', request.user, notes='RDV confirmé')
    except (InvalidTransitionError, AuthorizationError, ValueError):
        pass
    messages.success(request, f"Rendez-vous confirmé pour {req.display_id}.")
    return redirect_back(request, 'dashboard:requester')


@requester_required
def suggest_alternative_date(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    alt_date = request.POST.get('alt_date', '')
    alt_note = request.POST.get('alt_note', '')
    if alt_date:
        from core.models import RequestComment
        RequestComment.objects.create(
            request=req, author=request.user,
            text=f"Date alternative proposée: {alt_date}. {alt_note}",
            step=req.status
        )
        if req.assigned_to:
            Notification.objects.create(
                user=req.assigned_to.user,
                message=f"Nouvelle date proposée pour {req.display_id}: {alt_date}",
                request=req
            )
        messages.success(request, f"Date alternative proposée: {alt_date}")
    return redirect_back(request, 'dashboard:requester')


@requester_required
def rate_service(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    rating = int(request.POST.get('rating', 0))
    if 1 <= rating <= 5:
        req.service_rating = rating
        req.rating_comment = request.POST.get('comment', '')
        req.rated_at = timezone.now()
        req.save(update_fields=['service_rating', 'rating_comment', 'rated_at'])
        messages.success(request, "Merci pour votre évaluation.")
    return redirect_back(request, 'dashboard:requester')
