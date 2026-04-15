from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone
from dashboard.decorators import finance_required

from core.models import Request, Invoice
from core.workflow import transition
from core.financial import get_budget_dashboard, get_revenue_summary
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


@finance_required
def index(request):
    # KPIs from financial engine
    budget_data = get_budget_dashboard()
    revenue_summary = get_revenue_summary()
    ibtikar_virtual = budget_data['ibtikar']['total']
    genoclab_real = budget_data['genoclab']['total']
    total_invoices = revenue_summary['count']
    ibtikar_students = budget_data['ibtikar']['students']

    # IBTIKAR requests pending finance validation
    pending_validation = Request.objects.filter(
        channel='IBTIKAR', status='VALIDATION_FINANCE'
    ).select_related('service', 'requester').order_by('-created_at')

    # Budget overview by status
    ibtikar_by_status = (
        Request.objects.filter(channel='IBTIKAR')
        .values('status')
        .annotate(total_budget=Sum('budget_amount'))
        .order_by('-total_budget')
    )

    # GENOCLAB invoices
    invoices = Invoice.objects.select_related('request', 'client').order_by('-created_at')[:50]

    # GENOCLAB Invoice Workflow Querysets
    # 1. ANALYSIS_FINISHED - Ready for invoice generation
    invoice_gen_pending = Request.objects.filter(
        channel='GENOCLAB',
        status='ANALYSIS_FINISHED'
    ).select_related('service', 'requester').order_by('-created_at')
    
    # 2. INVOICE_GENERATED - Invoice generated, needs signing and transmission
    invoice_generated = Request.objects.filter(
        channel='GENOCLAB',
        status='INVOICE_GENERATED'
    ).select_related('service', 'requester').order_by('-created_at')
    
    # 3. INVOICE_SENT - Signed invoice sent to client, needs payment notification
    invoice_sent = Request.objects.filter(
        channel='GENOCLAB',
        status='INVOICE_SENT'
    ).select_related('service', 'requester').order_by('-created_at')
    
    # 4. PAYMENT_PENDING - Waiting for client payment
    payment_pending = Request.objects.filter(
        channel='GENOCLAB',
        status='PAYMENT_PENDING'
    ).select_related('service', 'requester').order_by('-created_at')

    # Completed/archived for revenue history
    completed_ibtikar = Request.objects.filter(
        channel='IBTIKAR', status__in=['COMPLETED', 'CLOSED']
    ).aggregate(total=Sum('budget_amount'))['total'] or 0
    completed_genoclab = Invoice.objects.filter(
        request__status__in=['COMPLETED', 'CLOSED']
    ).aggregate(total=Sum('total_ttc'))['total'] or 0

    context = {
        'ibtikar_virtual': ibtikar_virtual,
        'genoclab_real': genoclab_real,
        'total_invoices': total_invoices,
        'ibtikar_students': ibtikar_students,
        'budget_data': budget_data,
        'pending_validation': pending_validation,
        'ibtikar_by_status': ibtikar_by_status,
        'invoices': invoices,
        'completed_ibtikar': completed_ibtikar,
        'completed_genoclab': completed_genoclab,
        # Invoice workflow querysets
        'invoice_gen_pending': invoice_gen_pending,
        'invoice_generated': invoice_generated,
        'invoice_sent': invoice_sent,
        'payment_pending': payment_pending,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/finance/index.html', context)


@finance_required
def validate_budget(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    action = request.POST.get('action', '')
    if action == 'approve':
        req.admin_validated_price = req.budget_amount
        req.save(update_fields=['admin_validated_price'])
        try:
            transition(req, 'PLATFORM_NOTE_GENERATED', request.user, notes='Budget validé par finance')
            messages.success(request, f"Budget validé pour {req.display_id}.")
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, str(e))
    elif action == 'reject':
        reason = request.POST.get('reason', '')
        req.rejection_reason = reason
        req.save(update_fields=['rejection_reason'])
        try:
            transition(req, 'REJECTED', request.user, notes=f'Rejeté par finance: {reason}')
            messages.success(request, f"Demande {req.display_id} rejetée.")
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, str(e))
    return redirect_back(request, 'dashboard:finance')


