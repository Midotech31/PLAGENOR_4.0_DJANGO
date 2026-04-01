from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import uuid


class Service(models.Model):
    CHANNEL_CHOICES = [
        ('BOTH', 'IBTIKAR & GENOCLAB'),
        ('IBTIKAR', 'IBTIKAR uniquement'),
        ('GENOCLAB', 'GENOCLAB uniquement'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, help_text='Short code (e.g., EGTP-Seq02)')
    name = models.CharField(max_length=200)
    description = models.TextField(default='', blank=True)
    channel_availability = models.CharField(max_length=10, choices=CHANNEL_CHOICES, default='BOTH')
    service_type = models.CharField(max_length=50, default='Analysis')
    ibtikar_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    genoclab_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    turnaround_days = models.IntegerField(default=7)
    image = models.ImageField(upload_to='service_images/', null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # New IBTIKAR-specific fields
    service_code = models.CharField(
        max_length=50, 
        unique=True, 
        null=True, 
        blank=True,
        help_text='Official service code (e.g., EGTP-Seq02) — mirrors code field for IBTIKAR forms'
    )
    form_version = models.CharField(
        max_length=20, 
        default='V 01',
        help_text='Form version number (e.g., V 01)'
    )
    ibtikar_instructions = models.TextField(
        blank=True,
        help_text="'Tres important' warning block text in French"
    )
    ibtikar_instructions_en = models.TextField(
        blank=True,
        help_text="'Very important' warning block text in English"
    )
    checklist_items = models.JSONField(
        default=list, 
        blank=True,
        help_text='PLAGENOR validation checklist items as JSON list of strings'
    )
    deliverables = models.TextField(
        blank=True,
        help_text='Expected deliverables description'
    )
    processing_steps = models.TextField(
        blank=True,
        help_text='Processing/analysis workflow steps'
    )
    analysis_workflow = models.TextField(
        blank=True,
        help_text='Analysis workflow description'
    )

    class Meta:
        db_table = 'services'
        ordering = ['code']
        verbose_name = 'Service'
        verbose_name_plural = 'Services'

    def __str__(self):
        return f"{self.code} — {self.name}"
    
    def get_service_code(self):
        """Get the official service code, falling back to code."""
        return self.service_code or self.code


class ServiceFormField(models.Model):
    """
    Dynamic form fields for service-specific forms.
    
    These fields are used to:
    1. Define sample table columns (field_category='sample_table')
    2. Define additional information fields (field_category='additional_info')
    """
    
    CATEGORY_CHOICES = [
        ('sample_table', 'Sample Table Column'),
        ('additional_info', 'Additional Info Field'),
    ]
    
    WIDGET_CHOICES = [
        ('text', 'Text Input'),
        ('dropdown', 'Dropdown Select'),
        ('checkbox', 'Checkbox'),
        ('textarea', 'Textarea'),
        ('string', 'Texte'),
        ('enum', 'Liste'),
        ('boolean', 'Oui/Non'),
        ('number', 'Nombre'),
    ]
    
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='form_fields')
    field_category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES,
        default='sample_table',
        help_text='Whether this field is a sample table column or additional info field'
    )
    name = models.CharField(max_length=100, help_text='Field identifier for data storage')
    label = models.CharField(max_length=200, help_text='Display label (bilingual in FR/EN)')
    label_fr = models.CharField(max_length=255, blank=True, help_text='Label in French')
    label_en = models.CharField(max_length=255, blank=True, help_text='Label in English')
    field_type = models.CharField(
        max_length=20, 
        choices=WIDGET_CHOICES,
        default='text',
        help_text='Widget type for form rendering'
    )
    options = models.JSONField(default=list, blank=True, help_text='Options for dropdown/checkbox as JSON list')
    choices_json = models.JSONField(
        blank=True, 
        null=True, 
        help_text='Options for dropdown/checkbox as JSON list (alternative to options field)'
    )
    is_required = models.BooleanField(default=False, help_text='Whether this field is required')
    required = models.BooleanField(default=False)  # Keep for backward compatibility
    sort_order = models.IntegerField(default=0, help_text='Display order')
    order = models.PositiveIntegerField(
        default=0, 
        help_text='Order within the field category'
    )
    
    class Meta:
        db_table = 'service_form_fields'
        ordering = ['field_category', 'order', 'sort_order', 'pk']
        verbose_name = 'Champ de formulaire'
        verbose_name_plural = 'Champs de formulaire'

    def __str__(self):
        return f"{self.service.code} — {self.label}"
    
    def get_label(self, lang='fr'):
        """Get the appropriate label based on language."""
        if lang == 'en' and self.label_en:
            return self.label_en
        if self.label_fr:
            return self.label_fr
        return self.label
    
    def get_choices(self):
        """Get the list of choices for dropdown/checkbox fields."""
        if self.choices_json:
            return self.choices_json
        return self.options or []


