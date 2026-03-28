# core/services/genoclab.py — PLAGENOR 4.0 GENOCLAB Service (Django ORM)

from __future__ import annotations

from datetime import datetime

from core.models import Request, RequestHistory


def submit_genoclab_request(data: dict, user) -> Request:
    """Submit a new GENOCLAB request."""
    # Generate display_id
    year = datetime.now().year
    count = Request.objects.filter(channel='GENOCLAB', created_at__year=year).count() + 1
    display_id = f"GCL-{year}-{count:04d}"

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

    return request_obj
