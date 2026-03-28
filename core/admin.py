from django.contrib import admin
from .models import Service, Request, RequestHistory, RequestComment, Invoice, PlatformContent, PaymentMethod


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


admin.site.register(RequestHistory)
admin.site.register(RequestComment)
admin.site.register(PlatformContent)
admin.site.register(PaymentMethod)
