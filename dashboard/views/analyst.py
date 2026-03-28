from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request
from core.workflow import get_allowed_transitions, transition
from core.productivity import compute_member_productivity
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


def analyst_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'MEMBER':
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@analyst_required
def index(request):
    try:
        profile = request.user.member_profile
    except MemberProfile.DoesNotExist:
        profile = MemberProfile.objects.create(user=request.user)

    assigned_count = Request.objects.filter(assigned_to=profile).count()
    in_progress_count = Request.objects.filter(
        assigned_to=profile,
        status__in=['ANALYSIS_STARTED', 'SAMPLE_RECEIVED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'PENDING_ACCEPTANCE']
    ).count()
    completed_count = Request.objects.filter(
        assigned_to=profile, status__in=['COMPLETED', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT']
    ).count()

    # Pending tasks: waiting for analyst action
    pending_tasks = Request.objects.filter(
        assigned_to=profile,
        status__in=['PENDING_ACCEPTANCE', 'ASSIGNED']
    ).select_related('service', 'requester').order_by('-created_at')

    # In-progress work
    in_progress = Request.objects.filter(
        assigned_to=profile,
        status__in=[
            'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
            'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
        ]
    ).select_related('service', 'requester').order_by('-updated_at')

    # Completed history
    history = Request.objects.filter(
        assigned_to=profile,
        status__in=['COMPLETED', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT']
    ).select_related('service', 'requester').order_by('-updated_at')[:30]

    # Points and cheers
    points_history = profile.points_history.order_by('-created_at')[:10]
    cheers = profile.cheers.order_by('-created_at')[:10]

    # Productivity from engine
    productivity_data = compute_member_productivity(profile)

    # Notifications
    notifications = Notification.objects.filter(user=request.user, read=False).order_by('-created_at')[:10]

    context = {
        'profile': profile,
        'assigned_count': assigned_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'productivity': profile.productivity_score,
        'productivity_data': productivity_data,
        'pending_tasks': pending_tasks,
        'in_progress': in_progress,
        'history': history,
        'points_history': points_history,
        'cheers': cheers,
        'notifications': notifications,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/analyst/index.html', context)


@analyst_required
def accept_task(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    req.assignment_accepted = True
    req.assignment_accepted_at = timezone.now()
    req.save(update_fields=['assignment_accepted', 'assignment_accepted_at'])
    try:
        transition(req, 'APPOINTMENT_PROPOSED', request.user, notes='Tâche acceptée')
    except (InvalidTransitionError, AuthorizationError, ValueError):
        pass
    messages.success(request, f"Tâche {req.display_id} acceptée.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def decline_task(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    req.assignment_declined = True
    req.assignment_decline_reason = request.POST.get('reason', '')
    req.assigned_to = None
    req.save(update_fields=['assignment_declined', 'assignment_decline_reason', 'assigned_to'])
    try:
        transition(req, 'ASSIGNED', request.user, notes=f'Déclinée: {req.assignment_decline_reason}')
    except (InvalidTransitionError, AuthorizationError, ValueError):
        pass
    messages.success(request, f"Tâche {req.display_id} déclinée.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def workflow_action(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    to_status = request.POST.get('to_status', '')
    notes = request.POST.get('notes', '')
    try:
        transition(req, to_status, request.user, notes=notes)
        messages.success(request, f"Demande {req.display_id} mise à jour.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def suggest_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    date_str = request.POST.get('appointment_date', '')
    time_str = request.POST.get('appointment_time', '')
    appointment_note = request.POST.get('appointment_note', '')
    if date_str:
        from datetime import datetime
        try:
            req.appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            req.appointment_proposed_by = request.user
            req.save(update_fields=['appointment_date', 'appointment_proposed_by'])
            # Build transition notes with time and message
            notes_parts = [f'RDV proposé: {req.appointment_date}']
            if time_str:
                notes_parts.append(f'Heure: {time_str}')
            if appointment_note:
                notes_parts.append(f'Note: {appointment_note}')
            transition_notes = ' — '.join(notes_parts)
            # Transition to APPOINTMENT_PROPOSED if currently ASSIGNED
            if req.status == 'ASSIGNED':
                try:
                    transition(req, 'APPOINTMENT_PROPOSED', request.user, notes=transition_notes)
                except (InvalidTransitionError, AuthorizationError, ValueError):
                    pass
            messages.success(request, f"Date de RDV proposée: {req.appointment_date}" + (f" à {time_str}" if time_str else ""))
        except ValueError:
            messages.error(request, "Date invalide.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def upload_report(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    if 'report_file' in request.FILES:
        req.report_file = request.FILES['report_file']
        req.save(update_fields=['report_file'])
        try:
            transition(req, 'REPORT_UPLOADED', request.user, notes='Rapport uploadé')
            messages.success(request, f"Rapport uploadé pour {req.display_id}.")
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Veuillez sélectionner un fichier.")
    return redirect_back(request, 'dashboard:analyst')
