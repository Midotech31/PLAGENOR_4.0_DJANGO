# core/financial.py — PLAGENOR 4.0 Financial Engine (Django ORM)
# IBTIKAR: 200K DA per student/year (virtual revenue). GENOCLAB: Invoicing (real revenue).

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from django.conf import settings
from django.db.models import Count, Sum

from core.exceptions import BudgetExceededError

logger = logging.getLogger('plagenor.financial')


# ═══════════════════════════════════════════════════════════════════════════
# IBTIKAR — Virtual Revenue (per-student budget tracking)
# ═══════════════════════════════════════════════════════════════════════════

REJECTION_STATES = ['REJECTED', 'DRAFT', 'QUOTE_REJECTED_BY_CLIENT']


def get_ibtikar_virtual_revenue(year: Optional[int] = None) -> dict:
    """Calculate IBTIKAR virtual revenue using Django ORM aggregation."""
    from core.models import Request
    year = year or datetime.now().year
    qs = Request.objects.filter(
        channel='IBTIKAR',
        created_at__year=year,
    ).exclude(status__in=REJECTION_STATES)

    agg = qs.aggregate(
        total=Sum('budget_amount'),
        count=Count('id'),
        students=Count('requester', distinct=True),
    )
    return {
        'total': float(agg['total'] or 0),
        'count': agg['count'],
        'students': agg['students'],
    }


def get_ibtikar_budget_used_by_requester(requester_id, year: Optional[int] = None) -> float:
    """Budget used by ONE specific student/requester."""
    from core.models import Request
    year = year or datetime.now().year
    total = Request.objects.filter(
        channel='IBTIKAR',
        requester_id=requester_id,
        created_at__year=year,
    ).exclude(status__in=REJECTION_STATES).aggregate(
        total=Sum('budget_amount')
    )['total']
    return float(total or 0)


def get_ibtikar_budget_used(year: Optional[int] = None) -> float:
    """TOTAL IBTIKAR virtual revenue (all students combined)."""
    return get_ibtikar_virtual_revenue(year).get('total', 0.0)


def check_ibtikar_budget(amount, requester=None, request_obj=None) -> dict:
    """Check if THIS STUDENT's *declared* balance allows the amount.

    The cap is the requester's self-declared residual IBTIKAR balance
    (`User.ibtikar_declared_balance`) — NOT a flat 200K — because the
    DGRSDT IBTIKAR budget is shared across multiple platforms, so the
    candidate is the only one who knows their true residual at any given
    moment. The hard ceiling (settings.IBTIKAR_BUDGET_CAP, 200 000 DA)
    is only used to validate the upper bound of what they can *declare*.

    Returns `declared=None` when the requester has not yet declared a
    balance — callers must surface a declaration prompt before letting
    the requester submit.
    """
    declared = (
        float(requester.ibtikar_declared_balance)
        if requester and requester.ibtikar_declared_balance is not None
        else None
    )
    hard_cap = settings.IBTIKAR_BUDGET_CAP
    amount_f = float(amount)

    if declared is None:
        # Not declared yet — exceeded=True so the view refuses to submit
        # until the requester declares a balance.
        return {
            'declared': None,
            'cap': hard_cap,
            'amount': amount_f,
            'projected': amount_f,
            'exceeded': True,
            'remaining': 0.0,
            'pct_used': 0.0,
            'needs_declaration': True,
        }

    projected = amount_f
    result = {
        'declared': declared,
        'cap': hard_cap,
        'amount': amount_f,
        'projected': projected,
        'exceeded': projected > declared,
        'remaining': max(0, declared - projected),
        'pct_used': round((amount_f / declared) * 100, 1) if declared > 0 else 0.0,
        'needs_declaration': False,
    }

    if result['exceeded']:
        logger.warning(
            "Budget IBTIKAR exceeded: requester=%s amount=%s declared=%s",
            getattr(requester, 'id', '?'), amount_f, declared,
        )

    return result


