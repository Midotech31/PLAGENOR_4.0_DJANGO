"""Atomic multi-item distributions and controlled returns on the native ledger."""
from datetime import date
from decimal import Decimal
import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (Capability, Location, StockContainer, StockDispatch, StockDispatchLine,
                        StockMovement, StockReturn)
from erp.permissions import require
from .catalog import convert_quantity
from .common import Conflict, audit, check_version
from .stock import (_article, _container, _fifo_received_on, _key, _location, _movement,
                    _post, is_usable, require_container, stock_quantity, transfer_stock)


def _hash(payload):
    return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _business_date(value):
    if not isinstance(value, date) or value > timezone.localdate():
        raise ValidationError(_('Vérifiez la date réelle de l’opération.'))


@transaction.atomic
def distribute_stock(user, *, key, lines, mode, beneficiary, distributed_on, reason, destination=None):
    key = _key(key)
    lines = list(lines)
    if not 1 <= len(lines) <= 100:
        raise ValidationError(_('Un bon de distribution contient entre une et cent lignes.'))
    ids = [str(line['container'].pk) for line in lines]
    if len(set(ids)) != len(ids):
        raise ValidationError(_('Sélectionnez chaque contenant une seule fois.'))
    identities = list(StockContainer.objects.filter(pk__in=ids).values_list('lot__article_id', flat=True))
    if len(identities) != len(ids):
        raise ValidationError(_('Un contenant n’existe plus.'))
    for article_id in sorted(set(identities), key=str):
        _article(article_id)
    containers = {str(obj.pk): obj for obj in StockContainer.objects.select_for_update().filter(
        pk__in=ids).order_by('pk')}
    capability = Capability.CONSUME_STOCK if mode == StockDispatch.Mode.EXIT else Capability.TRANSFER_STOCK
    normalized = []
    for line in sorted(lines, key=lambda row: str(row['container'].pk)):
        container = containers[str(line['container'].pk)]
        require_container(user, capability, container)
        amount = stock_quantity(convert_quantity(container.lot.article, line['amount'], line['unit'])[0])
        normalized.append({'container': str(container.pk), 'quantity': str(amount),
            'destination_code': line.get('destination_code', '').strip().upper()})
    if destination is not None:
        destination = _location(destination.pk)
        for container in containers.values():
            require(user, Capability.TRANSFER_STOCK, category=container.lot.article.category, location=destination)
    payload = {'lines': normalized, 'mode': mode, 'beneficiary': beneficiary.strip(),
        'date': str(distributed_on), 'reason': reason.strip(),
        'destination': str(destination.pk) if destination else None}
    digest = _hash(payload)
    existing = StockDispatch.objects.filter(key=key).first()
    if existing:
        if existing.actor_id != user.pk or existing.payload_hash != digest:
            raise Conflict(_('Cet identifiant a déjà été utilisé pour une autre opération.'))
        return existing
    _business_date(distributed_on)
    if not beneficiary.strip() or not reason.strip() or mode not in StockDispatch.Mode.values:
        raise ValidationError(_('Renseignez le mode, le bénéficiaire et le motif de distribution.'))
    if (mode == StockDispatch.Mode.INTERNAL) != (destination is not None):
        raise ValidationError(_('Une destination suivie est obligatoire uniquement pour un transfert interne.'))
    for line in lines:
        container = containers[str(line['container'].pk)]
        if line.get('expected') is not None:
            check_version(container, line['expected'])
        if not is_usable(container):
            raise ValidationError(_('Ce stock est bloqué, expiré ou non accepté.'))
        receipt_date = _fifo_received_on(container)
        if distributed_on < receipt_date:
            raise ValidationError(_('La distribution ne peut pas précéder la réception.'))
    dispatch = StockDispatch(key=key, payload_hash=digest, mode=mode, beneficiary=beneficiary.strip(),
        distributed_on=distributed_on, actor=user, reason=reason.strip(), destination=destination)
    dispatch.full_clean()
    dispatch.save()
    for line in normalized:
        container = containers[line['container']]
        amount = Decimal(line['quantity'])
        origin = container.location
        snapshot = {'article': container.lot.article.code, 'designation': container.lot.article.name,
            'catalog_reference': container.lot.article.catalog_reference,
            'manufacturer_reference': container.lot.article.manufacturer_reference,
            'supplier_reference': container.lot.article.supplier_reference,
            'lot': container.lot.manufacturer_lot, 'unit': container.lot.article.base_unit.code,
            'container': container.code, 'location': origin.code, 'location_id': str(origin.pk)}
        movement_key = uuid.uuid5(key, line['container'])
        if mode == StockDispatch.Mode.INTERNAL:
            move = transfer_stock(user, container.pk, key=movement_key, destination=destination,
                amount=amount, unit=container.lot.article.base_unit,
                destination_code=line['destination_code'], reason=reason)
        else:
            move, unused = _movement(user, movement_key, StockMovement.Kind.EXIT,
                {'dispatch': dispatch.pk, 'container': container.pk, 'quantity': amount}, reason=reason)
            _post(move, container, -amount)
        StockDispatchLine.objects.create(dispatch=dispatch, container=container,
            movement=move, quantity=amount, snapshot=snapshot)
    audit(user, dispatch, 'distributed', reason=reason)
    return dispatch


