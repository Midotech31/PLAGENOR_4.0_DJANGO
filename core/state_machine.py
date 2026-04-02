# core/state_machine.py — PLAGENOR 4.0 State Machine
# STRICT transition matrices. No state jumps allowed.

from __future__ import annotations

from core.exceptions import InvalidTransitionError

# ═══════════════════════════════════════════════════════════════════════════
# IBTIKAR Official Workflow (definitive briefing Section 2/10)
# DRAFT → SUBMITTED → VALIDATION_PEDAGOGIQUE → VALIDATION_FINANCE →
# PLATFORM_NOTE_GENERATED → ASSIGNED → SAMPLE_RECEIVED → ANALYSIS_STARTED →
# ANALYSIS_FINISHED → REPORT_UPLOADED → REPORT_VALIDATED → COMPLETED → CLOSED
# REJECTED possible at: SUBMITTED, VALIDATION_PEDAGOGIQUE, VALIDATION_FINANCE
# ═══════════════════════════════════════════════════════════════════════════

IBTIKAR_TRANSITIONS: dict[str, set[str]] = {
    "DRAFT":                    {"SUBMITTED"},
    "SUBMITTED":                {"VALIDATION_PEDAGOGIQUE", "REJECTED"},
    "VALIDATION_PEDAGOGIQUE":   {"VALIDATION_FINANCE", "REJECTED"},
    "VALIDATION_FINANCE":       {"PLATFORM_NOTE_GENERATED", "REJECTED"},
    "PLATFORM_NOTE_GENERATED":  {"IBTIKAR_SUBMISSION_PENDING"},
    "IBTIKAR_SUBMISSION_PENDING": {"IBTIKAR_CODE_SUBMITTED"},
    "IBTIKAR_CODE_SUBMITTED":   {"ASSIGNED"},
    "ASSIGNED":                 {"PENDING_ACCEPTANCE"},
    "PENDING_ACCEPTANCE":       {"ACCEPTED", "DECLINED"},
    "ACCEPTED":                 {"APPOINTMENT_PROPOSED"},
    "DECLINED":                 {"IBTIKAR_CODE_SUBMITTED"},  # Returns for reassignment
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"REPORT_UPLOADED"},
    "REPORT_UPLOADED":          {"REPORT_VALIDATED", "ANALYSIS_STARTED"},
    "REPORT_VALIDATED":         {"SENT_TO_REQUESTER"},
    "SENT_TO_REQUESTER":        {"COMPLETED"},
    "COMPLETED":                {"CLOSED"},
    "CLOSED":                   set(),     # terminal
    "REJECTED":                 set(),     # terminal
}

# ═══════════════════════════════════════════════════════════════════════════
# GENOCLAB Official Workflow with Payment Gate (Algerian Commercial Code)
# REQUEST_CREATED → QUOTE_DRAFT → QUOTE_SENT → QUOTE_VALIDATED_BY_CLIENT →
# ORDER_UPLOADED → ASSIGNED → SAMPLE_RECEIVED → ANALYSIS_STARTED →
# ANALYSIS_FINISHED → PAYMENT_PENDING → PAYMENT_CONFIRMED → REPORT_UPLOADED →
# REPORT_VALIDATED → SENT_TO_CLIENT → COMPLETED → ARCHIVED
# REJECTED possible at any validation step
# NOTE: Purchase Order (Bon de commande) is mandatory per Algerian commercial code
# NOTE: Payment must be received BEFORE report delivery
# ═══════════════════════════════════════════════════════════════════════════

