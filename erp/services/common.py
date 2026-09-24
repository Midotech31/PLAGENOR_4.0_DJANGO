from datetime import date, datetime
from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.db import models,transaction
from django.utils.translation import gettext_lazy as _

from core.audit import log_action
from erp.models import AuditEvent, TreeLock


class Conflict(ValidationError):
    pass


def scalar(value):
    if isinstance(value, (Decimal, uuid.UUID, date, datetime)):
        return str(value)
    return value


def snapshot(instance):
    return {field.name: scalar(getattr(instance, field.attname))
            for field in instance._meta.concrete_fields if field.name not in ('created_at', 'updated_at') and not isinstance(field,models.BinaryField)}


def audit(user, instance, action, before=None, reason='', *, after=None):
    after = snapshot(instance) if after is None else after
    event = AuditEvent.objects.create(actor=user, entity_type=instance._meta.label_lower,
                                     entity_id=instance.pk, action=action, before=before or {}, after=after,
                                     reason=reason)
    transaction.on_commit(lambda: log_action('ERP:' + action, instance._meta.label_lower,
                                            str(instance.pk), actor=user, details={'event_id': event.pk}))
    return event


def lock_tree(name):
    TreeLock.objects.get_or_create(name=name)
    return TreeLock.objects.select_for_update().get(name=name)


def check_version(obj, expected):
    if obj.version != expected:
        raise Conflict(_('Cet enregistrement a changé. Rechargez-le avant de réessayer.'))


def assign(obj, values):
    allowed = {field.name for field in obj._meta.concrete_fields if field.editable and not field.primary_key}
    if set(values) - allowed:
        raise ValidationError(_('Champ non modifiable.'))
    if 'code' in values and not obj._state.adding and obj.code != values['code'].strip().upper():
        raise ValidationError(_('Un code interne attribué est immuable.'))
    for key, value in values.items():
        setattr(obj, key, value)
    if hasattr(obj, 'code'):
        obj.code = obj.code.strip().upper()
    if hasattr(obj, 'name'):
        obj.name = obj.name.strip()
    return obj
