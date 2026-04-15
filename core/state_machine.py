"""
Canonical state graphs for PLAGENOR channels.

Workflow map (high-level):
- IBTIKAR and GENOCLAB each define strict, explicit next states.
- Helpers expose allowed transitions, terminal checks, and compatibility utilities.
- Any undefined edge is rejected to prevent incoherent workflow jumps.
"""

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
    "IBTIKAR_CODE_SUBMITTED":   {"ASSIGNED", "PENDING_ACCEPTANCE"},
    "ASSIGNED":                 {"PENDING_ACCEPTANCE"},
    "PENDING_ACCEPTANCE":       {"ACCEPTED", "DECLINED"},
    "ACCEPTED":                 {"APPOINTMENT_PROPOSED"},
    "DECLINED":                 {"ASSIGNED"},
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"REPORT_UPLOADED"},
    "REPORT_UPLOADED":          {"REPORT_VALIDATED", "ANALYSIS_STARTED"},
    "REPORT_VALIDATED":         {"SENT_TO_REQUESTER"},
    "SENT_TO_REQUESTER":        {"COMPLETED"},
    "COMPLETED":                {"CLOSED"},
    "CLOSED":                   set(),
    "REJECTED":                 set(),
    "ADMINISTRATIVELY_CLOSED":  set(),     # terminal - admin close from any status
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
    "QUOTE_VALIDATED_BY_CLIENT": {"ORDER_UPLOADED"},
    "ORDER_UPLOADED":           {"ASSIGNED", "PENDING_ACCEPTANCE"},
    "QUOTE_REJECTED_BY_CLIENT": {"QUOTE_DRAFT"},
    "ASSIGNED":                 {"PENDING_ACCEPTANCE"},
    "PENDING_ACCEPTANCE":       {"ACCEPTED", "DECLINED"},
    "ACCEPTED":                 {"APPOINTMENT_PROPOSED"},
    "DECLINED":                 {"ASSIGNED"},
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED", "APPOINTMENT_RESCHEDULING_REQUESTED"},
    "APPOINTMENT_RESCHEDULING_REQUESTED": {"APPOINTMENT_PROPOSED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"INVOICE_GENERATED"},
    "INVOICE_GENERATED":        {"INVOICE_SENT"},
    "INVOICE_SENT":             {"PAYMENT_PENDING"},
    "PAYMENT_PENDING":          {"PAYMENT_UPLOADED"},
    "PAYMENT_UPLOADED":         {"PAYMENT_CONFIRMED"},
    "PAYMENT_CONFIRMED":        {"REPORT_UPLOADED", "PENDING_ACCEPTANCE"},
    "REPORT_UPLOADED":          {"REPORT_VALIDATED", "ANALYSIS_STARTED"},
    "REPORT_VALIDATED":         {"SENT_TO_CLIENT"},
    "SENT_TO_CLIENT":           {"COMPLETED"},
    "COMPLETED":                {"ARCHIVED"},
    "ARCHIVED":                 set(),
    "REJECTED":                 set(),
    "ADMINISTRATIVELY_CLOSED":  set(),     # terminal - admin close from any status
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


TERMINAL_STATES: set[str] = {"CLOSED", "REJECTED", "ARCHIVED", "ADMINISTRATIVELY_CLOSED"}


def is_terminal_state(state: str) -> bool:
    """Check if a state is terminal (no further transitions possible)."""
    return state in TERMINAL_STATES


def get_terminal_states(channel: str) -> set[str]:
    """Get all terminal states for a channel."""
    return TERMINAL_STATES


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
    
    Note: With the new state machine where DECLINED → ASSIGNED,
    the second transition is handled by the state machine.
    This function is kept for backward compatibility.
    """
    return "ASSIGNED"
