import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('plagenor.reminders')


REMINDER_RULES = [
    {
        'status': 'PENDING_ACCEPTANCE',
        'action_expected': 'Accept or decline the assignment',
        'delay_hours': 24,
        'escalation_hours': 48,
        'recipient': 'assigned_member',
        'channel': 'BOTH',
    },
    {
        'status': 'ACCEPTED',
        'action_expected': 'Propose an appointment date',
        'delay_hours': 48,
        'escalation_hours': 96,
        'recipient': 'assigned_member',
        'channel': 'BOTH',
    },
    {
        'status': 'APPOINTMENT_CONFIRMED',
        'action_expected': 'Start the analysis (appointment day passed)',
        'delay_hours': 24,
        'escalation_hours': 72,
        'recipient': 'assigned_member',
        'channel': 'BOTH',
        'reference_date': 'appointment_date',
    },
    {
        'status': 'ANALYSIS_STARTED',
        'action_expected': 'Complete the analysis and upload report',
        'delay_hours': 168,
        'escalation_hours': 336,
        'recipient': 'assigned_member',
        'channel': 'BOTH',
    },
    {
        'status': 'ANALYSIS_FINISHED',
        'action_expected': 'Upload the analysis report',
        'delay_hours': 48,
        'escalation_hours': 96,
        'recipient': 'assigned_member',
        'channel': 'BOTH',
    },
    {
        'status': 'REPORT_UPLOADED',
        'action_expected': 'Validate the report',
        'delay_hours': 48,
        'escalation_hours': 96,
        'recipient': 'admin',
        'channel': 'BOTH',
    },
    {
        'status': 'QUOTE_VALIDATED_BY_CLIENT',
        'action_expected': 'Upload purchase order',
        'delay_hours': 72,
        'escalation_hours': 168,
        'recipient': 'client',
        'channel': 'GENOCLAB',
    },
    {
        'status': 'PAYMENT_PENDING',
        'action_expected': 'Upload payment receipt',
        'delay_hours': 72,
        'escalation_hours': 168,
        'recipient': 'client',
        'channel': 'GENOCLAB',
    },
    {
        'status': 'APPOINTMENT_PROPOSED',
        'action_expected': 'Confirm or request new appointment',
        'delay_hours': 48,
        'escalation_hours': 96,
        'recipient': 'requester',
        'channel': 'IBTIKAR',
    },
]


class Command(BaseCommand):
    help = 'Check for overdue requests and create/send reminders'

    def handle(self, *args, **options):
        from core.models import Request
        from messaging.models import Reminder

        now = timezone.now()
        created_count = 0
        escalated_count = 0

        for rule in REMINDER_RULES:
            channel_filter = rule.get('channel', 'BOTH')
            requests_qs = Request.objects.filter(
                status=rule['status'],
                is_deleted=False,
            )
            if channel_filter != 'BOTH':
                requests_qs = requests_qs.filter(channel=channel_filter)

            for req in requests_qs:
                reference_date = self._get_reference_date(req, rule)
                if not reference_date:
                    continue

                hours_elapsed = (now - reference_date).total_seconds() / 3600
                target_user = self._get_target_user(req, rule)
                if not target_user:
                    continue

                existing = Reminder.objects.filter(
                    request=req,
                    status_when_created=rule['status'],
                    is_active=True,
                ).first()

                if hours_elapsed >= rule['escalation_hours']:
                    if existing and not existing.escalated:
                        existing.urgency = 'CRITICAL'
                        existing.escalated = True
                        existing.escalated_at = now
                        existing.save()
                        self._notify_escalation(req, rule, target_user)
                        escalated_count += 1
                        self.stdout.write(f"Escalated reminder for {req.display_id}")
                    elif not existing:
                        self._create_reminder(req, rule, target_user, 'CRITICAL', escalated=True)
                        self._notify_escalation(req, rule, target_user)
                        created_count += 1
                        escalated_count += 1
                        self.stdout.write(f"Created CRITICAL reminder for {req.display_id}")

                elif hours_elapsed >= rule['delay_hours']:
                    if not existing:
                        self._create_reminder(req, rule, target_user, 'NORMAL')
                        self._send_reminder_notification(req, rule, target_user)
                        created_count += 1
                        self.stdout.write(f"Created NORMAL reminder for {req.display_id}")

        self.stdout.write(
            self.style.SUCCESS(f"Check complete. Created: {created_count}, Escalated: {escalated_count}")
        )

    def _get_reference_date(self, req, rule):
        if rule.get('reference_date') == 'appointment_date':
            apt_date = getattr(req, 'appointment_date', None)
            if apt_date:
                from datetime import datetime
                if isinstance(apt_date, datetime):
                    return apt_date
                return timezone.make_aware(datetime.combine(apt_date, datetime.min.time()))
        return req.updated_at

    def _get_target_user(self, req, rule):
        from accounts.models import User
        
        recipient = rule.get('recipient', '')
        if recipient == 'assigned_member':
            return req.assigned_to.user if req.assigned_to and req.assigned_to.user else None
        elif recipient == 'admin':
            return User.objects.filter(role='PLATFORM_ADMIN', is_active=True).first()
        elif recipient == 'requester':
            return req.requester
        elif recipient == 'client':
            return req.requester
        return None

    def _create_reminder(self, req, rule, target_user, urgency='NORMAL', escalated=False):
        from messaging.models import Reminder
        
        return Reminder.objects.create(
            request=req,
            target_user=target_user,
            action_expected=rule['action_expected'],
            status_when_created=rule['status'],
            urgency=urgency,
            source='AUTO',
            escalated=escalated,
            escalated_at=timezone.now() if escalated else None,
            sent_at=timezone.now(),
        )

    def _send_reminder_notification(self, req, rule, target_user):
        from notifications.services import create_notification
        from accounts.models import User
        
        display_id = req.ibtikar_id or req.tracking_number or req.display_id or 'Request'
        create_notification(
            user=target_user,
            notification_type='REMINDER',
            title=f"Reminder: {display_id}",
            message=f"Action required: {rule['action_expected']}",
            request=req,
        )

    def _notify_escalation(self, req, rule, target_user):
        from notifications.services import create_notification
        from accounts.models import User
        
        display_id = req.ibtikar_id or req.tracking_number or req.display_id or 'Request'
        
        for admin in User.objects.filter(role__in=['PLATFORM_ADMIN', 'SUPER_ADMIN'], is_active=True):
            create_notification(
                user=admin,
                notification_type='REMINDER_ESCALATION',
                title=f"Reminder Escalated — {display_id}",
                message=f"Request {display_id} is overdue. Action: {rule['action_expected']}. Target: {target_user.get_full_name() if target_user else 'Unknown'}.",
                request=req,
            )
