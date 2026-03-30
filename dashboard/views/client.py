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

    from core.models import Message
    messages_list = Message.objects.filter(
        request=req, to_user=request.user
    ).select_related('from_user').order_by('created_at')

    context = {
        'req': req,
        'params_display': params_display,
        'sample_headers': sample_headers,
        'messages_list': messages_list,
    }
    return render(request, 'dashboard/client/request_detail.html', context)


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
    """After accepting quote, client must upload purchase order (Bon de commande)."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    try:
        transition(req, 'QUOTE_VALIDATED_BY_CLIENT', request.user, notes='Devis accepté par client')
        messages.success(request, f"Devis accepté pour {req.display_id}. Veuillez maintenant télécharger votre Bon de Commande (obligatoire selon le code de commerce algérien).")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect('dashboard:client_request_detail', pk=pk)


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
def upload_order(request, pk):
    """Upload purchase order (Bon de commande) - mandatory per Algerian commercial code."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    
    # Check status - client must have accepted quote
    if req.status != 'QUOTE_VALIDATED_BY_CLIENT':
        messages.error(request, "Vous ne pouvez pas télécharger de bon de commande à ce stade.")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    order_file = request.FILES.get('order_file')
    if not order_file:
        messages.error(request, "Veuillez sélectionner un fichier pour le Bon de Commande.")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    # Validate file type
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    import os
    ext = os.path.splitext(order_file.name)[1].lower()
    if ext not in allowed_extensions:
        messages.error(request, f"Type de fichier non autorisé. Formats acceptés: {', '.join(allowed_extensions)}")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    # Save the order file
    req.order_file = order_file
    req.order_uploaded_at = timezone.now()
    req.save(update_fields=['order_file', 'order_uploaded_at'])
    
    # Transition to ORDER_UPLOADED
    try:
        transition(req, 'ORDER_UPLOADED', request.user, notes='Bon de commande téléchargé par le client')
        
        # Notify admin about purchase order upload
        from notifications.services import notify_purchase_order_uploaded
        notify_purchase_order_uploaded(req)
        
        messages.success(request, f"Bon de Commande téléchargé avec succès pour {req.display_id}. L'administrateur va maintenant assigner votre demande à un analyste.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    
    return redirect('dashboard:client_request_detail', pk=pk)


@client_required
def upload_payment_receipt(request, pk):
    """Upload payment receipt after analysis is finished."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    
    # Check status - client must have received payment request
    if req.status != 'PAYMENT_PENDING':
        messages.error(request, "Vous ne pouvez pas télécharger de reçu de paiement à ce stade.")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    payment_receipt = request.FILES.get('payment_receipt_file')
    if not payment_receipt:
        messages.error(request, "Veuillez sélectionner un fichier pour le Reçu de Paiement.")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    # Validate file type
    allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
    import os
    ext = os.path.splitext(payment_receipt.name)[1].lower()
    if ext not in allowed_extensions:
        messages.error(request, f"Type de fichier non autorisé. Formats acceptés: {', '.join(allowed_extensions)}")
        return redirect('dashboard:client_request_detail', pk=pk)
    
    # Save the payment receipt
    req.payment_receipt_file = payment_receipt
    req.payment_uploaded_at = timezone.now()
    req.save(update_fields=['payment_receipt_file', 'payment_uploaded_at'])
    
    # Transition to PAYMENT_CONFIRMED
    try:
        transition(req, 'PAYMENT_CONFIRMED', request.user, notes='Reçu de paiement téléchargé par le client')
        
        # Notify assigned analyst that they can now upload the report
        from notifications.services import notify_payment_received
        notify_payment_received(req)
        
        messages.success(request, f"Paiement confirmé pour {req.display_id}. L'analyste assigné peut maintenant télécharger le rapport d'analyse.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    
    return redirect('dashboard:client_request_detail', pk=pk)


@client_required
def confirm_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    import uuid as _uuid
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    req.appointment_confirmed = True
    req.appointment_confirmed_at = timezone.now()
    if not req.report_token:
        req.report_token = _uuid.uuid4()
    req.save(update_fields=['appointment_confirmed', 'appointment_confirmed_at', 'report_token'])
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
    # Transition SENT_TO_CLIENT → COMPLETED
    if req.status == 'SENT_TO_CLIENT':
        try:
            transition(req, 'COMPLETED', request.user, notes='Réception confirmée par le client')
        except (InvalidTransitionError, AuthorizationError, ValueError):
            pass
    # Notify admin + analyst that report was downloaded/confirmed
    from accounts.models import User
    from notifications.models import Notification
    admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
    for admin in admins:
        Notification.objects.create(
            user=admin,
            message=f"{req.display_id}: Rapport téléchargé et réception confirmée par le client.",
            request=req,
            notification_type='WORKFLOW',
        )
    if req.assigned_to:
        Notification.objects.create(
            user=req.assigned_to.user,
            message=f"{req.display_id}: Rapport téléchargé et réception confirmée par le client.",
            request=req,
            notification_type='WORKFLOW',
        )
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
        from datetime import datetime as dt
        from core.models import RequestComment
        try:
            parsed_date = dt.strptime(alt_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Date invalide.")
            return redirect_back(request, 'dashboard:client')
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
