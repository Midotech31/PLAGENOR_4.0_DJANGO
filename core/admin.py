from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Service, Request, RequestHistory, RequestComment, Invoice,
    PlatformContent, PaymentMethod, Message, RevenueArchive, ServiceFormField,
    ServicePricing,
)


# =============================================================================
# Inlines
# =============================================================================

class ServiceFormFieldInline(admin.TabularInline):
    """
    Tabular inline for ServiceFormField - allows editing sample table columns
    and additional info fields directly from the Service admin page.
    """
    model = ServiceFormField
    extra = 1
    fields = (
        'field_category', 'name', 'label_fr', 'label_en', 
        'field_type', 'choices_json', 'is_required', 'order'
    )
    ordering = ['field_category', 'order']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('service')


# =============================================================================
# Service Admin
# =============================================================================

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'channel_availability', 'ibtikar_price', 'genoclab_price', 'active')
    list_filter = ('channel_availability', 'active')
    search_fields = ('code', 'name', 'description')
    
    inlines = [ServiceFormFieldInline]
    
    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'active', 'channel_availability', 'priority')
        }),
        ('Tarification', {
            'fields': ('ibtikar_price', 'genoclab_price', 'ibtikar_external_code')
        }),
        ('Descriptions', {
            'fields': ('description', 'ibtikar_instructions', 'ibtikar_instructions_en', 'deliverables')
        }),
        ('Paramètres PDF IBTIKAR', {
            'fields': ('service_code', 'form_version', 'checklist_items', 'processing_steps'),
            'classes': ('collapse',)
        }),
        ('Délai', {
            'fields': ('turnaround_time',)
        }),
    )


# =============================================================================
# Request Admin
# =============================================================================

@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = (
        'display_id', 'title', 'channel', 'status', 'urgency', 
        'requester', 'assigned_to', 'has_ibtikar_form', 
        'has_platform_note', 'has_reception_form', 'created_at'
    )
    list_filter = ('channel', 'status', 'urgency', 'archived')
    search_fields = ('display_id', 'title', 'guest_name', 'guest_email', 'requester__username')
    readonly_fields = (
        'id', 'display_id', 'created_at', 'updated_at', 
        'generated_ibtikar_form', 'generated_platform_note', 'generated_reception_form'
    )
    
    fieldsets = (
        (None, {
            'fields': ('display_id', 'channel', 'status', 'urgency', 'service', 'additional_data')
        }),
        ('Demandeur', {
            'fields': ('requester', 'submitted_as_guest', 'guest_name', 'guest_email', 'guest_phone')
        }),
        ('Analyse', {
            'fields': ('title', 'description', 'analysis_framework', 'project_title', 'pi_name', 'pi_email', 'pi_phone')
        }),
        ('Détails', {
            'fields': ('service_params', 'sample_table')
        }),
        ('Budget IBTIKAR', {
            'fields': ('budget_amount', 'declared_ibtikar_balance', 'ibtikar_external_code'),
            'classes': ('collapse',)
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'appointment_date', 'appointment_confirmed')
        }),
        ('Rapport', {
            'fields': ('report_file', 'report_token', 'report_delivered')
        }),
        ('Finances IBTIKAR', {
            'fields': ('validated_cost', 'discount_percentage', 'discount_amount', 'final_cost'),
            'classes': ('collapse',)
        }),
        ('Évaluation', {
            'fields': ('service_rating', 'rating_comment', 'receipt_confirmed', 'citation_accepted', 'citation_accepted_at'),
            'classes': ('collapse',)
        }),
        ('Documents Générés', {
            'fields': ('generated_ibtikar_form', 'generated_platform_note', 'generated_reception_form'),
            'description': 'PDFs générés automatiquement. Utilisez les actions pour régénérer.'
        }),
        ('Métadonnées', {
            'fields': ('id', 'created_at', 'updated_at', 'archived', 'archived_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = [
        'generate_ibtikar_forms', 
        'regenerate_ibtikar_forms',
        'generate_platform_notes',
        'generate_reception_forms',
    ]
    
    def has_ibtikar_form(self, obj):
        if obj.generated_ibtikar_form:
            return format_html(
                '<a href="{}" target="_blank">📄 Télécharger</a>',
                obj.generated_ibtikar_form.url
            )
        return '—'
    has_ibtikar_form.short_description = 'Formulaire IBTIKAR'
    
    def has_platform_note(self, obj):
        if obj.generated_platform_note:
            return format_html(
                '<a href="{}" target="_blank">📄 Télécharger</a>',
                obj.generated_platform_note.url
            )
        return '—'
    has_platform_note.short_description = 'Note de Plateforme'
    
    def has_reception_form(self, obj):
        if obj.generated_reception_form:
            return format_html(
                '<a href="{}" target="_blank">📄 Télécharger</a>',
                obj.generated_reception_form.url
            )
        return '—'
    has_reception_form.short_description = 'Formulaire Réception'
    
    def generate_ibtikar_forms(self, request, queryset):
        from documents.pdf_generator_ibtikar import generate_ibtikar_form_pdf
        
        success_count = 0
        error_count = 0
        errors = []
        
        for req in queryset.filter(channel='IBTIKAR'):
            try:
                file_path, error = generate_ibtikar_form_pdf(req, force_regenerate=False)
                if error:
                    error_count += 1
                    errors.append(f"{req.display_id}: {error}")
                else:
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"{req.display_id}: {str(e)}")
        
        if success_count:
            self.message_user(request, f'{success_count} formulaire(s) IBTIKAR généré(s) avec succès.')
        if error_count:
            self.message_user(request, f'{error_count} erreur(s): ' + '; '.join(errors[:5]), level='warning')
    generate_ibtikar_forms.short_description = 'Générer le formulaire IBTIKAR'
    
    def regenerate_ibtikar_forms(self, request, queryset):
        from documents.pdf_generator_ibtikar import generate_ibtikar_form_pdf
        
        success_count = 0
        error_count = 0
        errors = []
        
        for req in queryset.filter(channel='IBTIKAR'):
            try:
                file_path, error = generate_ibtikar_form_pdf(req, force_regenerate=True)
                if error:
                    error_count += 1
                    errors.append(f"{req.display_id}: {error}")
                else:
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"{req.display_id}: {str(e)}")
        
        if success_count:
            self.message_user(request, f'{success_count} formulaire(s) IBTIKAR régénéré(s) avec succès.')
        if error_count:
            self.message_user(request, f'{error_count} erreur(s): ' + '; '.join(errors[:5]), level='warning')
    regenerate_ibtikar_forms.short_description = 'Régénérer le formulaire IBTIKAR'
    
    def generate_platform_notes(self, request, queryset):
        from documents.pdf_generator_platform_note import generate_platform_note_pdf
        
        success_count = 0
        error_count = 0
        errors = []
        
        for req in queryset.filter(channel='IBTIKAR'):
            try:
                file_path, error = generate_platform_note_pdf(req, force_regenerate=True)
                if error:
                    error_count += 1
                    errors.append(f"{req.display_id}: {error}")
                else:
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"{req.display_id}: {str(e)}")
        
        if success_count:
            self.message_user(request, f'{success_count} Note(s) de Plateforme générée(s) avec succès.')
        if error_count:
            self.message_user(request, f'{error_count} erreur(s): ' + '; '.join(errors[:5]), level='warning')
    generate_platform_notes.short_description = 'Générer les Notes de Plateforme (IBTIKAR)'
    
    def generate_reception_forms(self, request, queryset):
        from documents.pdf_generator_reception import generate_reception_form_pdf
        
        success_count = 0
        error_count = 0
        errors = []
        
        for req in queryset:
            try:
                file_path, error = generate_reception_form_pdf(req, force_regenerate=True)
                if error:
                    error_count += 1
                    errors.append(f"{req.display_id}: {error}")
                else:
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"{req.display_id}: {str(e)}")
        
        if success_count:
            self.message_user(request, f'{success_count} Formulaire(s) de Réception généré(s) avec succès.')
        if error_count:
            self.message_user(request, f'{error_count} erreur(s): ' + '; '.join(errors[:5]), level='warning')
    generate_reception_forms.short_description = 'Générer les Formulaires de Réception'


