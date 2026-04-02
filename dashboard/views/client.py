from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back, paginate_queryset
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count
from dashboard.decorators import client_required

from core.models import Service, Request, Invoice
from core.workflow import transition
from core.services.genoclab import submit_genoclab_request
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


@client_required
def index(request):
    from django.db.models import Case, When, IntegerField
    
    # Base queryset for this user's requests
    my_requests = Request.objects.filter(requester=request.user, channel='GENOCLAB')
    
    # Consolidated count queries
    counts = my_requests.aggregate(
        total=Count('id'),
        active=Count(
            Case(
                When(status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED', 'QUOTE_REJECTED_BY_CLIENT'], then=None),
                default=1,
                output_field=IntegerField()
            )
        ),
        completed=Count(
            Case(
                When(status__in=['COMPLETED', 'CLOSED'], then=1),
                output_field=IntegerField()
            )
        ),
        rejected=Count(
            Case(
                When(status__in=['REJECTED', 'QUOTE_REJECTED_BY_CLIENT'], then=1),
                output_field=IntegerField()
            )
        )
    )
    total = counts['total']
    active = counts['active'] or 0
    completed = counts['completed'] or 0
    rejected = counts['rejected'] or 0

    # Active requests
    active_requests = my_requests.exclude(
        status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED', 'QUOTE_REJECTED_BY_CLIENT']
    ).select_related('service', 'assigned_to__user').order_by('-created_at')

    # Invoices for this client
    invoices = Invoice.objects.filter(client=request.user).select_related('request').order_by('-created_at')

    # Archives - paginated (exclude hidden from archive)
    archived_qs = my_requests.filter(
        status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
    ).exclude(hidden_from_archive=True).select_related('service').order_by('-updated_at')
    archived_paginator, archived, _ = paginate_queryset(archived_qs, request, per_page=25, page_param='archived_page')

    # Services for new request
    services = Service.objects.filter(
        active=True, channel_availability__in=['BOTH', 'GENOCLAB']
    ).order_by('code')

    # Notifications - paginated
    notifications_paginator, notifications, _ = paginate_queryset(
        Notification.objects.filter(user=request.user, read=False).order_by('-created_at'),
        request, per_page=10, page_param='notif_page'
    )
    
    # Profile stats for profile tab
    unread_notifications = Notification.objects.filter(user=request.user, read=False).count()
    profile_stats = {
        'total_requests': total,
        'completed_requests': completed,
        'pending_requests': active,
        'notifications_count': unread_notifications,
    }

    context = {
        'total': total,
        'active': active,
        'completed': completed,
        'rejected': rejected,
        'active_requests': active_requests,
        'invoices': invoices,
        'archived': archived,
        'archived_paginator': archived_paginator,
        'services': services,
        'notifications': notifications,
        'notifications_paginator': notifications_paginator,
        'profile_stats': profile_stats,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/client/index.html', context)


@client_required
def request_detail(request, pk):
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    from core.registry import get_service_def
    from core.models import PaymentSettings
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
    
    # Get payment settings for invoice section
    payment_settings = PaymentSettings.get_settings()
    
    # Get workflow history
    from core.models import RequestStatusHistory
    history = RequestStatusHistory.objects.filter(request=req).select_related('actor').order_by('created_at')

    context = {
        'req': req,
        'params_display': params_display,
        'sample_headers': sample_headers,
        'messages_list': messages_list,
        'payment_settings': payment_settings,
        'history': history,
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
    
    # Transition to PAYMENT_UPLOADED (admin will confirm to PAYMENT_CONFIRMED)
    try:
        transition(req, 'PAYMENT_UPLOADED', request.user, notes='Reçu de paiement téléchargé par le client, en attente de confirmation admin')
        
        # Notify admin that payment receipt needs verification
        from accounts.models import User
        admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'], is_active=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"{req.display_id}: Reçu de paiement uploadé par client — Confirmation requise",
                request=req,
                notification_type='PAYMENT',
            )
        
        messages.success(request, f"Reçu de paiement uploadé pour {req.display_id}. L'administrateur va vérifier et confirmer le paiement.")
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
        messages.success(request, f"Rendez-vous confirmé pour {req.display_id}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur: {str(e)}")
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
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, f"Erreur lors de la finalisation: {str(e)}")
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
    """Client requests appointment rescheduling with workflow transition and Admin Ops notification."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk, requester=request.user)
    alt_date = request.POST.get('alt_date', '')
    alt_note = request.POST.get('alt_note', '')
    if alt_date:
        from datetime import datetime as dt
        from core.models import RequestComment
        from core.workflow import transition
        from core.exceptions import InvalidTransitionError, AuthorizationError
        try:
            parsed_date = dt.strptime(alt_date, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Date invalide.")
            return redirect_back(request, 'dashboard:client')
        
        # Perform workflow transition to APPOINTMENT_RESCHEDULING_REQUESTED
        if req.status == 'APPOINTMENT_PROPOSED':
            try:
                transition(req, 'APPOINTMENT_RESCHEDULING_REQUESTED', request.user, 
                          notes=f"Client requested alternative date: {alt_date}. {alt_note}".strip())
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, f"Erreur de transition: {str(e)}")
                return redirect_back(request, 'dashboard:client')
        
        # Store the alternative date on the request
        req.alt_date_proposed = parsed_date
        req.alt_date_note = alt_note
        req.save(update_fields=['alt_date_proposed', 'alt_date_note'])
        
        # Log as comment for audit trail
        RequestComment.objects.create(
            request=req, author=request.user,
            text=f"Date alternative proposée: {alt_date}. {alt_note}".strip(),
            step=req.status
        )
        
        # Notify Admin Ops (primary notification)
        from accounts.models import User
        admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"{req.display_id}: Client a demandé une reprogrammation — {parsed_date.strftime('%d/%m/%Y')}",
                request=req,
                notification_type='WORKFLOW',
            )
        
        # Also notify the assigned analyst
        if req.assigned_to:
            Notification.objects.create(
                user=req.assigned_to.user,
                message=f"{req.display_id}: Reprogrammation demandée par client — {parsed_date.strftime('%d/%m/%Y')}",
                request=req,
                notification_type='WORKFLOW',
            )
        
        messages.success(request, f"Demande de reprogrammation envoyée: {parsed_date.strftime('%d/%m/%Y')}. L'administrateur va vous contacter.")
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


# =============================================================================
# Archive Feature (Feature 2)
# =============================================================================

@client_required
def archive_detail(request, pk):
    """View archived request details - read-only detail view."""
    req = get_object_or_404(
        Request.objects.filter(
            requester=request.user,
            status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
        ).exclude(hidden_from_archive=True),
        pk=pk
    )
    
    from core.registry import get_service_def
    yaml_def = get_service_def(req.service.code) if req.service else None
    
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
        'sample_headers': sample_headers,
    }
    return render(request, 'dashboard/client/archive_detail.html', context)


@client_required
def hide_from_archive(request, pk):
    """Hide a single request from the requester's archive."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    req = get_object_or_404(
        Request.objects.filter(
            requester=request.user,
            status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
        ),
        pk=pk
    )
    
    req.hidden_from_archive = True
    req.save(update_fields=['hidden_from_archive'])
    messages.success(request, f"La demande {req.display_id} a été retirée de vos archives.")
    return redirect('dashboard:client')


