from django.db import models
from django.conf import settings


class Notification(models.Model):
    TYPE_CHOICES = [
        ('INFO', 'Info'),
        ('WORKFLOW', 'Workflow'),
        ('SYSTEM', 'System'),
        ('ASSIGNMENT', 'Assignment'),
        ('STATUS_CHANGE', 'Status Change'),
        ('APPOINTMENT', 'Appointment'),
        ('REPORT', 'Report Ready'),
        ('PAYMENT', 'Payment'),
        ('REWARD', 'Reward'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='INFO')
    request = models.ForeignKey('core.Request', on_delete=models.SET_NULL, null=True, blank=True)
    # Deep linking support
    link_url = models.CharField(max_length=500, blank=True, help_text='URL for deep linking')
    link_text = models.CharField(max_length=200, blank=True, help_text='Text for the link')
    # Additional context
    action_url = models.CharField(max_length=500, blank=True, help_text='Action URL (e.g., accept, reject)')
    action_text = models.CharField(max_length=200, blank=True, help_text='Action button text')
    read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'read']),
            models.Index(fields=['created_at']),
        ]

    # Context icon (from core.templatetags.icons set) + accent colour per type,
    # so the notification panel shows a glanceable visual cue, not just text.
    _ICON_BY_TYPE = {
        'INFO': 'message-square',
        'WORKFLOW': 'flag',
        'SYSTEM': 'zap',
        'ASSIGNMENT': 'clipboard',
        'STATUS_CHANGE': 'send',
        'APPOINTMENT': 'clock',
        'REPORT': 'file-text',
        'PAYMENT': 'dollar-sign',
        'REWARD': 'award',
    }
    _ACCENT_BY_TYPE = {
        'INFO': '#64748b',
        'WORKFLOW': '#4f46e5',
        'SYSTEM': '#0ea5e9',
        'ASSIGNMENT': '#7c3aed',
        'STATUS_CHANGE': '#2563eb',
        'APPOINTMENT': '#d97706',
        'REPORT': '#059669',
        'PAYMENT': '#16a34a',
        'REWARD': '#eab308',
    }

    @property
    def icon(self):
        """Icon name for the context cue (see core.templatetags.icons)."""
        return self._ICON_BY_TYPE.get(self.notification_type, 'message-square')

    @property
    def accent(self):
        """Accent colour for the notification's icon badge."""
        return self._ACCENT_BY_TYPE.get(self.notification_type, '#64748b')

    def __str__(self):
        return f"{self.user} — {self.message[:50]}"

    def get_absolute_url(self):
        """Resolve the request-detail URL for the recipient's role.

        Each role has its own request-detail view; routing every recipient to
        the admin URL produces a 403 for analysts/clients/requesters. An
        explicit ``link_url`` always wins.
        """
        if self.link_url:
            return self.link_url
        if self.request:
            role = getattr(self.user, 'role', '')
            pk = self.request.pk
            if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
                return f"/dashboard/ops/request/{pk}/"
            if role == 'MEMBER':
                return f"/dashboard/analyst/request/{pk}/"
            if role == 'CLIENT':
                return f"/dashboard/client/request/{pk}/"
            if role == 'REQUESTER':
                return f"/dashboard/requester/request/{pk}/"
            # FINANCE has no per-request detail view; land on the finance index.
            if role == 'FINANCE':
                return "/dashboard/finance/"
        return "/dashboard/"
    
    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone
        if not self.read:
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])
