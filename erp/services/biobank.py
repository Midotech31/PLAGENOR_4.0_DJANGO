from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Request
from core.ibtikar.models import IbtikarSubmission
from core.ibtikar.schema import display_value, schema_for_service
from erp.models import (BiologicalSample, Capability, Location, LocationClosure,
    PositionReservation, SampleEvent, StorageIncident, StoragePosition, TemperatureReading, Unit)
from erp.permissions import is_manager, operational_scope, require, require_manager, storage_scope
from .common import Conflict, audit, check_version, lock_tree, snapshot
from .links import lock_request, require_request
from .stock import _key, _location, stock_quantity


FINAL_STATES = (BiologicalSample.Status.EXHAUSTED, BiologicalSample.Status.SHIPPED,
                BiologicalSample.Status.DESTROYED)


def biobank_scope(user):
    return operational_scope(BiologicalSample.objects.all(), user, Capability.VIEW_BIOBANK,
        category_field='source_kind').select_related('unit', 'location', 'position', 'root_sample', 'parent')


def require_sample(user, sample, *, write=True):
    require(user, Capability.MANAGE_BIOBANK if write else Capability.VIEW_BIOBANK, location=sample.location)


def convert_sample_quantity(value, unit, target):
    value = stock_quantity(value)
    if not unit.active or not target.active or unit.dimension != target.dimension:
        raise ValidationError(_('Les unités de l’échantillon sont inactives ou incompatibles.'))
    if unit.pk != target.pk and unit.dimension in (Unit.Dimension.PACKAGE, Unit.Dimension.OTHER):
        raise ValidationError(_('Une conversion de conditionnement biologique ne peut pas être déduite automatiquement.'))
    with localcontext() as context:
        context.prec = 60
        return stock_quantity(value * unit.factor / target.factor)


def source_samples(user, request):
    require_request(user, request, write=False)
    submission = IbtikarSubmission.objects.filter(request=request).first()
    kind = 'IBTIKAR' if submission else 'LEGACY'
    rows = submission.samples if submission else request.sample_table
    schema = submission.schema if submission else schema_for_service(request.service)
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValidationError(_('Le tableau source des échantillons est invalide ou trop volumineux.'))
    specs = {field['name']: field for field in schema.get('samples', [])}
    identities, result = set(), []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError(_('Une ligne d’échantillon source n’est pas structurée correctement.'))
        canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
        code = str(row.get('sample_code') or '').strip()
        if code:
            source_key = 'code:' + hashlib.sha256(code.casefold().encode()).hexdigest()
        else:
            source_key = 'row:' + str(index)
        if source_key in identities:
            raise ValidationError(_('Plusieurs échantillons portent le même code source. Corrigez les doublons dans la demande avant le stockage.'))
        identities.add(source_key)
        mapped = {}
        for name in ('sample_type', 'dna_type', 'nucleic_acid_type', 'organism_type', 'biological_origin', 'origin'):
            if row.get(name) and name in specs:
                mapped[name] = display_value(specs[name], row[name], 'fr')
        result.append({'key': source_key, 'kind': kind, 'fingerprint': fingerprint,
            'code': code or str(index + 1), 'index': index, 'row': row,
            'sample_type': next((mapped[name] for name in ('sample_type', 'nucleic_acid_type', 'dna_type', 'organism_type') if name in mapped), ''),
            'matrix': mapped.get('biological_origin', mapped.get('origin', '')),
            'preservation': str(row.get('storage') or row.get('thermal_conditions') or ''),
            'collected_on': row.get('collection_date'), 'declared_quantity': row.get('quantity'),
            'declared_unit': row.get('quantity_unit'), 'source_revision': submission.revision if submission else None})
    existing = {sample.source_key: sample for sample in BiologicalSample.objects.filter(origin_request=request, parent__isnull=True)}
    for item in result:
        item['existing'] = existing.get(item['key'])
        item['source_changed'] = bool(item['existing'] and item['existing'].source_fingerprint != item['fingerprint'])
    return result


