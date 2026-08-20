# core/services/ibtikar.py — PLAGENOR 4.0 IBTIKAR Service (Django ORM)

from __future__ import annotations

from datetime import datetime
import logging

from core.models import Request, RequestHistory
from core.sequences import next_display_id

logger = logging.getLogger('plagenor.services.ibtikar')


def submit_ibtikar_request(data: dict, user=None) -> Request:
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
        submitted_as_guest=bool(data.get('submitted_as_guest', False)),
        guest_token=data.get('guest_token'),
        guest_name=data.get('guest_name', ''),
        guest_email=data.get('guest_email', ''),
        guest_phone=data.get('guest_phone', ''),
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
        logger.exception(
            "Unable to notify administrators for IBTIKAR request %s",
            request_obj.pk,
        )

    # Email the requester their submission confirmation. The guest path
    # already did this; authenticated requesters were missing it.
    try:
        from notifications.emails import notify_submission_confirmation
        notify_submission_confirmation(request_obj)
    except Exception:
        logger.exception(
            "Unable to send submission confirmation for IBTIKAR request %s",
            request_obj.pk,
        )

    return request_obj


def get_ibtikar_request_context(user) -> dict:
    """Build the budget panel context for the requester dashboard.

    Returns the *declared* residual balance (what the candidate self-
    reports as their current IBTIKAR pot at DGRSDT) — not a flat
    200 000 DA. The hard ceiling stays available as `budget_cap` so the
    UI can validate the declaration input.

    Key flags:
      needs_declaration  True iff the requester has never declared a
                         balance yet → the form must be hidden behind a
                         declaration prompt.
      last_declared_at   When the declaration was last touched, so the
                         template can nudge the requester to refresh it.
    """
    from django.conf import settings

    declared = user.ibtikar_declared_balance
    hard_cap = settings.IBTIKAR_BUDGET_CAP

    if declared is None:
        return {
            'budget_declared': None,
            'budget_remaining': None,
            'budget_cap': hard_cap,
            'budget_pct': 0,
            'needs_declaration': True,
            'last_declared_at': None,
        }

    declared_f = float(declared)
    return {
        'budget_declared': declared_f,
        'budget_remaining': declared_f,
        'budget_cap': hard_cap,
        # Percentage of the *hard ceiling* used — gives a visual sense of
        # how much of the annual envelope is left. 0 % when no ceiling.
        'budget_pct': round((hard_cap - declared_f) / hard_cap * 100, 1) if hard_cap > 0 else 0,
        'needs_declaration': False,
        'last_declared_at': user.ibtikar_balance_declared_at,
    }
