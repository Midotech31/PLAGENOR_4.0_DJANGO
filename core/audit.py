# core/audit.py — PLAGENOR 4.0 Audit Engine (Django)
# Logs actions to Python logging + RequestHistory model for workflow transitions.

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger('plagenor.audit')


def log_action(
    action: str,
    entity_type: str = '',
    entity_id: str = '',
    actor=None,
    details: Optional[dict] = None,
    channel: str = '',
) -> None:
    """Log an action to the audit trail."""
    actor_name = actor.get_full_name() if actor and hasattr(actor, 'get_full_name') else 'system'
    actor_role = getattr(actor, 'role', 'SYSTEM') if actor else 'SYSTEM'
    logger.info(
        "[%s] %s:%s by %s (%s) — %s",
        action, entity_type, entity_id, actor_name, actor_role, details or '',
    )


def log_workflow_transition(request_obj, from_state: str, to_state: str,
                            actor, details: Optional[dict] = None) -> None:
    """Log a workflow state transition."""
    log_action(
        action=f"TRANSITION:{from_state}->{to_state}",
        entity_type='REQUEST',
        entity_id=str(request_obj.id),
        actor=actor,
        details={
            'from_state': from_state,
            'to_state': to_state,
            'channel': request_obj.channel,
            **(details or {}),
        },
        channel=request_obj.channel,
    )


def log_financial_action(action: str, entity_id: str, actor,
                         amount: float = 0, details: Optional[dict] = None) -> None:
    """Log a financial action."""
    log_action(
        action=f"FINANCIAL:{action}",
        entity_type='FINANCIAL',
        entity_id=entity_id,
        actor=actor,
        details={'amount': amount, **(details or {})},
    )


def log_budget_override(request_id: str, actor, amount: float,
                        justification: str) -> None:
    """Log a budget override by SUPER_ADMIN."""
    log_action(
        action='BUDGET_OVERRIDE',
        entity_type='REQUEST',
        entity_id=request_id,
        actor=actor,
        details={
            'amount': amount,
            'justification': justification,
            'override_type': 'IBTIKAR_ANNUAL_CAP',
        },
        channel='IBTIKAR',
    )
