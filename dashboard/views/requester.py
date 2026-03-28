import uuid
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
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
def create_request(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service_id = request.POST.get('service_id')
    service = get_object_or_404(Service, pk=service_id, active=True)

    # Budget check before submission
    budget_check = check_ibtikar_budget(amount=service.ibtikar_price, requester=request.user)
    if budget_check['exceeded']:
        messages.error(
            request,
            f"Budget IBTIKAR dépassé: {budget_check['projected']:,.0f} / {budget_check['cap']:,.0f} DZD. "
            f"Reste: {budget_check['remaining']:,.0f} DZD."
        )
        return redirect('dashboard:requester')

    # Use ibtikar service to submit
    req = submit_ibtikar_request(
        data={
            'title': request.POST.get('title', f"Demande {service.name}"),
            'description': request.POST.get('description', ''),
            'urgency': request.POST.get('urgency', 'Normal'),
            'service_id': str(service.pk),
            'budget_amount': float(service.ibtikar_price),
            'declared_ibtikar_balance': float(request.POST.get('declared_balance', 0)),
        },
        user=request.user,
    )
    messages.success(request, f"Demande {req.display_id} soumise avec succès.")
    return redirect('dashboard:requester')


@requester_required
def confirm_receipt(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.receipt_confirmed = True
    req.receipt_confirmed_at = timezone.now()
    req.save(update_fields=['receipt_confirmed', 'receipt_confirmed_at'])
    messages.success(request, f"Réception confirmée pour {req.display_id}.")
    return redirect('dashboard:requester')


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
    return redirect('dashboard:requester')
