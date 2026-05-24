from django.db import models
from core.models import Service


class ServiceTemplate(models.Model):
    """DOCX templates for auto-generating service-specific documents (IBTIKAR forms, etc.)"""
    
    TEMPLATE_TYPE_CHOICES = [
        ('IBTIKAR_FORM', 'Formulaire IBTIKAR'),
        ('PLATFORM_NOTE', 'Note de Plateforme'),
        ('RECEPTION_FORM', 'Fiche de Réception'),
        ('QUOTE', 'Devis'),
    ]
    
    service = models.ForeignKey(
        Service, 
        on_delete=models.CASCADE, 
        related_name='templates',
        verbose_name='Service',
        help_text='Service auquel ce modèle est associé'
    )
    template_type = models.CharField(
        max_length=20,
        choices=TEMPLATE_TYPE_CHOICES,
        default='IBTIKAR_FORM',
        verbose_name='Type de modèle'
    )
    name = models.CharField(max_length=200, verbose_name='Nom du modèle')
    description = models.TextField(blank=True, verbose_name='Description')
    file = models.FileField(
        upload_to='document_templates/%Y/%m/',
        verbose_name='Fichier DOCX',
        help_text='Modèle DOCX avec placeholders (ex: {{FULL_NAME}}, {{PROJECT_TITLE}})'
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_templates'
    )
    
    class Meta:
        db_table = 'service_templates'
        ordering = ['-created_at']
        verbose_name = 'Modèle de document'
        verbose_name_plural = 'Modèles de documents'
        unique_together = ['service', 'template_type', 'is_active']
        
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()}) - {self.service.code}"
    
    @property
    def file_url(self):
        if self.file:
            return self.file.url
        return None


class TemplatePlaceholder(models.Model):
    """Documentation of placeholders available in templates"""

    template = models.ForeignKey(
        ServiceTemplate,
        on_delete=models.CASCADE,
        related_name='placeholders'
    )
    placeholder = models.CharField(max_length=100, verbose_name='Placeholder')
    description = models.CharField(max_length=255, verbose_name='Description')
    example_value = models.CharField(max_length=255, blank=True, verbose_name='Exemple de valeur')

    class Meta:
        db_table = 'template_placeholders'
        ordering = ['placeholder']

    def __str__(self):
        return f"{self.placeholder} - {self.description[:50]}"


class DocumentBlock(models.Model):
    """Admin-editable text block injected into a generated document.

    Lets the SuperAdmin add or replace prose (notices, disclaimers,
    instructions, special remarks) in the IBTIKAR form / Platform Note /
    Quote / Reception form without re-uploading the DOCX template each
    time the wording needs to change. A block can be GLOBAL (no service
    set, applies to every request of that template_type) or SCOPED
    (service set, only applies when the request uses that service).
    Language is matched against the active request language with a
    French fallback, mirroring the PlatformContent pattern.
    """

    TEMPLATE_TYPE_CHOICES = ServiceTemplate.TEMPLATE_TYPE_CHOICES

    POSITION_CHOICES = [
        ('TOP', 'Haut du document (sous l\'en-tête)'),
        ('AFTER_REQUESTER', 'Après la section demandeur'),
        ('AFTER_SAMPLES', 'Après le tableau des échantillons'),
        ('BEFORE_FOOTER', 'Juste avant le pied de page'),
        ('BOTTOM', 'Bas du document'),
    ]

    LANGUAGE_CHOICES = [
        ('fr', 'Français'),
        ('en', 'English'),
        ('ar', 'العربية'),
    ]

    template_type = models.CharField(
        max_length=20,
        choices=TEMPLATE_TYPE_CHOICES,
        verbose_name='Type de document',
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.CASCADE,
        related_name='document_blocks',
        null=True,
        blank=True,
        verbose_name='Service',
        help_text='Laisser vide pour appliquer à tous les services',
    )
    position = models.CharField(
        max_length=20,
        choices=POSITION_CHOICES,
        default='BOTTOM',
        verbose_name='Position dans le document',
    )
    language = models.CharField(
        max_length=10,
        choices=LANGUAGE_CHOICES,
        default='fr',
        verbose_name='Langue',
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Titre (optionnel)',
        help_text='Titre en gras affiché avant le texte',
    )
    body = models.TextField(
        verbose_name='Contenu',
        help_text='Texte injecté dans le document. Lignes vides séparent les paragraphes.',
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    priority = models.IntegerField(
        default=0,
        verbose_name='Priorité',
        help_text='Ordre d\'insertion (priorité plus basse = inséré en premier)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_blocks',
    )
    updated_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_blocks',
    )

    class Meta:
        db_table = 'document_blocks'
        ordering = ['template_type', 'position', 'priority', 'pk']
        verbose_name = 'Bloc de contenu'
        verbose_name_plural = 'Blocs de contenu'
        indexes = [
            models.Index(fields=['template_type', 'service', 'language', 'is_active']),
        ]

    def __str__(self):
        scope = self.service.code if self.service else 'GLOBAL'
        return f"[{self.get_template_type_display()}] {scope} · {self.position} · {self.language}"

    @classmethod
    def applicable_blocks(cls, template_type, service, language):
        """Return active blocks that should be injected for this request.

        Matches blocks where:
        - template_type equals ``template_type``
        - language equals ``language`` (caller is expected to resolve the
          active language; if no block exists for it, caller falls back to
          ``settings.LANGUAGE_CODE`` separately)
        - service is either NULL (global) or equals the request's service

        Ordered by (position, priority, pk) so callers can iterate
        positionally.
        """
        from django.db.models import Q
        qs = cls.objects.filter(
            template_type=template_type,
            language=language,
            is_active=True,
        )
        if service is not None:
            qs = qs.filter(Q(service__isnull=True) | Q(service=service))
        else:
            qs = qs.filter(service__isnull=True)
        return qs.order_by('position', 'priority', 'pk')