def _sample(pk):
    lock_tree('locations')
    return BiologicalSample.objects.select_for_update().get(pk=pk)


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, default=str, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def _replay(user, key, kind, payload):
    key = _key(key)
    event = SampleEvent.objects.filter(key=key).first()
    if event and (event.actor_id != user.pk or event.kind != kind or event.payload_hash != _fingerprint(payload)):
        raise Conflict(_('Cet identifiant a déjà été utilisé pour une autre opération d’échantillon.'))
    return event


def _event(user, sample, key, kind, payload, *, before=None, delta=Decimal(0), reason='', request=None):
    if not reason.strip() or len(reason) > 500:
        raise ValidationError(_('Un motif entre 1 et 500 caractères est requis.'))
    before = before or {}
    return SampleEvent.objects.create(key=_key(key), payload_hash=_fingerprint(payload), sample=sample,
        kind=kind, actor=user, from_location_id=uuid.UUID(before['location']) if before.get('location') else None, to_location=sample.location,
        from_position_id=uuid.UUID(before['position']) if before.get('position') else None, to_position=sample.position, quantity_delta=delta,
        request=request, reason=reason.strip(), data={'operation': json.loads(json.dumps(payload, default=str)),
        'before': before, 'after': snapshot(sample)})


def _destination(user, location, position=None, *, sample=None, allow_reserved=False):
    location = _location(location.pk)
    require(user, Capability.MANAGE_BIOBANK, location=location)
    if location.grid_rows is not None and position is None:
        raise ValidationError(_('Choisissez une position précise dans cette boîte.'))
    if position is not None:
        position = StoragePosition.objects.select_for_update().get(pk=position.pk)
        if not position.active or position.location_id != location.pk:
            raise ValidationError(_('La position ne correspond pas à un emplacement actif de cette boîte.'))
        occupied = BiologicalSample.objects.filter(position=position)
        if sample is not None:
            occupied = occupied.exclude(pk=sample.pk)
        if occupied.exists():
            raise ValidationError(_('Cette position est déjà occupée.'))
        reservation = PositionReservation.objects.select_for_update().filter(position=position, active=True).first()
        if reservation:
            if reservation.until <= timezone.now():
                reservation.active, reservation.version = False, reservation.version + 1
                reservation.save()
                audit(user, reservation, 'expired')
            elif reservation.assignee_id != user.pk and not (is_manager(user) and allow_reserved):
                raise ValidationError(_('Cette position est réservée à un autre membre de l’équipe.'))
            else:
                reservation.active, reservation.version = False, reservation.version + 1
                reservation.save()
                audit(user, reservation, 'fulfilled')
    else:
        occupied = BiologicalSample.objects.filter(location=location, status__in=['STORED', 'QUARANTINE', 'OUT'])
        if sample:
            occupied = occupied.exclude(pk=sample.pk)
        if location.capacity is not None and occupied.count() >= location.capacity:
            raise ValidationError(_('La capacité configurée de cet emplacement est atteinte.'))
    return location, position


@transaction.atomic
def build_positions(user, location_id, *, expected):
    lock_tree('locations')
    location = Location.objects.select_for_update().get(pk=location_id)
    require(user, Capability.EDIT_STORAGE, location=location)
    check_version(location, expected)
    if not location.active or not location.kind.can_store or not location.grid_rows or not location.grid_columns:
        raise ValidationError(_('Définissez d’abord les dimensions de la grille d’un emplacement de stockage actif.'))
    if location.grid_rows * location.grid_columns > 10000:
        raise ValidationError(_('Une grille est limitée à 10 000 positions. Utilisez plusieurs boîtes au-delà.'))
    existing = {(position.row, position.column) for position in location.positions.all()}
    if any(row > location.grid_rows or column > location.grid_columns for row, column in existing):
        raise ValidationError(_('La nouvelle grille exclurait des positions existantes. Aucun emplacement n’a été supprimé.'))
    created = []
    for row in range(1, location.grid_rows + 1):
        for column in range(1, location.grid_columns + 1):
            if (row, column) not in existing:
                code = 'POS-' + uuid.uuid5(location.pk, str(row) + ':' + str(column)).hex[:28].upper()
                created.append(StoragePosition(code=code, name=str(row) + ':' + str(column), location=location, row=row, column=column))
    StoragePosition.objects.bulk_create(created)
    audit(user, location, 'positions_created', reason=str(len(created)))
    return location.positions.order_by('row', 'column')


