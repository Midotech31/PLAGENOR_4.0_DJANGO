from django.db import models
from django.conf import settings
"""
Core domain models for PLAGENOR 4.0.

Workflow map (high-level):
- Service + ServiceFormField define channel-aware analysis catalog and dynamic intake forms.
- Request stores IBTIKAR/GENOCLAB lifecycle state, pricing snapshot, sample data, documents, and traceability IDs.
- Quote/Invoice/PaymentSettings/GenoclabSettings support GENOCLAB commercial workflow.
- PDFFormField and Homepage* models power configurable document sections and CMS homepage blocks.
"""

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid


class SoftDeleteManager(models.Manager):
    """Manager that excludes soft-deleted objects by default."""
    
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)
    
    def all_with_deleted(self):
        """Return all objects including soft-deleted ones."""
        return super().get_queryset()
    
    def deleted_only(self):
        """Return only soft-deleted objects."""
        return super().get_queryset().filter(is_deleted=True)


class SoftDeleteModel(models.Model):
    """Mixin for soft delete functionality."""
    
    is_deleted = models.BooleanField(default=False, verbose_name=_('Soft deleted'))
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Deleted at'))
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name=_('Deleted by')
    )
    
    objects = SoftDeleteManager()
    all_objects = models.Manager()
    
    class Meta:
        abstract = True
    
    def soft_delete(self, deleted_by=None):
        """Mark this object as deleted."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])
    
    def restore(self):
        """Restore a soft-deleted object."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by'])
    
    def hard_delete(self):
        """Permanently delete this object."""
        super().delete()


class Service(SoftDeleteModel):
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

    # Turnaround time per channel (Part M)
    turnaround_days = models.IntegerField(default=7, help_text='Deprecated: use turnaround_ibtikar and turnaround_genoclab')
    turnaround_ibtikar = models.IntegerField(
        default=7,
        verbose_name='Délai IBTIKAR (jours)',
        help_text='Turnaround time in business days for IBTIKAR channel'
    )
    turnaround_genoclab = models.IntegerField(
        default=7,
        verbose_name='Délai GENOCLAB (jours)',
        help_text='Turnaround time in business days for GENOCLAB channel'
    )
    turnaround_unit = models.CharField(
        max_length=20,
        default='business_days',
        verbose_name='Unité de délai',
        choices=[
            ('business_days', 'Jours ouvrables / Business days'),
            ('calendar_days', 'Jours calendaires / Calendar days'),
            ('weeks', 'Semaines / Weeks'),
        ]
    )

    # Citation clause (Part K3) - Superadmin editable
    citation_clause_fr = models.TextField(
        blank=True,
        default='',
        verbose_name='Clause de citation (FR)',
        help_text='Texte de citation obligatoire pour les demandes IBTIKAR (Français)'
    )
    citation_clause_en = models.TextField(
        blank=True,
        default='',
        verbose_name='Citation clause (EN)',
        help_text='Mandatory citation text for IBTIKAR requests (English)'
    )

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
        ('parameter', 'Service Parameter'),
        ('sample_table', 'Sample Table Column'),
        ('additional_info', 'Additional Info Field'),
    ]
    
    WIDGET_CHOICES = [
        ('text', 'Text'),
        ('textarea', 'Textarea'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Select'),
        ('multiselect', 'Multi-select'),
        ('boolean', 'Yes/No'),
        ('checkbox', 'Checkbox'),
        ('string', 'Text (legacy)'),
        ('enum', 'Enum (legacy)'),
        ('dropdown', 'Dropdown (legacy)'),
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
    help_text_fr = models.CharField(max_length=500, blank=True, help_text='Help text in French')
    help_text_en = models.CharField(max_length=500, blank=True, help_text='Help text in English')
    channel = models.CharField(
        max_length=10,
        choices=[
            ('IBTIKAR', 'IBTIKAR'),
            ('GENOCLAB', 'GENOCLAB'),
            ('BOTH', 'IBTIKAR & GENOCLAB'),
        ],
        default='BOTH',
        help_text='Channel availability: IBTIKAR only, GENOCLAB only, or BOTH'
    )
    
    # Variable pricing fields
    affects_pricing = models.BooleanField(
        default=False,
        help_text='Whether selecting this option affects the price'
    )
    price_modifier_type = models.CharField(
        max_length=20,
        choices=[
            ('add', 'Surcharge / Supplément'),
            ('set', 'Override / Forfait'),
            ('multiply', 'Multiplier'),
        ],
        blank=True,
        default='',
        help_text='How this option modifies the price'
    )
    price_modifier_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Value of the price modifier (amount, new price, or multiplier)'
    )
    price_modifier_scope = models.CharField(
        max_length=20,
        choices=[
            ('per_sample', 'Per Sample / Par échantillon'),
            ('total', 'Total / Montant total'),
        ],
        blank=True,
        default='total',
        help_text='Apply modifier per sample (added before count/multiplier) or to final total'
    )
    condition_note_fr = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='French notice shown to user about additional charges'
    )
    condition_note_en = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='English notice shown to user about additional charges'
    )

    # Conditional Logic - Field visibility/requirement based on other field values
    conditional_logic = models.JSONField(
        default=list,
        blank=True,
        help_text='Conditional rules: [{"trigger_field": "field_name", "trigger_value": "value", "actions": ["show", "make_required"]}]'
    )

    # Option-level pricing for multi-choice fields
    option_pricing = models.JSONField(
        default=dict,
        blank=True,
        help_text='Per-option pricing: {"option_value": 500, "other_option": 1000} - for multi-select fields'
    )
    
    # Maximum selections for multi-select fields (security constraint)
    max_selections = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Maximum number of selections allowed for multi-select fields (security constraint)'
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
    
    def get_choices_list(self):
        """Get choices as a plain list (for API serialization)."""
        return self.get_choices() or []
    
    def get_help_text(self, lang='fr'):
        """Get help text in the requested language."""
        if lang == 'en' and self.help_text_en:
            return self.help_text_en
        return self.help_text_fr or ''