def returnable_quantity(line):
    if line.movement.reverses_id or StockMovement.objects.filter(reverses=line.movement).exists():
        return Decimal(0)
    returned = sum(line.returns.filter(movement__reversal__isnull=True).values_list('quantity', flat=True), Decimal(0))
    return max(Decimal(0), line.quantity - returned)


@transaction.atomic
def return_stock(user, line_id, *, key, amount, unit, destination, container_code, returned_on, condition, reason):
    line = StockDispatchLine.objects.select_related('container__lot__article', 'dispatch', 'movement').get(pk=line_id)
    source = _container(line.container_id)
    line = StockDispatchLine.objects.select_for_update().get(pk=line_id)
    origin = Location.objects.get(pk=line.snapshot['location_id'])
    require(user, Capability.VIEW_STOCK, category=source.lot.article.category, location=origin)
    destination = _location(destination.pk)
    require(user, Capability.RECEIVE_STOCK, category=source.lot.article.category, location=destination)
    amount = stock_quantity(convert_quantity(source.lot.article, amount, unit)[0])
    move, created = _movement(user, key, StockMovement.Kind.RETURN,
        {'line': line.pk, 'quantity': amount, 'destination': destination.pk,
         'container_code': container_code.strip().upper(), 'returned_on': returned_on,
         'condition': condition.strip(), 'reason': reason.strip()}, reason=reason)
    if not created:
        return move.stock_return
    _business_date(returned_on)
    if line.dispatch.mode != StockDispatch.Mode.EXIT or amount > returnable_quantity(line):
        raise ValidationError(_('La quantité retournée dépasse le reliquat de la sortie définitive.'))
    if returned_on < line.dispatch.distributed_on or not condition.strip() or not reason.strip():
        raise ValidationError(_('Vérifiez la date, l’état et le motif du retour.'))
    from .safety import enforce_storage
    enforce_storage(source.lot.article, destination)
    container = StockContainer(code=container_code.strip().upper(), name=source.name,
        lot=source.lot, location=destination, status=source.lot.Status.PENDING,
        source_container=source, fifo_received_on=_fifo_received_on(source),
        opened_on=source.opened_on, opened_by=source.opened_by,
        stability_days=source.stability_days, use_by=source.use_by)
    container.full_clean()
    container.save()
    _post(move, container, amount)
    returned = StockReturn(line=line, movement=move, container=container, quantity=amount,
        returned_on=returned_on, condition=condition.strip())
    returned.full_clean()
    returned.save()
    audit(user, container, 'returned', reason=reason)
    return returned
