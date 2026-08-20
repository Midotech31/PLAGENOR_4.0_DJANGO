"""Tests for notification service helpers."""
import uuid
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from core.models import Request
from notifications import services
from notifications.models import Notification


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username='notif-u', role='CLIENT')

    def test_notify_user_creates_notification(self):
        services.notify_user(self.user, 'Bonjour', notification_type='INFO')
        n = Notification.objects.filter(user=self.user).first()
        self.assertIsNotNone(n)
        self.assertEqual(n.message, 'Bonjour')
        self.assertFalse(n.read)

    def test_unread_count_and_mark_all_read(self):
        for i in range(3):
            services.notify_user(self.user, f'msg {i}')
        self.assertEqual(services.get_unread_count(self.user), 3)
        services.mark_all_as_read(self.user)
        self.assertEqual(services.get_unread_count(self.user), 0)

    def test_recent_notifications_limit(self):
        for i in range(15):
            services.notify_user(self.user, f'm{i}')
        recent = services.get_recent_notifications(self.user, limit=5)
        self.assertEqual(len(list(recent)), 5)


class NotificationWorkflowTests(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username='notif-requester', password='x', role='CLIENT',
            email='requester@example.test',
        )
        self.actor = User.objects.create_user(
            username='notif-actor', password='x', role='PLATFORM_ADMIN',
        )
        self.analyst = User.objects.create_user(
            username='notif-analyst', password='x', role='MEMBER',
            email='analyst@example.test',
        )
        self.profile = self.analyst.member_profile
        self.request = Request.objects.create(
            display_id='NOTIF-001', title='Notification contract',
            channel='GENOCLAB', requester=self.requester,
            assigned_to=self.profile, quote_amount=1250,
        )

    def test_every_supported_workflow_status_targets_expected_user(self):
        expected_types = {
            'VALIDATED': 'STATUS_CHANGE', 'REJECTED': 'STATUS_CHANGE',
            'ASSIGNED': 'ASSIGNMENT', 'REPORT_VALIDATED': 'REPORT',
            'COMPLETED': 'STATUS_CHANGE', 'APPOINTMENT_PROPOSED': 'APPOINTMENT',
            'QUOTE_SENT': 'PAYMENT', 'PAYMENT_CONFIRMED': 'PAYMENT',
        }
        for status, type_ in expected_types.items():
            with self.subTest(status=status):
                Notification.objects.all().delete()
                services.notify_workflow_transition(self.request, status, self.actor)
                notification = Notification.objects.get()
                expected_user = self.analyst if status == 'ASSIGNED' else self.requester
                self.assertEqual(notification.user, expected_user)
                self.assertEqual(notification.notification_type, type_)
                self.assertEqual(notification.request, self.request)
                self.assertIn(str(self.request.pk), notification.link_url)

    def test_unknown_transition_and_actor_self_notification_are_skipped(self):
        services.notify_workflow_transition(self.request, 'DRAFT', self.actor)
        services.notify_workflow_transition(self.request, 'VALIDATED', self.requester)
        self.assertFalse(Notification.objects.exists())

    def test_assignment_status_report_and_payment_helpers(self):
        services.notify_assignment(self.request, self.analyst, self.actor)
        services.notify_status_change(self.request, 'DRAFT', 'SUBMITTED', self.actor)
        services.notify_report_ready(self.request)
        services.notify_payment_required(self.request, 2500)
        self.assertEqual(Notification.objects.filter(user=self.requester).count(), 3)
        assignment = Notification.objects.get(user=self.analyst)
        self.assertEqual(assignment.notification_type, 'ASSIGNMENT')
        self.assertIn('/accept/', assignment.action_url)

    def test_status_change_does_not_notify_actor(self):
        services.notify_status_change(self.request, 'DRAFT', 'SUBMITTED', self.requester)
        self.assertFalse(Notification.objects.exists())

    def test_commercial_notifications_reach_only_intended_roles(self):
        superadmin = User.objects.create_user(username='notif-super', role='SUPER_ADMIN')
        platform_admin = User.objects.create_user(username='notif-platform', role='PLATFORM_ADMIN')
        outsider = User.objects.create_user(username='notif-outsider', role='REQUESTER')

        services.notify_purchase_order_uploaded(self.request)
        self.assertTrue(Notification.objects.filter(user=superadmin).exists())
        self.assertTrue(Notification.objects.filter(user=platform_admin).exists())
        self.assertFalse(Notification.objects.filter(user=outsider).exists())

        Notification.objects.all().delete()
        services.notify_payment_received(self.request)
        self.assertTrue(Notification.objects.filter(user=self.analyst, notification_type='REPORT').exists())
        self.assertEqual(Notification.objects.filter(notification_type='PAYMENT').count(), 3)
        self.assertFalse(Notification.objects.filter(user=outsider).exists())

    def test_payment_request_uses_admin_price_precedence(self):
        from decimal import Decimal

        self.request.admin_validated_price = Decimal('3456')
        self.request.save(update_fields=['admin_validated_price'])
        services.notify_payment_request(self.request)
        notification = Notification.objects.get(user=self.requester)
        self.assertIn('3,456', notification.message)


