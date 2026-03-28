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
    """Check if THIS STUDENT's budget allows the amount. Cap = 200K per student."""
    used = get_ibtikar_budget_used_by_requester(requester.id) if requester else 0.0
    cap = settings.IBTIKAR_BUDGET_CAP
    projected = used + float(amount)

    result = {
        'used': used,
        'cap': cap,
        'amount': float(amount),
        'projected': projected,
        'exceeded': projected > cap,
        'remaining': max(0, cap - used),
        'pct_used': round(used / cap * 100, 1) if cap > 0 else 0,
    }

    if result['exceeded']:
        logger.warning(
            "Budget IBTIKAR exceeded: requester=%s projected=%s cap=%s",
            getattr(requester, 'id', '?'), projected, cap,
        )

    return result


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
# ═══════════════════════════════════════════════════════════════════════════

def generate_invoice(request_obj, actor, line_items=None):
    """Generate a GENOCLAB invoice from a request."""
    from core.models import Invoice

    year = datetime.now().year
    last = Invoice.objects.count() + 1
    inv_number = f"{settings.INVOICE_PREFIX}-{year}-{last:04d}"

    items = line_items or []
    if not items and request_obj.quote_amount:
        items = [{
            'description': request_obj.title,
            'quantity': 1,
            'unit_price': float(request_obj.quote_amount),
        }]

    subtotal = sum(i.get('quantity', 1) * i.get('unit_price', 0) for i in items)
    vat = round(subtotal * float(settings.VAT_RATE), 2)
    total = round(subtotal + vat, 2)

    invoice = Invoice.objects.create(
        invoice_number=inv_number,
        request=request_obj,
        client=request_obj.requester,
        line_items=items,
        subtotal_ht=subtotal,
        vat_rate=settings.VAT_RATE,
        vat_amount=vat,
        total_ttc=total,
        created_by=actor,
    )

    logger.info("Invoice %s generated: total_ttc=%s", inv_number, total)
    return invoice


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
