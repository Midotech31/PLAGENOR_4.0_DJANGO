import uuid
from django.conf import settings
from django.db import models


class IbtikarSubmission(models.Model):
    request = models.OneToOneField('core.Request', on_delete=models.CASCADE, related_name='ibtikar_form')
    schema = models.JSONField(default=dict)
    schema_hash = models.CharField(max_length=64)
    applicant = models.JSONField(default=dict)
    parameters = models.JSONField(default=dict)
    samples = models.JSONField(default=list)
    staff = models.JSONField(default=dict)
    estimate = models.JSONField(default=dict)
    legacy_data = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'core'


class IbtikarAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submission = models.ForeignKey(IbtikarSubmission, on_delete=models.CASCADE, related_name='attachments')
    field_name = models.CharField(max_length=100)
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to='ibtikar_attachments/%Y/%m/')
    sha256 = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'core'
        constraints = [models.UniqueConstraint(fields=['submission', 'field_name'],
                       condition=models.Q(active=True), name='ibtikar_active_attachment_unique')]


class IbtikarRevision(models.Model):
    submission = models.ForeignKey(IbtikarSubmission, on_delete=models.CASCADE, related_name='revisions')
    revision = models.PositiveIntegerField()
    data = models.JSONField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'core'
        constraints = [models.UniqueConstraint(fields=['submission', 'revision'], name='ibtikar_revision_unique')]
