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
