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
    services = models.ManyToManyField(
        Service,
        related_name='document_blocks',
        blank=True,
        verbose_name='Services concernés',
        help_text=(
            "Laissez vide pour appliquer à tous les services (bloc global). "
            "Sélectionnez un ou plusieurs services pour limiter le bloc à ce sous-ensemble."
        ),
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
            models.Index(fields=['template_type', 'language', 'is_active']),
        ]

    def __str__(self):
        codes = list(self.services.values_list('code', flat=True)) if self.pk else []
        scope = ','.join(codes) if codes else 'GLOBAL'
        return f"[{self.get_template_type_display()}] {scope} · {self.position} · {self.language}"

    @property
    def is_global(self) -> bool:
        """A block is global when no services are attached — applies to every
        request of its template_type regardless of which service was picked."""
        return not self.services.exists()

    def scope_label(self) -> str:
        """Render the service scope for list views and admin display.

        Returns 'Global' when the M2M is empty, otherwise a comma-joined
        list of service codes ('PCR, Seq02, Lyoph'). Truncated at 60 chars
        with an ellipsis to keep table layouts tidy.
        """
        codes = list(self.services.order_by('code').values_list('code', flat=True))
        if not codes:
            return 'Global'
        rendered = ', '.join(codes)
        return rendered if len(rendered) <= 60 else rendered[:57] + '…'

    @classmethod
    def applicable_blocks(cls, template_type, service, language):
        """Return active blocks that should be injected for this request.

        Match rules:
        - ``template_type`` equals ``template_type``
        - ``language`` equals ``language`` (caller resolves; falls back to
          ``settings.LANGUAGE_CODE`` separately if nothing matches)
        - The block is either GLOBAL (no services attached) OR
          ``service`` appears in its M2M

        Returns a deduplicated queryset ordered by ``(position, priority,
        pk)``. ``.distinct()`` is necessary because the M2M filter
        produces a JOIN that can duplicate rows when a block targets the
        request's service AND happens to also target others.
        """
        from django.db.models import Count, Q
        qs = (
            cls.objects
            .filter(template_type=template_type, language=language, is_active=True)
            .annotate(_n_services=Count('services'))
        )
        if service is not None:
            qs = qs.filter(Q(_n_services=0) | Q(services=service))
        else:
            qs = qs.filter(_n_services=0)
        return qs.distinct().order_by('position', 'priority', 'pk')

