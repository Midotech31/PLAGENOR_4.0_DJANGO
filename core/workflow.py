# core/workflow.py — PLAGENOR 4.0 Workflow Engine (Django)
# Integrates state_machine.py transitions with role-based permission checks.

import logging

from django.db import transaction

from core.models import Request, RequestHistory

logger = logging.getLogger('plagenor.workflow')
from core.state_machine import (
    IBTIKAR_TRANSITIONS,
    GENOCLAB_TRANSITIONS,
    get_allowed_next_states,
    validate_transition,
    is_terminal,
)
from core.exceptions import InvalidTransitionError, AuthorizationError
from core.audit import log_workflow_transition

# Role-based permissions: which roles can trigger which transitions.
# Format: {(from_status, to_status): [allowed_roles]}
#
# This map MUST cover every edge declared in core/state_machine.py — any edge
# missing here is denied by default (see check_role_permission). SUPER_ADMIN
# always bypasses this map, and forced transitions skip it entirely.
_ADMINS = ['SUPER_ADMIN', 'PLATFORM_ADMIN']

ROLE_PERMISSIONS = {
    # ── IBTIKAR ──────────────────────────────────────────────────────────
    ('DRAFT', 'SUBMITTED'): _ADMINS + ['REQUESTER'],
    ('SUBMITTED', 'VALIDATION_PEDAGOGIQUE'): _ADMINS,
    ('SUBMITTED', 'REJECTED'): _ADMINS,
    ('VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE'): _ADMINS,
    ('VALIDATION_PEDAGOGIQUE', 'REJECTED'): _ADMINS,
    ('VALIDATION_FINANCE', 'PLATFORM_NOTE_GENERATED'): _ADMINS + ['FINANCE'],
    ('VALIDATION_FINANCE', 'REJECTED'): _ADMINS + ['FINANCE'],
    ('PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING'): _ADMINS,
    ('IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED'): _ADMINS + ['REQUESTER'],
    ('IBTIKAR_CODE_SUBMITTED', 'ASSIGNED'): _ADMINS,
    ('ANALYSIS_FINISHED', 'REPORT_UPLOADED'): _ADMINS + ['MEMBER'],
    ('REPORT_VALIDATED', 'SENT_TO_REQUESTER'): _ADMINS,
    ('SENT_TO_REQUESTER', 'COMPLETED'): _ADMINS + ['REQUESTER'],
    ('COMPLETED', 'CLOSED'): _ADMINS,
    # ── Shared analyst workflow (both channels) ──────────────────────────
    ('ASSIGNED', 'APPOINTMENT_PROPOSED'): _ADMINS + ['MEMBER'],
    ('APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED'): _ADMINS + ['MEMBER', 'REQUESTER', 'CLIENT'],
    ('APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED'): _ADMINS + ['MEMBER'],
    ('SAMPLE_RECEIVED', 'ANALYSIS_STARTED'): _ADMINS + ['MEMBER'],
    ('ANALYSIS_STARTED', 'ANALYSIS_FINISHED'): _ADMINS + ['MEMBER'],
    ('REPORT_UPLOADED', 'REPORT_VALIDATED'): _ADMINS,
    ('REPORT_UPLOADED', 'ANALYSIS_STARTED'): _ADMINS,  # revision loop
    # ── GENOCLAB ─────────────────────────────────────────────────────────
    ('REQUEST_CREATED', 'QUOTE_DRAFT'): _ADMINS,
    ('REQUEST_CREATED', 'REJECTED'): _ADMINS,
    ('QUOTE_DRAFT', 'QUOTE_SENT'): _ADMINS,
    ('QUOTE_DRAFT', 'REJECTED'): _ADMINS,
    ('QUOTE_SENT', 'QUOTE_VALIDATED_BY_CLIENT'): _ADMINS + ['CLIENT'],
    ('QUOTE_SENT', 'QUOTE_REJECTED_BY_CLIENT'): _ADMINS + ['CLIENT'],
    ('QUOTE_REJECTED_BY_CLIENT', 'QUOTE_DRAFT'): _ADMINS,  # admin renegotiates after rejection
    ('QUOTE_VALIDATED_BY_CLIENT', 'ORDER_UPLOADED'): _ADMINS + ['CLIENT'],
    ('ORDER_UPLOADED', 'INVOICE_GENERATED'): _ADMINS + ['FINANCE'],
    ('ORDER_UPLOADED', 'ASSIGNED'): _ADMINS,
    ('INVOICE_GENERATED', 'ASSIGNED'): _ADMINS,
    ('ANALYSIS_FINISHED', 'PAYMENT_PENDING'): _ADMINS + ['MEMBER'],
    ('PAYMENT_PENDING', 'PAYMENT_CONFIRMED'): _ADMINS + ['FINANCE', 'CLIENT'],
    ('PAYMENT_CONFIRMED', 'REPORT_UPLOADED'): _ADMINS + ['MEMBER'],
    ('REPORT_VALIDATED', 'SENT_TO_CLIENT'): _ADMINS,
    ('SENT_TO_CLIENT', 'COMPLETED'): _ADMINS + ['CLIENT'],
    ('COMPLETED', 'ARCHIVED'): _ADMINS,
}


