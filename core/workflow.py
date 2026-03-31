# core/workflow.py — PLAGENOR 4.0 Workflow Engine (Django)
# Integrates state_machine.py transitions with role-based permission checks.

import logging

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
    ('PLATFORM_NOTE_GENERATED', 'IBTIKAR_SUBMISSION_PENDING'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('IBTIKAR_SUBMISSION_PENDING', 'IBTIKAR_CODE_SUBMITTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER'],
    ('IBTIKAR_CODE_SUBMITTED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # Analyst workflow — appointment states
    ('ASSIGNED', 'APPOINTMENT_PROPOSED'): ['SUPER_ADMIN', 'MEMBER'],
    ('APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER', 'CLIENT'],
    ('APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'MEMBER'],
    ('SAMPLE_RECEIVED', 'ANALYSIS_STARTED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_STARTED', 'ANALYSIS_FINISHED'): ['SUPER_ADMIN', 'MEMBER'],
    ('ANALYSIS_FINISHED', 'REPORT_UPLOADED'): ['SUPER_ADMIN', 'MEMBER'],
    # GENOCLAB: Allow report upload after payment confirmation
    ('PAYMENT_CONFIRMED', 'REPORT_UPLOADED'): ['SUPER_ADMIN', 'MEMBER'],
    ('REPORT_UPLOADED', 'REPORT_VALIDATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REPORT_UPLOADED', 'ANALYSIS_STARTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],  # Revision loop
    ('REPORT_VALIDATED', 'SENT_TO_REQUESTER'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SENT_TO_REQUESTER', 'COMPLETED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'REQUESTER'],
    ('COMPLETED', 'CLOSED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    # GENOCLAB validations
    ('REQUEST_CREATED', 'QUOTE_DRAFT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REQUEST_CREATED', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'QUOTE_SENT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_DRAFT', 'REJECTED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('QUOTE_SENT', 'QUOTE_VALIDATED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_SENT', 'QUOTE_REJECTED_BY_CLIENT'): ['SUPER_ADMIN', 'CLIENT'],
    ('QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('INVOICE_GENERATED', 'PAYMENT_CONFIRMED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'],
    ('PAYMENT_CONFIRMED', 'ASSIGNED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('REPORT_VALIDATED', 'SENT_TO_CLIENT'): ['SUPER_ADMIN', 'PLATFORM_ADMIN'],
    ('SENT_TO_CLIENT', 'COMPLETED'): ['SUPER_ADMIN', 'PLATFORM_ADMIN', 'CLIENT'],
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

        # Notify the requester/client on relevant transitions
        if request_obj.requester and to_status in (
            # IBTIKAR states
            'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE', 'PLATFORM_NOTE_GENERATED',
            'IBTIKAR_SUBMISSION_PENDING', 'ASSIGNED', 'APPOINTMENT_PROPOSED',
            'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'COMPLETED', 'REJECTED',
            # GENOCLAB states - Full pipeline notifications
            'QUOTE_SENT', 'INVOICE_GENERATED', 'PAYMENT_CONFIRMED',
            'SENT_TO_CLIENT',
            'ORDER_UPLOADED',  # Client uploads purchase order
            'PAYMENT_PENDING',  # Client needs to pay
            'REPORT_UPLOADED',  # Report uploaded, awaiting validation
            'REPORT_VALIDATED',  # Report validated
        ):
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
    """Send email notifications for key transitions. Placeholder for future SMTP integration."""
    pass


def _auto_generate_documents(request_obj, to_status):
    """Auto-generate documents on specific transitions."""
    pass
