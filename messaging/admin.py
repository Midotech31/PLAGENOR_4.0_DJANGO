from django.contrib import admin
from messaging.models import EphemeralMessage, Reminder


@admin.register(EphemeralMessage)
class EphemeralMessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'request', 'sender', 'phase', 'created_at', 'is_archived']
    list_filter = ['phase', 'is_archived', 'is_system_message']
    search_fields = ['content', 'request__display_id', 'sender__username']
    readonly_fields = ['id', 'created_at', 'archived_at']


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ['id', 'request', 'target_user', 'action_expected', 'urgency', 'is_active']
    list_filter = ['urgency', 'source', 'is_active', 'escalated']
    search_fields = ['request__display_id', 'target_user__username', 'action_expected']
    readonly_fields = ['id', 'created_at', 'sent_at', 'acknowledged_at', 'escalated_at', 'deactivated_at']