def deduct_ibtikar_balance(requester, amount: float, reason: str = '') -> dict:
    """Deduct a resolved request cost from the requester's declared
    IBTIKAR balance. Called when an IBTIKAR request reaches COMPLETED
    (report delivered + receipt confirmed).

    Idempotency: caller passes `reason` (e.g. the request display_id)
    so we don't double-deduct if the workflow is replayed. We log every
    deduction; double-call protection at the workflow side uses a
    per-request flag (see core.workflow._deduct_on_complete).

    No-op if the requester never declared a balance — log a warning so
    operators can investigate. Refuses to go negative; floors at 0.
    """
    from django.utils import timezone

    if requester is None or requester.ibtikar_declared_balance is None:
        logger.warning(
            "deduct_ibtikar_balance skipped: requester=%s has no declared balance (amount=%s)",
            getattr(requester, 'id', '?'), amount,
        )
        return {'deducted': 0.0, 'remaining': None, 'skipped': True}

    before = float(requester.ibtikar_declared_balance)
    after = max(0.0, before - float(amount))
    requester.ibtikar_declared_balance = after
    requester.ibtikar_balance_declared_at = timezone.now()
    requester.save(update_fields=[
        'ibtikar_declared_balance', 'ibtikar_balance_declared_at',
    ])
    logger.info(
        "IBTIKAR deduction: requester=%s amount=%s before=%s after=%s reason=%s",
        requester.id, amount, before, after, reason,
    )
    return {'deducted': float(amount), 'remaining': after, 'skipped': False}


def approve_with_budget_override(request_obj, actor, amount: float, justification: str) -> dict:
    """SUPER_ADMIN budget override approval."""
    if actor.role != 'SUPER_ADMIN':
        raise BudgetExceededError("Seul le SUPER_ADMIN peut autoriser un override budgétaire")
    if not justification or len(justification.strip()) < 10:
        raise BudgetExceededError("La justification doit comporter au moins 10 caractères")

    from core.audit import log_action
    log_action(
        action='BUDGET_OVERRIDE',
        entity_type='REQUEST',
        entity_id=str(request_obj.id),
        actor=actor,
        details={'amount': amount, 'justification': justification},
    )
    return {'approved': True, 'override': True, 'justification': justification}


# ═══════════════════════════════════════════════════════════════════════════
# GENOCLAB — Real Revenue (invoicing)
# Invoice rows are created from the admin operations view
# (dashboard.views.admin_ops.generate_invoice), which composes the line items
# from the request's accepted quote.
# ═══════════════════════════════════════════════════════════════════════════

def get_revenue_summary() -> dict:
    """GENOCLAB real revenue from invoices."""
    from core.models import Invoice
    invoices = Invoice.objects.all()
    agg = invoices.aggregate(total=Sum('total_ttc'), count=Count('id'))
    return {
        'total': float(agg['total'] or 0),
        'count': agg['count'],
    }


# ═══════════════════════════════════════════════════════════════════════════
# COMBINED DASHBOARD DATA
# ═══════════════════════════════════════════════════════════════════════════

def archive_monthly_revenue(month: int = None, year: int = None) -> list:
    """Archive monthly revenue for both channels."""
    from core.models import Request, RevenueArchive, Invoice

    now = datetime.now()
    if month is None:
        month = now.month - 1 if now.month > 1 else 12
    if year is None:
        year = now.year if now.month > 1 else now.year - 1

    results = []
    for channel in ['IBTIKAR', 'GENOCLAB']:
        if channel == 'IBTIKAR':
            qs = Request.objects.filter(
                channel='IBTIKAR',
                created_at__month=month,
                created_at__year=year,
            ).exclude(status__in=REJECTION_STATES)
            total = float(qs.aggregate(total=Sum('budget_amount'))['total'] or 0)
            count = qs.count()
        else:
            qs = Invoice.objects.filter(
                created_at__month=month,
                created_at__year=year,
            )
            total = float(qs.aggregate(total=Sum('total_ttc'))['total'] or 0)
            count = qs.count()

        archive, created = RevenueArchive.objects.update_or_create(
            month=month,
            year=year,
            channel=channel,
            defaults={
                'total_revenue': total,
                'request_count': count,
            },
        )
        results.append({
            'channel': channel,
            'month': month,
            'year': year,
            'total_revenue': total,
            'request_count': count,
            'created': created,
        })

    logger.info("Revenue archived for %s/%s: %s", month, year, results)
    return results


def get_budget_dashboard() -> dict:
    """Return symmetric data for both IBTIKAR and GENOCLAB revenue display."""
    ibtikar = get_ibtikar_virtual_revenue()
    genoclab = get_revenue_summary()

    return {
        'ibtikar': {
            'total': ibtikar['total'],
            'count': ibtikar['count'],
            'students': ibtikar['students'],
            'budget_per_student': settings.IBTIKAR_BUDGET_CAP,
            'label': 'Revenus virtuels IBTIKAR',
        },
        'genoclab': {
            'total': genoclab['total'],
            'count': genoclab['count'],
            'label': 'Revenus GENOCLAB',
        },
    }
