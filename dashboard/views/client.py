from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.utils import timezone

from core.models import Service, Request, Invoice
from core.workflow import transition
from core.services.genoclab import submit_genoclab_request
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


def client_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'CLIENT':
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@client_required
def index(request):
    my_requests = Request.objects.filter(requester=request.user, channel='GENOCLAB')
    total = my_requests.count()
    active = my_requests.exclude(status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']).count()
    completed = my_requests.filter(status__in=['COMPLETED', 'CLOSED']).count()
    rejected = my_requests.filter(status__in=['REJECTED', 'QUOTE_REJECTED_BY_CLIENT']).count()

    # Active requests
    active_requests = my_requests.exclude(
        status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED', 'QUOTE_REJECTED_BY_CLIENT']
    ).select_related('service', 'assigned_to__user').order_by('-created_at')

    # Invoices for this client
    invoices = Invoice.objects.filter(client=request.user).select_related('request').order_by('-created_at')

    # Archives
    archived = my_requests.filter(
        status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
    ).select_related('service').order_by('-updated_at')[:30]

    # Services for new request
    services = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'GENOCLAB']
    ).order_by('code')

    # Notifications
    notifications = Notification.objects.filter(user=request.user, read=False).order_by('-created_at')[:10]

    context = {
        'total': total,
        'active': active,
        'completed': completed,
        'rejected': rejected,
        'active_requests': active_requests,
        'invoices': invoices,
        'archived': archived,
        'services': services,
        'notifications': notifications,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/client/index.html', context)


@client_required
def create_request(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service_id = request.POST.get('service_id')
    service = get_object_or_404(Service, pk=service_id, active=True)

    # Collect YAML parameter values
    service_params = {key.replace('param_', '', 1): val for key, val in request.POST.items() if key.startswith('param_')}
    sample_data = {}
    for key, val in request.POST.items():
        if key.startswith('sample_'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                sample_data.setdefault(parts[1], {})[parts[2]] = val
    sample_table_data = list(sample_data.values()) if sample_data else []

    # Use genoclab service to submit
    req = submit_genoclab_request(
        data={
            'title': request.POST.get('title', f"Demande {service.name}"),
            'description': request.POST.get('description', ''),
            'urgency': request.POST.get('urgency', 'Normal'),
            'service_id': str(service.pk),
            'quote_amount': float(service.genoclab_price),
            'service_params': service_params,
            'sample_table': sample_table_data,
        },
        user=request.user,
    )
    messages.success(request, f"Demande {req.display_id} créée avec succès.")
    return redirect_back(request, 'dashboard:client')


@client_required
def accept_quote(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    try:
        transition(req, 'QUOTE_VALIDATED_BY_CLIENT', request.user, notes='Devis accepté par client')
        messages.success(request, f"Devis accepté pour {req.display_id}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:client')


@client_required
def reject_quote(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    try:
        transition(req, 'QUOTE_REJECTED_BY_CLIENT', request.user, notes='Devis refusé par client')
        messages.success(request, f"Devis refusé pour {req.display_id}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:client')


@client_required
def confirm_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.appointment_confirmed = True
    req.appointment_confirmed_at = timezone.now()
    req.save(update_fields=['appointment_confirmed', 'appointment_confirmed_at'])
    try:
        transition(req, 'APPOINTMENT_CONFIRMED', request.user, notes='RDV confirmé')
    except (InvalidTransitionError, AuthorizationError, ValueError):
        pass
    messages.success(request, f"Rendez-vous confirmé pour {req.display_id}.")
    return redirect_back(request, 'dashboard:client')


@client_required
def confirm_receipt(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.receipt_confirmed = True
    req.receipt_confirmed_at = timezone.now()
    req.save(update_fields=['receipt_confirmed', 'receipt_confirmed_at'])
    messages.success(request, f"Réception confirmée pour {req.display_id}.")
    return redirect_back(request, 'dashboard:client')


@client_required
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
    return redirect_back(request, 'dashboard:client')


@client_required
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
    return redirect_back(request, 'dashboard:client')
