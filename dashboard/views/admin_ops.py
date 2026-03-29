from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone

from accounts.models import MemberProfile, Cheer, PointsHistory
from core.models import Request, RequestHistory, RequestComment, Invoice
from core.workflow import get_allowed_transitions, transition
from core.assignment import get_recommended_members
from core.registry import get_service_def
from core.pricing import calculate_price
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


def admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@admin_required
def index(request):
    total_requests = Request.objects.count()
    pending_count = Request.objects.filter(
        status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED', 'ADMIN_REVIEW']
    ).count()
    ibtikar_count = Request.objects.filter(channel='IBTIKAR').count()
    genoclab_count = Request.objects.filter(channel='GENOCLAB').count()
    completed_count = Request.objects.filter(status='COMPLETED').count()

    # Pending requests needing action (all non-terminal, non-assigned states)
    pending_requests = Request.objects.filter(
        status__in=[
            'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'PLATFORM_NOTE_GENERATED',
            'REPORT_UPLOADED', 'ADMIN_REVIEW', 'REPORT_VALIDATED',
            'COMPLETED',
            'REQUEST_CREATED', 'QUOTE_DRAFT', 'QUOTE_SENT',
            'QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED', 'PAYMENT_CONFIRMED',
            'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
        ]
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')[:50]

    # Requests needing validation
    validation_requests = Request.objects.filter(
        status__in=[
            'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'REQUEST_CREATED', 'QUOTE_DRAFT', 'QUOTE_SENT',
            'QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED',
        ]
    ).select_related('service', 'requester').order_by('-created_at')

    # Requests ready for assignment
    assignable_requests = Request.objects.filter(
        status__in=['PLATFORM_NOTE_GENERATED', 'PAYMENT_CONFIRMED']
    ).select_related('service', 'requester').order_by('-created_at')

    # Requests needing report review
    review_requests = Request.objects.filter(
        status__in=['REPORT_UPLOADED', 'ADMIN_REVIEW']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')

    # In-progress requests (assigned, appointment, analysis phases)
    in_progress_requests = Request.objects.filter(
        status__in=[
            'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
            'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
        ]
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-updated_at')

    # Requests needing completion/closure actions
    completion_requests = Request.objects.filter(
        status__in=['REPORT_VALIDATED', 'COMPLETED']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-updated_at')

    # All requests with optional filters
    channel_filter = request.GET.get('channel', '')
    status_filter = request.GET.get('status', '')
    search_q = request.GET.get('q', '')

    all_requests = Request.objects.select_related('service', 'requester', 'assigned_to__user')
    if channel_filter:
        all_requests = all_requests.filter(channel=channel_filter)
    if status_filter:
        all_requests = all_requests.filter(status=status_filter)
    if search_q:
        all_requests = all_requests.filter(
            Q(display_id__icontains=search_q) | Q(title__icontains=search_q)
        )
    all_requests = all_requests.order_by('-created_at')[:100]

    # Available members for assignment — scored by assignment engine
    recommended_members = get_recommended_members(limit=20)
    available_members = MemberProfile.objects.filter(
        available=True
    ).select_related('user').order_by('current_load')

    # Budget overview from financial engine
    from core.financial import get_budget_dashboard
    budget_data = get_budget_dashboard()
    ibtikar_budget = budget_data['ibtikar']['total']
    genoclab_revenue = budget_data['genoclab']['total']

    context = {
        'total_requests': total_requests,
        'pending_count': pending_count,
        'ibtikar_count': ibtikar_count,
        'genoclab_count': genoclab_count,
        'completed_count': completed_count,
        'pending_requests': pending_requests,
        'validation_requests': validation_requests,
        'assignable_requests': assignable_requests,
        'review_requests': review_requests,
        'in_progress_requests': in_progress_requests,
        'completion_requests': completion_requests,
        'all_requests': all_requests,
        'available_members': available_members,
        'recommended_members': recommended_members,
        'ibtikar_budget': ibtikar_budget,
        'genoclab_revenue': genoclab_revenue,
        'budget_data': budget_data,
        'channel_filter': channel_filter,
        'status_filter': status_filter,
        'search_q': search_q,
        'status_choices': Request.STATUS_CHOICES,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/admin_ops/index.html', context)


@admin_required
def request_detail(request, pk):
    """Full request preview — shows all submitted data for review."""
    from core.models import Message

    req = get_object_or_404(Request, pk=pk)
    history = req.history.select_related('actor').order_by('created_at')
    comments = req.comments.select_related('author').order_by('created_at')
    messages_list = Message.objects.filter(request=req).select_related('from_user', 'to_user').order_by('created_at')
    allowed = get_allowed_transitions(req)

    # Load YAML service definition for parameter labels
    yaml_def = None
    if req.service:
        yaml_def = get_service_def(req.service.code)

    context = {
        'req': req,
        'history': history,
        'comments': comments,
        'messages_list': messages_list,
        'allowed_transitions': allowed,
        'yaml_def': yaml_def,
        'available_members': MemberProfile.objects.filter(available=True).select_related('user'),
        'status_choices': Request.STATUS_CHOICES,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/admin_ops/request_detail.html', context)


@admin_required
def transition_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    to_status = request.POST.get('to_status', '')
    notes = request.POST.get('notes', '')
    try:
        transition(req, to_status, request.user, notes=notes)
        messages.success(request, f"Demande {req.display_id} transférée vers {to_status}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def assign_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    member_id = request.POST.get('member_id')
    if not member_id:
        messages.error(request, "Veuillez sélectionner un analyste.")
        return redirect_back(request, 'dashboard:admin_ops')
    member = get_object_or_404(MemberProfile, pk=member_id)

    # Check if request is in a state that allows assignment
    if req.status not in ('PLATFORM_NOTE_GENERATED', 'PAYMENT_CONFIRMED'):
        messages.error(
            request,
            f"La demande {req.display_id} n'est pas prête pour l'assignation "
            f"(statut actuel: {req.get_status_display()})."
        )
        return redirect_back(request, 'dashboard:admin_ops')

    req.assigned_to = member
    req.save(update_fields=['assigned_to'])
    try:
        transition(req, 'ASSIGNED', request.user, notes=f"Assigné à {member.user.get_full_name()}")
        messages.success(request, f"Demande {req.display_id} assignée à {member.user.get_full_name()}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur d'assignation: {e}")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def award_points(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    points = int(request.POST.get('points', 0))
    reason = request.POST.get('reason', '')
    PointsHistory.objects.create(
        member=member, points=points, reason=reason, awarded_by=request.user
    )
    member.total_points += points
    member.save(update_fields=['total_points'])
    # Notify member
    Notification.objects.create(
        user=member.user,
        message=f"{points} points reçus ! {reason}" if reason else f"{points} points reçus !",
        notification_type='reward'
    )
    messages.success(request, f"{points} points attribués à {member.user.get_full_name()}.")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def send_cheer(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    message_text = request.POST.get('message', '')
    Cheer.objects.create(member=member, message=message_text, from_user=request.user)
    Notification.objects.create(
        user=member.user,
        message=f"Encouragement reçu : {message_text}" if message_text else "Vous avez reçu un encouragement !",
        notification_type='reward'
    )
    messages.success(request, f"Encouragement envoyé à {member.user.get_full_name()}.")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def modify_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    if req.appointment_confirmed:
        messages.error(request, "Le RDV est déjà confirmé, impossible de modifier.")
        return redirect_back(request, 'dashboard:admin_ops')
    date_str = request.POST.get('appointment_date', '')
    if date_str:
        from datetime import datetime
        req.appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        req.save(update_fields=['appointment_date'])
        messages.success(request, f"Date de RDV modifiée: {req.appointment_date}")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def report_review(request, pk):
    req = get_object_or_404(Request, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'validate':
            try:
                transition(req, 'REPORT_VALIDATED', request.user, notes='Rapport validé par admin')
                messages.success(request, f"Rapport {req.display_id} validé.")
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        elif action == 'send_back':
            revision_notes = request.POST.get('revision_notes', '')
            req.admin_revision_notes = revision_notes
            req.save(update_fields=['admin_revision_notes'])
            try:
                transition(
                    req, 'ANALYSIS_STARTED', request.user,
                    notes=f"Rapport renvoyé pour révision. {revision_notes}".strip()
                )
                # Notify the assigned analyst about the revision
                if req.assigned_to:
                    Notification.objects.create(
                        user=req.assigned_to.user,
                        message=f"{req.display_id}: Rapport renvoyé pour révision. {revision_notes}".strip(),
                        request=req,
                        notification_type='WORKFLOW',
                    )
                messages.success(request, f"Rapport {req.display_id} renvoyé pour révision.")
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        return redirect_back(request, 'dashboard:admin_ops')
    allowed = get_allowed_transitions(req)
    return render(request, 'dashboard/admin_ops/report_review.html', {
        'req': req,
        'allowed_transitions': allowed,
    })


@admin_required
def adjust_cost(request, pk):
    """Admin adjusts the validated cost of a request with justification."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    new_price = request.POST.get('admin_price', '')
    justification = request.POST.get('cost_justification', '')
    
    if not new_price:
        messages.error(request, "Veuillez saisir un montant.")
        return redirect_back(request, 'dashboard:admin_ops')
    
    try:
        price = float(new_price)
    except ValueError:
        messages.error(request, "Montant invalide.")
        return redirect_back(request, 'dashboard:admin_ops')
    
    old_price = req.admin_validated_price or req.budget_amount or req.quote_amount
    req.admin_validated_price = price
    req.save(update_fields=['admin_validated_price'])
    
    # Log to audit
    from core.audit import log_action
    log_action(
        action='COST_ADJUSTMENT',
        entity_type='REQUEST',
        entity_id=str(req.id),
        actor=request.user,
        details={
            'old_price': str(old_price),
            'new_price': str(price),
            'justification': justification,
        }
    )
    
    messages.success(request, f"Coût ajusté pour {req.display_id}: {price:,.0f} DA. {f'Justification: {justification}' if justification else ''}")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def prepare_quote(request, pk):
    """Admin prepares/edits a detailed quote for a GENOCLAB request."""
    req = get_object_or_404(Request, pk=pk)

    if request.method == 'POST':
        # Parse form data for line items
        items = []
        idx = 0
        while f'item_label_{idx}' in request.POST:
            label = request.POST.get(f'item_label_{idx}', '')
            unit_price = float(request.POST.get(f'item_unit_price_{idx}', 0))
            quantity = int(request.POST.get(f'item_quantity_{idx}', 0))
            total = unit_price * quantity
            if label:
                items.append({
                    'label': label,
                    'unit_price': unit_price,
                    'quantity': quantity,
                    'total': total,
                })
            idx += 1

        admin_fees = float(request.POST.get('admin_fees', 0))
        report_fees = float(request.POST.get('report_fees', 0))
        vat_rate = float(request.POST.get('vat_rate', 19)) / 100
        notes = request.POST.get('quote_notes', '')

        subtotal_ht = sum(item['total'] for item in items)
        subtotal_before_tax = subtotal_ht + admin_fees + report_fees
        vat_amount = round(subtotal_before_tax * vat_rate, 2)
        total_ttc = round(subtotal_before_tax + vat_amount, 2)

        quote_detail = {
            'items': items,
            'subtotal_ht': subtotal_ht,
            'admin_fees': admin_fees,
            'report_fees': report_fees,
            'subtotal_before_tax': subtotal_before_tax,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'total_ttc': total_ttc,
            'notes': notes,
        }

        req.quote_detail = quote_detail
        req.quote_amount = total_ttc
        req.save(update_fields=['quote_detail', 'quote_amount'])

        action = request.POST.get('action', 'save')
        if action == 'send':
            # Transition to QUOTE_DRAFT first (if still REQUEST_CREATED), then to QUOTE_SENT
            try:
                if req.status == 'REQUEST_CREATED':
                    transition(req, 'QUOTE_DRAFT', request.user, notes='Devis préparé')
                if req.status == 'QUOTE_DRAFT':
                    transition(req, 'QUOTE_SENT', request.user, notes='Devis envoyé au client')
                messages.success(request, f"Devis envoyé au client pour {req.display_id}.")
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        else:
            # Just save as draft
            if req.status == 'REQUEST_CREATED':
                try:
                    transition(req, 'QUOTE_DRAFT', request.user, notes='Devis en brouillon')
                except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                    messages.error(request, str(e))
            messages.success(request, f"Devis enregistré pour {req.display_id}.")

        return redirect('dashboard:admin_request_detail', pk=req.pk)

    # GET: Show quote form with auto-estimate
    yaml_def = get_service_def(req.service.code) if req.service else None
    auto_estimate = _compute_auto_estimate(req, yaml_def)

    import json
    existing_quote = req.quote_detail or {}
    context = {
        'req': req,
        'yaml_def': yaml_def,
        'auto_estimate': auto_estimate,
        'existing_quote': existing_quote,
        'existing_items_json': json.dumps(existing_quote.get('items', [])),
    }
    return render(request, 'dashboard/admin_ops/prepare_quote.html', context)


def _compute_auto_estimate(req, yaml_def):
    """Compute auto price estimate from YAML pricing + sample table."""
    if not yaml_def:
        return None
    try:
        result = calculate_price(yaml_def, req.service_params or {}, req.sample_table or [])
        return result
    except Exception:
        return None


@admin_required
def generate_invoice(request, pk):
    """Generate an invoice from a GENOCLAB request's quote."""
    req = get_object_or_404(Request, pk=pk)

    if request.method == 'POST':
        quote = req.quote_detail or {}
        items = quote.get('items', [])

        # Build invoice line items from quote
        line_items = []
        for item in items:
            line_items.append({
                'description': item['label'],
                'unit_price': item['unit_price'],
                'quantity': item['quantity'],
                'total': item['total'],
            })
        if quote.get('admin_fees', 0) > 0:
            line_items.append({'description': 'Frais administratifs', 'unit_price': quote['admin_fees'], 'quantity': 1, 'total': quote['admin_fees']})
        if quote.get('report_fees', 0) > 0:
            line_items.append({'description': 'Frais de rapport', 'unit_price': quote['report_fees'], 'quantity': 1, 'total': quote['report_fees']})

        # Generate invoice number
        from datetime import datetime
        year = datetime.now().year
        count = Invoice.objects.filter(created_at__year=year).count() + 1
        invoice_number = f"GCL-INV-{year}-{count:04d}"

        subtotal_ht = quote.get('subtotal_before_tax', float(req.quote_amount))
        vat_rate = quote.get('vat_rate', 0.19)
        vat_amount = quote.get('vat_amount', round(subtotal_ht * vat_rate, 2))
        total_ttc = quote.get('total_ttc', round(subtotal_ht + vat_amount, 2))

        Invoice.objects.create(
            invoice_number=invoice_number,
            request=req,
            client=req.requester,
            line_items=line_items,
            subtotal_ht=subtotal_ht,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_ttc=total_ttc,
            created_by=request.user,
        )

        # Transition to INVOICE_GENERATED
        try:
            transition(req, 'INVOICE_GENERATED', request.user, notes=f'Facture {invoice_number} générée')
            messages.success(request, f"Facture {invoice_number} générée pour {req.display_id}.")
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, str(e))

        return redirect('dashboard:admin_request_detail', pk=req.pk)

    return redirect('dashboard:admin_request_detail', pk=req.pk)


@admin_required
def confirm_payment(request, pk):
    """Admin confirms payment for a GENOCLAB request."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    try:
        transition(req, 'PAYMENT_CONFIRMED', request.user, notes='Paiement confirmé par admin')
        messages.success(request, f"Paiement confirmé pour {req.display_id}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect('dashboard:admin_request_detail', pk=req.pk)