GENOCLAB_TRANSITIONS: dict[str, set[str]] = {
    "REQUEST_CREATED":          {"QUOTE_DRAFT", "REJECTED"},
    "QUOTE_DRAFT":              {"QUOTE_SENT", "REJECTED"},
    "QUOTE_SENT":               {"QUOTE_VALIDATED_BY_CLIENT", "QUOTE_REJECTED_BY_CLIENT"},
    "QUOTE_VALIDATED_BY_CLIENT": {"ORDER_UPLOADED"},  # Client uploads purchase order
    "ORDER_UPLOADED":           {"ASSIGNED"},  # Admin assigns after order verified
    "QUOTE_REJECTED_BY_CLIENT": set(),     # terminal
    "ASSIGNED":                 {"PENDING_ACCEPTANCE"},
    "PENDING_ACCEPTANCE":       {"ACCEPTED", "DECLINED"},
    "ACCEPTED":                 {"APPOINTMENT_PROPOSED"},
    "DECLINED":                 {"ORDER_UPLOADED"},  # Returns for reassignment
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED", "APPOINTMENT_RESCHEDULING_REQUESTED"},
    "APPOINTMENT_RESCHEDULING_REQUESTED": {"APPOINTMENT_PROPOSED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"PAYMENT_PENDING"},  # Notify client to pay
    "PAYMENT_PENDING":          {"PAYMENT_UPLOADED"},  # Client uploads receipt
    "PAYMENT_UPLOADED":         {"PAYMENT_CONFIRMED"},  # Admin confirms payment
    "PAYMENT_CONFIRMED":        {"REPORT_UPLOADED"},  # Member can upload report after payment
    "REPORT_UPLOADED":          {"REPORT_VALIDATED", "ANALYSIS_STARTED"},  # Admin validates or requests revision
    "REPORT_VALIDATED":         {"SENT_TO_CLIENT"},
    "SENT_TO_CLIENT":           {"COMPLETED"},
    "COMPLETED":                {"ARCHIVED"},
    "ARCHIVED":                 set(),     # terminal
    "REJECTED":                 set(),     # terminal
}


def get_graph(channel: str) -> dict[str, set[str]]:
    if channel == "IBTIKAR":
        return IBTIKAR_TRANSITIONS
    elif channel == "GENOCLAB":
        return GENOCLAB_TRANSITIONS
    raise InvalidTransitionError(f"Canal inconnu: {channel}")


def get_allowed_next_states(channel: str, current_state: str) -> set[str]:
    graph = get_graph(channel)
    return graph.get(current_state, set())


def validate_transition(channel: str, from_state: str, to_state: str) -> bool:
    """Validate that a transition is legal. Raises InvalidTransitionError if not."""
    allowed = get_allowed_next_states(channel, from_state)
    if to_state not in allowed:
        raise InvalidTransitionError(
            f"Transition illégale: {from_state} → {to_state} "
            f"(canal {channel}). "
            f"États autorisés depuis {from_state}: {sorted(allowed) if allowed else 'AUCUN (état terminal)'}"
        )
    return True


def validate_ibtikar_transition(from_state: str, to_state: str) -> bool:
    return validate_transition("IBTIKAR", from_state, to_state)


def validate_genoclab_transition(from_state: str, to_state: str) -> bool:
    return validate_transition("GENOCLAB", from_state, to_state)


def is_terminal(channel: str, state: str) -> bool:
    return len(get_allowed_next_states(channel, state)) == 0


def get_all_states(channel: str) -> list[str]:
    graph = get_graph(channel)
    return list(graph.keys())


# ═══════════════════════════════════════════════════════════════════════════
# Acceptance Workflow Helpers
# ═══════════════════════════════════════════════════════════════════════════

ACCEPTANCE_STATES: set[str] = {"PENDING_ACCEPTANCE"}


def is_acceptance_state(state: str) -> bool:
    """Check if the state requires member acceptance."""
    return state in ACCEPTANCE_STATES


def get_decline_return_state(channel: str) -> str:
    """
    Returns the state to transition back to after a decline.
    This allows admin to reassign to another member.
    """
    if channel == "IBTIKAR":
        return "IBTIKAR_CODE_SUBMITTED"
    elif channel == "GENOCLAB":
        return "ORDER_UPLOADED"
    raise InvalidTransitionError(f"Canal inconnu: {channel}")
