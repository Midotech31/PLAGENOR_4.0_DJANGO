from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (Article, Capability, Location, LocationClosure, StockContainer,
                       StockEntry, StockLot, StockMovement, StockReceipt, StockReservation)
from erp.permissions import is_manager, operational_scope, permitted, require, require_manager
from .catalog import convert_quantity, quantity
from .common import Conflict, audit, check_version, lock_tree, snapshot


OUTFLOWS = (StockMovement.Kind.CONSUMPTION, StockMovement.Kind.LOSS, StockMovement.Kind.BREAKAGE,
            StockMovement.Kind.CONTAMINATION, StockMovement.Kind.EXPIRY,
            StockMovement.Kind.DESTRUCTION, StockMovement.Kind.EXIT)


def stock_quantity(value, *, zero=False):
    value = quantity(value)
    if value != value.quantize(Decimal('0.000001')) or (not zero and value == 0):
        raise ValidationError(_('La quantité doit être positive et exacte à six décimales au maximum.'))
    return value


def _key(key):
    try:
        return uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_('Identifiant d’opération invalide.'))


def _movement(user, key, kind, payload, *, request=None, reason='', reverses=None):
    key = _key(key)
    data = json.loads(json.dumps(payload, default=str, sort_keys=True))
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    existing = StockMovement.objects.filter(key=key).first()
    if existing:
        if existing.actor_id != user.pk or existing.kind != kind or existing.payload_hash != digest:
            raise Conflict(_('Cet identifiant a déjà été utilisé pour une autre opération.'))
        return existing, False
    if len(reason) > 500:
        raise ValidationError(_('Le motif est limité à 500 caractères.'))
    obj = StockMovement.objects.create(key=key, payload_hash=digest, kind=kind, actor=user,
        reason=reason, request=request, reverses=reverses, snapshot=data)
    return obj, True


def _article(pk):
    lock_tree('locations')
    return Article.objects.select_for_update().get(pk=pk)


def _container(pk):
    identity = StockContainer.objects.values('lot__article_id').get(pk=pk)
    _article(identity['lot__article_id'])
    return StockContainer.objects.select_for_update().get(pk=pk)


def _location(pk):
    location = Location.objects.get(pk=pk)
    if not location.kind.can_store or LocationClosure.objects.filter(descendant=location, ancestor__active=False).exists():
        raise ValidationError(_('Choisissez un emplacement de stockage actif.'))
    return location


def require_container(user, capability, container):
    require(user, capability, category=container.lot.article.category, location=container.location)


def usable_filter(today=None):
    today = today or timezone.localdate()
    return Q(active=True, lot__active=True, lot__article__active=True,
             lot__status=StockLot.Status.AVAILABLE, status=StockLot.Status.AVAILABLE) & (
             Q(use_by__isnull=True) | Q(use_by__gte=today)) & (
             Q(lot__expires_on__isnull=True) | Q(lot__expires_on__gte=today))


def is_usable(container):
    return StockContainer.objects.filter(pk=container.pk).filter(usable_filter()).exists()


def _post(movement, container, physical=Decimal(0), reserved=Decimal(0), *, location=None):
    if physical == 0 and reserved == 0:
        return
    new_quantity, new_reserved = container.quantity + physical, container.reserved + reserved
    if new_quantity < 0 or new_reserved < 0 or new_reserved > new_quantity:
        raise ValidationError(_('Stock disponible insuffisant ou réservation incohérente.'))
    stock_quantity(new_quantity, zero=True)
    stock_quantity(new_reserved, zero=True)
    StockEntry.objects.create(movement=movement, container=container, location=location or container.location,
        quantity_delta=physical, reserved_delta=reserved,
        snapshot={'article': container.lot.article.code, 'designation': container.lot.article.name,
                  'unit': container.lot.article.base_unit.code, 'lot': container.lot.manufacturer_lot,
                  'container': container.code, 'location': (location or container.location).code})
    container.quantity, container.reserved = new_quantity, new_reserved
    container.version += 1
    container.save(update_fields=['quantity', 'reserved', 'version', 'updated_at'])


