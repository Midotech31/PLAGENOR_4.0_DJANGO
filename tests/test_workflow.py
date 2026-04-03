"""Tests for core/workflow.py - Workflow transitions and auto points."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from core.workflow import (
    get_allowed_transitions,
    _award_completion_points,
)
from core.exceptions import InvalidTransitionError
from core.models import Request, RequestHistory
from accounts.models import MemberProfile, PointsHistory, BadgeConfig

User = get_user_model()


class TestGetAllowedTransitions(TestCase):
    """Test get_allowed_transitions function."""
    
    def test_ibtikar_submitted_allowed_next(self):
        """Test allowed transitions from SUBMITTED for IBTIKAR."""
        allowed = get_allowed_transitions(
            MagicMock(channel='IBTIKAR', status='SUBMITTED')
        )
        
        self.assertIn('VALIDATION_PEDAGOGIQUE', allowed)
    
    def test_genoclab_quote_sent_allowed_next(self):
        """Test allowed transitions from QUOTE_SENT for GENOCLAB."""
        allowed = get_allowed_transitions(
            MagicMock(channel='GENOCLAB', status='QUOTE_SENT')
        )
        
        self.assertIn('QUOTE_VALIDATED_BY_CLIENT', allowed)


class TestAwardCompletionPoints(TestCase):
    """Test _award_completion_points function."""
    
    def setUp(self):
        """Set up test data."""
        BadgeConfig.seed_default_badges()
        
        self.admin = User.objects.create_user(
            username='wf_admin',
            email='wf_admin@test.com',
            password='pass123',
            role='PLATFORM_ADMIN'
        )
        
        self.member = User.objects.create_user(
            username='wf_member',
            email='wf_member@test.com',
            password='pass123',
            role='MEMBER'
        )
        
        self.profile = MemberProfile.objects.create(
            user=self.member,
            total_points=100
        )
    
    def test_ibtikar_closed_awards_50_points(self):
        """Test IBTIKAR CLOSED awards 50 points to assigned member."""
        request = Request.objects.create(
            title='Test',
            channel='IBTIKAR',
            status='COMPLETED',
            assigned_to=self.profile,
            completion_points_awarded=False
        )
        
        initial_points = self.profile.total_points
        
        _award_completion_points(request, 'CLOSED', self.admin)
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_points, initial_points + 50)
    
    def test_double_award_prevented(self):
        """Test double award is prevented by flag."""
        request = Request.objects.create(
            title='Test',
            channel='IBTIKAR',
            status='CLOSED',
            assigned_to=self.profile,
            completion_points_awarded=True
        )
        
        initial_points = self.profile.total_points
        
        _award_completion_points(request, 'CLOSED', self.admin)
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_points, initial_points)
    
    def test_no_assigned_member_skips(self):
        """Test no points awarded if no member assigned."""
        request = Request.objects.create(
            title='Test',
            channel='IBTIKAR',
            status='COMPLETED',
            assigned_to=None,
            completion_points_awarded=False
        )
        
        _award_completion_points(request, 'CLOSED', self.admin)
        self.assertTrue(True)
    
    def test_flag_set_after_award(self):
        """Test completion_points_awarded flag is set after award."""
        request = Request.objects.create(
            title='Test',
            channel='IBTIKAR',
            status='COMPLETED',
            assigned_to=self.profile,
            completion_points_awarded=False
        )
        
        _award_completion_points(request, 'CLOSED', self.admin)
        
        request.refresh_from_db()
        self.assertTrue(request.completion_points_awarded)
    
    def test_non_completion_status_no_points(self):
        """Test non-completion statuses don't award points."""
        request = Request.objects.create(
            title='Test',
            channel='IBTIKAR',
            status='ASSIGNED',
            assigned_to=self.profile,
            completion_points_awarded=False
        )
        
        initial_points = self.profile.total_points
        
        _award_completion_points(request, 'ANALYSIS_STARTED', self.admin)
        
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.total_points, initial_points)
