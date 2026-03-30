from django.contrib import admin
from .models import ServiceTemplate, TemplatePlaceholder


@admin.register(ServiceTemplate)
class ServiceTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'service', 'template_type', 'is_active', 'created_at', 'created_by']
    list_filter = ['template_type', 'is_active', 'service']
    search_fields = ['name', 'description', 'service__name', 'service__code']
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['service', 'created_by']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {
            'fields': ('service', 'template_type', 'name', 'description')
        }),
        ('Fichier', {
            'fields': ('file', 'is_active')
        }),
        ('Métadonnées', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TemplatePlaceholder)
class TemplatePlaceholderAdmin(admin.ModelAdmin):
    list_display = ['placeholder', 'description', 'template']
    list_filter = ['template']
    search_fields = ['placeholder', 'description']
    raw_id_fields = ['template']
