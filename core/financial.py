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
    """Budget used by ONE specific student/requester (all time, excluding rejected)."""
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


def get_ibtikar_budget_used_since_declaration(requester, declared_balance_at, exclude_request_id=None) -> float:
    """
    Calculate PLAGENOR consumption SINCE the user's last balance declaration.
    
    This is the SMART budget logic: only count requests made AFTER the student
    last updated their IBTIKAR balance on PLAGENOR. This handles the delay
    between PLAGENOR deductions and IBTIKAR's external balance updates.
    
    Args:
        requester: User instance
        declared_balance_at: datetime of the last balance declaration
        exclude_request_id: UUID of current request to exclude (optional)
    
    Returns:
        Total cost of requests submitted after declared_balance_at
    """
    from core.models import Request
    from django.db.models import Q
    
    qs = Request.objects.filter(
        channel='IBTIKAR',
        requester=requester,
    ).exclude(status__in=REJECTION_STATES)
    
    if declared_balance_at:
        qs = qs.filter(created_at__gt=declared_balance_at)
    
    if exclude_request_id:
        qs = qs.exclude(pk=exclude_request_id)
    
    total = qs.aggregate(total=Sum('budget_amount'))['total']
    return float(total or 0)


def get_ibtikar_budget_available(requester, declared_balance, declared_balance_at=None, exclude_request_id=None) -> dict:
    """
    SMART budget calculation for IBTIKAR requests.
    
    This function calculates the available budget based on the student's
    declared IBTIKAR balance minus PLAGENOR consumption since that declaration.
    
    Logic:
    1. Get the user's most recent balance declaration (if not provided)
    2. Calculate consumption at PLAGENOR since that declaration
    3. Available = Declared - Consumption since declaration
    
    Args:
        requester: User instance
        declared_balance: Current balance as declared by user (DA)
        declared_balance_at: When the balance was declared (datetime)
        exclude_request_id: UUID of current request to exclude from calculation
    
    Returns:
        dict with:
            - declared_balance: User's declared balance
            - declared_balance_at: When balance was declared
            - consumption_since_declaration: PLAGENOR requests since declaration
            - available_budget: Remaining available budget
            - exceeded: Boolean if estimated cost exceeds available
            - suggested_action: Message to user if exceeded
    """
    from core.models import Request
    from django.utils import timezone
    
    result = {
        'declared_balance': float(declared_balance) if declared_balance else 0.0,
        'declared_balance_at': declared_balance_at,
        'consumption_since_declaration': 0.0,
        'available_budget': float(declared_balance) if declared_balance else 0.0,
        'exceeded': False,
        'suggested_action': '',
        'cap': settings.IBTIKAR_BUDGET_CAP,
    }
    
    # If no declared_balance_at provided, get the most recent from requests
    # But keep the passed value for consumption calculation
    consumption_calc_balance_at = declared_balance_at
    if declared_balance_at is None:
        last_request = Request.objects.filter(
            channel='IBTIKAR',
            requester=requester,
            declared_ibtikar_balance__gt=0,
        ).exclude(status__in=REJECTION_STATES).order_by('-declared_balance_at').first()
        
        if last_request:
            result['declared_balance'] = float(last_request.declared_ibtikar_balance)
            result['declared_balance_at'] = last_request.declared_balance_at
    
    # Calculate consumption since the passed declared_balance_at
    # If declared_balance_at was None and we found a last_request, use its declared_balance_at
    # Otherwise (still None), don't filter by date
    calc_balance_at = consumption_calc_balance_at
    if calc_balance_at is None and 'declared_balance_at' in result and result['declared_balance_at'] is not None:
        calc_balance_at = result['declared_balance_at']
    
    consumption = get_ibtikar_budget_used_since_declaration(
        requester=requester,
        declared_balance_at=calc_balance_at,
        exclude_request_id=exclude_request_id
    )
    result['consumption_since_declaration'] = consumption
    
    # Available = Declared - Consumption since declaration
    result['available_budget'] = max(0, result['declared_balance'] - consumption)
    
    # Calculate total consumption for cap check
    total_consumption = get_ibtikar_budget_used_by_requester(requester.id)
    
    # Check if total would exceed cap
    result['total_consumed'] = total_consumption
    result['cap_exceeded'] = total_consumption > settings.IBTIKAR_BUDGET_CAP
    result['cap_remaining'] = max(0, settings.IBTIKAR_BUDGET_CAP - total_consumption)
    
    return result


def get_ibtikar_budget_used(year: Optional[int] = None) -> float:
    """TOTAL IBTIKAR virtual revenue (all students combined)."""
    return get_ibtikar_virtual_revenue(year).get('total', 0.0)


def check_ibtikar_budget(amount, requester=None, request_obj=None, declared_balance=None, declared_balance_at=None) -> dict:
    """
    Check if THIS STUDENT's budget allows the amount.
    
    Uses SMART budget logic when declared_balance is provided:
    - available = declared_balance - consumption_since_last_declaration
    
    Falls back to simple cap check (200K per student) when no declaration.
    
    Args:
        amount: Estimated cost of new request
        requester: User instance
        request_obj: Request instance (optional, for excluding current request)
        declared_balance: User's declared IBTIKAR balance (optional)
        declared_balance_at: When balance was declared (optional)
    
    Returns:
        dict with budget status and recommendations
    """
    from core.models import Request
    
    cap = settings.IBTIKAR_BUDGET_CAP
    
    # If declared_balance provided, use SMART logic
    if declared_balance is not None and requester:
        smart_result = get_ibtikar_budget_available(
            requester=requester,
            declared_balance=declared_balance,
            declared_balance_at=declared_balance_at,
            exclude_request_id=request_obj.pk if request_obj else None
        )
        
        amount_float = float(amount)
        exceeded = amount_float > smart_result['available_budget']
        
        result = {
            'smart_mode': True,
            'declared_balance': smart_result['declared_balance'],
            'declared_balance_at': smart_result['declared_balance_at'],
            'consumption_since_declaration': smart_result['consumption_since_declaration'],
            'available': smart_result['available_budget'],
            'total_consumed': smart_result['total_consumed'],
            'amount': amount_float,
            'projected': amount_float,
            'exceeded': exceeded,
            'remaining': smart_result['available_budget'],
            'cap': cap,
            'cap_exceeded': smart_result['cap_exceeded'],
            'cap_remaining': smart_result['cap_remaining'],
        }
        
        if exceeded:
            result['suggested_action'] = (
                f"Réduisez le nombre d'échantillons ou changez le type d'analyse "
                f"pour respecter votre budget disponible ({smart_result['available_budget']:,.0f} DA)."
            )
            logger.warning(
                "IBTIKAR Budget Guard: requester=%s amount=%s available=%s",
                getattr(requester, 'id', '?'), amount_float, smart_result['available_budget'],
            )
        
        if smart_result['cap_exceeded']:
            result['cap_warning'] = (
                f"Attention: votre consommation totale ({smart_result['total_consumed']:,.0f} DA) "
                f"dépasse le plafond IBTIKAR ({cap:,.0f} DA)."
            )
        
        return result
    
    # Fallback: simple cap-based check
    used = get_ibtikar_budget_used_by_requester(requester.id) if requester else 0.0
    projected = used + float(amount)

    result = {
        'smart_mode': False,
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
