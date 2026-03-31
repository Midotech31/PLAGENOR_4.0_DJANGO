# core/services/genoclab.py — PLAGENOR 4.0 GENOCLAB Service (Django ORM)

from __future__ import annotations

import logging
from datetime import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, IntegrityError

from core.models import Request, RequestHistory

logger = logging.getLogger('plagenor.services')


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
    except (DatabaseError, IntegrityError, ObjectDoesNotExist) as e:
        # Log the error but don't fail the request creation
        logger.error(
            f"Failed to create admin notifications for GENOCLAB request {display_id}: {str(e)}",
            extra={
                'request_display_id': display_id,
                'request_id': str(request_obj.id),
            },
            exc_info=True
        )

    return request_obj
