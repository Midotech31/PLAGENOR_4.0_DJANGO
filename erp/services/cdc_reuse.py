"""Selected technical copies from immutable, authorized historical CDC revisions."""
import copy
import uuid
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.cdc.lot_catalog import MAX_ITEMS, fingerprint, validate_catalog
from erp.models import Article, CdcItem, CdcLot, CdcRequirement, CdcReusePreview, CdcRevision, Unit
from .cdc import _dossier, _revision, document_data, dossier_scope
from .common import check_version
from .stock import stock_quantity


def source_rows(user, revision_id, family):
    revision = CdcRevision.objects.select_related('dossier').defer('dossier__data').filter(pk=revision_id,
        dossier__in=dossier_scope(user), dossier__family=family).first()
    if revision is None:
        raise PermissionDenied
    if fingerprint({'document': revision.data, 'estimates': revision.estimates}) != revision.sha256:
        raise ValidationError(_('L’intégrité de la révision CDC ne peut pas être confirmée.'))
    # Only technical content reaches the selector or the editable preview.
    rows = [dict(copy.deepcopy(item), selection=lot['id'] + ':' + item['key'],
                 source_lot=lot['id'], lot_name=lot['name'])
            for lot in revision.data['lot_catalog']['lots'] for item in lot['items']]
    return revision, rows


@transaction.atomic
def preview_reuse(user, pk, *, expected, source_revision, target_lot, selections, reason):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    revision, rows = source_rows(user, source_revision, dossier.family)
    target = CdcLot.objects.get(pk=target_lot, dossier=dossier, active=True)
    if not reason.strip() or not selections or len(selections) > MAX_ITEMS or len(set(selections)) != len(selections):
        raise ValidationError(_('Sélectionnez des articles distincts et justifiez leur réutilisation.'))
    selected = set(selections)
    chosen = [row for row in rows if row['selection'] in selected]
    if len(chosen) != len(selected):
        raise ValidationError(_('Un article sélectionné ne fait pas partie de cette révision.'))
    return CdcReusePreview.objects.create(dossier=dossier, actor=user, source_revision=revision,
        target_lot=target, base_version=dossier.version, payload={'rows': chosen, 'source_sha256': revision.sha256},
        reason=reason.strip()[:500], expires_at=timezone.now() + timedelta(hours=24))


@transaction.atomic
def apply_reuse(user, pk, *, rows):
    identity = CdcReusePreview.objects.get(pk=pk)
    dossier = _dossier(user, identity.dossier_id, edit=True)
    preview = CdcReusePreview.objects.select_for_update().get(pk=pk)
    if preview.actor_id != user.pk:
        raise PermissionDenied
    source, _rows = source_rows(user, preview.source_revision_id, dossier.family)
    if preview.payload['source_sha256'] != source.sha256:
        raise ValidationError(_('La révision source ne correspond plus à cet aperçu.'))
    if preview.applied_revision_id:
        return preview.applied_revision
    if preview.expires_at <= timezone.now():
        raise ValidationError(_('Cet aperçu a expiré. Sélectionnez à nouveau les articles.'))
    check_version(dossier, preview.base_version)
    target = CdcLot.objects.get(pk=preview.target_lot_id, dossier=dossier, active=True)
    originals = preview.payload['rows']
    fields = {'selection', 'designation', 'specifications', 'unit', 'packaging', 'quantity', 'details', 'omit'}
    if len(rows) != len(originals) or any(set(row) - fields or row['selection'] != original['selection']
        for row, original in zip(rows, originals)):
        raise ValidationError(_('Le contenu de l’aperçu ne correspond plus à la sélection.'))
    if not any(not row.get('omit') for row in rows):
        raise ValidationError(_('Conservez au moins un article à réutiliser.'))
    # Historical links come from the immutable snapshot, never from posted IDs or live source items.
    legacy_ids = [entry['id'] for entry in source.estimates if 'source_key' not in entry]
    legacy_keys = dict(CdcItem.objects.filter(pk__in=legacy_ids).values_list('id', 'source_key'))
    estimates = {(entry['lot'], entry.get('source_key', legacy_keys.get(uuid.UUID(entry['id'])))): entry
        for entry in source.estimates}
    articles = {str(article.pk): article for article in Article.objects.filter(
        pk__in=[entry['article'] for entry in source.estimates if entry.get('article')], active=True)}
    units = {str(unit.pk): unit for unit in Unit.objects.filter(
        pk__in=[entry['purchase_unit'] for entry in source.estimates if entry.get('purchase_unit')], active=True)}
    position = (target.items.aggregate(n=Max('position'))['n'] or 0) + 1
    requirements_by_item = {}
    for requirement in source.data.get('requirements', []):
        requirements_by_item.setdefault((requirement['lot'], requirement['item_key']), []).append(requirement)
    copies, copied_requirements = [], []
    for row, original in zip(rows, originals):
        if row.get('omit'):
            continue
        link = estimates.get((original['source_lot'], original['key']), {})
        article = articles.get(link.get('article'))
        unit = units.get(link.get('purchase_unit'))
        if article and unit and (not dossier.work.category_id or article.category_id == dossier.work.category_id):
            if row['unit'] != unit.name:
                raise ValidationError(_('L’unité liée au catalogue doit être conservée dans la copie.'))
            linked = {'article': article, 'purchase_unit': unit, 'base_factor': link['base_factor'],
                      'article_snapshot': link['article_snapshot']}
        else:
            linked = {}
        item = CdcItem(lot=target, source_key='new-' + str(uuid.uuid4()), position=position,
            designation=row['designation'], specifications=row['specifications'], unit_label=row['unit'],
            packaging=row['packaging'], quantity=stock_quantity(row['quantity']), details=row['details'], **linked)
        # FK identities were already checked above; database constraints still guard the atomic batch.
        item.full_clean(exclude=['lot', 'article', 'purchase_unit'], validate_unique=False, validate_constraints=False)
        copies.append(item)
        requirements = requirements_by_item.get((original['source_lot'], original['key']), [])
        for requirement in requirements:
            copied_requirements.append(CdcRequirement(item=item, **{field: requirement[field] for field in
                ('position', 'kind', 'statement', 'evidence', 'verification_method', 'justification')}))
        position += 1
    CdcItem.objects.bulk_create(copies)
    CdcRequirement.objects.bulk_create(copied_requirements)
    validate_catalog(document_data(dossier)['lot_catalog'])
    revision = _revision(user, dossier, preview.reason)
    preview.applied_revision = revision
    preview.save(update_fields=['applied_revision', 'updated_at'])
    return revision