@transaction.atomic
def reserve_position(user, position_id, *, assignee, until, reason):
    lock_tree('locations')
    position = StoragePosition.objects.select_for_update().get(pk=position_id)
    require(user, Capability.MANAGE_BIOBANK, location=position.location)
    from .work import _member
    assignee = _member(assignee)
    if assignee is None or (assignee.pk != user.pk and not is_manager(user)):
        raise PermissionDenied
    if until <= timezone.now() or not reason.strip() or len(reason) > 500:
        raise ValidationError(_('La réservation exige une échéance future et un motif.'))
    _destination(user, position.location, position)
    reservation = PositionReservation.objects.create(position=position, assignee=assignee,
        until=until, reason=reason, created_by=user)
    audit(user, reservation, 'reserved')
    return reservation


@transaction.atomic
def receive_sample(user, *, key, code, amount, unit, location, received_on, reason,
                   position=None, request=None, source_key='', source_fingerprint='',
                   sample_type='', matrix='', collected_on=None, concentration_value=None,
                   concentration_unit=None, temperature_min=None, temperature_max=None,
                   preservation='', freeze_thaw_limit=None, notes=''):
    request = lock_request(user, request)
    lock_tree('locations')
    require(user, Capability.MANAGE_BIOBANK, location=location)
    require_request(user, request)
    payload = {'code': code, 'quantity': amount, 'unit': unit.pk, 'location': location.pk,
        'position': position.pk if position else None, 'request': request.pk if request else None,
        'source_key': source_key, 'source_fingerprint': source_fingerprint, 'received_on': received_on,
        'reason': reason, 'sample_type': sample_type, 'matrix': matrix, 'collected_on': collected_on,
        'concentration_value': concentration_value, 'concentration_unit': concentration_unit.pk if concentration_unit else None,
        'temperature_min': temperature_min, 'temperature_max': temperature_max, 'preservation': preservation,
        'freeze_thaw_limit': freeze_thaw_limit, 'notes': notes}
    replay = _replay(user, key, SampleEvent.Kind.RECEIPT, payload)
    if replay:
        return replay.sample
    source = None
    if request:
        request = Request.objects.select_for_update().get(pk=request.pk)
        require_request(user, request)
        source = next((value for value in source_samples(user, request) if value['key'] == source_key), None)
        if source is None or source['fingerprint'] != source_fingerprint:
            raise Conflict(_('La ligne source a changé. Rechargez la demande avant la réception.'))
        if source['existing']:
            raise Conflict(_('Cet échantillon de la demande est déjà présent dans l’échantillothèque.'))
    elif source_key or source_fingerprint:
        raise ValidationError(_('Une identité source doit être associée à une demande PLAGENOR.'))
    amount = convert_sample_quantity(amount, unit, unit)
    if received_on > timezone.localdate():
        raise ValidationError(_('La réception ne peut pas être datée dans le futur.'))
    location, position = _destination(user, location, position)
    sample = BiologicalSample(code=code.strip().upper(), name=code.strip().upper(), unit=unit,
        initial_quantity=amount, remaining_quantity=amount, location=location, position=position,
        origin_request=request, source_kind=source['kind'] if source else 'MANUAL', source_key=source_key,
        source_fingerprint=source_fingerprint, source_snapshot={'row': source['row'], 'revision': source['source_revision']} if source else {},
        sample_type=sample_type or (source['sample_type'] if source else ''), matrix=matrix or (source['matrix'] if source else ''),
        received_on=received_on, collected_on=collected_on, concentration_value=concentration_value,
        concentration_unit=concentration_unit, created_by=user, temperature_min=temperature_min,
        temperature_max=temperature_max, preservation=preservation, freeze_thaw_limit=freeze_thaw_limit, notes=notes)
    if source and not collected_on and source['collected_on']:
        try:
            sample.collected_on = date.fromisoformat(str(source['collected_on']))
        except ValueError:
            raise ValidationError(_('La date de prélèvement source doit être corrigée avant le stockage.'))
    sample.full_clean()
    sample.save()
    _event(user, sample, key, SampleEvent.Kind.RECEIPT, payload, delta=amount, reason=reason, request=request)
    audit(user, sample, 'received', reason=reason)
    return sample


