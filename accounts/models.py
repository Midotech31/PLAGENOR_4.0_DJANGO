from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

from .countries import COUNTRY_CHOICES


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

    GENDER_CHOICES = [
        ('M', 'Homme'),
        ('F', 'Femme'),
    ]

    # Organisation type — GENOCLAB (commercial) clients are mostly companies
    # and private labs, not just academics. "Autre" reveals a free-text box.
    ORGANIZATION_TYPE_CHOICES = [
        ('academique', 'Académique'),
        ('entreprise', 'Entreprise'),
        ('laboratoire', 'Laboratoire'),
        ('particulier', 'Particulier'),
        ('autre', 'Autre'),
    ]

    # Algerian wilayas — official 2021 list (58 entries: 48 historic + 10
    # new southern wilayas created by the 2019/2021 reform). Stored as the
    # numeric code (01-58) so the label can be translated independently.
    WILAYA_CHOICES = [
        ('01', 'Adrar'), ('02', 'Chlef'), ('03', 'Laghouat'),
        ('04', "Oum El Bouaghi"), ('05', 'Batna'), ('06', 'Béjaïa'),
        ('07', 'Biskra'), ('08', 'Béchar'), ('09', 'Blida'),
        ('10', 'Bouira'), ('11', 'Tamanrasset'), ('12', 'Tébessa'),
        ('13', 'Tlemcen'), ('14', 'Tiaret'), ('15', 'Tizi Ouzou'),
        ('16', 'Alger'), ('17', 'Djelfa'), ('18', 'Jijel'),
        ('19', 'Sétif'), ('20', 'Saïda'), ('21', 'Skikda'),
        ('22', 'Sidi Bel Abbès'), ('23', 'Annaba'), ('24', 'Guelma'),
        ('25', 'Constantine'), ('26', 'Médéa'), ('27', 'Mostaganem'),
        ('28', "M'Sila"), ('29', 'Mascara'), ('30', 'Ouargla'),
        ('31', 'Oran'), ('32', 'El Bayadh'), ('33', 'Illizi'),
        ('34', 'Bordj Bou Arréridj'), ('35', 'Boumerdès'),
        ('36', 'El Tarf'), ('37', 'Tindouf'), ('38', 'Tissemsilt'),
        ('39', 'El Oued'), ('40', 'Khenchela'), ('41', 'Souk Ahras'),
        ('42', 'Tipaza'), ('43', 'Mila'), ('44', 'Aïn Defla'),
        ('45', 'Naâma'), ('46', 'Aïn Témouchent'), ('47', 'Ghardaïa'),
        ('48', 'Relizane'), ('49', 'Timimoun'),
        ('50', 'Bordj Badji Mokhtar'), ('51', 'Ouled Djellal'),
        ('52', 'Béni Abbès'), ('53', 'In Salah'), ('54', 'In Guezzam'),
        ('55', 'Touggourt'), ('56', 'Djanet'), ('57', "El M'Ghair"),
        ('58', 'El Meniaa'),
    ]

    objects = UserManager()

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='REQUESTER')
    organization = models.CharField(max_length=200, default='', blank=True)
    organization_type = models.CharField(
        max_length=20, choices=ORGANIZATION_TYPE_CHOICES, blank=True, default='',
        verbose_name="Type d'organisation",
    )
    organization_type_other = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name="Préciser le type d'organisation",
    )
    country = models.CharField(
        max_length=2, choices=COUNTRY_CHOICES, blank=True, default='DZ',
        verbose_name='Pays',
    )
    phone = models.CharField(max_length=50, default='', blank=True)
    student_level = models.CharField(max_length=100, default='', blank=True)
    supervisor = models.CharField(max_length=200, default='', blank=True)
    laboratory = models.CharField(max_length=200, default='', blank=True)
    ibtikar_id = models.CharField(max_length=20, blank=True, default='', verbose_name='Identifiant IBTIKAR')
    # Demographics used by the stats dashboard. Both optional.
    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, blank=True, default='',
        verbose_name='Sexe',
    )
    wilaya = models.CharField(
        max_length=2, choices=WILAYA_CHOICES, blank=True, default='',
        verbose_name='Wilaya',
    )

    # Login security
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Photo de profil')
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='Dernière activité')
    login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # Password reset (Prompt 11)
    must_change_password = models.BooleanField(default=False, verbose_name='Doit changer le mot de passe')

    # Localization preference (Phase 3.0).
    # Empty string ('') means: defer to cookie / Accept-Language. When set,
    # PreferredLanguageMiddleware (Phase 3.3) will override the active language
    # for this user. Storing the field in 3.0 lets the SuperAdmin / profile
    # editor populate it ahead of middleware roll-out.
    LANGUAGE_PREFERENCE_CHOICES = [
        ('', 'Suivre la configuration du navigateur'),
        ('fr', 'Français'),
        ('en', 'English'),
        ('ar', 'العربية'),
    ]
    preferred_language = models.CharField(
        max_length=5, blank=True, default='',
        choices=LANGUAGE_PREFERENCE_CHOICES,
        verbose_name='Langue préférée',
        help_text='Laisser vide pour utiliser la langue du navigateur.',
    )

    # Optional TOTP two-factor auth (opt-in, mainly for staff). When
    # ``totp_enabled`` is True the login flow demands a 6-digit code after the
    # password. A Super Admin can reset both fields if a device is lost.
    totp_secret = models.CharField(max_length=512, blank=True, default='')
    totp_enabled = models.BooleanField(default=False, verbose_name='2FA activé')

    # IBTIKAR running balance, self-declared by the requester.
    #
    # NULL = the requester has NOT yet declared their residual balance for
    # this year — the requester dashboard must surface a declaration prompt
    # before any new request can be submitted. A non-null value (incl. 0) is
    # the working balance used to size estimates and as the cap-check. After
    # a request reaches COMPLETED, the resolved cost is deducted here. The
    # requester can revise this number at any time to mirror what their
    # actual DGRSDT IBTIKAR account shows (the IBTIKAR budget can be spent
    # on platforms outside PLAGENOR too).
    ibtikar_declared_balance = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name='Solde IBTIKAR déclaré (DA)',
    )
    ibtikar_balance_declared_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name='Dernière mise à jour du solde IBTIKAR',
    )

    class Meta:
        db_table = 'users'
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(ibtikar_declared_balance__isnull=True)
                           | models.Q(ibtikar_declared_balance__gte=0)),
                name='user_ibtikar_balance_nonnegative',
            ),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"

    def set_totp_secret(self, secret):
        from .totp import encrypt_secret
        self.totp_secret = encrypt_secret(secret)

    def get_totp_secret(self):
        from .totp import decrypt_secret
        return decrypt_secret(self.totp_secret)

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