class PDFFormField(models.Model):
    PDF_TARGETS = [
        ('ibtikar_form', 'Formulaire IBTIKAR'),
        ('platform_note', 'Note de Plateforme'),
        ('reception_form', 'Formulaire de Réception'),
    ]
    SCOPE_TYPES = [
        ('global', 'Tous les services'),
        ('service', 'Service spécifique'),
    ]
    FIELD_KINDS = [
        ('text_line', 'Ligne de texte'),
        ('text_block', 'Bloc de texte'),
        ('checkbox', 'Case à cocher'),
        ('signature', 'Zone de signature'),
        ('separator', 'Séparateur / ligne'),
        ('section_title', 'Titre de section'),
        ('table_row', 'Ligne de tableau'),
        ('image', 'Image / Logo'),
    ]

    pdf_target = models.CharField(max_length=20, choices=PDF_TARGETS)
    scope_type = models.CharField(max_length=10, choices=SCOPE_TYPES, default='global')
    service = models.ForeignKey(
        'Service',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='pdf_fields',
    )

    name = models.CharField(max_length=100)
    label_fr = models.CharField(max_length=255)
    label_en = models.CharField(max_length=255, blank=True)
    field_kind = models.CharField(max_length=20, choices=FIELD_KINDS)
    default_value = models.TextField(blank=True)
    options = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['pdf_target', 'order', 'pk']
        unique_together = ['pdf_target', 'scope_type', 'service', 'name']
        verbose_name = 'Champ PDF'
        verbose_name_plural = 'Champs PDF'

    def __str__(self):
        scope = self.service.code if self.service else 'GLOBAL'
        return f"{self.get_pdf_target_display()} — {scope} — {self.name}"

    def clean(self):
        if self.scope_type == 'service' and not self.service:
            raise ValidationError("Un service est requis quand scope_type='service'")
        if self.scope_type == 'global' and self.service:
            raise ValidationError("Pas de service quand scope_type='global'")