@transaction.atomic
def receive_stock(user, *, key, article, location, manufacturer_lot, lot_code, container_code,
                  amount, unit, received_on, supplier=None, order_reference='', ordered_on=None,
                  ordered_quantity=None, expires_on=None, manufactured_on=None, serial_number='',
                  condition='', cold_chain_ok=None, control_notes='', unit_price=None, currency='DZD',
                  initial=False, barcode=''):
    article = _article(article.pk)
    location = _location(location.pk)
    require(user, Capability.RECEIVE_STOCK, category=article.category, location=location)
    amount = stock_quantity(convert_quantity(article, amount, unit)[0])
    if unit_price is not None:
        require(user, Capability.EDIT_COST, category=article.category)
    payload = {'article': article.pk, 'location': location.pk, 'manufacturer_lot': manufacturer_lot,
        'lot_code': lot_code, 'container_code': container_code, 'quantity': amount, 'unit': unit.pk,
        'received_on': received_on, 'supplier': supplier.pk if supplier else None,
        'order_reference': order_reference, 'ordered_on': ordered_on, 'ordered_quantity': ordered_quantity,
        'expires_on': expires_on, 'manufactured_on': manufactured_on, 'serial_number': serial_number,
        'condition': condition, 'cold_chain_ok': cold_chain_ok, 'control_notes': control_notes,
        'unit_price': unit_price, 'currency': currency, 'barcode': barcode}
    move, created = _movement(user, key, StockMovement.Kind.INITIAL if initial else StockMovement.Kind.RECEIPT, payload)
    if not created:
        return move
    if not condition.strip() or received_on > timezone.localdate() or (ordered_on and ordered_on > received_on):
        raise ValidationError(_('Vérifiez l’état à réception et les dates de commande et de réception.'))
    if supplier and (not supplier.active or not supplier.is_supplier):
        raise ValidationError(_('Sélectionnez un fournisseur actif.'))
    if manufactured_on and manufactured_on > received_on:
        raise ValidationError(_('La fabrication ne peut pas être postérieure à la réception.'))
    lot = StockLot.objects.filter(article=article, manufacturer_lot=manufacturer_lot.strip(), serial_number=serial_number).first()
    if lot:
        if lot.code != lot_code.strip().upper() or lot.expires_on != expires_on or lot.manufactured_on != manufactured_on:
            raise ValidationError(_('Ce lot existe déjà avec d’autres métadonnées. Vérifiez la réception.'))
    else:
        lot = StockLot(article=article, code=lot_code.strip().upper(), name=article.name + ' — ' + manufacturer_lot.strip(),
            manufacturer_lot=manufacturer_lot.strip(), serial_number=serial_number, manufactured_on=manufactured_on,
            expires_on=expires_on, status=StockLot.Status.AVAILABLE, barcode=barcode,
            specifications_snapshot=snapshot(article))
        lot.full_clean()
        lot.save()
        audit(user, lot, 'created')
    container = StockContainer(code=container_code.strip().upper(), name=lot.name, lot=lot, location=location,
        use_by=lot.expires_on, status=StockLot.Status.QUARANTINE if cold_chain_ok is False else StockLot.Status.PENDING)
    container.full_clean()
    container.save()
    receipt = StockReceipt(movement=move, container=container, supplier=supplier, order_reference=order_reference,
        ordered_on=ordered_on, received_on=received_on, ordered_quantity=ordered_quantity,
        received_quantity=amount, condition=condition.strip(), cold_chain_ok=cold_chain_ok,
        control_notes=control_notes, unit_price=unit_price, currency=currency)
    receipt.full_clean()
    receipt.save()
    _post(move, container, amount)
    audit(user, container, 'received')
    return move


