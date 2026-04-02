from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import ALL_POSITION_CHOICES


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
    # Milestone tracking (every 1000 points = 1 milestone)
    milestone_count = models.IntegerField(default=0)
    last_milestone_at = models.DateTimeField(null=True, blank=True)
    # Reward cycle tracking (new fields for redesigned rewards system)
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
        """Get the name of the current reward level."""
        levels = {
            1: 'Bronze', 2: 'Silver', 3: 'Gold', 4: 'Platinum',
            5: 'Diamond', 6: 'Master', 7: 'Grand Master',
            8: 'Elite', 9: 'Champion', 10: 'Legend'
        }
        return levels.get(self.milestone_level, f'Level {self.milestone_level}')
    
    @property
    def next_level_name(self):
        """Get the name of the next reward level."""
        levels = {
            1: 'Bronze', 2: 'Silver', 3: 'Gold', 4: 'Platinum',
            5: 'Diamond', 6: 'Master', 7: 'Grand Master',
            8: 'Elite', 9: 'Champion', 10: 'Legend'
        }
        return levels.get(self.milestone_level + 1, f'Level {self.milestone_level + 1}')
    
    @property
    def level_display(self):
        """Get display string for current level with cycle info."""
        return f"Level {self.milestone_level} — {self.reward_level_name} ({self.total_points} pts)"
    
    @property
    def badge_tier(self):
        """Get badge tier name for the current level."""
        if self.milestone_level <= 1:
            return 'Bronze'
        elif self.milestone_level <= 3:
            return 'Silver'
        elif self.milestone_level <= 5:
            return 'Gold'
        elif self.milestone_level <= 7:
            return 'Platinum'
        else:
            return 'Diamond'
    
    def award_points(self, points, reason, awarded_by=None, save=True):
        """Award points to the member and check for milestone unlock."""
        from django.utils import timezone
        from notifications.models import Notification
        
        # Track previous milestone
        prev_milestone = self.milestone_count
        
        # Add to total
        self.total_points += points
        self.reward_points = self.total_points % 1000
        
        # Check for milestone (every 1000 points)
        new_milestone = self.total_points // 1000
        if new_milestone > self.milestone_count:
            old_level = self.milestone_level
            self.milestone_count = new_milestone
            self.milestone_level = new_milestone
            self.last_milestone_at = timezone.now()
            self.gift_unlocked = True
            self.gift_collected = False
            self.reward_points = 0
            
            # Add to milestone history
            history_entry = {
                'level': self.milestone_level,
                'total_points': self.total_points,
                'achieved_at': timezone.now().isoformat(),
                'previous_level': old_level,
            }
            history = self.milestone_history or []
            history.append(history_entry)
            self.milestone_history = history[-10:]  # Keep last 10 entries
            
            # Create notification for the milestone
            level_name = self.reward_level_name
            Notification.objects.create(
                user=self.user,
                message=f"🎉 Félicitations ! Vous avez atteint le niveau {self.milestone_level} — {level_name} ! ({self.total_points} points)",
                notification_type='POINTS',
            )
        
        if save:
            self.save(update_fields=[
                'total_points', 'milestone_count', 'milestone_level',
                'last_milestone_at', 'gift_unlocked', 'gift_collected',
                'reward_points', 'milestone_history'
            ])
        
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


class Cheer(models.Model):
    member = models.ForeignKey(MemberProfile, on_delete=models.CASCADE, related_name='cheers')
    message = models.TextField()
    from_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cheers'
        ordering = ['-created_at']
