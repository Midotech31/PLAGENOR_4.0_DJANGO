# core/services/ibtikar.py — PLAGENOR 4.0 IBTIKAR Service (Django ORM)

from __future__ import annotations

import logging
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

from core.models import Request, RequestHistory
from core.financial import check_ibtikar_budget

logger = logging.getLogger('plagenor.services')


def submit_ibtikar_request(data: dict, user) -> Request:
    """Submit a new IBTIKAR request with budget check."""
    # Generate display_id
    year = datetime.now().year
    count = Request.objects.filter(channel='IBTIKAR', created_at__year=year).count() + 1
    display_id = f"IBK-{year}-{count:04d}"

    # Optional budget check
    budget_amount = data.get('budget_amount', 0)
    if budget_amount:
        budget_check = check_ibtikar_budget(amount=budget_amount, requester=user)
        if budget_check['exceeded']:
            # Store warning but don't block — SUPER_ADMIN can override
            data.setdefault('_budget_warning', budget_check)

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
        declared_ibtikar_balance=data.get('declared_ibtikar_balance', 0),
        service_params=data.get('service_params', {}),
        pricing=data.get('pricing', {}),
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

    # Notify admins of new submission
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
        # Log the error but don't fail the request creation
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
    """Get context data for the IBTIKAR request form."""
    from core.financial import get_ibtikar_budget_used_by_requester
    from django.conf import settings

    used = get_ibtikar_budget_used_by_requester(user.id)
    cap = settings.IBTIKAR_BUDGET_CAP
    return {
        'budget_used': used,
        'budget_cap': cap,
        'budget_remaining': max(0, cap - used),
        'budget_pct': round(used / cap * 100, 1) if cap > 0 else 0,
    }
