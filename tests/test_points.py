"""Tests for accounts/models.py - Points and Rewards System."""
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model

from accounts.models import MemberProfile, PointsHistory, BadgeConfig

User = get_user_model()


class TestBadgeConfigModel(TestCase):
    """Test BadgeConfig model and badge level calculation."""
    
    def setUp(self):
        """Seed default badges."""
        BadgeConfig.seed_default_badges()
    
    def test_seed_creates_10_badges(self):
        """Test that seed creates exactly 10 badges."""
        badges = BadgeConfig.objects.all()
        self.assertEqual(badges.count(), 10)
    
    def test_badge_levels_are_sequential(self):
        """Test badge levels go from 1 to 10."""
        badges = BadgeConfig.objects.order_by('level')
        levels = [b.level for b in badges]
        self.assertEqual(levels, list(range(1, 11)))
    
    def test_get_badge_for_points_newcomer(self):
        """Test newcomer (0 points) gets Bronze badge."""
        badge = BadgeConfig.get_badge_for_points(0)
        self.assertEqual(badge.level, 1)
        self.assertEqual(badge.name, 'Bronze')
    
    def test_get_badge_for_points_bronze_range(self):
        """Test points 0-999 get Bronze."""
        for pts in [0, 100, 500, 999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 1, f"Points {pts} should be Bronze")
    
    def test_get_badge_for_points_silver_range(self):
        """Test points 1000-1999 get Silver."""
        for pts in [1000, 1500, 1999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 2, f"Points {pts} should be Silver")
    
    def test_get_badge_for_points_gold_range(self):
        """Test points 2000-2999 get Gold."""
        for pts in [2000, 2500, 2999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 3, f"Points {pts} should be Gold")
    
    def test_get_badge_for_points_platinum_range(self):
        """Test points 3000-3999 get Platinum."""
        for pts in [3000, 3500, 3999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 4, f"Points {pts} should be Platinum")
    
    def test_get_badge_for_points_diamond_range(self):
        """Test points 4000-4999 get Diamond."""
        for pts in [4000, 4500, 4999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 5, f"Points {pts} should be Diamond")
    
    def test_get_badge_for_points_master_range(self):
        """Test points 5000-5999 get Master."""
        for pts in [5000, 5500, 5999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 6, f"Points {pts} should be Master")
    
    def test_get_badge_for_points_grandmaster_range(self):
        """Test points 6000-6999 get Grand Master."""
        for pts in [6000, 6500, 6999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 7, f"Points {pts} should be Grand Master")
    
    def test_get_badge_for_points_elite_range(self):
        """Test points 7000-7999 get Elite."""
        for pts in [7000, 7500, 7999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 8, f"Points {pts} should be Elite")
    
    def test_get_badge_for_points_champion_range(self):
        """Test points 8000-8999 get Champion."""
        for pts in [8000, 8500, 8999]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 9, f"Points {pts} should be Champion")
    
    def test_get_badge_for_points_legend_range(self):
        """Test points 9000+ get Legend."""
        for pts in [9000, 10000, 15000]:
            badge = BadgeConfig.get_badge_for_points(pts)
            self.assertEqual(badge.level, 10, f"Points {pts} should be Legend")


