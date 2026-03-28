from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from core.models import Service, Request, Invoice
from core.workflow import transition
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

    count = Request.objects.filter(channel='GENOCLAB').count() + 1
    display_id = f"GCL-{count:05d}"

    req = Request.objects.create(
        display_id=display_id,
        title=request.POST.get('title', f"Demande {service.name}"),
        description=request.POST.get('description', ''),
        channel='GENOCLAB',
        status='REQUEST_CREATED',
        urgency=request.POST.get('urgency', 'Normal'),
        service=service,
        requester=request.user,
        quote_amount=service.genoclab_price,
    )
    messages.success(request, f"Demande {req.display_id} créée avec succès.")
    return redirect('dashboard:client')


@client_required
def accept_quote(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    try:
        transition(req, 'QUOTE_VALIDATED_BY_CLIENT', request.user, notes='Devis accepté par client')
        messages.success(request, f"Devis accepté pour {req.display_id}.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('dashboard:client')


@client_required
def reject_quote(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    try:
        transition(req, 'QUOTE_REJECTED_BY_CLIENT', request.user, notes='Devis refusé par client')
        messages.success(request, f"Devis refusé pour {req.display_id}.")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('dashboard:client')


@client_required
def confirm_receipt(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.receipt_confirmed = True
    req.receipt_confirmed_at = timezone.now()
    req.save(update_fields=['receipt_confirmed', 'receipt_confirmed_at'])
    messages.success(request, f"Réception confirmée pour {req.display_id}.")
    return redirect('dashboard:client')


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
    return redirect('dashboard:client')
