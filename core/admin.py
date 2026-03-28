from django.contrib import admin
from .models import (
    Service, Request, RequestHistory, RequestComment, Invoice,
    PlatformContent, PaymentMethod, Message, RevenueArchive, ServiceFormField,
)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'channel_availability', 'ibtikar_price', 'genoclab_price', 'active')
    list_filter = ('channel_availability', 'active')


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ('display_id', 'title', 'channel', 'status', 'urgency', 'requester', 'assigned_to', 'created_at')
    list_filter = ('channel', 'status', 'urgency', 'archived')
    search_fields = ('display_id', 'title', 'guest_name', 'guest_email')
    readonly_fields = ('id', 'display_id', 'created_at', 'updated_at')


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
    list_display = ('service', 'name', 'label', 'field_type', 'required', 'sort_order')
    list_filter = ('field_type', 'required')


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