class ServicePricing(models.Model):
    """Dynamic pricing configuration for services - allows Super Admin to set detailed pricing."""
    
    PRICING_TYPE_CHOICES = [
        ('BASE', 'Prix de base'),
        ('PER_SAMPLE', 'Par échantillon'),
        ('PER_PARAMETER', 'Par paramètre'),
        ('URGENCY_SURCHARGE', 'Majoration urgence'),
        ('DISCOUNT', 'Remise'),
    ]
    
    CHANNEL_CHOICES = [
        ('IBTIKAR', 'IBTIKAR'),
        ('GENOCLAB', 'GENOCLAB'),
        ('BOTH', 'Les deux'),
    ]
    
    service = models.ForeignKey(
        Service, 
        on_delete=models.CASCADE, 
        related_name='pricing_configs'
    )
    pricing_type = models.CharField(
        max_length=20,
        choices=PRICING_TYPE_CHOICES,
        default='BASE'
    )
    channel = models.CharField(
        max_length=10,
        choices=CHANNEL_CHOICES,
        default='BOTH'
    )
    name = models.CharField(max_length=200, verbose_name='Nom du tarif')
    description = models.TextField(default='', blank=True, verbose_name='Description')
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0,
        verbose_name='Montant (DZD)'
    )
    unit = models.CharField(
        max_length=50, 
        default='固定',
        blank=True,
        verbose_name='Unité (ex: par échantillon)'
    )
    min_quantity = models.IntegerField(default=1, verbose_name='Quantité minimum')
    max_quantity = models.IntegerField(null=True, blank=True, verbose_name='Quantité maximum')
    min_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name='Montant minimum'
    )
    max_amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name='Montant maximum'
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    priority = models.IntegerField(default=0, verbose_name='Priorité')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pricing_updates'
    )
    
    class Meta:
        db_table = 'service_pricing'
        ordering = ['service', 'priority', 'pk']
        verbose_name = 'Configuration tarifaire'
        verbose_name_plural = 'Configurations tarifaires'
    
    def __str__(self):
        return f"{self.service.code} - {self.name}: {self.amount} DZD"