class NotificationEmailTests(TestCase):
    def setUp(self):
        self.requester = User.objects.create_user(
            username='email-requester', role='REQUESTER',
            email='requester@example.test', first_name='Test', last_name='User',
        )
        self.request = Request.objects.create(
            display_id='EMAIL-001', title='Email contract', channel='IBTIKAR',
            requester=self.requester, report_token=uuid.uuid4(),
        )

    def test_low_level_sender_logs_success_and_failure_without_recipient_address(self):
        from notifications.emails import send_email_notification

        with patch('notifications.emails.send_mail', return_value=1) as send:
            with self.assertLogs('plagenor.email', level='INFO') as logs:
                send_email_notification('secret@example.test', 'Subject', '<b>Body</b>')
        self.assertEqual(send.call_args.kwargs['recipient_list'], ['secret@example.test'])
        self.assertNotIn('secret@example.test', ' '.join(logs.output))

        with patch('notifications.emails.send_mail', side_effect=OSError('SMTP down')):
            with self.assertLogs('plagenor.email', level='ERROR') as logs:
                send_email_notification(['a@example.test'], 'Subject', '<b>Body</b>')
        self.assertIn('SMTP down', ' '.join(logs.output))
        self.assertNotIn('a@example.test', ' '.join(logs.output))

    def test_all_request_email_helpers_render_and_dispatch(self):
        from notifications import emails

        with patch('notifications.emails.send_email_notification') as send:
            emails.notify_submission_confirmation(self.request)
            emails.notify_status_change(self.request, 'DRAFT', 'SUBMITTED')
            emails.notify_appointment(self.request)
            emails.notify_report_delivery(self.request)
        self.assertEqual(send.call_count, 4)
        self.assertTrue(all(call.args[0] == self.requester.email for call in send.call_args_list))
        self.assertIn(str(self.request.report_token), send.call_args_list[-1].args[2])

    def test_assignment_and_guest_tracking_delivery(self):
        from notifications import emails

        analyst = User.objects.create_user(
            username='email-analyst', role='MEMBER', email='analyst@example.test')
        profile = analyst.member_profile
        guest = Request.objects.create(
            display_id='EMAIL-GUEST', title='Guest', channel='GENOCLAB',
            submitted_as_guest=True, guest_email='guest@example.test',
            guest_name='Guest User', guest_token=uuid.uuid4(),
        )
        with patch('notifications.emails.send_email_notification') as send:
            emails.notify_assignment(self.request, profile)
            emails.notify_guest_tracking_code(guest)
        self.assertEqual(send.call_args_list[0].args[0], analyst.email)
        self.assertEqual(send.call_args_list[1].args[0], guest.guest_email)
        self.assertIn(str(guest.guest_token), send.call_args_list[1].args[2])

    def test_missing_recipient_is_a_noop(self):
        from notifications import emails

        orphan = Request.objects.create(
            display_id='EMAIL-NONE', title='No recipient', channel='IBTIKAR')
        with patch('notifications.emails.send_email_notification') as send:
            emails.notify_submission_confirmation(orphan)
            emails.notify_status_change(orphan, 'DRAFT', 'SUBMITTED')
            emails.notify_appointment(orphan)
            emails.notify_report_delivery(orphan)
            emails.notify_guest_tracking_code(orphan)
        send.assert_not_called()


class NotificationViewSecurityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='notif-view-user', password='x', role='CLIENT')
        self.other = User.objects.create_user(
            username='notif-view-other', password='x', role='CLIENT')
        self.request = Request.objects.create(
            display_id='NOTIF-VIEW', title='View contract', channel='GENOCLAB',
            requester=self.user,
        )
        self.client.force_login(self.user)

    def test_click_marks_owned_notification_read_and_allows_local_link(self):
        notification = Notification.objects.create(
            user=self.user, message='Open', link_url='/dashboard/client/')
        response = self.client.get(f'/notifications/{notification.pk}/click/')
        self.assertRedirects(response, '/dashboard/client/', fetch_redirect_response=False)
        notification.refresh_from_db()
        self.assertTrue(notification.read)

    def test_external_redirect_is_blocked_and_cross_user_access_is_hidden(self):
        notification = Notification.objects.create(
            user=self.user, message='Unsafe', link_url='https://evil.example/path')
        response = self.client.get(f'/notifications/{notification.pk}/click/')
        self.assertRedirects(response, '/dashboard/', fetch_redirect_response=False)
        foreign = Notification.objects.create(user=self.other, message='Private')
        self.assertEqual(self.client.get(f'/notifications/{foreign.pk}/click/').status_code, 404)

    def test_request_and_reward_destinations_are_role_aware(self):
        linked = Notification.objects.create(
            user=self.user, message='Request', request=self.request)
        response = self.client.get(f'/notifications/{linked.pk}/click/')
        self.assertIn(f'/dashboard/client/request/{self.request.pk}/', response['Location'])

        member = User.objects.create_user(username='reward-member', password='x', role='MEMBER')
        reward = Notification.objects.create(user=member, message='Points', notification_type='REWARD')
        self.client.force_login(member)
        response = self.client.get(f'/notifications/{reward.pk}/click/')
        self.assertEqual(response['Location'], '/dashboard/analyst/?tab=points')

    def test_mark_all_read_requires_post_for_mutation(self):
        Notification.objects.create(user=self.user, message='One')
        Notification.objects.create(user=self.user, message='Two')
        self.client.get('/notifications/mark-all-read/')
        self.assertEqual(Notification.objects.filter(user=self.user, read=False).count(), 2)
        self.client.post('/notifications/mark-all-read/')
        self.assertEqual(Notification.objects.filter(user=self.user, read=False).count(), 0)


class NotificationModelTests(TestCase):
    def test_visual_defaults_and_mark_as_read(self):
        user = User.objects.create_user(username='notif-model', role='FINANCE')
        notification = Notification.objects.create(
            user=user, message='A' * 60, notification_type='UNKNOWN')
        self.assertEqual(notification.icon, 'message-square')
        self.assertEqual(notification.accent, '#64748b')
        self.assertEqual(notification.get_absolute_url(), '/dashboard/')
        self.assertIn('A' * 50, str(notification))
        notification.mark_as_read()
        notification.refresh_from_db()
        self.assertTrue(notification.read)
        self.assertIsNotNone(notification.read_at)
