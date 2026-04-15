import uuid
from django.db import models
from django.conf import settings


class EphemeralMessage(models.Model):
    """
    Phase-bound message tied to a specific request.
    Automatically archived when request transitions to next phase.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    request = models.ForeignKey(
        'core.Request',
        on_delete=models.CASCADE,
        related_name='ephemeral_messages'
    )
    phase = models.CharField(
        max_length=50,
        help_text="The workflow status/phase when this message was sent"
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_ephemeral_messages'
    )

    content = models.TextField(max_length=1000)

    created_at = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField(
        default=False,
        help_text="Archived when request moves to next phase"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    attachment = models.FileField(
        upload_to='ephemeral_attachments/%Y/%m/',
        null=True,
        blank=True,
        help_text="Optional file attachment (max 5MB)"
    )
    attachment_name = models.CharField(max_length=255, blank=True, default='')

    is_system_message = models.BooleanField(default=False)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['request', 'phase', 'is_archived']),
            models.Index(fields=['request', 'created_at']),
        ]

    def __str__(self):
        return f"{self.sender} → {self.request} [{self.phase}]: {self.content[:50]}"


class Reminder(models.Model):
    """
    Reminder for pending actions on requests.
    Can be auto-generated or manually created by admin.
    """
    URGENCY_CHOICES = [
        ('NORMAL', 'Normal'),
        ('URGENT', 'Urgent'),
        ('CRITICAL', 'Critical — Escalated'),
    ]
    SOURCE_CHOICES = [
        ('AUTO', 'Automatic'),
        ('MANUAL', 'Manual (Admin)'),
        ('POKE', 'Poke from Admin'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request = models.ForeignKey(
        'core.Request',
        on_delete=models.CASCADE,
        related_name='reminders'
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reminders_received'
    )

    action_expected = models.CharField(max_length=255)
    status_when_created = models.CharField(max_length=50)

    urgency = models.CharField(max_length=20, choices=URGENCY_CHOICES, default='NORMAL')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='AUTO')

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    escalated = models.BooleanField(default=False)
    escalated_at = models.DateTimeField(null=True, blank=True)
    escalation_notified_admin = models.BooleanField(default=False)

    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_reason = models.CharField(max_length=100, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['request', 'is_active']),
            models.Index(fields=['target_user', 'is_active']),
            models.Index(fields=['urgency', 'is_active']),
        ]
