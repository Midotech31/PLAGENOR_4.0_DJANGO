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
    "PLATFORM_NOTE_GENERATED":  {"ASSIGNED"},
    "ASSIGNED":                 {"APPOINTMENT_PROPOSED"},
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"REPORT_UPLOADED"},
    "REPORT_UPLOADED":          {"REPORT_VALIDATED"},
    "REPORT_VALIDATED":         {"COMPLETED"},
    "COMPLETED":                {"CLOSED"},
    "CLOSED":                   set(),     # terminal
    "REJECTED":                 set(),     # terminal
}

# ═══════════════════════════════════════════════════════════════════════════
# GENOCLAB Official Workflow (definitive briefing Section 2/10)
# REQUEST_CREATED → QUOTE_DRAFT → QUOTE_SENT → QUOTE_VALIDATED_BY_CLIENT →
# INVOICE_GENERATED → PAYMENT_CONFIRMED → ASSIGNED → SAMPLE_RECEIVED →
# ANALYSIS_STARTED → ANALYSIS_FINISHED → REPORT_UPLOADED → REPORT_VALIDATED →
# COMPLETED → ARCHIVED
# REJECTED possible at any validation step
# ═══════════════════════════════════════════════════════════════════════════

GENOCLAB_TRANSITIONS: dict[str, set[str]] = {
    "REQUEST_CREATED":          {"QUOTE_DRAFT", "REJECTED"},
    "QUOTE_DRAFT":              {"QUOTE_SENT", "REJECTED"},
    "QUOTE_SENT":               {"QUOTE_VALIDATED_BY_CLIENT", "QUOTE_REJECTED_BY_CLIENT"},
    "QUOTE_VALIDATED_BY_CLIENT": {"INVOICE_GENERATED"},
    "QUOTE_REJECTED_BY_CLIENT": set(),     # terminal
    "INVOICE_GENERATED":        {"PAYMENT_CONFIRMED"},
    "PAYMENT_CONFIRMED":        {"ASSIGNED"},
    "ASSIGNED":                 {"APPOINTMENT_PROPOSED"},
    "APPOINTMENT_PROPOSED":     {"APPOINTMENT_CONFIRMED"},
    "APPOINTMENT_CONFIRMED":    {"SAMPLE_RECEIVED"},
    "SAMPLE_RECEIVED":          {"ANALYSIS_STARTED"},
    "ANALYSIS_STARTED":         {"ANALYSIS_FINISHED"},
    "ANALYSIS_FINISHED":        {"REPORT_UPLOADED"},
    "REPORT_UPLOADED":          {"REPORT_VALIDATED"},
    "REPORT_VALIDATED":         {"COMPLETED"},
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