@finance_required
def update_payment_status(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    invoice = get_object_or_404(Invoice, pk=pk)
    new_status = request.POST.get('payment_status', '')
    if new_status in dict(Invoice.PAYMENT_STATUS_CHOICES):
        invoice.payment_status = new_status
        invoice.save(update_fields=['payment_status'])
        messages.success(request, f"Statut de paiement mis à jour: {invoice.get_payment_status_display()}")
    else:
        messages.error(request, "Statut invalide.")
    return redirect_back(request, 'dashboard:finance')


@finance_required
def generate_invoice(request, pk):
    """
    Finance generates invoice for GENOCLAB requests.
    
    Invoice workflow:
    1. ANALYSIS_FINISHED → Member marks analysis as done
    2. INVOICE_GENERATED → Finance generates and downloads invoice (THIS)
    3. INVOICE_SENT → Finance uploads signed invoice + transmits to client
    4. PAYMENT_PENDING → Client notified to pay
    """
    req = get_object_or_404(Request, pk=pk)
    
    if req.channel != 'GENOCLAB':
        messages.error(request, "Invoice generation is only for GENOCLAB requests.")
        return redirect_back(request, 'dashboard:finance')
    
    if req.status != 'ANALYSIS_FINISHED':
        messages.error(
            request,
            f"Invoice can only be generated when analysis is finished (current: {req.get_status_display()})."
        )
        return redirect_back(request, 'dashboard:finance')
    
    try:
        from documents.invoice import generate_invoice_excel
        from django.core.files.base import ContentFile
        
        excel_data = generate_invoice_excel(req)
        invoice_filename = f"invoice-{req.display_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        req.generated_invoice.save(invoice_filename, ContentFile(excel_data))
        req.save(update_fields=['generated_invoice'])
        
        transition(req, 'INVOICE_GENERATED', request.user, notes='Facture générée par finance')
        messages.success(request, f"Invoice generated for {req.display_id}. Next: sign and send to client.")
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect_back(request, 'dashboard:finance')


@finance_required
def send_invoice(request, pk):
    """
    Finance sends signed invoice to client.
    Transitions to INVOICE_SENT, then to PAYMENT_PENDING.
    """
    req = get_object_or_404(Request, pk=pk)
    
    if req.channel != 'GENOCLAB':
        messages.error(request, "Invoice sending is only for GENOCLAB requests.")
        return redirect_back(request, 'dashboard:finance')
    
    if req.status != 'INVOICE_GENERATED':
        messages.error(
            request,
            f"Must generate invoice first (current: {req.get_status_display()})."
        )
        return redirect_back(request, 'dashboard:finance')
    
    if not req.signed_invoice:
        messages.error(request, "Please upload signed invoice first.")
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    client = req.requester
    if not client:
        messages.error(request, "No client associated with this request.")
        return redirect_back(request, 'dashboard:finance')
    
    try:
        req.invoice_sent_at = timezone.now()
        req.save(update_fields=['invoice_sent_at'])
        
        transition(req, 'INVOICE_SENT', request.user, notes='Facture signée transmise au client')
        
        Notification.objects.create(
            user=client,
            message=f"Your invoice for {req.display_id} is ready. Please proceed with payment.",
            request=req,
            notification_type='INVOICE_READY',
        )
        
        messages.success(request, f"Invoice sent to client {client.get_full_name()}.")
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect_back(request, 'dashboard:finance')


@finance_required
def trigger_payment_pending(request, pk):
    """
    Trigger PAYMENT_PENDING after invoice has been sent.
    This can be automatic or manual trigger.
    """
    req = get_object_or_404(Request, pk=pk)
    
    if req.channel != 'GENOCLAB':
        messages.error(request, "Payment trigger is only for GENOCLAB requests.")
        return redirect_back(request, 'dashboard:finance')
    
    if req.status != 'INVOICE_SENT':
        messages.error(
            request,
            f"Invoice must be sent first (current: {req.get_status_display()})."
        )
        return redirect_back(request, 'dashboard:finance')
    
    try:
        transition(req, 'PAYMENT_PENDING', request.user, notes='Client notifié pour paiement')
        
        from notifications.services import notify_payment_request
        notify_payment_request(req)
        
        messages.success(request, f"Client notified for payment for {req.display_id}.")
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Error: {str(e)}")
        return redirect_back(request, 'dashboard:finance')
