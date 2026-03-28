from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone

from accounts.models import MemberProfile, Cheer, PointsHistory
from core.models import Request, Invoice
from core.workflow import get_allowed_transitions, transition
from core.assignment import get_recommended_members
from core.exceptions import InvalidTransitionError, AuthorizationError


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
    return redirect('dashboard:admin_ops')


@admin_required
def assign_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    member_id = request.POST.get('member_id')
    if not member_id:
        messages.error(request, "Veuillez sélectionner un analyste.")
        return redirect('dashboard:admin_ops')
    member = get_object_or_404(MemberProfile, pk=member_id)

    # Check if request is in a state that allows assignment
    if req.status not in ('PLATFORM_NOTE_GENERATED', 'PAYMENT_CONFIRMED'):
        messages.error(
            request,
            f"La demande {req.display_id} n'est pas prête pour l'assignation "
            f"(statut actuel: {req.get_status_display()})."
        )
        return redirect('dashboard:admin_ops')

    req.assigned_to = member
    req.save(update_fields=['assigned_to'])
    try:
        transition(req, 'ASSIGNED', request.user, notes=f"Assigné à {member.user.get_full_name()}")
        messages.success(request, f"Demande {req.display_id} assignée à {member.user.get_full_name()}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur d'assignation: {e}")
    return redirect('dashboard:admin_ops')


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
    messages.success(request, f"{points} points attribués à {member.user.get_full_name()}.")
    return redirect('dashboard:admin_ops')


@admin_required
def send_cheer(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    message_text = request.POST.get('message', '')
    Cheer.objects.create(member=member, message=message_text, from_user=request.user)
    messages.success(request, f"Encouragement envoyé à {member.user.get_full_name()}.")
    return redirect('dashboard:admin_ops')


@admin_required
def modify_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    if req.appointment_confirmed:
        messages.error(request, "Le RDV est déjà confirmé, impossible de modifier.")
        return redirect('dashboard:admin_ops')
    date_str = request.POST.get('appointment_date', '')
    if date_str:
        from datetime import datetime
        req.appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        req.save(update_fields=['appointment_date'])
        messages.success(request, f"Date de RDV modifiée: {req.appointment_date}")
    return redirect('dashboard:admin_ops')


@admin_required
def report_review(request, pk):
    req = get_object_or_404(Request, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'validate':
            try:
                transition(req, 'REPORT_VALIDATED', request.user, notes='Rapport validé par admin')
                messages.success(request, f"Rapport {req.display_id} validé.")
            except ValueError as e:
                messages.error(request, str(e))
        elif action == 'send_back':
            req.admin_revision_notes = request.POST.get('revision_notes', '')
            req.save(update_fields=['admin_revision_notes'])
            try:
                transition(req, 'ANALYSIS_STARTED', request.user, notes='Rapport renvoyé pour révision')
                messages.success(request, f"Rapport {req.display_id} renvoyé pour révision.")
            except ValueError as e:
                messages.error(request, str(e))
        return redirect('dashboard:admin_ops')
    allowed = get_allowed_transitions(req)
    return render(request, 'dashboard/admin_ops/report_review.html', {
        'req': req,
        'allowed_transitions': allowed,
    })
