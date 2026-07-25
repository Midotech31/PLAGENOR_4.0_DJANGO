# core/services/genoclab.py — PLAGENOR 4.0 GENOCLAB Service (Django ORM)

from __future__ import annotations

from datetime import datetime

from core.models import Request, RequestHistory
from core.sequences import next_display_id


def submit_genoclab_request(data: dict, user) -> Request:
    """Submit a new GENOCLAB request."""
    # Generate display_id atomically (no .count()+1 race).
    year = datetime.now().year
    display_id = next_display_id(
        'GCL', year,
        initial_value_fn=lambda: Request.objects.filter(
            channel='GENOCLAB', created_at__year=year,
            display_id__startswith=f'GCL-{year}-',
        ).count(),
    )

    service_id = data.get('service_id')

    request_obj = Request.objects.create(
        display_id=display_id,
        title=data.get('title', ''),
        description=data.get('description', ''),
        channel='GENOCLAB',
        status='REQUEST_CREATED',
        urgency=data.get('urgency', 'Normal'),
        service_id=service_id,
        requester=user,
        quote_amount=data.get('quote_amount', 0),
        service_params=data.get('service_params', {}),
        pricing=data.get('pricing', {}),
        sample_table=data.get('sample_table', []),
        requester_data=data.get('requester_data', {}),
    )

    RequestHistory.objects.create(
        request=request_obj,
        from_status='',
        to_status='REQUEST_CREATED',
        actor=user,
    )

    # Notify admins of new GENOCLAB request
    try:
        from notifications.models import Notification
        from accounts.models import User
        admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'], is_active=True)
        for admin in admins:
            Notification.objects.create(
                user=admin,
                message=f"Nouvelle demande GENOCLAB: {request_obj.display_id} — {request_obj.title[:50]}",
                request=request_obj,
                notification_type='WORKFLOW',
            )
    except Exception:
        pass

    # Email the client their submission confirmation. Same fix as IBTIKAR:
    # only the guest path was emailing; authenticated clients now get one too.
    try:
        from notifications.emails import notify_submission_confirmation
        notify_submission_confirmation(request_obj)
    except Exception:
        pass

    return request_obj