class TestMemberProfileAwardPoints(TestCase):
    """Test MemberProfile.award_points method."""
    
    def setUp(self):
        """Set up test user and profile."""
        BadgeConfig.seed_default_badges()
        self.user = User.objects.create_user(
            username='testmember1',
            email='test1@example.com',
            password='testpass123'
        )
        self.profile = MemberProfile.objects.create(
            user=self.user,
            total_points=0
        )
    
    def test_award_points_basic_increment(self):
        """Test basic point increment."""
        self.profile.award_points(100, reason='Test award')
        self.assertEqual(self.profile.total_points, 100)
    
    def test_award_points_cumulative(self):
        """Test cumulative point awards."""
        self.profile.award_points(100, reason='First award')
        self.profile.award_points(50, reason='Second award')
        self.assertEqual(self.profile.total_points, 150)
    
    def test_milestone_at_1000_points(self):
        """Test milestone triggers at 1000 points."""
        self.profile.total_points = 900
        self.profile.milestone_count = 0
        self.profile.save()
        
        self.profile.award_points(100, reason='Crossing milestone')
        
        self.assertEqual(self.profile.milestone_count, 1)
        self.assertEqual(self.profile.milestone_level, 1)
    
    def test_badge_level_at_1000_points(self):
        """Test badge level changes at 1000 points."""
        self.profile.total_points = 900
        self.profile.badge_level = 1
        self.profile.save()
        
        self.profile.award_points(100, reason='Upgrading to Silver')
        
        self.assertEqual(self.profile.badge_level, 2)
    
    def test_badge_level_calculation_all_thresholds(self):
        """Test badge level calculation at all thresholds."""
        test_cases = [
            (0, 1),     # 0 pts = Bronze (level 1)
            (999, 1),   # 999 pts = Bronze
            (1000, 2),  # 1000 pts = Silver
            (1999, 2),  # 1999 pts = Silver
            (2000, 3),  # 2000 pts = Gold
            (2999, 3),  # 2999 pts = Gold
            (3000, 4),  # 3000 pts = Platinum
            (3999, 4),  # 3999 pts = Platinum
            (4000, 5),  # 4000 pts = Diamond
            (4999, 5),  # 4999 pts = Diamond
            (5000, 6),  # 5000 pts = Master
            (5999, 6),  # 5999 pts = Master
            (6000, 7),  # 6000 pts = Grand Master
            (6999, 7),  # 6999 pts = Grand Master
            (7000, 8),  # 7000 pts = Elite
            (7999, 8),  # 7999 pts = Elite
            (8000, 9),  # 8000 pts = Champion
            (8999, 9),  # 8999 pts = Champion
            (9000, 10), # 9000 pts = Legend
            (9999, 10), # 9999 pts = Legend
        ]
        
        for points, expected_level in test_cases:
            with self.subTest(points=points):
                badge_level = self.profile._calculate_badge_level(points)
                self.assertEqual(
                    badge_level, expected_level,
                    f"Points {points} should give level {expected_level}, got {badge_level}"
                )
    
    def test_reward_boxes_unlocked_at_2000_points(self):
        """Test reward box unlocked at 2000 points."""
        self.profile.total_points = 1900
        self.profile.unlocked_reward_boxes = 0
        self.profile.save()
        
        self.profile.award_points(100, reason='Reaching 2000')
        
        self.assertEqual(self.profile.unlocked_reward_boxes, 1)
    
    def test_calculate_unlocked_boxes(self):
        """Test reward box unlock calculation."""
        test_cases = [
            (0, 0),
            (999, 0),
            (1000, 0),
            (1999, 0),
            (2000, 1),
            (3999, 1),
            (4000, 2),
            (6000, 3),
            (10000, 5),
        ]
        
        for points, expected_boxes in test_cases:
            with self.subTest(points=points):
                boxes = self.profile._calculate_unlocked_boxes(points)
                self.assertEqual(
                    boxes, expected_boxes,
                    f"Points {points} should give {expected_boxes} boxes"
                )


class TestMemberProfileRewardBoxes(TestCase):
    """Test reward box calculations."""
    
    def setUp(self):
        """Set up test profile."""
        BadgeConfig.seed_default_badges()
        self.user = User.objects.create_user(
            username='testmember2',
            email='test2@example.com',
            password='testpass123'
        )
        self.profile = MemberProfile.objects.create(
            user=self.user,
            total_points=0,
            unlocked_reward_boxes=0,
            collected_reward_boxes=0
        )
    
    def test_available_reward_boxes_calculation(self):
        """Test available boxes = unlocked - collected."""
        self.profile.unlocked_reward_boxes = 5
        self.profile.collected_reward_boxes = 2
        
        self.assertEqual(self.profile.available_reward_boxes, 3)
    
    def test_available_reward_boxes_never_negative(self):
        """Test available boxes never goes negative."""
        self.profile.unlocked_reward_boxes = 0
        self.profile.collected_reward_boxes = 5
        
        self.assertEqual(self.profile.available_reward_boxes, 0)