class ServicePricing(models.Model):
    """Dynamic pricing configuration for services - allows Super Admin to set detailed pricing."""
    
    PRICING_TYPE_CHOICES = [
        ('BASE', 'Prix de base'),
        ('PER_SAMPLE', 'Par échantillon'),
        ('PER_PARAMETER', 'Par paramètre'),
        ('URGENCY_SURCHARGE', 'Majoration urgence'),
        ('DISCOUNT', 'Remise'),
        ('OVERRIDE', 'Forfait (override total)'),
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
        verbose_name='Montant (DZD)',
        help_text='Prix en DZD. Les modifications s\'appliquent aux nouvelles demandes uniquement. Les demandes en cours conservent leur prix validé.'
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


class GenoclabSettings(models.Model):
    """Global settings for GENOCLAB channel - editable by superadmin.
    
    Stores company information, logo, payment details, and contact information
    that appears on official quotes and invoices.
    """
    
    # Company Info
    company_name = models.CharField(max_length=200, default='GENOCLAB', verbose_name='Nom de la société')
    company_subtitle = models.CharField(max_length=200, default='Plateforme d\'Analyses Génomiques', verbose_name='Sous-titre')
    
    # Logo
    logo = models.ImageField(upload_to='genoclab/logo/', null=True, blank=True, verbose_name='Logo GENOCLAB')
    
    # Contact Information
    address_line1 = models.CharField(max_length=200, default='', blank=True, verbose_name='Adresse ligne 1')
    address_line2 = models.CharField(max_length=200, default='', blank=True, verbose_name='Adresse ligne 2')
    phone = models.CharField(max_length=50, default='', blank=True, verbose_name='Téléphone')
    email = models.EmailField(default='', blank=True, verbose_name='Email')
    website = models.URLField(default='', blank=True, verbose_name='Site web')
    
    # Payment Information
    bank_name = models.CharField(max_length=200, default='', blank=True, verbose_name='Nom de la banque')
    account_number = models.CharField(max_length=100, default='', blank=True, verbose_name='Numéro de compte')
    rib = models.CharField(max_length=50, default='', blank=True, verbose_name='RIB')
    swift_code = models.CharField(max_length=50, default='', blank=True, verbose_name='Code SWIFT')
    
    # Legal Information
    rc_number = models.CharField(max_length=50, default='', blank=True, verbose_name='Numéro RC')
    nif = models.CharField(max_length=50, default='', blank=True, verbose_name='NIF')
    ai = models.CharField(max_length=50, default='', blank=True, verbose_name='AI')
    
    # Quote/Invoice Settings
    quote_validity_days = models.IntegerField(default=30, verbose_name='Validité du devis (jours)')
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19, verbose_name='Taux de TVA (%)')
    
    # Footer Text
    quote_footer_text = models.TextField(
        default='Ce devis est établi sous réserve de disponibilité. '
               'Les conditions de paiement sont mentionnées ci-dessus.',
        blank=True,
        verbose_name='Texte de pied de page du devis'
    )
    
    # Singleton pattern - ensure only one record exists
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='genoclab_settings_updates'
    )
    
    class Meta:
        verbose_name = 'Paramètres GENOCLAB'
        verbose_name_plural = 'Paramètres GENOCLAB'
        db_table = 'genoclab_settings'
    
    def __str__(self):
        return f"Paramètres GENOCLAB - {self.company_name}"
    
    @classmethod
    def get_settings(cls):
        """Get the active settings (singleton pattern)."""
        settings_obj = cls.objects.filter(is_active=True).first()
        if not settings_obj:
            # Create default settings if none exist
            settings_obj = cls.objects.create()
        return settings_obj


