"""Native, versioned CDC workbook exchange; no client-supplied preview is trusted."""
import copy
from datetime import timedelta
from decimal import Decimal
import uuid

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.cdc.lot_catalog import get_catalog, validate_catalog
from erp.cdc.lot_workbook import MAX_FILE, build_workbook, parse_workbook
from erp.models import CdcItem, CdcLot, CdcRevision, CdcWorkbookPreview
from erp.permissions import require_manager
from .cdc import _dossier, _revision, document_data, dossier_scope
from .common import check_version
from .work import require_work

SALT = 'plagenor.cdc.workbook.v1'


def export_workbook(user, dossier, *, filled=True, prices=False):
    require_work(user, dossier.work, costs=prices)
    estimates = {}
    if prices:
        items = CdcItem.objects.filter(lot__dossier=dossier, lot__active=True, active=True)
        if items.exclude(currency='DZD').filter(estimated_price__isnull=False).exists():
            raise ValidationError(_('Le classeur financier est en DZD. Exportez sans prix les dossiers comportant une autre devise.'))
        estimates = {i.source_key: i.estimated_price for i in items}
    return build_workbook(document_data(dossier), dossier.pk, dossier.revision_number,
        lambda meta: signing.dumps(meta, salt=SALT, compress=True), filled=filled, estimates=estimates)


@transaction.atomic
def preview_workbook(user, pk, *, expected, upload, mode, import_prices=False, reason=''):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    require_work(user, dossier.work, costs=import_prices)
    if not reason.strip():
        raise ValidationError(_('Justifiez l’import et indiquez la source des prix si vous les importez.'))
    if upload.size > MAX_FILE:
        raise ValidationError(_('Le fichier dépasse la limite de 20 Mo.'))
    result = parse_workbook(upload.read(MAX_FILE + 1), upload.name, document_data(dossier),
        dossier.pk, dossier.revision_number, lambda token: signing.loads(token, salt=SALT), mode=mode)
    if not import_prices:
        result['financial'] = {}
    return CdcWorkbookPreview.objects.create(dossier=dossier, actor=user, base_version=dossier.version,
        filename=upload.name[:180], payload=result, import_prices=import_prices, reason=reason.strip()[:500],
        expires_at=timezone.now() + timedelta(hours=24))


def _apply_catalog(dossier, catalog, *, financial=None, reason='', restoring=False):
    """Preserve relational identities, links, historical snapshots and removed rows."""
    validate_catalog(catalog)
    for row in catalog['lots']:
        lot = CdcLot.objects.get(pk=row['id'], dossier=dossier, active=True)
        retained = set()
        for value in row['items']:
            item = lot.items.filter(source_key=value['key']).first()
            if item is None:
                item = CdcItem(lot=lot, source_key=value['key'])
            if not restoring and item.article_id and value['unit'] != item.unit_label:
                raise ValidationError(_('Une unité liée au catalogue ne peut pas être changée dans Excel. Utilisez la fiche article du dossier.'))
            for field in ('designation', 'specifications', 'packaging', 'details', 'position'):
                setattr(item, field, value[field])
            item.unit_label = value['unit']
            item.quantity = Decimal(value['quantity'].replace(',', '.'))
            item.active = True
            if financial is not None and value['key'] in financial:
                if item.currency != 'DZD':
                    raise ValidationError(_('Les estimations Excel sont en DZD ; aucune conversion de devise implicite n’est autorisée.'))
                item.estimated_price = financial[value['key']]
                item.price_source = reason
            item.full_clean()
            item.version += 1
            item.save()
            retained.add(item.pk)
        lot.items.exclude(pk__in=retained).update(active=False)


@transaction.atomic
def apply_workbook(user, pk):
    # Same work -> dossier -> preview lock order as all CDC mutations.
    identity = CdcWorkbookPreview.objects.get(pk=pk)
    dossier = _dossier(user, identity.dossier_id, edit=True)
    preview = CdcWorkbookPreview.objects.select_for_update().get(pk=pk)
    if preview.actor_id != user.pk:
        raise PermissionDenied
    require_work(user, dossier.work, costs=preview.import_prices)
    if preview.applied_revision_id:
        return preview.applied_revision
    if preview.expires_at <= timezone.now():
        raise ValidationError(_('Cet aperçu a expiré. Analysez à nouveau votre fichier.'))
    check_version(dossier, preview.base_version)
    _apply_catalog(dossier, get_catalog(preview.payload['data']),
        financial=preview.payload['financial'] if preview.import_prices else None, reason=preview.reason)
    revision = _revision(user, dossier, preview.reason)
    preview.applied_revision = revision
    preview.save(update_fields=['applied_revision', 'updated_at'])
    return revision