class TestMemberProfileProperties(TestCase):
    """Test MemberProfile computed properties."""
    
    def setUp(self):
        """Set up test profile."""
        BadgeConfig.seed_default_badges()
        self.user = User.objects.create_user(
            username='testmember3',
            email='test3@example.com',
            password='testpass123'
        )
        self.profile = MemberProfile.objects.create(
            user=self.user,
            total_points=0
        )
    
    def test_points_to_next_milestone(self):
        """Test points to next milestone calculation."""
        self.profile.total_points = 350
        self.assertEqual(self.profile.points_to_next_milestone, 650)
    
    def test_progress_to_next_milestone(self):
        """Test progress percentage calculation."""
        self.profile.total_points = 350
        self.assertEqual(self.profile.progress_to_next_milestone, 35.0)
    
    def test_current_cycle_points(self):
        """Test current cycle points (0-999)."""
        self.profile.total_points = 1250
        self.assertEqual(self.profile.current_cycle_points, 250)
    
    def test_reward_level_name(self):
        """Test reward level name based on badge level."""
        self.profile.total_points = 2500  # Gold range (2000-2999)
        self.assertEqual(self.profile.reward_level_name, 'Gold')
    
    def test_get_current_badge(self):
        """Test getting current badge from points."""
        self.profile.total_points = 2500
        badge = self.profile.get_current_badge()
        
        self.assertEqual(badge.level, 3)
        self.assertEqual(badge.name, 'Gold')


class TestExtendedBadgeNotifications(TestCase):
    """Test badge notifications for all 10 levels."""
    
    def setUp(self):
        """Set up test user and profile."""
        BadgeConfig.seed_default_badges()
        self.user = User.objects.create_user(
            username='badge_test_user',
            email='badge_test@example.com',
            password='testpass123'
        )
        self.profile = MemberProfile.objects.create(
            user=self.user,
            total_points=0,
            badge_level=1
        )
    
    def test_badge_notification_legend_level(self):
        """Test badge notification for Legend (level 10)."""
        self.profile.total_points = 8900
        self.profile.badge_level = 9
        self.profile.save()
        
        self.profile.award_points(200, reason='Reaching Legend')
        
        self.assertEqual(self.profile.badge_level, 10)
        # Events: [milestone, badge_change, reward_box] - badge_change at index 1
        self.assertEqual(self.profile._last_events[1]['to_badge'], 'Legend')
    
    def test_badge_notification_master_level(self):
        """Test badge notification for Master (level 6)."""
        self.profile.total_points = 4900
        self.profile.badge_level = 5
        self.profile.save()
        
        self.profile.award_points(200, reason='Reaching Master')
        
        self.assertEqual(self.profile.badge_level, 6)
        # Events: [milestone, badge_change, reward_box] - badge_change at index 1
        self.assertEqual(self.profile._last_events[1]['to_badge'], 'Master')
    
    def test_badge_notification_champion_level(self):
        """Test badge notification for Champion (level 9)."""
        self.profile.total_points = 7900
        self.profile.badge_level = 8
        self.profile.save()
        
        self.profile.award_points(200, reason='Reaching Champion')
        
        self.assertEqual(self.profile.badge_level, 9)
        # Events: [milestone, badge_change, reward_box] - badge_change at index 1
        self.assertEqual(self.profile._last_events[1]['to_badge'], 'Champion')
    
    def test_badge_notification_creates_notification(self):
        """Test that badge change creates a notification."""
        from notifications.models import Notification
        
        self.profile.total_points = 900
        self.profile.badge_level = 1
        self.profile.save()
        
        initial_count = Notification.objects.filter(user=self.user).count()
        
        self.profile.award_points(100, reason='Crossing Silver')
        
        final_count = Notification.objects.filter(user=self.user).count()
        self.assertGreater(final_count, initial_count)
