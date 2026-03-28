from core.models import Request, RequestHistory

# State machine transitions — IBTIKAR channel
IBTIKAR_TRANSITIONS = {
    'SUBMITTED': ['VALIDATION_PEDAGOGIQUE', 'REJECTED'],
    'VALIDATION_PEDAGOGIQUE': ['VALIDATION_FINANCE', 'REJECTED'],
    'VALIDATION_FINANCE': ['PLATFORM_NOTE_GENERATED', 'REJECTED'],
    'PLATFORM_NOTE_GENERATED': ['ASSIGNED', 'REJECTED'],
    'ASSIGNED': ['PENDING_ACCEPTANCE'],
    'PENDING_ACCEPTANCE': ['APPOINTMENT_SCHEDULED', 'ASSIGNED'],
    'APPOINTMENT_SCHEDULED': ['SAMPLE_RECEIVED'],
    'SAMPLE_RECEIVED': ['ANALYSIS_STARTED'],
    'ANALYSIS_STARTED': ['ANALYSIS_FINISHED'],
    'ANALYSIS_FINISHED': ['REPORT_UPLOADED'],
    'REPORT_UPLOADED': ['ADMIN_REVIEW'],
    'ADMIN_REVIEW': ['REPORT_VALIDATED', 'ANALYSIS_STARTED'],
    'REPORT_VALIDATED': ['SENT_TO_REQUESTER'],
    'SENT_TO_REQUESTER': ['COMPLETED'],
}

# State machine transitions — GENOCLAB channel
GENOCLAB_TRANSITIONS = {
    'REQUEST_CREATED': ['QUOTE_DRAFT', 'REJECTED'],
    'QUOTE_DRAFT': ['QUOTE_SENT'],
    'QUOTE_SENT': ['QUOTE_VALIDATED_BY_CLIENT', 'QUOTE_REJECTED_BY_CLIENT'],
    'QUOTE_VALIDATED_BY_CLIENT': ['INVOICE_GENERATED'],
    'INVOICE_GENERATED': ['PAYMENT_CONFIRMED'],
    'PAYMENT_CONFIRMED': ['ASSIGNED'],
    'ASSIGNED': ['PENDING_ACCEPTANCE'],
    'PENDING_ACCEPTANCE': ['APPOINTMENT_SCHEDULED', 'ASSIGNED'],
    'APPOINTMENT_SCHEDULED': ['SAMPLE_RECEIVED'],
    'SAMPLE_RECEIVED': ['ANALYSIS_STARTED'],
    'ANALYSIS_STARTED': ['ANALYSIS_FINISHED'],
    'ANALYSIS_FINISHED': ['REPORT_UPLOADED'],
    'REPORT_UPLOADED': ['ADMIN_REVIEW'],
    'ADMIN_REVIEW': ['REPORT_VALIDATED', 'ANALYSIS_STARTED'],
    'REPORT_VALIDATED': ['SENT_TO_CLIENT'],
    'SENT_TO_CLIENT': ['COMPLETED'],
}


def get_allowed_transitions(request_obj):
    """Return list of allowed next statuses for a request."""
    transitions = IBTIKAR_TRANSITIONS if request_obj.channel == 'IBTIKAR' else GENOCLAB_TRANSITIONS
    return transitions.get(request_obj.status, [])


def transition(request_obj, to_status, actor, notes=''):
    """
    Transition a request to a new status, recording history.
    Raises ValueError if the transition is not allowed.
    """
    allowed = get_allowed_transitions(request_obj)
    if to_status not in allowed:
        raise ValueError(f"Transition {request_obj.status} -> {to_status} not allowed")

    old_status = request_obj.status
    request_obj.status = to_status
    request_obj.save()

    RequestHistory.objects.create(
        request=request_obj,
        from_status=old_status,
        to_status=to_status,
        actor=actor,
        notes=notes,
    )

    return request_obj