@transaction.atomic
def add_lot(user, pk, *, expected, name, name_ar='', source=None, reason='', source_slot=None):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    if dossier.family == 'works':
        raise ValidationError(_('Le modèle Travaux conserve son lot documentaire unique.'))
    position = (dossier.lots.aggregate(n=Max('position'))['n'] or 0) + 1
    lot = CdcLot(dossier=dossier, position=position, name=name.strip(), name_ar=name_ar.strip(), source_slot=source_slot or 0)
    lot.full_clean()
    lot.save()
    if source is not None:
        source = CdcLot.objects.select_related('dossier__work').get(pk=source.pk,
            dossier__in=dossier_scope(user), active=True)
        if source.dossier.family != dossier.family:
            raise ValidationError(_('Réutilisez un lot de la même famille documentaire.'))
        for item in source.items.filter(active=True):
            item.pk = None
            item.lot = lot
            item.source_key = 'new-' + str(uuid.uuid4())
            item.version = 1
            # Reuse technical data only; estimates must be confirmed for the new lot.
            item.estimated_price = item.tax_rate = None
            item.price_source = ''
            item.save()
    _revision(user, dossier, reason)
    return lot


@transaction.atomic
def set_lot_active(user, pk, *, expected, active, reason):
    lot = CdcLot.objects.get(pk=pk)
    dossier = _dossier(user, lot.dossier_id, edit=True)
    check_version(dossier, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez le retrait ou la réintégration du lot.'))
    lot.active = active
    lot.version += 1
    lot.save(update_fields=['active', 'version', 'updated_at'])
    return _revision(user, dossier, reason)


@transaction.atomic
def restore_revision(user, pk, *, expected, reason):
    require_manager(user)
    source = CdcRevision.objects.get(pk=pk)
    dossier = _dossier(user, source.dossier_id, edit=True)
    check_version(dossier, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez la reprise de cette révision.'))
    catalog = get_catalog(source.data)
    ids = [lot['id'] for lot in catalog['lots']]
    dossier.lots.update(active=False)
    for value in catalog['lots']:
        CdcLot.objects.get_or_create(pk=value['id'], dossier=dossier, defaults={
            'position': 20000 + value['number'], 'name': value['name'], 'name_ar': value['name_ar'],
            'source_slot': value['source_slot']})
    dossier.lots.filter(pk__in=ids).update(active=True)
    for n, lot in enumerate(dossier.lots.order_by('id'), 1):
        lot.position = 30000 + n
        lot.save(update_fields=['position'])
    for value in catalog['lots']:
        CdcLot.objects.filter(pk=value['id'], dossier=dossier).update(position=value['number'],
            name=value['name'], name_ar=value['name_ar'], source_slot=value['source_slot'])
    for n, lot in enumerate(dossier.lots.filter(active=False).order_by('id'), len(ids) + 1):
        lot.position = n
        lot.save(update_fields=['position'])
    _apply_catalog(dossier, catalog, restoring=True)
    for lot in catalog['lots']:
        estimates = [value for value in source.estimates if value['lot'] == lot['id'] and value['active']]
        for row, value in zip(lot['items'], estimates, strict=True):
            item = CdcItem.objects.get(lot_id=lot['id'], source_key=row['key'])
            item.article_id, item.purchase_unit_id = value['article'], value['purchase_unit']
            item.article_snapshot, item.base_factor = value['article_snapshot'], value['base_factor']
            item.estimated_price, item.tax_rate = value['price'], value['tax_rate']
            item.currency, item.price_source = value['currency'], value['source']
            item.save()
    dossier.data = copy.deepcopy(source.data)
    dossier.reference = source.data['reference']
    dossier.full_clean()
    return _revision(user, dossier, reason)