class ServiceFieldTemplate(models.Model):
    """Template for service form fields - allows Super Admin to save and reuse field configurations."""
    
    name = models.CharField(
        max_length=200,
        verbose_name='Nom du modèle',
        help_text='Ex: "Champs échantillons standard", "Champs analyse PCR"'
    )
    description = models.TextField(
        default='',
        blank=True,
        verbose_name='Description',
        help_text='Description optionnelle du modèle'
    )
    fields = models.JSONField(
        default=list,
        verbose_name='Configuration des champs',
        help_text='JSON containing field definitions'
    )
    applicable_services = models.JSONField(
        default=list,
        verbose_name='Services applicables',
        help_text='List of service codes this template can be applied to (empty = all)'
    )
    source_service = models.ForeignKey(
        'Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='field_templates',
        verbose_name='Service source',
        help_text='Service used as source for this template'
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    is_default_for_new = models.BooleanField(
        default=False,
        verbose_name='Par défaut pour nouveaux services',
        help_text='Use as default template when creating new services'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_templates'
    )
    
    class Meta:
        db_table = 'service_field_templates'
        ordering = ['-is_default_for_new', 'name']
        verbose_name = 'Modèle de champs'
        verbose_name_plural = 'Modèles de champs'
    
    def __str__(self):
        return self.name
    
    @classmethod
    def create_from_service(cls, service, name=None, description=''):
        """Create a template from an existing service's field configuration."""
        if name is None:
            name = f"Template: {service.name}"
        
        fields_data = []
        for field in service.form_fields.all():
            fields_data.append({
                'field_category': field.field_category,
                'name': field.name,
                'label': field.label,
                'label_fr': field.label_fr,
                'label_en': field.label_en,
                'field_type': field.field_type,
                'options': field.options or [],
                'choices_json': field.choices_json or [],
                'order': field.order,
                'sort_order': field.sort_order,
                'required': field.required,
                'help_text_fr': field.help_text_fr or '',
                'help_text_en': field.help_text_en or '',
                'conditional_logic': field.conditional_logic or [],
                'affects_pricing': field.affects_pricing,
                'price_modifier_type': field.price_modifier_type,
                'price_modifier_value': str(field.price_modifier_value) if field.price_modifier_value else None,
                'option_pricing': field.option_pricing or {},
                'condition_note_fr': field.condition_note_fr,
                'condition_note_en': field.condition_note_en,
                'max_selections': field.max_selections,
                'channel': field.channel,
            })
        
        return cls.objects.create(
            name=name,
            description=description,
            fields=fields_data,
            applicable_services=[service.code],
            source_service=service,
        )
    
    def apply_to_service(self, service):
        """Apply this template's fields to a service."""
        from django.db import transaction
        from .models import ServiceFormField
        
        with transaction.atomic():
            service.form_fields.all().delete()
            
            for field_data in self.fields:
                if not field_data.get('name'):
                    continue
                
                price_mod_value = None
                if field_data.get('price_modifier_value'):
                    try:
                        price_mod_value = float(field_data['price_modifier_value'])
                    except (ValueError, TypeError):
                        pass
                
                ServiceFormField.objects.create(
                    service=service,
                    field_category=field_data.get('field_category', 'sample_table'),
                    name=field_data['name'],
                    label=field_data.get('label', field_data['name']),
                    label_fr=field_data.get('label_fr', field_data.get('label', field_data['name'])),
                    label_en=field_data.get('label_en', field_data.get('label', field_data['name'])),
                    field_type=field_data.get('field_type', 'text'),
                    options=field_data.get('options', []),
                    choices_json=field_data.get('choices_json', field_data.get('options', [])),
                    order=field_data.get('order', 0),
                    sort_order=field_data.get('sort_order', 0),
                    required=field_data.get('required', False),
                    help_text_fr=field_data.get('help_text_fr', ''),
                    help_text_en=field_data.get('help_text_en', ''),
                    conditional_logic=field_data.get('conditional_logic', []),
                    affects_pricing=field_data.get('affects_pricing', False),
                    price_modifier_type=field_data.get('price_modifier_type', ''),
                    price_modifier_value=price_mod_value,
                    option_pricing=field_data.get('option_pricing', {}),
                    condition_note_fr=field_data.get('condition_note_fr', ''),
                    condition_note_en=field_data.get('condition_note_en', ''),
                    max_selections=field_data.get('max_selections'),
                    channel=field_data.get('channel', 'BOTH'),
                )


class Quote(models.Model):
    """Official quote for GENOCLAB requests - tracks quote history and versions."""
    
    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('sent', 'Envoyé'),
        ('accepted', 'Accepté'),
        ('rejected', 'Refusé'),
        ('expired', 'Expiré'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey('Request', on_delete=models.CASCADE, related_name='quotes')
    
    # Quote Data
    items = models.JSONField(default=list, verbose_name='Lignes du devis')
    subtotal_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    admin_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    report_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal_before_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Discount/Adjustment
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Remise')
    discount_reason = models.TextField(default='', blank=True, verbose_name='Raison de la remise')
    
    # Notes
    notes = models.TextField(default='', blank=True, verbose_name='Notes')
    terms = models.TextField(default='', blank=True, verbose_name='Conditions')
    
    # Status and Dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name='Date d\'expiration')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Date d\'envoi')
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name='Date de réponse')
    
    # Version tracking
    version = models.IntegerField(default=1, verbose_name='Version')
    is_current = models.BooleanField(default=True, verbose_name='Version actuelle')
    
    # Creator
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='quotes_created'
    )
    
    class Meta:
        verbose_name = 'Devis'
        verbose_name_plural = 'Devis'
        db_table = 'quotes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Devis {self.request.display_id} v{self.version} - {self.get_status_display()}"
    
    def save(self, *args, **kwargs):
        # Calculate expiration date if not set
        if not self.expires_at and self.status == 'sent':
            from datetime import timedelta
            validity_days = GenoclabSettings.get_settings().quote_validity_days
            self.expires_at = timezone.now() + timedelta(days=validity_days)
        super().save(*args, **kwargs)
    
    @property
    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at
    
    def to_dict(self):
        """Convert quote to dictionary for template rendering."""
        return {
            'id': str(self.id),
            'items': self.items,
            'subtotal_ht': float(self.subtotal_ht),
            'admin_fees': float(self.admin_fees),
            'report_fees': float(self.report_fees),
            'subtotal_before_tax': float(self.subtotal_before_tax),
            'vat_rate': float(self.vat_rate),
            'vat_amount': float(self.vat_amount),
            'total_ttc': float(self.total_ttc),
            'discount_amount': float(self.discount_amount),
            'discount_reason': self.discount_reason,
            'notes': self.notes,
            'terms': self.terms,
            'status': self.status,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'version': self.version,
            'is_expired': self.is_expired,
        }
    
    @classmethod
    def create_from_request(cls, request_obj, items_data, created_by, 
                           admin_fees=0, report_fees=0, vat_rate=19,
                           discount_amount=0, discount_reason='', notes=''):
        """Create a new quote for a request."""
        # Calculate totals
        subtotal_ht = sum(item['total'] for item in items_data)
        subtotal_before_tax = subtotal_ht + admin_fees + report_fees - discount_amount
        vat_amount = round(subtotal_before_tax * (vat_rate / 100), 2)
        total_ttc = round(subtotal_before_tax + vat_amount, 2)
        
        # Get next version number
        last_quote = cls.objects.filter(request=request_obj).order_by('-version').first()
        version = (last_quote.version + 1) if last_quote else 1
        
        # Mark previous quotes as not current
        cls.objects.filter(request=request_obj).update(is_current=False)
        
        return cls.objects.create(
            request=request_obj,
            items=items_data,
            subtotal_ht=subtotal_ht,
            admin_fees=admin_fees,
            report_fees=report_fees,
            subtotal_before_tax=subtotal_before_tax,
            vat_rate=vat_rate,
            vat_amount=vat_amount,
            total_ttc=total_ttc,
            discount_amount=discount_amount,
            discount_reason=discount_reason,
            notes=notes,
            version=version,
            is_current=True,
            created_by=created_by,
        )


