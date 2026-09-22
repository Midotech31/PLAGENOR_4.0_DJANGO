import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _, get_language


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.PositiveIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CodedRecord(Record):
    code = models.CharField(_('Code interne'), max_length=32, unique=True,
                            validators=[RegexValidator(r'^[A-Z0-9][A-Z0-9._-]{0,31}$')])
    name = models.CharField(_('Désignation française'), max_length=255)
    name_en = models.CharField(_('Désignation anglaise'), max_length=255, blank=True)
    name_ar = models.CharField(_('Désignation arabe'), max_length=255, blank=True)
    active = models.BooleanField(_('Actif'), default=True)

    class Meta:
        abstract = True
        ordering = ['code']

    def __str__(self):
        language = (get_language() or 'fr').split('-')[0]
        return (getattr(self, 'name_' + language, '') or self.name)


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(_('Une écriture historique ne peut pas être modifiée.'))

    def delete(self):
        raise ValidationError(_('Une écriture historique ne peut pas être supprimée.'))


class ImmutableRecord(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(_('Une écriture historique ne peut pas être modifiée.'))
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_('Une écriture historique ne peut pas être supprimée.'))


class AuditEvent(ImmutableRecord):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    entity_type = models.CharField(max_length=64)
    entity_id = models.UUIDField()
    action = models.CharField(max_length=32)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-id']
        indexes = [models.Index(fields=['entity_type', 'entity_id', 'created_at'])]


class TreeLock(models.Model):
    name = models.CharField(max_length=32, primary_key=True)
