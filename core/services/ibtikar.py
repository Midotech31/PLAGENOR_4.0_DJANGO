# core/services/ibtikar.py — PLAGENOR 4.0 IBTIKAR Service (Django ORM)

from __future__ import annotations

import logging
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from core.models import Request, RequestHistory
from core.financial import check_ibtikar_budget, get_ibtikar_budget_available

logger = logging.getLogger('plagenor.services')


def submit_ibtikar_request(data: dict, user) -> Request:
    """Submit a new IBTIKAR request with SMART budget check and IBTIKAR ID validation."""
    from django.conf import settings
    
    with transaction.atomic():
        year = datetime.now().year
        count = Request.objects.filter(channel='IBTIKAR', created_at__year=year).count() + 1
        display_id = f"IBK-{year}-{count:04d}"

        budget_amount = data.get('budget_amount', 0)
        declared_balance = data.get('declared_ibtikar_balance', 0)
        declared_balance_at = data.get('declared_balance_at')
        
        # For budget calculation, use the passed declared_balance_at (None = look up last)
        # For storage in request, use current time as fallback
        budget_check_balance_at = declared_balance_at
        storage_balance_at = declared_balance_at if declared_balance_at else timezone.now()
        
        # SMART budget check using declared balance
        if budget_amount and declared_balance is not None:
            budget_check = check_ibtikar_budget(
                amount=budget_amount,
                requester=user,
                declared_balance=declared_balance,
                declared_balance_at=budget_check_balance_at
            )
            if budget_check['exceeded']:
                data.setdefault('_budget_warning', budget_check)
            if budget_check.get('cap_exceeded'):
                data.setdefault('_cap_warning', budget_check)

        ibtikar_id = data.get('ibtikar_id', '')
        if not ibtikar_id and hasattr(user, 'ibtikar_id'):
            ibtikar_id = user.ibtikar_id

        if ibtikar_id:
            from core.models import Request as CoreRequest
            duplicate_check = CoreRequest.objects.filter(
                ibtikar_id=ibtikar_id,
                channel='IBTIKAR'
            ).exclude(
                status__in=['COMPLETED', 'CLOSED', 'REJECTED']
            ).exists()
            if duplicate_check:
                data.setdefault('_ibtikar_id_warning', 
                    'Cet identifiant IBTIKAR est déjà utilisé sur une autre demande active.')

        service_id = data.get('service_id')

        request_obj = Request.objects.create(
            display_id=display_id,
            title=data.get('title', ''),
            description=data.get('description', ''),
            channel='IBTIKAR',
            status='SUBMITTED',
            urgency=data.get('urgency', 'Normal'),
            service_id=service_id,
            requester=user,
            budget_amount=budget_amount,
            declared_ibtikar_balance=declared_balance,
            declared_balance_at=storage_balance_at,
            ibtikar_id=ibtikar_id,
            service_params=data.get('service_params', {}),
            pricing=data.get('pricing_breakdown', data.get('pricing', {})),
            sample_table=data.get('sample_table', []),
            requester_data=data.get('requester_data', {}),
            analysis_framework=data.get('analysis_framework', ''),
            pi_name=data.get('pi_name', ''),
            pi_email=data.get('pi_email', ''),
            pi_phone=data.get('pi_phone', ''),
        )

        RequestHistory.objects.create(
            request=request_obj,
            from_status='',
            to_status='SUBMITTED',
            actor=user,
        )

        try:
            from notifications.models import Notification
            from accounts.models import User
            admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
            for admin in admins:
                Notification.objects.create(
                    user=admin,
                    message=f"Nouvelle demande IBTIKAR: {request_obj.display_id} — {request_obj.title[:50]}",
                    request=request_obj,
                    notification_type='WORKFLOW',
                )
        except (DatabaseError, IntegrityError, ObjectDoesNotExist) as e:
            logger.error(
                f"Failed to create admin notifications for IBTIKAR request {display_id}: {str(e)}",
                extra={
                    'request_display_id': display_id,
                    'request_id': str(request_obj.id),
                },
                exc_info=True
            )

    return request_obj


def get_ibtikar_request_context(user) -> dict:
    """
    Get context data for the IBTIKAR request form using SMART budget logic.
    
    Returns:
        dict with:
            - declared: Last declared IBTIKAR balance
            - declared_balance_at: When balance was last declared
            - budget_used: Total PLAGENOR consumption
            - consumption_since_declaration: Consumption since last declaration
            - available: Available budget (declared - consumption_since_declaration)
            - budget_cap: IBTIKAR budget cap (200K)
            - budget_remaining: Remaining before cap
            - budget_pct: Percentage of cap used
    """
    from core.financial import get_ibtikar_budget_used_by_requester, get_ibtikar_budget_available
    from core.models import Request
    from django.conf import settings
    
    cap = settings.IBTIKAR_BUDGET_CAP
    
    # Get the most recent declared balance from user's requests
    last_request = Request.objects.filter(
        channel='IBTIKAR',
        requester=user,
        declared_ibtikar_balance__gt=0,
    ).exclude(status__in=['REJECTED', 'DRAFT', 'QUOTE_REJECTED_BY_CLIENT']).order_by('-declared_balance_at').first()
    
    declared = float(last_request.declared_ibtikar_balance) if last_request and last_request.declared_ibtikar_balance else cap
    declared_at = last_request.declared_balance_at if last_request else None
    
    # Get total PLAGENOR consumption
    total_consumption = get_ibtikar_budget_used_by_requester(user.id)
    
    # Get consumption since last declaration
    consumption_since_decl = 0
    available = declared
    if declared_at:
        consumption_since_decl = sum(
            float(r.budget_amount) for r in Request.objects.filter(
                channel='IBTIKAR',
                requester=user,
                created_at__gt=declared_at,
            ).exclude(status__in=['REJECTED', 'DRAFT', 'QUOTE_REJECTED_BY_CLIENT'])
        )
        available = max(0, declared - consumption_since_decl)
    
    return {
        'declared': declared,
        'declared_balance_at': declared_at,
        'budget_used': total_consumption,
        'consumption_since_declaration': consumption_since_decl,
        'available': available,
        'budget_cap': cap,
        'budget_remaining': max(0, cap - total_consumption),
        'budget_pct': round(total_consumption / cap * 100, 1) if cap > 0 else 0,
    }