@transaction.atomic
def transfer_sample(user, pk, *, key, destination, position=None, reason, expected=None, allow_reserved=False):
    sample = _sample(pk)
    require_sample(user, sample)
    payload = {'sample': sample.pk, 'destination': destination.pk, 'position': position.pk if position else None,
        'reason': reason, 'allow_reserved': allow_reserved}
    replay = _replay(user, key, SampleEvent.Kind.TRANSFER, payload)
    if replay:
        return replay
    if expected is not None:
        check_version(sample, expected)
    if sample.status not in ('STORED', 'QUARANTINE'):
        raise ValidationError(_('Seul un échantillon stocké peut être transféré.'))
    if destination.pk == sample.location_id and (position.pk if position else None) == sample.position_id:
        raise ValidationError(_('La nouvelle localisation doit être différente.'))
    before = snapshot(sample)
    sample.location, sample.position = _destination(user, destination, position, sample=sample, allow_reserved=allow_reserved)
    sample.version += 1
    sample.full_clean()
    sample.save()
    event = _event(user, sample, key, SampleEvent.Kind.TRANSFER, payload, before=before, reason=reason)
    audit(user, sample, 'transferred', before, reason)
    return event


@transaction.atomic
def aliquot_sample(user, pk, *, key, code, amount, unit, location, position=None, reason, expected=None):
    parent = _sample(pk)
    require_sample(user, parent)
    require(user, Capability.MANAGE_BIOBANK, location=location)
    amount = convert_sample_quantity(amount, unit, parent.unit)
    payload = {'parent': parent.pk, 'code': code, 'quantity': amount, 'unit': unit.pk,
        'location': location.pk, 'position': position.pk if position else None, 'reason': reason}
    replay = _replay(user, key, SampleEvent.Kind.ALIQUOT, payload)
    if replay:
        return BiologicalSample.objects.get(pk=uuid.uuid5(_key(key), 'sample'))
    if expected is not None:
        check_version(parent, expected)
    if parent.status not in ('STORED', 'OUT') or amount > parent.remaining_quantity:
        raise ValidationError(_('Le parent est indisponible ou la quantité à aliquoter dépasse le volume restant.'))
    before = snapshot(parent)
    location, position = _destination(user, location, position)
    child = BiologicalSample(id=uuid.uuid5(_key(key), 'sample'), code=code.strip().upper(), name=code.strip().upper(), parent=parent,
        root_sample=parent.root_sample or parent, source_kind='ALIQUOT',
        source_key='aliquot:' + str(uuid.uuid4()), unit=parent.unit, initial_quantity=amount,
        remaining_quantity=amount, location=location, position=position, received_on=timezone.localdate(),
        created_by=user, freeze_thaw_cycles=parent.freeze_thaw_cycles)
    child.full_clean()
    child.save()
    parent.remaining_quantity -= amount
    if parent.remaining_quantity == 0:
        parent.status, parent.position = BiologicalSample.Status.EXHAUSTED, None
    parent.version += 1
    parent.save()
    event = _event(user, parent, key, SampleEvent.Kind.ALIQUOT, payload, before=before, delta=-amount, reason=reason)
    child_payload = {**payload, 'parent_event': str(event.pk)}
    _event(user, child, uuid.uuid5(_key(key), 'child'), SampleEvent.Kind.RECEIPT, child_payload,
           delta=amount, reason=reason)
    audit(user, parent, 'aliquoted', before, reason)
    audit(user, child, 'aliquot_created', reason=reason)
    return child