@transaction.atomic
def control_container(user, pk, *, expected, status, reason):
    container = _container(pk)
    require_container(user, Capability.CONTROL_STOCK, container)
    check_version(container, expected)
    if status not in StockLot.Status.values or not reason.strip():
        raise ValidationError(_('Sélectionnez un état et justifiez le contrôle.'))
    if status == StockLot.Status.AVAILABLE and ((container.use_by and container.use_by < timezone.localdate())
        or container.lot.status != StockLot.Status.AVAILABLE):
        raise ValidationError(_('Un contenant expiré ou un lot bloqué ne peut pas être libéré.'))
    if status == StockLot.Status.DESTROYED and container.quantity:
        raise ValidationError(_('Enregistrez la destruction du stock avant de clôturer le contenant.'))
    before = snapshot(container)
    container.status, container.version = status, container.version + 1
    container.save()
    audit(user, container, 'controlled', before, reason)
    return container


@transaction.atomic
def control_lot(user, pk, *, expected, status, reason):
    require_manager(user)
    lot = StockLot.objects.get(pk=pk)
    _article(lot.article_id)
    lot = StockLot.objects.select_for_update().get(pk=pk)
    check_version(lot, expected)
    if status not in StockLot.Status.values or not reason.strip():
        raise ValidationError(_('Sélectionnez un état et justifiez le contrôle.'))
    if status == StockLot.Status.AVAILABLE and lot.expires_on and lot.expires_on < timezone.localdate():
        raise ValidationError(_('Un lot expiré ne peut pas être libéré.'))
    if status == StockLot.Status.DESTROYED and lot.containers.filter(quantity__gt=0).exists():
        raise ValidationError(_('Le lot contient encore du stock physique.'))
    before = snapshot(lot)
    lot.status, lot.version = status, lot.version + 1
    lot.save()
    audit(user, lot, 'controlled', before, reason)
    return lot


@transaction.atomic
def open_container(user, pk, *, expected, opened_on, reason=''):
    container = _container(pk)
    require_container(user, Capability.CONSUME_STOCK, container)
    check_version(container, expected)
    if container.opened_on is not None or opened_on > timezone.localdate():
        raise ValidationError(_('Ce contenant est déjà ouvert ou la date d’ouverture est future.'))
    if not is_usable(container):
        raise ValidationError(_('Seul un contenant utilisable peut être ouvert.'))
    receipt = StockReceipt.objects.filter(container=container).order_by('received_on').first()
    if receipt and opened_on < receipt.received_on:
        raise ValidationError(_('L’ouverture ne peut pas précéder la réception.'))
    before = snapshot(container)
    container.opened_on, container.opened_by = opened_on, user
    container.stability_days = container.lot.article.after_open_days
    limits = [day for day in (container.lot.expires_on,
              opened_on + timedelta(days=container.stability_days) if container.stability_days is not None else None) if day is not None]
    container.use_by = min(limits) if limits else None
    container.version += 1
    container.save()
    audit(user, container, 'opened', before, reason)
    return container



def fefo(user, article):
    return operational_scope(StockContainer.objects.filter(lot__article=article), user).filter(
        usable_filter(), quantity__gt=F('reserved')).select_related('lot', 'location', 'lot__article__base_unit').order_by(
        F('use_by').asc(nulls_last=True), 'created_at', 'code')