class Request(models.Model):
    CHANNEL_CHOICES = [
        ('IBTIKAR', 'IBTIKAR'),
        ('GENOCLAB', 'GENOCLAB'),
    ]

    URGENCY_CHOICES = [
        ('Normal', 'Normal'),
        ('Urgent', 'Urgent'),
        ('Très urgent', 'Très urgent'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Brouillon'),
        ('SUBMITTED', 'Soumis'),
        ('VALIDATION_PEDAGOGIQUE', 'Validation Pédagogique'),
        ('VALIDATION_FINANCE', 'Validation Finance'),
        ('PLATFORM_NOTE_GENERATED', 'Note Générée'),
        ('IBTIKAR_SUBMISSION_PENDING', 'En attente soumission IBTIKAR'),
        ('IBTIKAR_CODE_SUBMITTED', 'Code IBTIKAR soumis'),
        ('ASSIGNED', 'Assigné'),
        ('PENDING_ACCEPTANCE', 'En Attente Acceptation'),
        ('APPOINTMENT_PROPOSED', 'RDV Proposé'),
        ('APPOINTMENT_CONFIRMED', 'RDV Confirmé'),
        ('SAMPLE_RECEIVED', 'Échantillon Reçu'),
        ('ANALYSIS_STARTED', 'Analyse Démarrée'),
        ('ANALYSIS_FINISHED', 'Analyse Terminée'),
        ('REPORT_UPLOADED', 'Rapport Uploadé'),
        ('ADMIN_REVIEW', 'Révision Admin'),
        ('REPORT_VALIDATED', 'Rapport Validé'),
        ('SENT_TO_REQUESTER', 'Transmis Demandeur'),
        ('COMPLETED', 'Complété'),
        ('CLOSED', 'Clôturé'),
        ('REJECTED', 'Rejeté'),
        # GENOCLAB-specific
        ('REQUEST_CREATED', 'Demande Créée'),
        ('QUOTE_DRAFT', 'Devis En Cours'),
        ('QUOTE_SENT', 'Devis Envoyé'),
        ('QUOTE_VALIDATED_BY_CLIENT', 'Devis Accepté'),
        ('QUOTE_REJECTED_BY_CLIENT', 'Devis Refusé'),
        ('ORDER_UPLOADED', 'Bon de Commande Uploadé'),
        ('PAYMENT_PENDING', 'En Attente Paiement'),
        ('PAYMENT_CONFIRMED', 'Paiement Confirmé'),
        ('SENT_TO_CLIENT', 'Transmis Client'),
        ('ARCHIVED', 'Archivé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=300)
    description = models.TextField(default='', blank=True)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='SUBMITTED')
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='Normal')

    # Relationships
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests_made')
    assigned_to = models.ForeignKey('accounts.MemberProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_requests')

    # Financial
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    declared_ibtikar_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quote_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quote_detail = models.JSONField(default=dict, blank=True, verbose_name='Détail du devis')
    admin_validated_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    # GENOCLAB: Purchase Order (Bon de commande - mandatory per Algerian commercial code)
    order_file = models.FileField(upload_to='orders/', null=True, blank=True, verbose_name='Bon de commande')
    order_uploaded_at = models.DateTimeField(null=True, blank=True)
    
    # GENOCLAB: Payment receipt
    payment_receipt_file = models.FileField(upload_to='payments/', null=True, blank=True, verbose_name='Reçu de paiement')
    payment_uploaded_at = models.DateTimeField(null=True, blank=True)

    # Appointment
    appointment_date = models.DateField(null=True, blank=True)
    appointment_proposed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    appointment_confirmed = models.BooleanField(default=False)
    appointment_confirmed_at = models.DateTimeField(null=True, blank=True)
    alt_date_proposed = models.DateField(null=True, blank=True, verbose_name='Date alternative proposée')
    alt_date_note = models.TextField(default='', blank=True, verbose_name='Note date alternative')

    # Assignment acceptance
    assignment_accepted = models.BooleanField(default=False)
    assignment_accepted_at = models.DateTimeField(null=True, blank=True)
    assignment_declined = models.BooleanField(default=False)
    assignment_decline_reason = models.TextField(default='', blank=True)

    # Report
    report_file = models.FileField(upload_to='reports/', null=True, blank=True)
    report_token = models.UUIDField(null=True, blank=True, unique=True)
    report_delivered = models.BooleanField(default=False)
    report_delivered_at = models.DateTimeField(null=True, blank=True)
    admin_revision_notes = models.TextField(default='', blank=True)

    # Rating
    service_rating = models.IntegerField(null=True, blank=True)
    rating_comment = models.TextField(default='', blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)
    receipt_confirmed = models.BooleanField(default=False)
    receipt_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Citation acknowledgment (Prompt 10) - for download acceptance
    citation_accepted = models.BooleanField(default=False, verbose_name='Citation accepted')
    citation_accepted_at = models.DateTimeField(null=True, blank=True, verbose_name='Citation accepted at')

    # IBTIKAR Form Generation
    generated_ibtikar_form = models.FileField(
        upload_to='ibtikar_generated/',
        null=True,
        blank=True,
        verbose_name=_('Generated IBTIKAR Form')
    )

    # Platform Note (IBTIKAR) - Programmatic PDF generation
    generated_platform_note = models.FileField(
        upload_to='platform_notes/',
        null=True,
        blank=True,
        verbose_name=_('Generated Platform Note')
    )

    # Sample Reception Form - Programmatic PDF generation
    generated_reception_form = models.FileField(
        upload_to='sample_reception_forms/',
        null=True,
        blank=True,
        verbose_name=_('Generated Reception Form')
    )

    # Guest
    submitted_as_guest = models.BooleanField(default=False)
    guest_token = models.UUIDField(null=True, blank=True, unique=True)
    guest_name = models.CharField(max_length=200, default='', blank=True)
    guest_email = models.EmailField(default='', blank=True)
    guest_phone = models.CharField(max_length=50, default='', blank=True)

    # JSON fields (for flexible data)
    service_params = models.JSONField(default=dict, blank=True)
    pricing = models.JSONField(default=dict, blank=True)
    sample_table = models.JSONField(default=list, blank=True)
    requester_data = models.JSONField(default=dict, blank=True)
    
    # Additional data from dynamic service-specific fields (ServiceFormField)
    additional_data = models.JSONField(default=dict, blank=True, 
                                        verbose_name=_('Additional Data'))
    
    # Research Director (PI) information for IBTIKAR
    pi_name = models.CharField(
        max_length=200, 
        default='', 
        blank=True,
        verbose_name=_('Research Director Name')
    )
    pi_email = models.EmailField(
        default='', 
        blank=True,
        verbose_name=_('Research Director Email')
    )
    pi_phone = models.CharField(
        max_length=50, 
        default='', 
        blank=True,
        verbose_name=_('Research Director Phone')
    )
    
    # Analysis framework (required for IBTIKAR)
    analysis_framework = models.CharField(
        max_length=50, 
        choices=[
            ('memoire_fin_cycle', _('Mémoire de fin de cycle')),
            ('these_doctorat', _('Thèse de doctorat')),
            ('projet_recherche', _('Projet de recherche')),
            ('habilitation', _('Habilitation universitaire')),
            ('autre', _('Autre')),
        ],
        blank=True,
        verbose_name=_('Analysis Framework')
    )

    # Metadata
    ibtikar_external_code = models.CharField(max_length=50, default='', blank=True, verbose_name='Code demande IBTIKAR-DGRSDT')
    rejection_reason = models.TextField(default='', blank=True)
    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    
    # Client archive visibility (True = hidden from requester's archive list)
    hidden_from_archive = models.BooleanField(default=False, verbose_name=_('Hidden from archive'))
    
    # GENOCLAB Invoice fields
    generated_invoice = models.FileField(
        upload_to='invoices/generated/',
        null=True,
        blank=True,
        verbose_name=_('Generated Invoice (Excel)')
    )
    signed_invoice = models.FileField(
        upload_to='invoices/signed/',
        null=True,
        blank=True,
        verbose_name=_('Signed Invoice')
    )
    invoice_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Invoice Sent At')
    )
    invoice_downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Invoice Downloaded At')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'requests'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['channel', 'status']),
            models.Index(fields=['channel', 'archived']),
            models.Index(fields=['status']),
            models.Index(fields=['requester']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['guest_token']),
            models.Index(fields=['report_token']),
        ]

    def __str__(self):
        return f"{self.display_id} — {self.title}"


