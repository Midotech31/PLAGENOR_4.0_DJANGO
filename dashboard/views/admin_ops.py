from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back, redirect_to_detail, safe_int, safe_float
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone

from accounts.models import MemberProfile, Cheer, PointsHistory
from core.models import Request, RequestHistory, RequestComment, Invoice
from core.workflow import get_allowed_transitions, transition
from core.assignment import get_recommended_members
from core.assignment import member_is_eligible
from core.registry import get_service_def
from core.pricing import calculate_price
from core.exceptions import (
    InvalidTransitionError, AuthorizationError, FinancialValidationError,
)
from core.financial import compute_invoice_totals, parse_money
from core.uploads import validate_upload
from django.core.exceptions import ValidationError
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
        status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED']
    ).count()
    ibtikar_count = Request.objects.filter(channel='IBTIKAR').count()
    genoclab_count = Request.objects.filter(channel='GENOCLAB').count()
    completed_count = Request.objects.filter(status='COMPLETED').count()

    # Pending requests needing action (all non-terminal, non-assigned states)
    pending_requests = Request.objects.filter(
        status__in=[
            'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'PLATFORM_NOTE_GENERATED',
            'REPORT_UPLOADED', 'REPORT_VALIDATED',
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

    # Requests ready for assignment — newly-ready requests plus tasks an
    # analyst declined (back to ASSIGNED with no assignee).
    assignable_requests = Request.objects.filter(
        Q(status__in=['IBTIKAR_CODE_SUBMITTED', 'ORDER_UPLOADED', 'INVOICE_GENERATED'])
        | Q(status='ASSIGNED', assigned_to__isnull=True)
    ).select_related('service', 'requester').order_by('-created_at')

    # Requests needing report review
    review_requests = Request.objects.filter(
        status__in=['REPORT_UPLOADED']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')

    # In-progress requests (assigned, appointment, analysis phases)
    in_progress_requests = Request.objects.filter(
        status__in=[
            'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
            'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
        ]
    ).select_related('service', 'requester', 'assigned_to__user').prefetch_related('messages__from_user').order_by('-updated_at')

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

    # All members sorted by performance (productivity_score desc, then total_points desc)
    all_members_ranked = MemberProfile.objects.select_related('user').order_by(
        '-productivity_score', '-total_points'
    )
    # Compute max values for bar scaling
    max_productivity = max((m.productivity_score for m in all_members_ranked), default=100) or 100
    max_points = max((m.total_points for m in all_members_ranked), default=1) or 1

    # Budget overview from financial engine
    from core.financial import get_budget_dashboard
    budget_data = get_budget_dashboard()
    ibtikar_budget = budget_data['ibtikar']['total']
    genoclab_revenue = budget_data['genoclab']['total']

    # Ratings & Reviews overview
    from django.db.models import Avg
    rated_requests = Request.objects.filter(service_rating__isnull=False)
    avg_rating = rated_requests.aggregate(avg=Avg('service_rating'))['avg'] or 0
    total_ratings = rated_requests.count()
    recent_reviews = rated_requests.select_related('requester', 'service').order_by('-rated_at')[:10]

    # Rating distribution with computed percentages
    rating_distribution = {}
    rating_percentages = {}
    for star in range(1, 6):
        count = rated_requests.filter(service_rating=star).count()
        rating_distribution[star] = count
        rating_percentages[star] = round((count / total_ratings * 100), 1) if total_ratings > 0 else 0
    
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
        # Ratings & Reviews
        'avg_rating': avg_rating,
        'total_ratings': total_ratings,
        'recent_reviews': recent_reviews,
        'rating_distribution': rating_distribution,
        'rating_percentages': rating_percentages,
        # Performance ranking
        'all_members_ranked': all_members_ranked,
        'max_productivity': max_productivity,
        'max_points': max_points,
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

    # Pre-compute the "still in the analyst pipeline" flag for the
    # template. Django's {% if x in 'A B C'.split %} hack tries to call
    # str.split as an attribute and fails with TemplateSyntaxError, so
    # we hand the check off here instead.
    REASSIGN_ACTIVE_STATES = (
        'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
        'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
    )
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
        'can_reassign_active': req.status in REASSIGN_ACTIVE_STATES,
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
    return redirect_to_detail(request, req, 'dashboard:admin_ops')


@admin_required
def assign_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    member_id = request.POST.get('member_id')
    if not member_id:
        messages.error(request, "Veuillez sélectionner un analyste.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')
    member = get_object_or_404(MemberProfile, pk=member_id)
    if not member_is_eligible(member, req.service):
        messages.error(
            request,
            "Cet analyste n'est pas éligible: vérifiez son activation, sa "
            "disponibilité, sa charge et ses techniques certifiées.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    previous = req.assigned_to  # may be None
    reason = (request.POST.get('reason', '') or '').strip()

    # Reassignment paths
    # ──────────────────
    #   1) Decline-rebound:  status=ASSIGNED & assigned_to=None       (the
    #      analyst declined; admin picks a replacement; no status edge).
    #   2) Active reassignment: assigned_to is set on a request that is
    #      still in the analyst's hands (ASSIGNED through ANALYSIS_FINISHED).
    #      Used when the assignee is late / absent / off. We require a
    #      non-empty reason for the audit trail, log_action, and notify
    #      both the outgoing and incoming analyst.
    #   3) Standard assignment: post-validation states that flow into the
    #      analyst pipeline (IBTIKAR_CODE_SUBMITTED, ORDER_UPLOADED,
    #      INVOICE_GENERATED). Drives the state machine transition.
    REASSIGN_ACTIVE_STATES = (
        'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
        'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
    )
    is_decline_rebound = (req.status == 'ASSIGNED' and previous is None)
    is_active_reassignment = (
        previous is not None
        and previous.pk != member.pk
        and req.status in REASSIGN_ACTIVE_STATES
    )
    is_initial_assign = req.status in (
        'IBTIKAR_CODE_SUBMITTED', 'ORDER_UPLOADED', 'INVOICE_GENERATED',
    )

    if not (is_decline_rebound or is_active_reassignment or is_initial_assign):
        messages.error(
            request,
            f"La demande {req.display_id} n'est pas prête pour l'assignation "
            f"(statut actuel: {req.get_status_display()})."
        )
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    if is_active_reassignment and len(reason) < 5:
        messages.error(
            request,
            "Une raison (retard, absence, congé, surcharge…) d'au moins "
            "5 caractères est obligatoire pour réassigner une demande en cours.",
        )
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    if (is_decline_rebound or is_active_reassignment) and previous is not None and previous.pk == member.pk:
        messages.warning(request, "L'analyste sélectionné est déjà l'assigné de cette demande.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    req.assigned_to = member
    if is_active_reassignment:
        # Reset assignment_accepted so the new analyst has to accept the
        # task explicitly — they shouldn't inherit the previous one's
        # acceptance flag.
        req.assignment_accepted = False
        req.assignment_accepted_at = None
        req.save(update_fields=['assigned_to', 'assignment_accepted', 'assignment_accepted_at'])
    else:
        req.save(update_fields=['assigned_to'])

    if is_decline_rebound:
        RequestHistory.objects.create(
            request=req, from_status='ASSIGNED', to_status='ASSIGNED',
            actor=request.user, notes=f"Réassigné à {member.user.get_full_name()}",
        )
        Notification.objects.create(
            user=member.user,
            message=f"Nouvelle tâche assignée — {req.display_id}",
            request=req, notification_type='ASSIGNMENT',
        )
        messages.success(request, f"Demande {req.display_id} réassignée à {member.user.get_full_name()}.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    if is_active_reassignment:
        # No status edge — we stay in REASSIGN_ACTIVE_STATES. The audit
        # entry uses status→status so the timeline still shows the event.
        RequestHistory.objects.create(
            request=req, from_status=req.status, to_status=req.status,
            actor=request.user,
            notes=(
                f"Réassignée de {previous.user.get_full_name()} à "
                f"{member.user.get_full_name()}. Raison : {reason}"
            ),
        )
        # Outgoing analyst
        Notification.objects.create(
            user=previous.user,
            message=(
                f"{req.display_id} : la demande vous a été retirée et "
                f"confiée à {member.user.get_full_name()}. Raison : {reason}"
            ),
            request=req, notification_type='ASSIGNMENT',
        )
        # Incoming analyst
        Notification.objects.create(
            user=member.user,
            message=(
                f"{req.display_id} : tâche réassignée à vous. "
                f"Statut courant : {req.get_status_display()}. Raison : {reason}"
            ),
            request=req, notification_type='ASSIGNMENT',
        )
        messages.success(
            request,
            f"Demande {req.display_id} réassignée de {previous.user.get_full_name()} "
            f"à {member.user.get_full_name()}.",
        )
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    try:
        transition(req, 'ASSIGNED', request.user, notes=f"Assigné à {member.user.get_full_name()}")
        messages.success(request, f"Demande {req.display_id} assignée à {member.user.get_full_name()}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, f"Erreur d'assignation: {e}")
    return redirect_to_detail(request, req, 'dashboard:admin_ops')


@login_required
def platform_note_view(request, pk):
    """Internal devis (note de plateforme) for IBTIKAR requests.

    Visibility is strictly limited to people who legitimately need it:
        * SUPER_ADMIN / PLATFORM_ADMIN
        * the request's currently assigned analyst
        * the request's observers (informed_members)
    Everyone else gets 403. The note carries the full tariff
    justification so the admin can defend the total line by line.

    GENOCLAB has its own quote pipeline; this endpoint is IBTIKAR-only
    and refuses (404) otherwise.
    """
    req = get_object_or_404(Request, pk=pk)
    if req.channel != 'IBTIKAR':
        raise Http404("La note de plateforme est propre au canal IBTIKAR.")

    user = request.user
    is_admin = user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')
    is_assignee = (
        req.assigned_to is not None
        and req.assigned_to.user_id == user.pk
    )
    profile = getattr(user, 'member_profile', None)
    is_observer = (
        profile is not None
        and req.informed_members.filter(pk=profile.pk).exists()
    )
    if not (is_admin or is_assignee or is_observer):
        return HttpResponseForbidden()

    # Status gate. The platform note is the DGRSDT-bound devis the
    # admin uses to argue the budget consumption — it only makes sense
    # AFTER pedagogical + financial validation. Generating it before
    # the request has passed those checks would let the admin (or an
    # observer) print a document with an unvalidated tariff.
    READY_STATUSES = {
        'PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING',
        'IBTIKAR_CODE_SUBMITTED', 'ASSIGNED',
        'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
        'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
        'REPORT_UPLOADED', 'REPORT_VALIDATED',
        'SENT_TO_REQUESTER', 'COMPLETED', 'CLOSED',
    }
    if req.status not in READY_STATUSES:
        messages.error(
            request,
            "La note de plateforme ne peut être générée qu'après la "
            "validation pédagogique et financière de la demande "
            f"(statut actuel : {req.get_status_display()})."
        )
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    # Generate fresh on each view so the document always reflects the
    # current price / parameters / sample table. Cheap (a few hundred ms
    # for a typical request), and avoids stale-cache classes of bugs.
    from documents.generators import generate_platform_note
    path = generate_platform_note(req)

    # Stream as a download (attachment) using the FileResponse helper.
    from django.http import FileResponse
    return FileResponse(
        open(path, 'rb'), as_attachment=True,
        filename=f"NOTE_PLATEFORME_{req.display_id}.docx",
    )


@login_required
def download_quote(request, pk):
    """Serve the GENOCLAB quote (devis) as a DOCX, with access gating.

    Visibility:
      * SUPER_ADMIN / PLATFORM_ADMIN
      * the requester themselves (the CLIENT who owns the request)
      * the assigned analyst, if any
    GENOCLAB only — IBTIKAR doesn't use the commercial quote pipeline.
    Refuses with 404 when no quote has been prepared yet (status before
    QUOTE_DRAFT, or empty quote_detail), so the UI never points at an
    empty document.
    """
    req = get_object_or_404(Request, pk=pk)
    if req.channel != 'GENOCLAB':
        raise Http404("Le devis est propre au canal GENOCLAB.")
    if not req.quote_detail or req.status in ('REQUEST_CREATED',):
        raise Http404("Aucun devis préparé pour cette demande.")

    user = request.user
    is_admin = user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')
    is_owner = (req.requester_id == user.pk)
    is_assignee = (
        req.assigned_to is not None
        and req.assigned_to.user_id == user.pk
    )
    if not (is_admin or is_owner or is_assignee):
        return HttpResponseForbidden()

    from documents.generators import generate_quote
    from django.http import FileResponse
    path = generate_quote(req)
    return FileResponse(
        open(path, 'rb'), as_attachment=True,
        filename=f"DEVIS_{req.display_id}.docx",
    )


@login_required
def download_invoice(request, pk):
    """Serve a GENOCLAB invoice as a DOCX, with access gating.

    Visibility:
      * SUPER_ADMIN / PLATFORM_ADMIN
      * the invoice's billed client
      * the assigned analyst of the underlying request (so they can
        cross-check the figures against the analysis they performed)
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    user = request.user
    is_admin = user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')
    is_owner = (invoice.client_id == user.pk)
    is_assignee = (
        invoice.request is not None
        and invoice.request.assigned_to is not None
        and invoice.request.assigned_to.user_id == user.pk
    )
    if not (is_admin or is_owner or is_assignee):
        return HttpResponseForbidden()

    from documents.generators import generate_invoice_document
    from django.http import FileResponse
    path = generate_invoice_document(invoice)
    return FileResponse(
        open(path, 'rb'), as_attachment=True,
        filename=f"FACTURE_{invoice.invoice_number}.docx",
    )


@admin_required
def manage_observers(request, pk):
    """Add or remove read-only observers on a request.

    Observers are MemberProfile rows that get follow-only access to the
    request: it shows up in their "Observations" tab, they can open the
    detail page, but they cannot accept/decline/transition or upload the
    report (those endpoints all check ``assigned_to == profile``).
    Useful when a colleague needs to monitor progress on behalf of a
    delayed/absent analyst, or for senior review without reassignment.

    POST {action: add|remove, member_id: pk} — returns to the detail page.
    """
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    action = request.POST.get('action', '').strip()
    member_id = request.POST.get('member_id', '').strip()
    if action not in ('add', 'remove') or not member_id:
        messages.error(request, "Action invalide.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')
    member = get_object_or_404(MemberProfile, pk=member_id)

    if action == 'add':
        # Don't add the assignee as an observer — they already have full
        # write access; observer status would be confusing/dead noise.
        if req.assigned_to_id == member.pk:
            messages.warning(
                request,
                f"{member.user.get_full_name()} est déjà l'analyste assigné.",
            )
            return redirect_to_detail(request, req, 'dashboard:admin_ops')
        if req.informed_members.filter(pk=member.pk).exists():
            messages.warning(request, f"{member.user.get_full_name()} suit déjà cette demande.")
            return redirect_to_detail(request, req, 'dashboard:admin_ops')
        req.informed_members.add(member)
        RequestHistory.objects.create(
            request=req, from_status=req.status, to_status=req.status,
            actor=request.user,
            notes=f"Observateur ajouté : {member.user.get_full_name()}",
        )
        Notification.objects.create(
            user=member.user,
            message=f"Vous avez été ajouté en observateur sur {req.display_id}.",
            request=req, notification_type='ASSIGNMENT',
        )
        messages.success(
            request,
            f"{member.user.get_full_name()} suit désormais la demande {req.display_id}.",
        )
    else:  # remove
        if not req.informed_members.filter(pk=member.pk).exists():
            messages.warning(request, "Ce membre ne suit pas cette demande.")
            return redirect_to_detail(request, req, 'dashboard:admin_ops')
        req.informed_members.remove(member)
        RequestHistory.objects.create(
            request=req, from_status=req.status, to_status=req.status,
            actor=request.user,
            notes=f"Observateur retiré : {member.user.get_full_name()}",
        )
        Notification.objects.create(
            user=member.user,
            message=f"Vous ne suivez plus la demande {req.display_id}.",
            request=req, notification_type='WORKFLOW',
        )
        messages.success(
            request,
            f"{member.user.get_full_name()} ne suit plus la demande {req.display_id}.",
        )
    return redirect_to_detail(request, req, 'dashboard:admin_ops')


@admin_required
def award_points(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    points = safe_int(request.POST.get('points'))
    if points <= 0:
        messages.error(request, "Nombre de points invalide.")
        return redirect_back(request, 'dashboard:admin_ops')
    reason = request.POST.get('reason', '')
    PointsHistory.objects.create(
        member=member, points=points, reason=reason, awarded_by=request.user
    )
    member.total_points += points
    # Auto-unlock gift box at 100 points threshold
    if member.total_points >= 100 and not member.gift_unlocked:
        member.gift_unlocked = True
        Notification.objects.create(
            user=member.user,
            message="Félicitations ! Vous avez débloqué une boîte surprise ! Rendez-vous dans votre espace Points.",
            notification_type='REWARD'
        )
    member.save(update_fields=['total_points', 'gift_unlocked'])
    # Notify member
    Notification.objects.create(
        user=member.user,
        message=f"{points} points reçus ! {reason}" if reason else f"{points} points reçus !",
        notification_type='REWARD'
    )
    messages.success(request, f"{points} points attribués à {member.user.get_full_name()}.")
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def upload_gift(request, member_pk):
    """Admin uploads a reward picture into the member's gift box."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    gift_image = request.FILES.get('gift_image')
    if gift_image:
        try:
            gift_image = validate_upload(gift_image, 'image')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect_back(request, 'dashboard:admin_ops')
        member.gift_image = gift_image
        member.gift_unlocked = True
        member.gift_collected = False
        member.save(update_fields=['gift_image', 'gift_unlocked', 'gift_collected'])
        Notification.objects.create(
            user=member.user,
            message="Une récompense vous attend ! Ouvrez votre boîte surprise dans votre espace Points.",
            notification_type='REWARD'
        )
        messages.success(request, f"Récompense ajoutée pour {member.user.get_full_name()}.")
    else:
        messages.error(request, "Veuillez sélectionner une image.")
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
        notification_type='REWARD'
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
        return redirect_to_detail(request, req, 'dashboard:admin_ops')
    date_str = request.POST.get('appointment_date', '')
    if date_str:
        from datetime import datetime
        try:
            req.appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Date invalide.")
            return redirect_to_detail(request, req, 'dashboard:admin_ops')
        req.save(update_fields=['appointment_date'])
        messages.success(request, f"Date de RDV modifiée: {req.appointment_date}")
    return redirect_to_detail(request, req, 'dashboard:admin_ops')


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
        return redirect_to_detail(request, req, 'dashboard:admin_ops')
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
    justification = request.POST.get('cost_justification', '').strip()
    
    if not new_price:
        messages.error(request, "Veuillez saisir un montant.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')
    
    if len(justification) < 10:
        messages.error(request, "La justification doit comporter au moins 10 caractères.")
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    try:
        price = parse_money(new_price, field='Montant', allow_zero=False)
    except FinancialValidationError as exc:
        messages.error(request, str(exc))
        return redirect_to_detail(request, req, 'dashboard:admin_ops')

    with transaction.atomic():
        req = get_object_or_404(Request.objects.select_for_update(), pk=pk)
        old_price = req.admin_validated_price or req.budget_amount or req.quote_amount
        req.admin_validated_price = price
        req.save(update_fields=['admin_validated_price'])

        # Keep the financial mutation and its audit evidence indivisible.
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
    
    messages.success(
        request,
        f"Coût ajusté pour {req.display_id}: {price:,.0f} DA. "
        f"Justification: {justification}",
    )
    return redirect_to_detail(request, req, 'dashboard:admin_ops')


@admin_required
def prepare_quote(request, pk):
    """Admin prepares/edits a detailed quote for a GENOCLAB request."""
    req = get_object_or_404(Request, pk=pk)

    if request.method == 'POST':
        try:
            # Parse form data strictly: malformed financial input must not
            # silently become a zero-value quote.
            items = []
            idx = 0
            while f'item_label_{idx}' in request.POST:
                label = request.POST.get(f'item_label_{idx}', '').strip()
                unit_price = parse_money(
                    request.POST.get(f'item_unit_price_{idx}'),
                    field=f'Prix unitaire de la ligne {idx + 1}',
                    allow_zero=False,
                )
                try:
                    quantity = int(request.POST.get(f'item_quantity_{idx}', ''))
                except (TypeError, ValueError) as exc:
                    raise FinancialValidationError(
                        f'Quantité de la ligne {idx + 1} invalide.') from exc
                if quantity <= 0:
                    raise FinancialValidationError(
                        f'Quantité de la ligne {idx + 1} doit être strictement positive.')
                if not label:
                    raise FinancialValidationError(
                        f'Libellé de la ligne {idx + 1} obligatoire.')
                total = unit_price * quantity
                items.append({
                    'label': label,
                    'unit_price': float(unit_price),
                    'quantity': quantity,
                    'total': float(total),
                })
                idx += 1

            if not items:
                raise FinancialValidationError('Le devis doit contenir au moins une ligne.')

            admin_fees = parse_money(
                request.POST.get('admin_fees'), field='Frais administratifs')
            report_fees = parse_money(
                request.POST.get('report_fees'), field='Frais de rapport')
            vat_percent = parse_money(
                request.POST.get('vat_rate', 19), field='Taux de TVA')
            if vat_percent > 100:
                raise FinancialValidationError(
                    'Le taux de TVA doit être compris entre 0 et 100.')
            vat_rate = vat_percent / 100
            totals = compute_invoice_totals(
                items, admin_fees, report_fees, vat_rate)
        except FinancialValidationError as exc:
            messages.error(request, str(exc))
            return redirect('dashboard:admin_prepare_quote', pk=req.pk)

        notes = request.POST.get('quote_notes', '')
        total_ttc = totals['total_ttc']

        quote_detail = {'items': items, 'notes': notes, **totals}

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

    existing_quote = req.quote_detail or {}
    context = {
        'req': req,
        'yaml_def': yaml_def,
        'auto_estimate': auto_estimate,
        'existing_quote': existing_quote,
        'existing_items': existing_quote.get('items', []),
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
    if request.method == 'POST':
        try:
            with transaction.atomic():
                req = get_object_or_404(Request.objects.select_for_update(), pk=pk)
                if req.status != 'ORDER_UPLOADED':
                    raise InvalidTransitionError(
                        "La facture ne peut être générée que depuis le statut "
                        f"« Bon de Commande Uploadé » (statut actuel: {req.get_status_display()}).")

                quote = req.quote_detail or {}
                items = quote.get('items', [])
                if not items:
                    raise FinancialValidationError(
                        'Le devis validé ne contient aucune ligne facturable.')

                canonical_items = []
                for index, item in enumerate(items, start=1):
                    label = str(item.get('label', '')).strip()
                    if not label:
                        raise FinancialValidationError(
                            f'Libellé de la ligne {index} obligatoire.')
                    unit_price = parse_money(
                        item.get('unit_price'),
                        field=f'Prix unitaire de la ligne {index}',
                        allow_zero=False,
                    )
                    try:
                        quantity = int(item.get('quantity'))
                    except (TypeError, ValueError) as exc:
                        raise FinancialValidationError(
                            f'Quantité de la ligne {index} invalide.') from exc
                    if quantity <= 0:
                        raise FinancialValidationError(
                            f'Quantité de la ligne {index} doit être strictement positive.')
                    canonical_items.append({
                        'label': label,
                        'unit_price': float(unit_price),
                        'quantity': quantity,
                        # Recompute; never trust a stale/tampered JSON total.
                        'total': float(unit_price * quantity),
                    })

                totals = compute_invoice_totals(
                    canonical_items,
                    quote.get('admin_fees', 0),
                    quote.get('report_fees', 0),
                    quote.get('vat_rate', 0.19),
                )
                line_items = [
                    {
                        'description': item['label'],
                        'unit_price': item['unit_price'],
                        'quantity': item['quantity'],
                        'total': item['total'],
                    }
                    for item in canonical_items
                ]
                if totals['admin_fees'] > 0:
                    line_items.append({
                        'description': 'Frais administratifs',
                        'unit_price': totals['admin_fees'], 'quantity': 1,
                        'total': totals['admin_fees'],
                    })
                if totals['report_fees'] > 0:
                    line_items.append({
                        'description': 'Frais de rapport',
                        'unit_price': totals['report_fees'], 'quantity': 1,
                        'total': totals['report_fees'],
                    })

                from datetime import datetime
                from core.sequences import next_display_id
                year = datetime.now().year
                invoice_number = next_display_id(
                    'GCL-INV', year,
                    initial_value_fn=lambda: Invoice.objects.filter(
                        created_at__year=year,
                        invoice_number__startswith=f'GCL-INV-{year}-',
                    ).count(),
                )
                Invoice.objects.create(
                    invoice_number=invoice_number,
                    request=req,
                    client=req.requester,
                    line_items=line_items,
                    subtotal_ht=totals['subtotal_before_tax'],
                    vat_rate=totals['vat_rate'],
                    vat_amount=totals['vat_amount'],
                    total_ttc=totals['total_ttc'],
                    created_by=request.user,
                )
                # If this transition fails, the surrounding transaction also
                # removes the invoice and sequence allocation.
                transition(
                    req, 'INVOICE_GENERATED', request.user,
                    notes=f'Facture {invoice_number} générée')
        except (InvalidTransitionError, AuthorizationError,
                FinancialValidationError, ValueError) as e:
            messages.error(request, str(e))
        else:
            messages.success(
                request, f"Facture {invoice_number} générée pour {req.display_id}.")

        return redirect('dashboard:admin_request_detail', pk=req.pk)

    req = get_object_or_404(Request, pk=pk)
    return redirect('dashboard:admin_request_detail', pk=req.pk)


@admin_required
def confirm_payment(request, pk):
    """Admin confirms payment for a GENOCLAB request."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    note = request.POST.get('verification_note', '').strip()
    if len(note) < 3:
        messages.error(request, "Une note de vérification est obligatoire.")
        return redirect('dashboard:admin_request_detail', pk=pk)
    try:
        from django.db import transaction
        with transaction.atomic():
            req = get_object_or_404(
                Request.objects.select_for_update(), pk=pk,
                status='PAYMENT_PROOF_UPLOADED')
            req.payment_verified_at = timezone.now()
            req.payment_verified_by = request.user
            req.payment_verification_note = note
            req.save(update_fields=[
                'payment_verified_at', 'payment_verified_by',
                'payment_verification_note'])
            transition(req, 'PAYMENT_CONFIRMED', request.user,
                       notes='Preuve de paiement vérifiée par admin')
        messages.success(request, f"Paiement confirmé pour {req.display_id}.")
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        messages.error(request, str(e))
    return redirect('dashboard:admin_request_detail', pk=req.pk)
