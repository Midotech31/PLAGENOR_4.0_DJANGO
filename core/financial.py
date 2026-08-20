# core/financial.py — PLAGENOR 4.0 Financial Engine (Django ORM)
# IBTIKAR: 200K DA per student/year (virtual revenue). GENOCLAB: Invoicing (real revenue).

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from django.conf import settings
from django.db.models import Count, Sum

from core.exceptions import BudgetExceededError, FinancialValidationError

logger = logging.getLogger('plagenor.financial')


# ═══════════════════════════════════════════════════════════════════════════
# GENOCLAB — Invoice / quote totals (HT → VAT → TTC)
# ═══════════════════════════════════════════════════════════════════════════
def parse_money(value, *, field: str = 'Montant', allow_zero: bool = True) -> Decimal:
    """Parse a finite, non-negative money value or fail closed.

    Blank values are treated as zero only for optional fee fields. Callers
    that require a strictly positive value set ``allow_zero=False``.
    """
    try:
        amount = Decimal(str(value if value not in (None, '') else 0))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise FinancialValidationError(f"{field} invalide.") from exc
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        qualifier = "strictement positif" if not allow_zero else "positif ou nul"
        raise FinancialValidationError(f"{field} doit être un nombre fini {qualifier}.")
    return amount


def _q2(amount: Decimal) -> Decimal:
    """Round to 2 decimals using ROUND_HALF_UP (the conventional invoice rule)."""
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def compute_invoice_totals(line_items, admin_fees=0, report_fees=0, vat_rate=0.19):
    """Compute HT / VAT / TTC for a GENOCLAB quote or invoice.

    ``line_items``: iterable of dicts each carrying a numeric ``total`` (the
    per-line subtotal). ``vat_rate`` is a fraction (0.19 = 19%).

    Arithmetic is done in ``Decimal`` to avoid binary-float drift on money, and
    VAT / total are rounded to 2 decimals with ROUND_HALF_UP (standard invoice
    rounding — not Python's banker's rounding). Values are returned as ``float``
    so the result stays JSON-serialisable for ``Request.quote_detail`` and
    assignable to the ``DecimalField`` invoice columns, exactly as before.
    """
    admin_fees = parse_money(admin_fees, field='Frais administratifs')
    report_fees = parse_money(report_fees, field='Frais de rapport')
    vat_rate = parse_money(vat_rate, field='Taux de TVA')
    if vat_rate > 1:
        raise FinancialValidationError("Le taux de TVA doit être compris entre 0 et 1.")
    subtotal_ht = sum((
        parse_money(i.get('total', 0), field=f"Total de la ligne {index}")
        for index, i in enumerate(line_items, start=1)
    ), Decimal('0'))
    subtotal_before_tax = subtotal_ht + admin_fees + report_fees
    vat_amount = _q2(subtotal_before_tax * vat_rate)
    total_ttc = _q2(subtotal_before_tax + vat_amount)
    return {
        'subtotal_ht': float(subtotal_ht),
        'admin_fees': float(admin_fees),
        'report_fees': float(report_fees),
        'subtotal_before_tax': float(subtotal_before_tax),
        'vat_rate': float(vat_rate),
        'vat_amount': float(vat_amount),
        'total_ttc': float(total_ttc),
    }


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


def deduct_ibtikar_balance(requester, amount: Decimal, reason: str = '') -> dict:
    """Deduct a resolved request cost from the requester's declared
    IBTIKAR balance. Called when an IBTIKAR request reaches COMPLETED
    (report delivered + receipt confirmed).

    NOT idempotent on its own: every call debits. `reason` is only
    recorded in the log. The once-per-request guarantee lives in the
    caller, which claims ``Request.budget_deducted`` under
    ``SELECT … FOR UPDATE`` before calling this
    (see core.workflow._deduct_ibtikar_on_complete). Any new caller must
    provide its own guard.

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

    before = Decimal(requester.ibtikar_declared_balance)
    amount = parse_money(amount, field='Montant à déduire')
    after = max(Decimal('0.00'), before - amount)
    requester.ibtikar_declared_balance = after
    requester.ibtikar_balance_declared_at = timezone.now()
    requester.save(update_fields=[
        'ibtikar_declared_balance', 'ibtikar_balance_declared_at',
    ])
    logger.info(
        "IBTIKAR deduction: requester=%s amount=%s before=%s after=%s reason=%s",
        requester.id, amount, before, after, reason,
    )
    return {'deducted': amount, 'remaining': after, 'skipped': False}


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
