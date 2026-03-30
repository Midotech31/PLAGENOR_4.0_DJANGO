from django.db import models
from django.conf import settings
import uuid


class Service(models.Model):
    CHANNEL_CHOICES = [
        ('BOTH', 'IBTIKAR & GENOCLAB'),
        ('IBTIKAR', 'IBTIKAR uniquement'),
        ('GENOCLAB', 'GENOCLAB uniquement'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)
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

    class Meta:
        db_table = 'services'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class ServiceFormField(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='custom_fields')
    name = models.CharField(max_length=100)
    label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=[
        ('string', 'Texte'), ('enum', 'Liste'), ('boolean', 'Oui/Non'), ('number', 'Nombre'),
    ], default='string')
    options = models.JSONField(default=list, blank=True, help_text='Options for enum type')
    required = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    class Meta:
        db_table = 'service_form_fields'
        ordering = ['sort_order', 'pk']

    def __str__(self):
        return f"{self.service.code} — {self.label}"


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

    # Citation acknowledgment (Prompt 10)
    citation_acknowledged = models.BooleanField(default=False, verbose_name='Citation acknowledgée')

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

    # Metadata
    ibtikar_external_code = models.CharField(max_length=50, default='', blank=True, verbose_name='Code demande IBTIKAR-DGRSDT')
    rejection_reason = models.TextField(default='', blank=True)
    archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
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
