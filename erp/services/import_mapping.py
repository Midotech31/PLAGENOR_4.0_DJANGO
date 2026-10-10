from datetime import timedelta
from pathlib import PurePath
import hashlib

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import ImportMapping
from .bulk_imports import preview_import, require_kind
from .common import Conflict, audit, lock_tree
from .stock import _key
from .table_intake import MAX_FILE, SCHEMAS, read_matrix


@transaction.atomic
def stage_import(user, *, key, kind, filename, data, reason, plan=None):
    require_kind(user, kind, plan)
    if not reason.strip() or len(reason) > 500 or not isinstance(data, bytes) or not 0 < len(data) <= MAX_FILE:
        raise ValidationError(_('Justifiez l’import et choisissez un fichier de 10 Mo au maximum.'))
    if plan is not None and kind != 'PLAN':
        raise ValidationError(_('Un plan ne doit être associé qu’à un import de ses articles.'))
    key = _key(key)
    digest = hashlib.sha256(data).hexdigest()
    lock_tree('import-creation')
    existing = ImportMapping.objects.filter(key=key).first()
    if existing:
        if (existing.actor_id, existing.kind, existing.sha256, existing.plan_id, existing.reason) != (
                user.pk, kind, digest, plan.pk if plan else None, reason.strip()):
            raise Conflict(_('Cette clé de correspondance a déjà été utilisée pour un autre import.'))
        return existing
    matrix = read_matrix(data, PurePath(filename).suffix.lower())
    obj = ImportMapping(key=key, actor=user, kind=kind, plan=plan,
        filename=PurePath(filename.replace(chr(92), '/')).name[:180], sha256=digest,
        matrix=matrix, reason=reason.strip(), expires_at=timezone.now() + timedelta(hours=24))
    obj.full_clean()
    obj.save()
    audit(user, obj, 'mapping_staged')
    return obj


def require_mapping(user, mapping):
    if mapping.actor_id != user.pk or not user.is_active:
        raise PermissionDenied
    require_kind(user, mapping.kind, mapping.plan)
    if mapping.expires_at <= timezone.now():
        raise ValidationError(_('Cet import a expiré. Déposez de nouveau le fichier.'))


@transaction.atomic
def preview_mapping(user, pk, *, choices, clear_fields=()):
    mapping = ImportMapping.objects.select_for_update().get(pk=pk)
    require_mapping(user, mapping)
    if mapping.batch_id:
        if mapping.choices != {'columns': choices, 'clear_fields': list(clear_fields)}:
            raise Conflict(_('Cet aperçu utilise déjà une autre correspondance.'))
        return mapping.batch
    names = SCHEMAS[mapping.kind]['required'] + SCHEMAS[mapping.kind]['optional']
    indices = []
    for name, index in choices.items():
        if name not in names or not isinstance(index, int) or not 0 <= index < len(mapping.matrix[0]):
            raise ValidationError(_('Correspondance de colonne invalide.'))
        indices.append(index)
    if len(set(indices)) != len(indices) or set(SCHEMAS[mapping.kind]['required']) - set(choices):
        raise ValidationError(_('Associez chaque colonne obligatoire une seule fois.'))
    if mapping.kind != 'CATALOG' and clear_fields or set(clear_fields) - set(SCHEMAS['CATALOG']['optional']):
        raise ValidationError(_('Seuls les champs facultatifs du catalogue peuvent être effacés.'))
    rows = []
    for number, values in enumerate(mapping.matrix[1:], 2):
        if any(values):
            rows.append({'row': number, 'data': {name: values[index] if index < len(values) else '' for name, index in choices.items()},
                'clear_fields': list(clear_fields)})
    if not rows:
        raise ValidationError(_('Le tableau ne contient aucune ligne de données.'))
    batch = preview_import(user, key=mapping.key, kind=mapping.kind, filename=mapping.filename,
        data=b'', reason=mapping.reason, plan=mapping.plan, prepared_rows=rows, source_sha256=mapping.sha256)
    mapping.batch = batch
    mapping.choices = {'columns': choices, 'clear_fields': list(clear_fields)}
    mapping.matrix = mapping.matrix[:1]
    mapping.version += 1
    mapping.save()
    audit(user, mapping, 'mapping_previewed')
    return batch
