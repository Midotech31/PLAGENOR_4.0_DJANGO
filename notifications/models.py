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

    def __str__(self):
        return f"{self.user} — {self.message[:50]}"
    
    def get_absolute_url(self):
        """Get the URL to navigate to when clicking this notification."""
        if self.link_url:
            return self.link_url
        if self.request:
            return f"/dashboard/ops/request/{self.request.pk}/"
        return "/dashboard/"
    
    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone
        if not self.read:
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])