@transaction.atomic
def remove_stock(user, pk, *, key, amount, unit, kind=StockMovement.Kind.CONSUMPTION,
                 reason='', request=None, reservation=None):
    from .links import lock_request, require_request
    request = lock_request(user, request)
    container = _container(pk)
    capability = Capability.CONSUME_STOCK if kind == StockMovement.Kind.CONSUMPTION else Capability.CONTROL_STOCK
    require_container(user, capability, container)
    require_request(user, request)
    amount = stock_quantity(convert_quantity(container.lot.article, amount, unit)[0])
    payload = {'container': container.pk, 'quantity': amount, 'unit': unit.pk, 'reason': reason,
               'request': request.pk if request else None, 'reservation': reservation.pk if reservation else None}
    move, created = _movement(user, key, kind, payload, request=request, reason=reason)
    if not created:
        return move
    if kind not in OUTFLOWS:
        raise ValidationError(_('Type de sortie non autorisé.'))
    reserved = Decimal(0)
    if reservation is not None:
        reservation = StockReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.container_id != container.pk or reservation.request_id != (request.pk if request else None):
            raise ValidationError(_('La réservation ne correspond pas au contenant et à la demande.'))
        if kind != StockMovement.Kind.CONSUMPTION or reservation.remaining < amount:
            raise ValidationError(_('Quantité réservée insuffisante.'))
        reserved = amount
        reservation.remaining -= amount
        reservation.version += 1
        reservation.save()
    if kind == StockMovement.Kind.CONSUMPTION:
        if not is_usable(container):
            raise ValidationError(_('Ce stock est bloqué, expiré ou non accepté.'))
        suggested = fefo(user, container.lot.article).first()
        if suggested and suggested.pk != container.pk and not reason.strip():
            raise ValidationError(_('Justifiez la sélection d’un contenant différent de la proposition FEFO.'))
    elif not reason.strip():
        raise ValidationError(_('Une sortie non analytique doit être justifiée.'))
    _post(move, container, -amount, -reserved)
    audit(user, container, 'stock_removed', reason=reason)
    return move


@transaction.atomic
def reserve_stock(user, pk, *, key, amount, unit, reference, request=None):
    from .links import lock_request, require_request
    request = lock_request(user, request)
    container = _container(pk)
    require_container(user, Capability.RESERVE_STOCK, container)
    require_request(user, request)
    amount = stock_quantity(convert_quantity(container.lot.article, amount, unit)[0])
    payload = {'container': container.pk, 'quantity': amount, 'unit': unit.pk,
               'reference': reference, 'request': request.pk if request else None}
    move, created = _movement(user, key, StockMovement.Kind.RESERVATION, payload, request=request)
    if not created:
        return StockReservation.objects.get(movement=move)
    if not reference.strip() or not is_usable(container):
        raise ValidationError(_('La réservation exige un stock utilisable et une référence.'))
    _post(move, container, reserved=amount)
    reservation = StockReservation(container=container, request=request, reference=reference.strip(),
        movement=move, remaining=amount, created_by=user)
    reservation.full_clean()
    reservation.save()
    audit(user, reservation, 'reserved')
    return reservation


@transaction.atomic
def release_stock(user, reservation_id, *, key, reason):
    reservation = StockReservation.objects.get(pk=reservation_id)
    from .links import lock_request
    lock_request(user, reservation.request, allow_closed=True)
    container = _container(reservation.container_id)
    require_container(user, Capability.RESERVE_STOCK, container)
    reservation = StockReservation.objects.select_for_update().get(pk=reservation_id)
    move, created = _movement(user, key, StockMovement.Kind.RELEASE,
        {'reservation': reservation.pk, 'reason': reason}, request=reservation.request, reason=reason)
    if not created:
        return move
    if not reason.strip() or reservation.remaining == 0:
        raise ValidationError(_('Justifiez la libération d’une réservation encore ouverte.'))
    before = snapshot(reservation)
    _post(move, container, reserved=-reservation.remaining)
    reservation.remaining = 0
    reservation.version += 1
    reservation.save()
    audit(user, reservation, 'released', before, reason)
    return move


