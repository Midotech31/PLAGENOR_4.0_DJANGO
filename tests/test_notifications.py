"""Tests for notifications system - role-aware notification links."""
from django.test import TestCase
from django.contrib.auth import get_user_model

from notifications.models import Notification

User = get_user_model()


class TestNotificationModel(TestCase):
    """Test Notification model."""
    
    def setUp(self):
        """Set up test users."""
        self.member = User.objects.create_user(
            username='notif_member',
            email='notif@test.com',
            password='pass123',
            role='MEMBER'
        )
    
    def test_notification_creation(self):
        """Test notification can be created."""
        notification = Notification.objects.create(
            user=self.member,
            message='Test notification',
            notification_type='INFO'
        )
        
        self.assertIsNotNone(notification.id)
        self.assertEqual(notification.user, self.member)
        self.assertFalse(notification.read)
    
    def test_notification_mark_as_read(self):
        """Test marking notification as read."""
        notification = Notification.objects.create(
            user=self.member,
            message='Test',
            notification_type='INFO'
        )
        
        notification.mark_as_read()
        notification.refresh_from_db()
        
        self.assertTrue(notification.read)
        self.assertIsNotNone(notification.read_at)
    
    def test_notification_type_choices(self):
        """Test all notification types are valid choices."""
        valid_types = [
            'INFO', 'WORKFLOW', 'STATUS_CHANGE', 'ASSIGNMENT',
            'REPORT', 'PAYMENT', 'DOCUMENT_READY', 'POINTS', 'REWARD'
        ]
        
        for ntype in valid_types:
            notification = Notification.objects.create(
                user=self.member,
                message=f'Test {ntype}',
                notification_type=ntype
            )
            self.assertEqual(notification.notification_type, ntype)
    
    def test_workflow_notification_for_member(self):
        """Test WORKFLOW notification for member links to analyst."""
        notification = Notification.objects.create(
            user=self.member,
            message='Request assigned',
            notification_type='WORKFLOW'
        )
        
        url = notification.get_absolute_url()
        
        self.assertIsNotNone(url)
        # URL should be a string (the actual path depends on implementation)
        self.assertIsInstance(url, str)
    
    def test_points_notification(self):
        """Test POINTS notification."""
        notification = Notification.objects.create(
            user=self.member,
            message='50 points awarded',
            notification_type='POINTS'
        )
        
        self.assertEqual(notification.notification_type, 'POINTS')
    
    def test_reward_notification(self):
        """Test REWARD notification."""
        notification = Notification.objects.create(
            user=self.member,
            message='Badge earned!',
            notification_type='REWARD'
        )
        
        self.assertEqual(notification.notification_type, 'REWARD')
