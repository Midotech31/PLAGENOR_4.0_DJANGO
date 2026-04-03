from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ALL_POSITION_CHOICES


class SoftDeleteUserManager(models.Manager):
    """Manager that excludes soft-deleted users by default."""
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        """Return all users including soft-deleted ones."""
        return super().get_queryset()
    
    def deleted_only(self):
        """Return only soft-deleted users."""
        return super().get_queryset().filter(is_deleted=True)


class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required')
        email = self.normalize_email(email) if email else ''
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'SUPER_ADMIN')
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    
    objects = SoftDeleteUserManager()
    all_objects = models.Manager()
    
    is_deleted = models.BooleanField(default=False, verbose_name=_('Soft deleted'))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Deleted at'))
    ROLE_CHOICES = [
        ('SUPER_ADMIN', 'Super Administrateur'),
        ('PLATFORM_ADMIN', 'Administrateur Plateforme'),
        ('MEMBER', 'Analyste / Opérateur'),
        ('FINANCE', 'Responsable Financier'),
        ('REQUESTER', 'Demandeur IBTIKAR'),
        ('CLIENT', 'Client GENOCLAB'),
    ]
    
    STUDENT_LEVEL_CHOICES = [
        ('phd_student', 'PhD Student / Doctorant'),
        ('phd_intern', 'PhD Intern / Stagiaire Doctorant'),
        ('master', "Master's Student / Étudiant en Master"),
        ('analyst', 'Analyst / Analyste'),
        ('intern', 'Intern / Stagiaire'),
        ('lecturer', 'Lecturer / Enseignant-Chercheur'),
        ('other', 'Other / Autre'),
    ]
    
    POSITION_CHOICES = [
        ('etudiant_doctorant', 'Étudiant/Doctorant'),
        ('chercheur', 'Chercheur'),
        ('mca', 'MCA'),
        ('mcb', 'MCB'),
        ('professeur', 'Professeur'),
        ('ingenieur', 'Ingénieur'),
        ('technicien', 'Technicien'),
        ('autre', 'Autre'),
    ]

    objects = UserManager()

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='REQUESTER')
    organization = models.CharField(max_length=200, default='', blank=True)
    phone = models.CharField(max_length=50, default='', blank=True)
    student_level = models.CharField(max_length=50, default='', blank=True, choices=STUDENT_LEVEL_CHOICES)
    student_level_other = models.CharField(max_length=200, default='', blank=True, verbose_name='Autre niveau (à préciser)')
    supervisor = models.CharField(max_length=200, default='', blank=True)
    laboratory = models.CharField(max_length=200, default='', blank=True, verbose_name=_('Laboratory'))
    position = models.CharField(
        max_length=50,
        choices=ALL_POSITION_CHOICES,
        default='',
        blank=True,
        verbose_name=_('Position / Fonction')
    )
    department = models.CharField(
        max_length=200, 
        default='', 
        blank=True,
        verbose_name=_('Department')
    )
    ibtikar_id = models.CharField(max_length=20, blank=True, default='', verbose_name='Identifiant IBTIKAR')

    # GENOCLAB-specific fields (for external clients)
    address = models.CharField(max_length=300, blank=True, default='', verbose_name=_('Adresse'))
    country = models.CharField(max_length=100, blank=True, default='', verbose_name=_('Pays'))

    # IBTIKAR-specific academic fields (Part K4)
    faculty = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Faculté / Faculty'),
        help_text=_('Faculty or department within the university')
    )
    research_team = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Équipe de recherche / Research Team'),
        help_text=_('Research team or laboratory unit')
    )

    # Login security
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Photo de profil')
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='Dernière activité')
    login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Password reset (Prompt 11)
    must_change_password = models.BooleanField(default=False, verbose_name='Doit changer le mot de passe')

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    @property
    def is_superadmin(self):
        return self.role == 'SUPER_ADMIN'

    @property
    def is_admin(self):
        return self.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN')

    @property
    def is_analyst(self):
        return self.role == 'MEMBER'

    @property
    def is_finance(self):
        return self.role == 'FINANCE'
    
    def soft_delete(self, deleted_by=None):
        """Mark this user as deleted."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save(update_fields=['is_deleted', 'deleted_at', 'is_active'])
    
    def restore(self):
        """Restore a soft-deleted user."""
        self.is_deleted = False
        self.deleted_at = None
        self.is_active = True
        self.save(update_fields=['is_deleted', 'deleted_at', 'is_active'])
    
    def hard_delete(self):
        """Permanently delete this user."""
        super().delete()


class Technique(models.Model):
    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=100, default='', blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'techniques'
        ordering = ['name']

    def __str__(self):
        return self.name


class MemberProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='member_profile')
    max_load = models.IntegerField(default=5)
    current_load = models.IntegerField(default=0)
    available = models.BooleanField(default=True)
    techniques = models.ManyToManyField(Technique, blank=True)
    productivity_score = models.FloatField(default=50.0)
    productivity_status = models.CharField(max_length=20, default='NORMAL')
    total_points = models.IntegerField(default=0)
    gift_unlocked = models.BooleanField(default=False)
    gift_image = models.ImageField(upload_to='gifts/', null=True, blank=True)
    gift_collected = models.BooleanField(default=False)
    
    # Milestone tracking (every 1000 points = 1 milestone) - determines level
    milestone_count = models.IntegerField(default=0)
    last_milestone_at = models.DateTimeField(null=True, blank=True)
    
    # Badge tier (changes at specific thresholds) - synced with BadgeConfig
    badge_level = models.IntegerField(default=1, help_text='Badge level from BadgeConfig (1=Bronze, 2=Silver, etc.)')
    
    # Reward cycle tracking
    milestone_level = models.IntegerField(
        default=1,
        help_text='Current reward cycle level (1=first 1000pts, 2=second 1000pts, etc.)'
    )
    milestone_history = models.JSONField(
        default=list,
        blank=True,
        help_text='History of milestones achieved with dates and rewards'
    )
    reward_points = models.IntegerField(
        default=0,
        help_text='Points accumulated in current reward cycle (resets at 1000)'
    )
    
    # Reward boxes tracking (every 2000 points = 1 reward box)
    # These are unlocked boxes that can be claimed
    unlocked_reward_boxes = models.IntegerField(
        default=0,
        help_text='Number of reward boxes unlocked (every 2000 points)'
    )
    collected_reward_boxes = models.IntegerField(
        default=0,
        help_text='Number of reward boxes that have been collected/opened'
    )
    reward_history = models.JSONField(
        default=list,
        blank=True,
        help_text='History of collected rewards with dates and descriptions'
    )

    class Meta:
        db_table = 'member_profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} — Profile"

    @property
    def load_percentage(self):
        if self.max_load <= 0:
            return 0
        return round(self.current_load / self.max_load * 100, 1)
    
    @property
    def points_to_next_milestone(self):
        """Returns points needed to reach the next 1000-point milestone."""
        return 1000 - (self.total_points % 1000)
    
    @property
    def progress_to_next_milestone(self):
        """Returns progress percentage to next milestone (0-100)."""
        return (self.total_points % 1000) / 10
    
    @property
    def current_cycle_points(self):
        """Points in current reward cycle (0-999)."""
        return self.total_points % 1000
    
    @property
    def reward_level_name(self):
        """Get the name of the current badge from BadgeConfig."""
        badge = BadgeConfig.get_badge_for_points(self.total_points)
        if badge:
            return badge.get_display_name('fr')
        return 'Newcomer'
    
    @property
    def badge_tier(self):
        """Get badge tier name from BadgeConfig."""
        return self.reward_level_name
    
    @property
    def next_level_name(self):
        """Get the name of the next badge level from BadgeConfig."""
        all_badges = BadgeConfig.get_all_badges()
        current_badge = self.get_current_badge()
        if current_badge:
            try:
                current_idx = all_badges.index(current_badge)
                if current_idx + 1 < len(all_badges):
                    return all_badges[current_idx + 1].get_display_name('fr')
            except ValueError:
                pass
        return f'Level {self.badge_level + 1}'
    
    @property
    def level_display(self):
        """Get display string for current level with cycle info."""
        return f"{self.reward_level_name} ({self.total_points} pts)"
    
    @property
    def available_reward_boxes(self):
        """Number of reward boxes available to collect (unlocked but not collected)."""
        return max(0, self.unlocked_reward_boxes - self.collected_reward_boxes)
    
    def _calculate_badge_level(self, total_points):
        """Calculate badge level based on total points using BadgeConfig.
        
        Single source of truth: queries BadgeConfig DB model to find
        the highest badge threshold ≤ total_points.
        
        Returns badge level number (1-10), or 0 for Newcomer (no badge).
        """
        badge = BadgeConfig.get_badge_for_points(total_points)
        if badge:
            return badge.level
        return 0  # Newcomer
    
    def get_current_badge(self):
        """Get the current BadgeConfig for this member's points total."""
        return BadgeConfig.get_badge_for_points(self.total_points)
    
    def _calculate_unlocked_boxes(self, total_points):
        """Calculate unlocked reward boxes (every 2000 points = 1 box)."""
        return total_points // 2000
    
    def award_points(self, points, reason, awarded_by=None, save=True):
        """Award points to the member and check for milestone unlock."""
        from django.utils import timezone
        from notifications.models import Notification
        
        prev_total = self.total_points
        prev_badge = self.badge_level
        prev_milestone = self.milestone_count
        prev_unlocked_boxes = self.unlocked_reward_boxes
        
        # Add to total
        self.total_points += points
        self.reward_points = self.total_points % 1000
        
        # Check for milestone (every 1000 points)
        new_milestone = self.total_points // 1000
        milestone_changed = False
        if new_milestone > self.milestone_count:
            self.milestone_count = new_milestone
            self.milestone_level = new_milestone
            self.last_milestone_at = timezone.now()
            milestone_changed = True
            
            # Add to milestone history
            history_entry = {
                'type': 'milestone',
                'level': self.milestone_level,
                'total_points': self.total_points,
                'achieved_at': timezone.now().isoformat(),
            }
            history = self.milestone_history or []
            history.append(history_entry)
            self.milestone_history = history[-20:]  # Keep last 20 entries
        
        # Check for badge change (1000, 2000, 3000, 4000, 5000 pts)
        new_badge = self._calculate_badge_level(self.total_points)
        badge_changed = new_badge > prev_badge
        if badge_changed:
            self.badge_level = new_badge
        
        # Check for new reward boxes (every 2000 points)
        new_unlocked_boxes = self._calculate_unlocked_boxes(self.total_points)
        reward_box_unlocked = new_unlocked_boxes > prev_unlocked_boxes
        if reward_box_unlocked:
            self.unlocked_reward_boxes = new_unlocked_boxes
        
        # Reset gift for new milestone
        if milestone_changed:
            self.gift_unlocked = True
            self.gift_collected = False
        
        # Build events list for return
        events = []
        
        # Milestone notification
        if milestone_changed:
            level_name = self.reward_level_name
            events.append({
                'type': 'milestone',
                'message': f"🎉 {self.user.get_full_name()} a atteint {self.total_points} points! Niveau {self.milestone_level} — {level_name}!",
                'title': f"Félicitations ! Niveau {self.milestone_level} atteint!",
                'points': self.total_points,
                'level': self.milestone_level,
            })
            Notification.objects.create(
                user=self.user,
                message=f"🎉 Félicitations ! Vous avez atteint {self.total_points} points! Niveau {self.milestone_level} — {level_name}!",
                notification_type='REWARD',
            )
        
        # Badge change notification
        if badge_changed:
            badge_emoji = {1: '🥉', 2: '🥈', 3: '🥇', 4: '💎', 5: '👑', 6: '⭐', 7: '🌟', 8: '✨', 9: '🏆', 10: '🔱'}
            current_badge_config = BadgeConfig.objects.filter(level=new_badge, is_active=True).first()
            prev_badge_config = BadgeConfig.objects.filter(level=prev_badge, is_active=True).first()
            old_badge = prev_badge_config.get_display_name('fr') if prev_badge_config else 'Newcomer'
            new_badge_name = current_badge_config.get_display_name('fr') if current_badge_config else 'Newcomer'
            events.append({
                'type': 'badge_change',
                'message': f"{badge_emoji.get(new_badge, '🎖️')} Badge {old_badge} → {new_badge_name}!",
                'title': f"Badge changé: {new_badge_name}!",
                'from_badge': old_badge,
                'to_badge': new_badge_name,
                'celebration': True,
            })
            Notification.objects.create(
                user=self.user,
                message=f"{badge_emoji.get(new_badge, '🎖️')} Nouveau badge: {new_badge_name}! Vous êtes passé de {old_badge} à {new_badge_name}!",
                notification_type='REWARD',
            )
        
        # Reward box unlocked notification
        if reward_box_unlocked:
            new_boxes_count = new_unlocked_boxes - prev_unlocked_boxes
            events.append({
                'type': 'reward_box',
                'message': f"🎁 {new_boxes_count} boîte(s) de récompense débloquée(s)!",
                'title': f"Récompense débloquée!",
                'boxes_unlocked': new_boxes_count,
                'total_boxes': new_unlocked_boxes,
                'celebration': True,
            })
            Notification.objects.create(
                user=self.user,
                message=f"🎁 Félicitations! Vous avez débloqué une nouvelle boîte de récompense! ({self.total_points} points)",
                notification_type='reward',
            )
        
        if save:
            self.save(update_fields=[
                'total_points', 'milestone_count', 'milestone_level',
                'last_milestone_at', 'gift_unlocked', 'gift_collected',
                'reward_points', 'milestone_history', 'badge_level',
                'unlocked_reward_boxes', 'collected_reward_boxes', 'reward_history'
            ])
        
        # Store events for return
        self._last_events = events
        self._badge_changed = badge_changed
        self._reward_box_unlocked = reward_box_unlocked
        self._milestone_changed = milestone_changed
        
        return self