@transaction.atomic
def sample_action(user, pk, *, key, action, reason, amount=None, unit=None,
                  destination=None, position=None, request=None, thawed=False, expected=None):
    request = lock_request(user, request)
    sample = _sample(pk)
    require_sample(user, sample)
    payload = {'sample': sample.pk, 'action': action, 'reason': reason, 'amount': amount,
        'unit': unit.pk if unit else None, 'destination': destination.pk if destination else None,
        'position': position.pk if position else None, 'request': request.pk if request else None, 'thawed': thawed}
    if action not in ('CHECK_OUT', 'RETURN', 'CONSUMPTION', 'QUARANTINE', 'RELEASE', 'SHIPMENT', 'DESTRUCTION', 'ANALYSIS'):
        raise ValidationError(_('Action biologique non reconnue.'))
    replay = _replay(user, key, action, payload)
    if replay:
        return replay
    if expected is not None:
        check_version(sample, expected)
    if sample.status in FINAL_STATES:
        raise ValidationError(_('Cet échantillon est clôturé. Son historique reste consultable.'))
    require_request(user, request)
    before, delta = snapshot(sample), Decimal(0)
    if action == 'CHECK_OUT':
        if sample.status != 'STORED':
            raise ValidationError(_('Seul un échantillon stocké et libéré peut être sorti pour analyse.'))
        if destination is None:
            raise ValidationError(_('Indiquez la localisation de travail pendant la sortie.'))
        sample.location, sample.position = _destination(user, destination, position, sample=sample)
        sample.status, sample.checked_out_at = 'OUT', timezone.now()
        sample.thawed_during_checkout = bool(thawed)
    elif action == 'RETURN':
        if sample.status != 'OUT' or sample.checked_out_at is None or destination is None:
            raise ValidationError(_('Un retour exige une sortie ouverte et une destination.'))
        sample.location, sample.position = _destination(user, destination, position, sample=sample)
        sample.out_of_storage_seconds += max(0, int((timezone.now() - sample.checked_out_at).total_seconds()))
        if thawed or sample.thawed_during_checkout:
            sample.freeze_thaw_cycles += 1
        sample.checked_out_at, sample.thawed_during_checkout, sample.status = None, False, 'STORED'
    elif action == 'CONSUMPTION':
        if sample.status not in ('STORED', 'OUT') or amount is None or unit is None:
            raise ValidationError(_('La consommation exige une quantité, une unité et un échantillon disponible.'))
        delta = -convert_sample_quantity(amount, unit, sample.unit)
        if -delta > sample.remaining_quantity:
            raise ValidationError(_('La quantité demandée dépasse la quantité biologique restante.'))
        sample.remaining_quantity += delta
        if sample.remaining_quantity == 0:
            sample.status, sample.position = 'EXHAUSTED', None
    elif action == 'ANALYSIS':
        if sample.status not in ('STORED', 'OUT'):
            raise ValidationError(_('L’échantillon n’est pas disponible pour une analyse.'))
    elif action == 'QUARANTINE':
        if sample.status != 'STORED':
            raise ValidationError(_('Le placement en quarantaine exige un échantillon stocké.'))
        sample.status = 'QUARANTINE'
    elif action == 'RELEASE':
        require_manager(user)
        if sample.status != 'QUARANTINE':
            raise ValidationError(_('L’échantillon n’est pas en quarantaine.'))
        sample.status = 'STORED'
    else:
        delta = -sample.remaining_quantity
        sample.remaining_quantity, sample.position = Decimal(0), None
        sample.status = 'SHIPPED' if action == 'SHIPMENT' else 'DESTROYED'
    sample.version += 1
    sample.full_clean()
    sample.save()
    event = _event(user, sample, key, action, payload, before=before, delta=delta, reason=reason, request=request)
    audit(user, sample, action.lower(), before, reason)
    return event


def reconcile_biobank(user):
    require_manager(user)
    return [{'sample': sample.code, 'remaining': sample.remaining_quantity,
        'ledger_remaining': sample.ledger_remaining or Decimal(0)} for sample in
        BiologicalSample.objects.annotate(ledger_remaining=Sum('events__quantity_delta'))
        if sample.remaining_quantity != (sample.ledger_remaining or 0)]