@client_required
def remove_from_archive(request):
    """Remove multiple requests from the requester's archive (bulk action)."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    action = request.POST.get('action', '')
    selected_ids = request.POST.getlist('selected_requests', [])
    
    if action == 'clear_all':
        # Hide all completed requests for this user
        Request.objects.filter(
            requester=request.user,
            status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
        ).update(hidden_from_archive=True)
        messages.success(request, "Toutes les demandes ont été retirées de vos archives.")
    elif selected_ids:
        # Hide only selected requests
        updated = Request.objects.filter(
            pk__in=selected_ids,
            requester=request.user,
            status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
        ).update(hidden_from_archive=True)
        messages.success(request, f"{updated} demande(s) ont été retirée(s) de vos archives.")
    
    return redirect('dashboard:client')


@client_required
def accept_citation(request, pk):
    """Accept citation terms before downloading report."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    req = get_object_or_404(
        Request.objects.filter(
            requester=request.user,
            status__in=['COMPLETED', 'CLOSED', 'ARCHIVED']
        ),
        pk=pk
    )
    
    req.citation_accepted = True
    req.citation_accepted_at = timezone.now()
    req.save(update_fields=['citation_accepted', 'citation_accepted_at'])
    
    # Return JSON response for AJAX
    from django.http import JsonResponse
    return JsonResponse({'success': True})


# =============================================================================
# INVOICE DOWNLOAD FOR CLIENTS (GENOCLAB)
# =============================================================================

@client_required
def download_invoice(request, pk):
    """
    Download the signed invoice for a GENOCLAB request.
    When the client downloads the invoice, notify Admin Ops.
    """
    from django.http import HttpResponse
    from accounts.models import User
    
    req = get_object_or_404(Request, pk=pk, requester=request.user, channel='GENOCLAB')
    
    # Check if invoice has been sent
    if not req.signed_invoice:
        from django.contrib import messages
        messages.error(request, _("No signed invoice available for this request. Please contact support."))
        return redirect('dashboard:client_request_detail', pk=pk)
    
    if not req.invoice_sent_at:
        from django.contrib import messages
        messages.error(request, _("Invoice has not been sent yet. Please wait for notification."))
        return redirect('dashboard:client_request_detail', pk=pk)
    
    # Update download timestamp
    if not req.invoice_downloaded_at:
        req.invoice_downloaded_at = timezone.now()
        req.save(update_fields=['invoice_downloaded_at'])
        
        # Notify Admin Ops about the invoice download
        # Get all admin users
        admin_users = User.objects.filter(role__in=['ADMIN', 'PLATFORM_ADMIN', 'SUPER_ADMIN'])
        for admin in admin_users:
            Notification.objects.create(
                user=admin,
                message=_("Client %(client_name)s has downloaded the invoice for request %(display_id)s.") % {
                    'client_name': request.user.get_full_name(),
                    'display_id': req.display_id
                },
                request=req,
                notification_type='INVOICE_DOWNLOADED'
            )
    
    # Serve the file
    try:
        file_obj = req.signed_invoice
        content_type = 'application/octet-stream'
        
        # Try to determine content type based on file extension
        filename = file_obj.name.lower()
        if filename.endswith('.pdf'):
            content_type = 'application/pdf'
        elif filename.endswith('.xlsx'):
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif filename.endswith('.docx'):
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        response = HttpResponse(file_obj.read(), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{req.signed_invoice.name.split("/")[-1]}"'
        return response
        
    except Exception as e:
        from django.contrib import messages
        messages.error(request, _("Error downloading invoice: %(error)s") % {'error': str(e)})
        return redirect('dashboard:client_request_detail', pk=pk)