def get_allowed_transitions(request_obj):
    """Return list of allowed next statuses for a request."""
    return list(get_allowed_next_states(request_obj.channel, request_obj.status))


def check_role_permission(request_obj, to_status, actor) -> bool:
    """Check if the actor's role allows this transition.

    SUPER_ADMIN always passes. Transitions with no rule in ROLE_PERMISSIONS are
    denied (fail-closed); a missing rule is logged so it can be added rather
    than silently blocking a legitimate flow.
    """
    if getattr(actor, 'role', '') == 'SUPER_ADMIN':
        return True
    key = (request_obj.status, to_status)
    allowed_roles = ROLE_PERMISSIONS.get(key)
    if allowed_roles is None:
        logger.warning(
            "No ROLE_PERMISSIONS rule for transition %s -> %s; denying by default.",
            request_obj.status, to_status,
        )
        return False
    return getattr(actor, 'role', '') in allowed_roles


def transition(request_obj, to_status, actor, notes='', force=False):
    """
    Transition a request to a new status, recording history.
    Validates the transition against the state machine and role permissions.
    Raises InvalidTransitionError or AuthorizationError on failure.
    """
    old_status = request_obj.status

    if not force:
        # Validate state machine
        allowed = get_allowed_next_states(request_obj.channel, old_status)
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"Transition {old_status} -> {to_status} non autorisée pour le canal {request_obj.channel}. "
                f"États autorisés: {sorted(allowed) if allowed else 'AUCUN (état terminal)'}"
            )

        # Validate role permissions
        if not check_role_permission(request_obj, to_status, actor):
            raise AuthorizationError(
                f"Le rôle {getattr(actor, 'role', '?')} n'est pas autorisé pour la transition "
                f"{old_status} -> {to_status}"
            )

    # Status change + history must be all-or-nothing.
    with transaction.atomic():
        request_obj.status = to_status
        request_obj.save(update_fields=['status', 'updated_at'])

        RequestHistory.objects.create(
            request=request_obj,
            from_status=old_status,
            to_status=to_status,
            actor=actor,
            notes=notes,
            forced=force,
        )

    # Audit log
    log_workflow_transition(request_obj, old_status, to_status, actor, {'notes': notes, 'forced': force})

    # IBTIKAR balance deduction — fires once per request, at the moment
    # the requester has confirmed reception (COMPLETED). The financial
    # helper is responsible for idempotency safety.
    _deduct_ibtikar_on_complete(request_obj, old_status, to_status)

    # Email notifications for key transitions
    _send_transition_emails(request_obj, old_status, to_status)

    # In-app notifications for key transitions
    _create_notifications(request_obj, to_status)

    # Auto-generate documents on specific transitions
    _auto_generate_documents(request_obj, to_status)

    return request_obj


def force_transition(request_obj, to_status, actor, notes=''):
    """Force a request into `to_status`, bypassing the state-machine graph and
    role checks. Restricted to SUPER_ADMIN at the view layer. The target must
    still be a declared status; the move is recorded in history with
    ``forced=True``.
    """
    valid_statuses = {s for s, _ in Request.STATUS_CHOICES}
    if to_status not in valid_statuses:
        raise InvalidTransitionError(f"Statut inconnu: {to_status}")
    return transition(request_obj, to_status, actor, notes=notes, force=True)


def _create_notifications(request_obj, to_status):
    """Create in-app notifications for ALL workflow transitions."""
    try:
        from notifications.models import Notification
        from accounts.models import User

        # Notify the assigned member on relevant transitions
        if request_obj.assigned_to and to_status in (
            'ASSIGNED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
            # GENOCLAB: Member should be notified of all relevant steps
            'PAYMENT_CONFIRMED',  # Member can now upload report
            'REPORT_VALIDATED',  # Admin validated the report
            'SENT_TO_CLIENT',    # Report sent to client
        ):
            Notification.objects.create(
                user=request_obj.assigned_to.user,
                message=f"{request_obj.display_id}: {request_obj.get_status_display()}",
                request=request_obj,
                notification_type='WORKFLOW',
            )

        # In-app notify the requester/client on EVERY workflow transition
        # so they can follow the full progress of their request. Email is
        # rationed separately to the milestones in _IMPORTANT_EMAIL_STATUSES
        # so the inbox stays uncluttered while the in-app feed stays
        # complete. Skip only purely-internal transitions that never reach
        # the user-facing pipeline.
        _SILENT_FOR_REQUESTER = {
            'REQUEST_CREATED',          # internal seed status
            'PENDING_ACCEPTANCE',       # analyst-side ack, invisible to candidate
            'ADMIN_REVIEW',             # internal validation step
        }
        if request_obj.requester and to_status not in _SILENT_FOR_REQUESTER:
            Notification.objects.create(
                user=request_obj.requester,
                message=f"{request_obj.display_id}: {request_obj.get_status_display()}",
                request=request_obj,
                notification_type='WORKFLOW',
            )

        # Always notify admins for important transitions
        if to_status in (
            'SUBMITTED', 'IBTIKAR_CODE_SUBMITTED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'REPORT_UPLOADED', 'REQUEST_CREATED',
            # GENOCLAB admin-relevant states
            'QUOTE_VALIDATED_BY_CLIENT', 'QUOTE_REJECTED_BY_CLIENT', 'PAYMENT_CONFIRMED',
        ):
            admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    message=f"Nouvelle action: {request_obj.display_id} → {request_obj.get_status_display()}",
                    request=request_obj,
                    notification_type='WORKFLOW',
                )
    except Exception as e:
        # Log notification errors but don't break the workflow transition
        logger.exception(
            f"Failed to create notifications for request {request_obj.display_id}: {str(e)}",
            extra={
                'request_id': str(request_obj.id),
                'request_display_id': request_obj.display_id,
                'to_status': to_status,
            }
        )