# =============================================================================
# Other Admins
# =============================================================================

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'client', 'total_ttc', 'locked', 'created_at')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('request', 'from_user', 'to_user', 'read', 'created_at')
    list_filter = ('read',)


@admin.register(RevenueArchive)
class RevenueArchiveAdmin(admin.ModelAdmin):
    list_display = ('month', 'year', 'channel', 'total_revenue', 'request_count')
    list_filter = ('channel', 'year')


@admin.register(ServiceFormField)
class ServiceFormFieldAdmin(admin.ModelAdmin):
    list_display = ('service', 'field_category', 'name', 'label_fr', 'field_type', 'is_required', 'order')
    list_filter = ('field_category', 'field_type', 'is_required', 'service')
    search_fields = ('name', 'label_fr', 'label_en', 'service__name')


admin.site.register(RequestHistory)
admin.site.register(RequestComment)


@admin.register(PlatformContent)
class PlatformContentAdmin(admin.ModelAdmin):
    list_display = ('key', 'short_value', 'updated_at', 'updated_by')
    search_fields = ('key', 'value')
    list_filter = ('updated_at',)
    ordering = ('key',)

    fieldsets = (
        (None, {
            'fields': ('key', 'value'),
            'description': 'Modifiez le texte visible sur le site. La clé identifie l\'élément, la valeur est le texte affiché.'
        }),
    )

    def short_value(self, obj):
        return obj.value[:80] + '...' if len(obj.value) > 80 else obj.value
    short_value.short_description = 'Contenu'


admin.site.register(PaymentMethod)


@admin.register(ServicePricing)
class ServicePricingAdmin(admin.ModelAdmin):
    list_display = ('service', 'pricing_type', 'name', 'amount', 'unit', 'is_active', 'priority')
    list_filter = ('pricing_type', 'channel', 'is_active', 'service')
    search_fields = ('name', 'description', 'service__name', 'service__code')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('service', 'updated_by')
    ordering = ['service', 'priority', 'pk']
    
    fieldsets = (
        (None, {
            'fields': ('service', 'pricing_type', 'channel', 'name', 'description')
        }),
        ('Tarif', {
            'fields': ('amount', 'unit', 'min_quantity', 'max_quantity', 'min_amount', 'max_amount')
        }),
        ('Options', {
            'fields': ('is_active', 'priority')
        }),
        ('Métadonnées', {
            'fields': ('updated_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