class Request(SoftDeleteModel):
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
        ('ACCEPTED', 'Accepté'),
        ('DECLINED', 'Refusé'),
        ('APPOINTMENT_PROPOSED', 'RDV Proposé'),
        ('APPOINTMENT_RESCHEDULING_REQUESTED', 'Reprogrammation Demandée'),
        ('APPOINTMENT_CONFIRMED', 'RDV Confirmé'),
        ('SAMPLE_RECEIVED', 'Échantillon Reçu'),
        ('ANALYSIS_STARTED', 'Analyse Démarrée'),
        ('ANALYSIS_FINISHED', 'Analyse Terminée'),
        ('REPORT_UPLOADED', 'Rapport Uploadé'),
        ('REPORT_VALIDATED', 'Rapport Validé'),
        ('SENT_TO_REQUESTER', 'Transmis Demandeur'),
        ('COMPLETED', 'Complété'),
        ('CLOSED', 'Clôturé'),
        ('REJECTED', 'Rejeté'),
        ('ADMINISTRATIVELY_CLOSED', 'Fermé Administrativement'),
        # GENOCLAB-specific
        ('REQUEST_CREATED', 'Demande Créée'),
        ('QUOTE_DRAFT', 'Devis En Cours'),
        ('QUOTE_SENT', 'Devis Envoyé'),
        ('QUOTE_VALIDATED_BY_CLIENT', 'Devis Accepté'),
        ('QUOTE_REJECTED_BY_CLIENT', 'Devis Refusé'),
        ('ORDER_UPLOADED', 'Bon de Commande Uploadé'),
        ('PAYMENT_PENDING', 'En Attente Paiement'),
        ('PAYMENT_UPLOADED', 'Reçu de Paiement Uploadé'),
        ('PAYMENT_CONFIRMED', 'Paiement Confirmé'),
        ('INVOICE_GENERATED', 'Facture Générée'),
        ('INVOICE_SENT', 'Facture Transmise'),
        ('SENT_TO_CLIENT', 'Transmis Client'),
        ('ARCHIVED', 'Archivé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    display_id = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=300)
    description = models.TextField(default='', blank=True)
    channel = models.CharField(max_length=10, choices=CHANNEL_CHOICES)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default='SUBMITTED')
    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='Normal')

    # Relationships
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='requests_made')
    assigned_to = models.ForeignKey('accounts.MemberProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_requests')
    informed_members = models.ManyToManyField(
        'accounts.MemberProfile',
        blank=True,
        related_name='observed_requests',
        help_text=_('Members informed about this request (read-only access)')
    )

    # Financial
    budget_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    declared_ibtikar_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    declared_balance_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Declared balance timestamp'))
    quote_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quote_detail = models.JSONField(default=dict, blank=True, verbose_name='Détail du devis')
    admin_validated_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Tracking IDs (Part J)
    ibtikar_id = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Identifiant IBTIKAR-DGRSDT',
        help_text='IBTIKAR tracking ID provided by requester (e.g., IDGRSTD00001)'
    )
    tracking_number = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Numéro de suivi',
        help_text='Auto-generated tracking number for GENOCLAB (GCL-YYYY-XXXXX)'
    )

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
    
    # Points awarded for service completion (prevents double awards)
    completion_points_awarded = models.BooleanField(default=False, verbose_name=_('Completion points awarded'))
    
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
    
    # Appointment rescheduling limit (prevents infinite reschedule loops)
    reschedule_count = models.PositiveIntegerField(
        default=0,
        verbose_name=_('Reschedule Count'),
        help_text=_('Number of times appointment has been rescheduled')
    )
    MAX_RESCHEDULE_LIMIT = 3
    
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
            models.Index(fields=['channel', 'status', 'updated_at']),
            models.Index(fields=['requester', 'status']),
            models.Index(fields=['assigned_to', 'status', 'updated_at']),
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


