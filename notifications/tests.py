"""Tests for notification service helpers."""
from django.test import TestCase

from accounts.models import User
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
