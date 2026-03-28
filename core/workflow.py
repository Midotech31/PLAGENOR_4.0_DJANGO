# core/workflow.py — PLAGENOR 4.0 Workflow Engine (Django)
# Integrates state_machine.py transitions with role-based permission checks.

from core.models import Request, RequestHistory
from core.state_machine import (
    IBTIKAR_TRANSITIONS,
    GENOCLAB_TRANSITIONS,
    get_allowed_next_states,
    validate_transition,
    is_terminal,
)
from core.exceptions import InvalidTransitionError, AuthorizationError
from core.audit import log_workflow_transition

# Role-based permissions: which roles can trigger which transitions
# Format: {(from_status, to_status): [allowed_roles]}
ROLE_PERMISSIONS = {
    # IBTIKAR validations
    ('SUBMITTED', 'VALIDATION_PEDAGOGIQUE'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SUBMITTED', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_PEDAGOGIQUE', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('VALIDATION_FINANCE', 'PLATFORM_NOTE_GENERATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('VALIDATION_FINANCE', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('PLATFORM_NOTE_GENERATED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # Analyst workflow — appointment states
    ('ASSIGNED', 'APPOINTMENT_PROPOSED'): ['SUPER_ADMIN', 'MEMBER'],
    ('APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER', 'CLIENT'],
    ('APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER'],
    ('SAMPLE_RECEIVED', 'ANALYSIS_STARTED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_STARTED', 'ANALYSIS_FINISHED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_FINISHED', 'REPORT_UPLOADED'): ['SUPER_ADMIN', 'MEMBER'],
    ('REPORT_UPLOADED', 'REPORT_VALIDATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REPORT_VALIDATED', 'COMPLETED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('COMPLETED', 'CLOSED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # GENOCLAB validations
    ('REQUEST_CREATED', 'QUOTE_DRAFT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REQUEST_CREATED', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'QUOTE_SENT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_SENT', 'QUOTE_VALIDATED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_SENT', 'QUOTE_REJECTED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED'): ['SUPER_ADMIN', 'FINANCE'],
    ('INVOICE_GENERATED', 'PAYMENT_CONFIRMED'): ['SUPER_ADMIN', 'FINANCE'],
    ('PAYMENT_CONFIRMED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('COMPLETED', 'ARCHIVED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
}


def get_allowed_transitions(request_obj):
    """Return list of allowed next statuses for a request."""
    return list(get_allowed_next_states(request_obj.channel, request_obj.status))


def check_role_permission(request_obj, to_status, actor) -> bool:
    """Check if actor's role allows this transition. SUPER_ADMIN always allowed."""
    if getattr(actor, 'role', '') == 'SUPER_ADMIN':
        return True
    key = (request_obj.status, to_status)
    allowed_roles = ROLE_PERMISSIONS.get(key)
    if allowed_roles is None:
        # No explicit rule — allow by default (permissive for unlisted transitions)
        return True
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

    # Email notifications for key transitions
    _send_transition_emails(request_obj, old_status, to_status)

    # In-app notifications for key transitions
    _create_notifications(request_obj, to_status)

    # Auto-generate documents on specific transitions
    _auto_generate_documents(request_obj, to_status)

    return request_obj


def _create_notifications(request_obj, to_status):
    """Create in-app notifications for key workflow transitions."""
    try:
        from notifications.models import Notification

        if to_status == 'ASSIGNED' and request_obj.assigned_to:
            Notification.objects.create(
                user=request_obj.assigned_to.user,
                message=f"Nouvelle assignation: {request_obj.display_id} - {request_obj.title}",
                request=request_obj,
                notification_type='WORKFLOW',
            )
        elif to_status == 'APPOINTMENT_PROPOSED' and request_obj.requester:
            Notification.objects.create(
                user=request_obj.requester,
                message=f"RDV proposé pour {request_obj.display_id}: {request_obj.appointment_date}",
                request=request_obj,
                notification_type='WORKFLOW',
            )
        elif to_status == 'APPOINTMENT_CONFIRMED' and request_obj.assigned_to:
            Notification.objects.create(
                user=request_obj.assigned_to.user,
                message=f"RDV confirmé pour {request_obj.display_id}",
                request=request_obj,
                notification_type='WORKFLOW',
            )
        elif to_status in ('REPORT_VALIDATED', 'COMPLETED') and request_obj.requester:
            msg = 'Rapport validé' if to_status == 'REPORT_VALIDATED' else 'Demande complétée'
            Notification.objects.create(
                user=request_obj.requester,
                message=f"{msg}: {request_obj.display_id}",
                request=request_obj,
                notification_type='WORKFLOW',
            )
    except Exception:
        pass  # Never break workflow due to notification failure


def _auto_generate_documents(request_obj, to_status):
    """Automatically generate documents when reaching specific states."""
    try:
        if to_status == 'PLATFORM_NOTE_GENERATED':
            from documents.generators import generate_platform_note
            filepath = generate_platform_note(request_obj)
            if filepath:
                import logging
                logging.getLogger('plagenor.workflow').info(
                    "Platform note generated for %s: %s", request_obj.display_id, filepath
                )
    except Exception as e:
        import logging
        logging.getLogger('plagenor.workflow').error(
            "Document generation failed for %s: %s", request_obj.display_id, e
        )


def _send_transition_emails(request_obj, old_status, to_status):
    """Fire email notifications for key workflow transitions."""
    try:
        from notifications.emails import (
            notify_status_change,
            notify_assignment,
            notify_appointment,
            notify_report_delivery,
        )

        # Status change notification to requester
        notify_status_change(request_obj, old_status, to_status)

        # Assignment notification to member
        if to_status == 'ASSIGNED' and request_obj.assigned_to:
            notify_assignment(request_obj, request_obj.assigned_to)

        # Appointment notification
        if to_status == 'APPOINTMENT_PROPOSED' and request_obj.appointment_date:
            notify_appointment(request_obj)

        # Report delivery
        if to_status in ('REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'SENT_TO_CLIENT', 'COMPLETED'):
            if request_obj.report_token:
                notify_report_delivery(request_obj)
    except Exception:
        pass  # Never break workflow due to email failure


def force_transition(request_obj, to_status, actor, notes=''):
    """SUPER_ADMIN only: force a transition bypassing state machine rules."""
    if getattr(actor, 'role', '') != 'SUPER_ADMIN':
        raise AuthorizationError("Seul le SUPER_ADMIN peut forcer une transition")
    return transition(request_obj, to_status, actor, notes=notes, force=True)


def get_request_timeline(request_obj):
    """Get full history timeline for a request."""
    return request_obj.history.select_related('actor').order_by('created_at')