def homepage_section_image_upload_to(instance, filename):
    section_type = (instance.section_type or 'custom').lower()
    return f'homepage/{section_type}/{filename}'


def homepage_block_image_upload_to(instance, filename):
    section_type = 'custom'
    if instance.section_id and instance.section and instance.section.section_type:
        section_type = instance.section.section_type.lower()
    return f'homepage/{section_type}/{filename}'


class Homepage(models.Model):
    title = models.CharField(max_length=200, default='Homepage')
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='homepage_updates'
    )

    class Meta:
        db_table = 'homepage'
        verbose_name = 'Homepage'
        verbose_name_plural = 'Homepages'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_active:
            Homepage.objects.exclude(pk=self.pk).update(is_active=False)

    @classmethod
    def get_active(cls):
        obj = cls.objects.filter(is_active=True).first()
        if not obj:
            obj = cls.objects.create(title='Homepage', is_active=True)
        return obj


class HomepageSection(models.Model):
    SECTION_TYPE_CHOICES = [
        ('hero', 'Hero'),
        ('partners', 'Partners'),
        ('services', 'Services'),
        ('stats', 'Stats'),
        ('about', 'About'),
        ('contact', 'Contact'),
        ('custom', 'Custom'),
    ]

    homepage = models.ForeignKey(Homepage, on_delete=models.CASCADE, related_name='sections')
    section_type = models.CharField(max_length=20, choices=SECTION_TYPE_CHOICES, default='custom')
    slug = models.SlugField(max_length=100)
    title = models.CharField(max_length=255, blank=True, default='')
    subtitle = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    image = models.ImageField(upload_to=homepage_section_image_upload_to, null=True, blank=True)
    link_url = models.URLField(blank=True, default='')
    payload = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='homepage_section_updates'
    )

    class Meta:
        db_table = 'homepage_sections'
        ordering = ['position', 'pk']
        unique_together = [('homepage', 'slug')]

    def __str__(self):
        return f'{self.homepage_id}:{self.slug}'