@transaction.atomic
def transfer_stock(user, pk, *, key, destination, amount=None, unit=None, destination_code='', reason):
    container = _container(pk)
    require_container(user, Capability.TRANSFER_STOCK, container)
    destination = _location(destination.pk)
    require(user, Capability.TRANSFER_STOCK, category=container.lot.article.category, location=destination)
    payload = {'container': container.pk, 'destination': destination.pk, 'amount': amount,
               'unit': unit.pk if unit else None, 'destination_code': destination_code, 'reason': reason}
    move, created = _movement(user, key, StockMovement.Kind.TRANSFER, payload, reason=reason)
    if not created:
        return move
    if destination.pk == container.location_id or not reason.strip() or container.quantity == 0:
        raise ValidationError(_('Le transfert exige du stock, une nouvelle destination et un motif.'))
    moving = container.quantity if amount is None else stock_quantity(convert_quantity(container.lot.article, amount, unit or container.lot.article.base_unit)[0])
    if moving > container.quantity:
        raise ValidationError(_('Quantité à transférer supérieure au stock physique.'))
    if moving == container.quantity:
        reserved = container.reserved
        _post(move, container, -moving, -reserved)
        container.location = destination
        container.save(update_fields=['location', 'updated_at'])
        _post(move, container, moving, reserved)
    else:
        if not destination_code.strip():
            raise ValidationError(_('Attribuez un code au nouveau contenant issu de la division.'))
        target = StockContainer(code=destination_code.strip().upper(), name=container.name, lot=container.lot,
            location=destination, opened_on=container.opened_on, opened_by=container.opened_by,
            stability_days=container.stability_days, use_by=container.use_by, status=container.status)
        target.full_clean()
        target.save()
        _post(move, container, -moving)
        _post(move, target, moving)
        audit(user, target, 'split_created')
    audit(user, container, 'transferred', reason=reason)
    return move


@transaction.atomic
def reverse_stock(user, pk, *, key, reason):
    require_manager(user)
    original = StockMovement.objects.get(pk=pk)
    from .links import lock_request
    lock_request(user, original.request, allow_closed=True)
    entries = list(original.entries.select_related('container__lot', 'location').order_by('-id'))
    for article_id in sorted({entry.container.lot.article_id for entry in entries}):
        _article(article_id)
    containers = {obj.pk: obj for obj in StockContainer.objects.select_for_update().filter(
        pk__in={entry.container_id for entry in entries}).order_by('pk')}
    existing_reversal = StockMovement.objects.filter(reverses=original).first()
    if existing_reversal and existing_reversal.key != _key(key):
        raise Conflict(_('Ce mouvement a déjà été contre-passé.'))
    move, created = _movement(user, key, StockMovement.Kind.CORRECTION,
        {'original': original.pk, 'reason': reason}, request=original.request, reason=reason, reverses=original)
    if not created:
        return move
    if not reason.strip() or original.kind in (StockMovement.Kind.RESERVATION, StockMovement.Kind.RELEASE,
        StockMovement.Kind.INVENTORY, StockMovement.Kind.CORRECTION, StockMovement.Kind.PREPARATION):
        raise ValidationError(_('Cette écriture exige une procédure métier de correction dédiée.'))
    if any(StockEntry.objects.filter(container_id=pk).exclude(movement=move).order_by('-id').first().movement_id
           != original.pk for pk in containers):
        raise ValidationError(_('Des écritures ultérieures existent. Utilisez un inventaire contrôlé pour corriger le solde.'))
    for entry in entries:
        container = containers[entry.container_id]
        _post(move, container, -entry.quantity_delta, -entry.reserved_delta, location=entry.location)
        container.location = entry.location
        container.save(update_fields=['location', 'updated_at'])
        audit(user, container, 'reversed', reason=reason)
    if original.snapshot.get('reservation'):
        reservation = StockReservation.objects.select_for_update().get(pk=original.snapshot['reservation'])
        reservation.remaining += sum(-entry.reserved_delta for entry in entries)
        reservation.version += 1
        reservation.save()
    return move


def reconcile_stock(user, *, queryset=None):
    require_manager(user)
    queryset = queryset if queryset is not None else StockContainer.objects.all()
    rows = queryset.annotate(ledger_quantity=Sum('entries__quantity_delta'), ledger_reserved=Sum('entries__reserved_delta'))
    return [{'container': row.code, 'physical': row.quantity, 'reserved': row.reserved,
             'ledger_physical': row.ledger_quantity or Decimal(0), 'ledger_reserved': row.ledger_reserved or Decimal(0)}
            for row in rows if row.quantity != (row.ledger_quantity or 0) or row.reserved != (row.ledger_reserved or 0)]
