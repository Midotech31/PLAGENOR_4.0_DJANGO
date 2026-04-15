from django.utils import timezone


def archive_phase_messages(request_obj, phase):
    """Archive all messages for a completed phase."""
    from messaging.models import EphemeralMessage

    count = EphemeralMessage.objects.filter(
        request=request_obj,
        phase=phase,
        is_archived=False
    ).update(
        is_archived=True,
        archived_at=timezone.now()
    )

    if count > 0:
        sender_user = request_obj.assigned_to.user if request_obj.assigned_to else None
        if not sender_user:
            from accounts.models import User
            sender_user = User.objects.filter(role='PLATFORM_ADMIN').first()

        if sender_user:
            EphemeralMessage.objects.create(
                request=request_obj,
                phase=request_obj.status,
                sender=sender_user,
                content=f"Phase changed: {phase} → {request_obj.status}",
                is_system_message=True
            )

    return count


def deactivate_reminders(request_obj, reason=''):
    """Deactivate all active reminders when request moves forward."""
    from messaging.models import Reminder

    count = Reminder.objects.filter(
        request=request_obj,
        is_active=True
    ).update(
        is_active=False,
        deactivated_at=timezone.now(),
        deactivated_reason=reason
    )

    return count


def _notify_message_participants(request_obj, sender, content):
    """Send notification to all participants EXCEPT the sender."""
    from notifications.services import create_notification

    participants = set()

    from accounts.models import User
    admins = User.objects.filter(role='PLATFORM_ADMIN', is_active=True)
    for admin in admins:
        participants.add(admin)

    if request_obj.assigned_to and request_obj.assigned_to.user:
        participants.add(request_obj.assigned_to.user)

    if request_obj.requester:
        participants.add(request_obj.requester)

    for observer in request_obj.informed_members.all():
        if observer.user:
            participants.add(observer.user)

    participants.discard(sender)

    preview = content[:80] + '...' if len(content) > 80 else content
    display_id = request_obj.ibtikar_id or request_obj.tracking_number or request_obj.display_id or 'Request'

    for user in participants:
        create_notification(
            user=user,
            notification_type='MESSAGE',
            title=f"New message on {display_id}",
            message=f"{sender.get_full_name()}: {preview}",
            request=request_obj,
        )


def create_reminder(request_obj, rule, target_user, urgency='NORMAL', escalated=False):
    """Create a new reminder for a request."""
    from messaging.models import Reminder

    reminder = Reminder.objects.create(
        request=request_obj,
        target_user=target_user,
        action_expected=rule['action_expected'],
        status_when_created=rule['status'],
        urgency=urgency,
        source='AUTO',
        escalated=escalated,
        escalated_at=timezone.now() if escalated else None,
    )

    reminder.sent_at = timezone.now()
    reminder.save(update_fields=['sent_at'])

    return reminder


def _notify_escalation(request_obj, rule, target_user):
    """Notify admin when a reminder is escalated to CRITICAL."""
    from notifications.services import create_notification
    from accounts.models import User

    display_id = request_obj.ibtikar_id or request_obj.tracking_number or request_obj.display_id or 'Request'

    for admin in User.objects.filter(role__in=['PLATFORM_ADMIN', 'SUPER_ADMIN'], is_active=True):
        create_notification(
            user=admin,
            notification_type='REMINDER_ESCALATION',
            title=f"Reminder Escalated — {display_id}",
            message=f"Request {display_id} is overdue. "
                   f"Action: {rule['action_expected']}. "
                   f"Target: {target_user.get_full_name() if target_user else 'Unknown'}.",
            request=request_obj,
        )


def _send_reminder_notification(request_obj, rule, target_user):
    """Send notification to the reminder target user."""
    from notifications.services import create_notification

    display_id = request_obj.ibtikar_id or request_obj.tracking_number or request_obj.display_id or 'Request'

    create_notification(
        user=target_user,
        notification_type='REMINDER',
        title=f"Reminder: {display_id}",
        message=f"Action required: {rule['action_expected']}",
        request=request_obj,
    )