class HomepageBlock(models.Model):
    BLOCK_TYPE_CHOICES = [
        ('card', 'Card'),
        ('logo', 'Logo'),
        ('button', 'Button/CTA'),
        ('text', 'Text'),
        ('image', 'Image'),
        ('stat', 'Stat'),
    ]

    PAYLOAD_SCHEMA = {
        'card': {'required': [], 'allowed': ['title', 'text', 'link', 'image_alt']},
        'logo': {'required': ['name'], 'allowed': ['name', 'link', 'image_alt']},
        'button': {'required': ['text', 'link'], 'allowed': ['text', 'link', 'style']},
        'text': {'required': ['content'], 'allowed': ['content']},
        'image': {'required': ['alt'], 'allowed': ['alt', 'caption']},
        'stat': {'required': ['value', 'label'], 'allowed': ['value', 'label']},
    }

    CTA_STYLE_CHOICES = [
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
        ('ghost', 'Ghost'),
    ]

    section = models.ForeignKey(HomepageSection, on_delete=models.CASCADE, related_name='blocks')
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES)
    title = models.CharField(max_length=255, blank=True, default='')
    text = models.TextField(blank=True, default='')
    link_url = models.URLField(blank=True, default='')
    image = models.ImageField(upload_to=homepage_block_image_upload_to, null=True, blank=True)
    image_alt = models.CharField(max_length=255, blank=True, default='')
    cta_style = models.CharField(max_length=20, choices=CTA_STYLE_CHOICES, blank=True, default='primary')
    payload = models.JSONField(default=dict, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='homepage_block_updates'
    )

    class Meta:
        db_table = 'homepage_blocks'
        ordering = ['position', 'pk']

    def __str__(self):
        return f'{self.section.slug}:{self.block_type}'

    def clean(self):
        super().clean()
        schema = self.PAYLOAD_SCHEMA.get(self.block_type)
        if not schema:
            raise ValidationError({'block_type': 'Unsupported block_type.'})
        if self.payload is None:
            self.payload = {}
        if not isinstance(self.payload, dict):
            raise ValidationError({'payload': 'Payload must be a JSON object.'})

        payload_keys = set(self.payload.keys())
        required = set(schema['required'])
        allowed = set(schema['allowed'])

        missing = sorted(required - payload_keys)
        if missing:
            raise ValidationError({'payload': f"Missing required payload keys: {', '.join(missing)}"})

        extra = sorted(payload_keys - allowed)
        if extra:
            raise ValidationError({'payload': f"Unsupported payload keys: {', '.join(extra)}"})

        if self.block_type == 'button':
            style = self.payload.get('style', self.cta_style or 'primary')
            if style not in {'primary', 'secondary', 'ghost'}:
                raise ValidationError({'payload': 'Invalid button style. Use primary, secondary, or ghost.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


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
