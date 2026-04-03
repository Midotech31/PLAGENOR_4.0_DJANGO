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
        ('DOCUMENT_READY', 'Document Ready'),
        ('REWARD', 'Reward/Gift'),
        ('POINTS', 'Points'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='INFO')
    request = models.ForeignKey('core.Request', on_delete=models.SET_NULL, null=True, blank=True)
    link_url = models.CharField(max_length=500, blank=True, help_text='URL for deep linking')
    link_text = models.CharField(max_length=200, blank=True, help_text='Text for the link')
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
    
    def _get_role_based_request_url(self, req):
        """Get the correct request detail URL based on user role and request channel."""
        role = getattr(self.user, 'role', None)
        
        if role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return f"/dashboard/ops/request/{req.pk}/"
        elif role == 'MEMBER':
            return f"/dashboard/analyst/request/{req.pk}/"
        elif role == 'FINANCE':
            return f"/dashboard/ops/request/{req.pk}/"
        elif role in ('REQUESTER', 'CLIENT'):
            if req.channel == 'GENOCLAB':
                return f"/dashboard/client/request/{req.pk}/"
            else:
                return f"/dashboard/requester/request/{req.pk}/"
        return f"/dashboard/ops/request/{req.pk}/"
    
    def _get_points_page_url(self):
        """Get the URL for points/rewards/milestone notifications."""
        role = getattr(self.user, 'role', None)
        
        if role == 'MEMBER':
            return "/dashboard/analyst/"
        elif role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
            return "/dashboard/ops/performance/"
        elif role in ('REQUESTER', 'CLIENT'):
            return "/dashboard/"
        return "/dashboard/"
    
    def get_absolute_url(self):
        """Get the URL to navigate to when clicking this notification.
        
        Notification type determines the destination:
        - POINTS, REWARD: Points/rewards page (analyst dashboard or performance page)
        - ASSIGNMENT, STATUS_CHANGE, WORKFLOW, REPORT, APPOINTMENT: Request detail
        - DOCUMENT_READY: Document download or request detail
        - PAYMENT: Request detail or payment page
        - INFO, SYSTEM: Role-based dashboard
        """
        if self.link_url:
            return self.link_url
        
        notif_type = self.notification_type
        
        if notif_type in ('POINTS', 'REWARD'):
            return self._get_points_page_url()
        
        if self.request:
            req = self.request
            
            if notif_type == 'DOCUMENT_READY':
                if req.generated_platform_note:
                    return f"/dashboard/ops/request/{req.pk}/"
                elif req.generated_ibtikar_form:
                    return f"/dashboard/ops/request/{req.pk}/"
                elif req.generated_reception_form:
                    return f"/dashboard/ops/request/{req.pk}/"
                elif req.generated_invoice:
                    if req.channel == 'GENOCLAB':
                        return f"/dashboard/client/request/{req.pk}/"
                return self._get_role_based_request_url(req)
            
            return self._get_role_based_request_url(req)
        
        return self._get_points_page_url()
    
    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone
        if not self.read:
            self.read = True
            self.read_at = timezone.now()
            self.save(update_fields=['read', 'read_at'])
