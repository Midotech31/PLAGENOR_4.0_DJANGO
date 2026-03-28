from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


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

    objects = UserManager()

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='REQUESTER')
    organization = models.CharField(max_length=200, default='', blank=True)
    phone = models.CharField(max_length=50, default='', blank=True)
    student_level = models.CharField(max_length=100, default='', blank=True)
    supervisor = models.CharField(max_length=200, default='', blank=True)
    laboratory = models.CharField(max_length=200, default='', blank=True)
    ibtikar_id = models.CharField(max_length=20, blank=True, default='', verbose_name='Identifiant IBTIKAR')

    # Login security
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Photo de profil')
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='Dernière activité')
    login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

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

    class Meta:
        db_table = 'member_profiles'

    def __str__(self):
        return f"{self.user.get_full_name()} — Profile"

    @property
    def load_percentage(self):
        if self.max_load <= 0:
            return 0
        return round(self.current_load / self.max_load * 100, 1)


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
