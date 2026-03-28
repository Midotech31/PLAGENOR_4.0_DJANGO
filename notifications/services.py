from .models import Notification


def notify_user(user, message, notification_type='INFO', request_obj=None):
    """Create an in-app notification for a user."""
    Notification.objects.create(
        user=user,
        message=message,
        notification_type=notification_type,
        request=request_obj,
    )


def notify_workflow_transition(request_obj, to_status, actor):
    """Send notifications based on workflow events."""
    messages = {
        'VALIDATED': ('Votre demande a été validée', [request_obj.requester]),
        'REJECTED': ('Votre demande a été rejetée', [request_obj.requester]),
        'ASSIGNED': (
            'Une analyse vous a été assignée',
            [request_obj.assigned_to.user if request_obj.assigned_to else None],
        ),
        'REPORT_VALIDATED': ('Le rapport a été validé', [request_obj.requester]),
        'COMPLETED': ('Votre demande est complétée', [request_obj.requester]),
    }

    entry = messages.get(to_status)
    if entry:
        msg, targets = entry
        for target in targets:
            if target and target != actor:
                notify_user(
                    target,
                    f"{msg} — {request_obj.display_id}",
                    'WORKFLOW',
                    request_obj,
                )


def get_unread_count(user):
    """Return the number of unread notifications for a user."""
    return Notification.objects.filter(user=user, read=False).count()
