from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back, paginate_queryset
from django.contrib import messages
from django.utils import timezone
from dashboard.decorators import analyst_required

from accounts.models import MemberProfile
from core.models import Request
from core.workflow import get_allowed_transitions, transition
from core.state_machine import get_decline_return_state, is_acceptance_state
from core.productivity import compute_member_productivity
from core.exceptions import InvalidTransitionError, AuthorizationError
from notifications.models import Notification


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
    ).select_related('service', 'requester').prefetch_related('comments').order_by('-updated_at')

    # Completed history - paginated
    history_qs = Request.objects.filter(
        assigned_to=profile,
        status__in=['COMPLETED', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT']
    ).select_related('service', 'requester').order_by('-updated_at')
    history_paginator, history, _ = paginate_queryset(history_qs, request, per_page=25, page_param='history_page')

    # Points and cheers - paginated
    points_paginator, points_history, _ = paginate_queryset(profile.points_history.order_by('-created_at'), request, per_page=10, page_param='points_page')
    cheers_paginator, cheers, _ = paginate_queryset(profile.cheers.order_by('-created_at'), request, per_page=10, page_param='cheers_page')

    # Productivity from engine
    productivity_data = compute_member_productivity(profile)

    # Notifications - paginated
    notifications_paginator, notifications, _ = paginate_queryset(
        Notification.objects.filter(user=request.user, read=False).order_by('-created_at'),
        request, per_page=10, page_param='notif_page'
    )

    # Ranking position among all members (sorted by productivity_score desc, total_points desc)
    all_members = list(MemberProfile.objects.order_by('-productivity_score', '-total_points').values_list('pk', flat=True))
    try:
        rank_position = all_members.index(profile.pk) + 1
    except ValueError:
        rank_position = None
    total_members_count = len(all_members)

    # Performance status label based on productivity_score
    score = profile.productivity_score
    if score >= 90:
        perf_status = {'label': '🔥 On Fire', 'color': '#dc2626', 'bg': '#fee2e2'}
    elif score >= 75:
        perf_status = {'label': '⭐ Very Good', 'color': '#d97706', 'bg': '#fef3c7'}
    elif score >= 55:
        perf_status = {'label': '✅ Good', 'color': '#059669', 'bg': '#d1fae5'}
    elif score >= 35:
        perf_status = {'label': '👍 Not Bad', 'color': '#0284c7', 'bg': '#dbeafe'}
    else:
        perf_status = {'label': '⏰ Wake Up!', 'color': '#6b7280', 'bg': '#f3f4f6'}

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
        'history_paginator': history_paginator,
        'points_history': points_history,
        'points_paginator': points_paginator,
        'cheers': cheers,
        'cheers_paginator': cheers_paginator,
        'notifications': notifications,
        'notifications_paginator': notifications_paginator,
        'now': timezone.now(),
        'rank_position': rank_position,
        'total_members_count': total_members_count,
        'perf_status': perf_status,
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
        transition(req, 'ACCEPTED', request.user, notes='Tâche acceptée')
        messages.success(request, f"Tâche {req.display_id} acceptée. Proposez un rendez-vous pour continuer.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur: {str(e)}")
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
    req.save(update_fields=['assignment_declined', 'assignment_decline_reason'])
    try:
        # First transition to DECLINED state
        transition(req, 'DECLINED', request.user, notes=f'Déclinée: {req.assignment_decline_reason}')

        # Get return state for reassignment by admin
        return_state = get_decline_return_state(req.channel)

        # Clear assignment before returning to admin
        req.assigned_to = None
        req.save(update_fields=['assigned_to'])

        # Transition to return state for reassignment
        transition(req, return_state, request.user, notes='Retour pour réassignation après refus')

        # Notify admin that task was declined
        from notifications.services import notify_admin_task_declined
        notify_admin_task_declined(req, profile, req.assignment_decline_reason)

        messages.success(request, f"Tâche {req.display_id} déclinée. L'administrateur va être notifié.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur: {str(e)}")
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
        
        # For GENOCLAB: when analysis is finished, notify client to pay before report delivery
        if to_status == 'ANALYSIS_FINISHED' and req.channel == 'GENOCLAB':
            from notifications.services import notify_payment_request
            notify_payment_request(req)
            messages.success(request, f"Demande {req.display_id} mise à jour. Le client a été notifié pour le paiement.")
        else:
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
            # Transition to APPOINTMENT_PROPOSED if currently ASSIGNED or APPOINTMENT_RESCHEDULING_REQUESTED
            if req.status in ['ASSIGNED', 'APPOINTMENT_RESCHEDULING_REQUESTED']:
                try:
                    transition(req, 'APPOINTMENT_PROPOSED', request.user, notes=transition_notes)
                except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                    messages.error(request, f"Erreur: {str(e)}")
            messages.success(request, f"Date de RDV proposée: {req.appointment_date}" + (f" à {time_str}" if time_str else ""))
        except ValueError:
            messages.error(request, "Date invalide.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def request_detail(request, pk):
    from core.models import RequestComment, Message
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    # Allow access to currently assigned requests AND historical ones (once completed/sent)
    from core.models import RequestHistory
    was_assigned = req.assigned_to == profile or req.history.filter(actor=request.user).exists()
    if not was_assigned:
        return HttpResponseForbidden()
    history = req.history.select_related('actor').order_by('created_at')
    comments = req.comments.select_related('author').order_by('created_at')
    messages_list = Message.objects.filter(request=req).select_related('from_user', 'to_user').order_by('created_at')
    return render(request, 'dashboard/analyst/request_detail.html', {
        'req': req, 'history': history, 'comments': comments,
        'messages_list': messages_list, 'now': timezone.now(),
    })


@analyst_required
def accept_alt_date(request, pk):
    """Analyst accepts the requester/client's proposed alternative date."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    if not req.alt_date_proposed:
        messages.error(request, "Aucune date alternative à accepter.")
        return redirect_back(request, 'dashboard:analyst')

    # Update appointment date to the proposed alternative
    import uuid as _uuid
    old_date = req.appointment_date
    req.appointment_date = req.alt_date_proposed
    req.appointment_confirmed = True
    req.appointment_confirmed_at = timezone.now()
    req.alt_date_proposed = None
    req.alt_date_note = ''
    if not req.report_token:
        req.report_token = _uuid.uuid4()
    req.save(update_fields=[
        'appointment_date', 'appointment_confirmed', 'appointment_confirmed_at',
        'alt_date_proposed', 'alt_date_note', 'report_token',
    ])

    # Transition to APPOINTMENT_CONFIRMED if currently APPOINTMENT_PROPOSED
    if req.status == 'APPOINTMENT_PROPOSED':
        try:
            transition(
                req, 'APPOINTMENT_CONFIRMED', request.user,
                notes=f"Date alternative acceptée: {req.appointment_date.strftime('%d/%m/%Y')} (ancienne: {old_date})"
            )
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, f"Erreur: {str(e)}")

    # Notify the requester/client
    if req.requester:
        Notification.objects.create(
            user=req.requester,
            message=f"{req.display_id}: Date alternative acceptée — RDV confirmé le {req.appointment_date.strftime('%d/%m/%Y')}",
            request=req,
            notification_type='WORKFLOW',
        )

    messages.success(request, f"Date alternative acceptée. RDV confirmé le {req.appointment_date.strftime('%d/%m/%Y')}.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def decline_alt_date(request, pk):
    """Analyst declines the requester/client's proposed alternative date."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()

    decline_reason = request.POST.get('decline_reason', '')

    # Clear the proposed alternative
    req.alt_date_proposed = None
    req.alt_date_note = ''
    req.save(update_fields=['alt_date_proposed', 'alt_date_note'])

    # Log as comment
    from core.models import RequestComment
    RequestComment.objects.create(
        request=req, author=request.user,
        text=f"Date alternative refusée. {decline_reason}".strip(),
        step=req.status,
    )

    # Notify the requester/client
    if req.requester:
        msg = f"{req.display_id}: Date alternative refusée par l'analyste."
        if decline_reason:
            msg += f" Raison: {decline_reason}"
        Notification.objects.create(
            user=req.requester,
            message=msg,
            request=req,
            notification_type='WORKFLOW',
        )

    messages.success(request, "Date alternative refusée. Le demandeur en sera notifié.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def upload_report(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    profile = request.user.member_profile
    if req.assigned_to != profile:
        return HttpResponseForbidden()
    
    # For GENOCLAB: Payment must be confirmed before report upload
    if req.channel == 'GENOCLAB' and req.status != 'PAYMENT_CONFIRMED':
        messages.error(request, "Le paiement doit être confirmé avant de télécharger le rapport. Le client sera notifié pour effectuer le paiement.")
        return redirect_back(request, 'dashboard:analyst')
    
    if 'report_file' in request.FILES:
        # Archive the previous report version if exists
        from core.models import ReportVersion
        if req.report_file:
            ReportVersion.objects.create(
                request=req,
                file=req.report_file,
                uploaded_by=request.user,
                version_number=req.report_versions.count() + 1,
                notes=f"Version {req.report_versions.count() + 1} uploaded"
            )
        
        req.report_file = request.FILES['report_file']
        req.save(update_fields=['report_file'])
        
        # Only transition if request is not already closed
        if req.status not in ['CLOSED']:
            try:
                transition(req, 'REPORT_UPLOADED', request.user, notes='Rapport uploadé')
                messages.success(request, f"Rapport uploadé pour {req.display_id}.")
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        else:
            # Just save the new version for closed requests
            messages.success(request, f"Nouvelle version du rapport uploadée pour {req.display_id}.")
            
            # Notify requester about new revision
            if req.requester:
                Notification.objects.create(
                    user=req.requester,
                    message=f"{req.display_id}: Nouvelle version du rapport disponible",
                    request=req,
                    notification_type='WORKFLOW',
                )
    else:
        messages.error(request, "Veuillez sélectionner un fichier.")
    return redirect_back(request, 'dashboard:analyst')


@analyst_required
def collect_gift(request):
    """Member marks their gift as collected (physically picked up from admin)."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    profile = request.user.member_profile
    if profile.gift_unlocked and not profile.gift_collected:
        profile.gift_collected = True
        profile.save(update_fields=['gift_collected'])
        messages.success(request, "🎁 Cadeau marqué comme récupéré ! Rendez-vous chez l'administrateur.")
    else:
        messages.info(request, "Aucun cadeau disponible à récupérer.")
    return redirect_back(request, 'dashboard:analyst')