def _send_transition_emails(request_obj, old_status, to_status):
    """Send email notifications on workflow transitions.

    Routes the transition to the matching ``notifications.emails.notify_*``
    function. Backend is config-driven (console in dev, SMTP when
    ``SMTP_HOST`` is set in ``.env``). Failures never block a transition —
    they're logged and swallowed.
    """
    try:
        from notifications import emails as nem
    except Exception:
        return

    def _safe(fn, *args, **kw):
        try:
            fn(*args, **kw)
        except Exception as exc:
            logger.exception(
                "email notification %s failed for %s (%s -> %s): %s",
                getattr(fn, '__name__', 'notify'),
                getattr(request_obj, 'display_id', '?'),
                old_status, to_status, exc,
            )

    # Dedicated templates first.
    if to_status == 'ASSIGNED' and request_obj.assigned_to:
        _safe(nem.notify_assignment, request_obj, request_obj.assigned_to)
    elif to_status in ('APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED'):
        _safe(nem.notify_appointment, request_obj)
    elif to_status in ('REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT'):
        _safe(nem.notify_report_delivery, request_obj)

    # Generic status-change email so the requester/client gets a paper
    # trail of every meaningful step. Sent ON TOP of dedicated templates
    # above when the status overlaps.
    # Email is reserved for the milestones the user actually needs to act
    # on or that materially change the request's status. The in-app
    # notification ringtone fires on every transition (see
    # _create_notifications) so nothing is lost — only the inbox stays
    # uncluttered.
    _IMPORTANT_EMAIL_STATUSES = {
        # IBTIKAR — validations + handoffs + end-state
        'VALIDATION_FINANCE',         # request approved, will be billed
        'PLATFORM_NOTE_GENERATED',    # note ready, requester acts next
        'IBTIKAR_SUBMISSION_PENDING', # requester needs to submit code
        'APPOINTMENT_PROPOSED',       # requester needs to confirm
        'APPOINTMENT_CONFIRMED',      # confirmation receipt
        'SENT_TO_REQUESTER',          # report is ready to download
        'COMPLETED', 'REJECTED',      # terminal states
        # GENOCLAB — quote / payment / report milestones
        'QUOTE_SENT',                 # client must decide
        'INVOICE_GENERATED',          # client must pay
        'PAYMENT_PENDING',            # gentle nudge
        'SENT_TO_CLIENT',             # report is ready
    }
    if to_status in _IMPORTANT_EMAIL_STATUSES:
        _safe(nem.notify_status_change, request_obj, old_status, to_status)


def _auto_generate_documents(request_obj, to_status):
    """Auto-generate documents on specific transitions."""
    pass


def _deduct_ibtikar_on_complete(request_obj, old_status, to_status):
    """Deduct the resolved request cost from the requester's declared
    IBTIKAR balance on the transition that marks reception as confirmed
    (REQUEST → COMPLETED on the IBTIKAR channel).

    Why this trigger and not REPORT_VALIDATED / SENT_TO_REQUESTER?
    The user's rule is: once the requester has actually received the
    report, the budget is consumed. ``confirm_receipt`` is what advances
    the request to COMPLETED — that's the moment the candidate has the
    deliverable in hand.

    The actual amount deducted is ``budget_amount`` (the resolved cost
    captured at submission and refined into ``admin_validated_price`` if
    the admin re-priced the request). We prefer ``admin_validated_price``
    when present, fall back to ``budget_amount``, and skip silently if
    neither is set.

    Failures here NEVER block the workflow — log and continue.
    """
    if to_status != 'COMPLETED' or request_obj.channel != 'IBTIKAR':
        return
    requester = getattr(request_obj, 'requester', None)
    if requester is None:
        return
    amount = (
        float(request_obj.admin_validated_price)
        if getattr(request_obj, 'admin_validated_price', None)
        else float(request_obj.budget_amount or 0)
    )
    if amount <= 0:
        return
    try:
        from core.financial import deduct_ibtikar_balance
        deduct_ibtikar_balance(
            requester, amount,
            reason=f"COMPLETED:{request_obj.display_id}",
        )
    except Exception as exc:
        logger.exception(
            "IBTIKAR deduction failed for %s (%s DA): %s",
            request_obj.display_id, amount, exc,
        )
