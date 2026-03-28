from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum

from core.models import Request, Invoice
from core.workflow import transition


def finance_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('FINANCE', 'SUPER_ADMIN'):
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@finance_required
def index(request):
    # KPIs
    ibtikar_virtual = Request.objects.filter(channel='IBTIKAR').aggregate(
        total=Sum('budget_amount')
    )['total'] or 0
    genoclab_real = Invoice.objects.aggregate(total=Sum('total_ttc'))['total'] or 0
    total_invoices = Invoice.objects.count()
    ibtikar_students = Request.objects.filter(channel='IBTIKAR').values('requester').distinct().count()

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
        request__status__in=['COMPLETED', 'CLOSED']
    ).aggregate(total=Sum('total_ttc'))['total'] or 0

    context = {
        'ibtikar_virtual': ibtikar_virtual,
        'genoclab_real': genoclab_real,
        'total_invoices': total_invoices,
        'ibtikar_students': ibtikar_students,
        'pending_validation': pending_validation,
        'ibtikar_by_status': ibtikar_by_status,
        'invoices': invoices,
        'completed_ibtikar': completed_ibtikar,
        'completed_genoclab': completed_genoclab,
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
        except ValueError as e:
            messages.error(request, str(e))
    elif action == 'reject':
        reason = request.POST.get('reason', '')
        req.rejection_reason = reason
        req.save(update_fields=['rejection_reason'])
        try:
            transition(req, 'REJECTED', request.user, notes=f'Rejeté par finance: {reason}')
            messages.success(request, f"Demande {req.display_id} rejetée.")
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('dashboard:finance')