class PointsHistory(models.Model):
    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name='points_history')
    points = models.IntegerField()
    reason = models.CharField(max_length=500)
    awarded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'points_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['member', 'reason', 'created_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'reason', 'points'],
                name='unique_points_history_entry',
                violation_error_message='Duplicate points entry: This award has already been recorded.'
            ),
        ]
    
    def save(self, *args, **kwargs):
        if self.pk is None:
            if PointsHistory.objects.filter(
                member=self.member,
                reason=self.reason,
                points=self.points,
            ).exists():
                raise ValueError(f"Duplicate PointsHistory entry: {self.member} already has points '{self.reason}'")
        super().save(*args, **kwargs)


class Cheer(models.Model):
    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name='cheers')
    message = models.TextField()
    from_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cheers'
        ordering = ['-created_at']


class BadgeConfig(models.Model):
    """DB-configurable badge levels for the rewards system.
    
    Single source of truth for badge definitions. Allows Superadmin
    to customize badge names, thresholds, colors, and icons without
    code changes.
    """
    level = models.PositiveSmallIntegerField(unique=True, help_text=_('Badge level (1-10)'))
    name = models.CharField(max_length=100, help_text=_('Badge name'))
    name_fr = models.CharField(max_length=100, blank=True, help_text=_('Badge name in French'))
    name_en = models.CharField(max_length=100, blank=True, help_text=_('Badge name in English'))
    points_threshold = models.PositiveIntegerField(help_text=_('Minimum points to achieve this badge'))
    color_hex = models.CharField(max_length=7, default='#6b7280', help_text=_('Primary color (hex)'))
    secondary_color_hex = models.CharField(max_length=7, blank=True, help_text=_('Secondary color (hex)'))
    icon_svg = models.TextField(blank=True, help_text=_('SVG icon path data'))
    description = models.TextField(blank=True, help_text=_('Badge description'))
    is_active = models.BooleanField(default=True, help_text=_('Whether this badge is active'))
    display_order = models.PositiveSmallIntegerField(default=0, help_text=_('Display order in gallery'))
    
    class Meta:
        db_table = 'badge_config'
        ordering = ['points_threshold']
        verbose_name = _('Badge Configuration')
        verbose_name_plural = _('Badge Configurations')
    
    def __str__(self):
        return f"Level {self.level}: {self.name} ({self.points_threshold} pts)"
    
    def get_display_name(self, language='fr'):
        """Get localized name."""
        if language == 'en' and self.name_en:
            return self.name_en
        if self.name_fr:
            return self.name_fr
        return self.name
    
    @classmethod
    def get_badge_for_points(cls, total_points):
        """Get the highest badge achievable for given points total.
        
        Returns the BadgeConfig with the highest points_threshold
        that is less than or equal to total_points.
        """
        badge = cls.objects.filter(
            is_active=True,
            points_threshold__lte=total_points
        ).order_by('-points_threshold').first()
        
        if badge:
            return badge
        
        # No badge yet - return Newcomer
        return cls.objects.filter(is_active=True, points_threshold=0).first()
    
    @classmethod
    def get_all_badges(cls):
        """Get all active badges ordered by threshold."""
        return list(cls.objects.filter(is_active=True).order_by('points_threshold'))
    
    @classmethod
    def seed_default_badges(cls):
        """Seed the database with default 10 badge levels."""
        defaults = [
            (1, 'Bronze', 0, '#cd7f32', '#a0522d'),
            (2, 'Silver', 1000, '#c0c0c0', '#808080'),
            (3, 'Gold', 2000, '#ffd700', '#daa520'),
            (4, 'Platinum', 3000, '#8b5cf6', '#6d28d9'),
            (5, 'Diamond', 4000, '#3b82f6', '#1d4ed8'),
            (6, 'Master', 5000, '#ef4444', '#b91c1c'),
            (7, 'Grand Master', 6000, '#f59e0b', '#d97706'),
            (8, 'Elite', 7000, '#10b981', '#059669'),
            (9, 'Champion', 8000, '#ec4899', '#db2777'),
            (10, 'Legend', 9000, '#f97316', '#ea580c'),
        ]
        
        created = []
        for level, name, threshold, color, secondary in defaults:
            badge, created_flag = cls.objects.get_or_create(
                level=level,
                defaults={
                    'name': name,
                    'name_fr': name,
                    'name_en': name,
                    'points_threshold': threshold,
                    'color_hex': color,
                    'secondary_color_hex': secondary,
                    'display_order': level,
                    'is_active': True,
                }
            )
            created.append((badge, created_flag))
        
        return created
