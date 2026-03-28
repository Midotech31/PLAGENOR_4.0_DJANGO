from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request
from core.workflow import get_allowed_transitions, transition
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
        status__in=['ANALYSIS_STARTED', 'SAMPLE_RECEIVED', 'APPOINTMENT_SCHEDULED', 'PENDING_ACCEPTANCE']
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
            'APPOINTMENT_SCHEDULED', 'SAMPLE_RECEIVED',
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

    # Notifications
    notifications = Notification.objects.filter(user=request.user, read=False).order_by('-created_at')[:10]

    context = {
        'profile': profile,
        'assigned_count': assigned_count,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'productivity': profile.productivity_score,
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
        transition(req, 'APPOINTMENT_SCHEDULED', request.user, notes='Tâche acceptée')
    except ValueError:
        try:
            transition(req, 'PENDING_ACCEPTANCE', request.user, notes='Tâche acceptée')
        except ValueError:
            pass
    messages.success(request, f"Tâche {req.display_id} acceptée.")
    return redirect('dashboard:analyst')


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
    except ValueError:
        pass
    messages.success(request, f"Tâche {req.display_id} déclinée.")
    return redirect('dashboard:analyst')


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
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('dashboard:analyst')


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
        except ValueError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Veuillez sélectionner un fichier.")
    return redirect('dashboard:analyst')
