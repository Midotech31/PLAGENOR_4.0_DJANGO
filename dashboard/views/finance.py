from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import Request, Invoice
from core.workflow import transition
from core.financial import get_budget_dashboard, get_revenue_summary
from core.audit import log_financial_action
from core.exceptions import InvalidTransitionError, AuthorizationError


def finance_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('FINANCE', 'SUPER_ADMIN'):
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


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

    # Completed/archived for revenue history
    completed_ibtikar = Request.objects.filter(
        channel='IBTIKAR', status__in=['COMPLETED', 'CLOSED']
    ).aggregate(total=Sum('budget_amount'))['total'] or 0
    completed_genoclab = Invoice.objects.filter(
        request__status__in=['COMPLETED', 'ARCHIVED'], cancelled_at__isnull=True
    ).aggregate(total=Sum('total_ttc'))['total'] or 0

    context = {
        'ibtikar_virtual': ibtikar_virtual,
        'genoclab_real': genoclab_real,
        'ohb_real': budget_data['ohb']['total'],
        'total_invoices': total_invoices,
        'ibtikar_students': ibtikar_students,
        'budget_data': budget_data,
        'pending_validation': pending_validation,
        'ibtikar_by_status': ibtikar_by_status,
        'invoices': invoices,
        'completed_ibtikar': completed_ibtikar,
        'completed_genoclab': completed_genoclab,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/finance/index.html', context)


@finance_required
def validate_budget(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    action = request.POST.get('action', '')
    try:
        with transaction.atomic():
            req = get_object_or_404(
                Request.objects.select_for_update(), pk=pk)
            if action == 'approve':
                req.admin_validated_price = req.budget_amount
                req.save(update_fields=['admin_validated_price'])
                transition(
                    req, 'PLATFORM_NOTE_GENERATED', request.user,
                    notes='Budget validé par finance')
                messages.success(request, f"Budget validé pour {req.display_id}.")
            elif action == 'reject':
                reason = request.POST.get('reason', '').strip()
                if not reason:
                    raise ValueError("Le motif du rejet est obligatoire.")
                req.rejection_reason = reason
                req.save(update_fields=['rejection_reason'])
                transition(
                    req, 'REJECTED', request.user,
                    notes=f'Rejeté par finance: {reason}')
                messages.success(request, f"Demande {req.display_id} rejetée.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:finance')


@finance_required
def update_payment_status(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    new_status = request.POST.get('payment_status', '')
    note = request.POST.get('verification_note', '').strip()
    if new_status not in dict(Invoice.PAYMENT_STATUS_CHOICES) or len(note) < 3:
        messages.error(request, "Un statut valide et une note de vérification sont obligatoires.")
        return redirect_back(request, 'dashboard:finance')
    try:
        with transaction.atomic():
            invoice = get_object_or_404(Invoice, pk=pk)
            req = Request.objects.select_for_update().get(pk=invoice.request_id) if invoice.request_id else None
            invoice = Invoice.objects.select_for_update().get(pk=pk)
            if invoice.cancelled_at or (invoice.payment_status == 'COMPLETED' and new_status != 'COMPLETED'):
                raise ValueError("Une facture annulée ou un paiement confirmé ne peut être modifié ici.")
            if new_status == 'COMPLETED' and req and req.status != 'PAYMENT_CONFIRMED':
                if req.status != 'PAYMENT_PROOF_UPLOADED' or not req.payment_receipt_file:
                    raise ValueError("Une preuve de paiement doit être reçue et vérifiée avant confirmation.")
                req.payment_verified_at = timezone.now()
                req.payment_verified_by = request.user
                req.payment_verification_note = note
                req.save(update_fields=['payment_verified_at', 'payment_verified_by', 'payment_verification_note'])
                transition(req, 'PAYMENT_CONFIRMED', request.user, notes=note)
            invoice.payment_status = new_status
            invoice.save(update_fields=['payment_status'])
            log_financial_action('PAYMENT_STATUS_CHANGED', str(invoice.pk), request.user,
                amount=float(invoice.total_ttc), details={'payment_status': new_status, 'verification_note': note})
        messages.success(request, "Paiement mis à jour.")
    except (ValueError, InvalidTransitionError, AuthorizationError) as exc:
        messages.error(request, str(exc))
    return redirect_back(request, 'dashboard:finance')
