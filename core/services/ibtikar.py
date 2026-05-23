# core/services/ibtikar.py — PLAGENOR 4.0 IBTIKAR Service (Django ORM)

from __future__ import annotations

from datetime import datetime

from core.models import Request, RequestHistory
from core.sequences import next_display_id


def submit_ibtikar_request(data: dict, user) -> Request:
    """Submit a new IBTIKAR request. Budget enforcement happens at the view
    layer (see dashboard.views.requester.create_request)."""
    # Generate display_id atomically (no .count()+1 race).
    year = datetime.now().year
    display_id = next_display_id(
        'IBK', year,
        initial_value_fn=lambda: Request.objects.filter(
            channel='IBTIKAR', created_at__year=year,
            display_id__startswith=f'IBK-{year}-',
        ).count(),
    )

    budget_amount = data.get('budget_amount', 0)
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
    except Exception:
        pass

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