class RequestHistory(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='history')
    from_status = models.CharField(max_length=30, default='', blank=True)
    to_status = models.CharField(max_length=30)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(default='', blank=True)
    forced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'request_history'
        ordering = ['-created_at']


class RequestComment(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    step = models.CharField(max_length=30, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'request_comments'
        ordering = ['created_at']


class ReportVersion(models.Model):
    """
    Stores archived versions of reports for each request.
    Allows members to upload new versions even after request completion.
    """
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='report_versions')
    file = models.FileField(upload_to='reports/versions/')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    version_number = models.PositiveIntegerField(default=1)
    notes = models.TextField(default='', blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'report_versions'
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.request.display_id} - v{self.version_number}"


class Invoice(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'En attente'),
        ('PARTIAL', 'Partiel'),
        ('COMPLETED', 'Payé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=50, unique=True)
    request = models.ForeignKey(Request, on_delete=models.SET_NULL, null=True, blank=True)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    line_items = models.JSONField(default=list)
    subtotal_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_rate = models.DecimalField(max_digits=4, decimal_places=2, default=0.19)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    locked = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')

    class Meta:
        db_table = 'invoices'
        ordering = ['-created_at']

    def __str__(self):
        return self.invoice_number


class PlatformContent(models.Model):
    key = models.CharField(max_length=100, primary_key=True)
    value = models.TextField(default='')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'platform_content'


class PaymentMethod(models.Model):
    name = models.CharField(max_length=100, unique=True)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'payment_methods'

    def __str__(self):
        return self.name


class Message(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name='messages')
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages_sent')
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages_received')
    text = models.TextField()
    read = models.BooleanField(default=False)
    step = models.CharField(max_length=30, default='', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['request', 'created_at']),
        ]

    def __str__(self):
        return f"Message {self.from_user} -> {self.to_user} ({self.request.display_id})"


class RevenueArchive(models.Model):
    month = models.IntegerField()
    year = models.IntegerField()
    channel = models.CharField(max_length=10)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    request_count = models.IntegerField(default=0)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_archives'
        ordering = ['-year', '-month']
        unique_together = ['month', 'year', 'channel']

    def __str__(self):
        return f"{self.channel} {self.month}/{self.year} — {self.total_revenue} DA"


class PaymentSettings(models.Model):
    """
    Singleton model for payment configuration settings.
    These settings are used to auto-fill invoices and payment instructions.
    """
    bank_account = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name=_('Bank Account Number'),
        help_text=_('Account number for bank transfers')
    )
    beneficiary_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Beneficiary Name'),
        help_text=_('Name of the account holder')
    )
    bank_name = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name=_('Bank Name'),
        help_text=_('Name of the bank')
    )
    payment_instructions = models.TextField(
        blank=True,
        default='',
        verbose_name=_('Payment Instructions'),
        help_text=_('Additional instructions for making payment (free text)')
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_settings_updates'
    )

    class Meta:
        db_table = 'payment_settings'
        verbose_name = _('Payment Settings')
        verbose_name_plural = _('Payment Settings')

    def __str__(self):
        return _('Payment Settings')

    def save(self, *args, **kwargs):
        # Ensure only one instance exists (singleton pattern)
        if not self.pk and PaymentSettings.objects.exists():
            # Update existing instance instead of creating new one
            existing = PaymentSettings.objects.first()
            self.pk = existing.pk
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        """Get or create payment settings singleton."""
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings
