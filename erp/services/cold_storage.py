from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (BiologicalSample, Capability, Location, LocationClosure,
    PositionReservation, StorageIncident, StoragePosition, StorageTransfer, TemperatureReading, WorkItem)
from erp.permissions import is_manager, permitted, require, storage_scope
from .biobank import _fingerprint, biobank_scope, transfer_sample
from .common import Conflict, audit, check_version, lock_tree, snapshot
from .stock import _key
from .work import _transition, require_work


def _temperature_permission(user, location, work=None):
    if work is not None:
        require_work(user, work, edit=True)
        if work.kind != WorkItem.Kind.TEMPERATURE or not work.location_id or not LocationClosure.objects.filter(
            ancestor_id=work.location_id, descendant=location).exists():
            raise PermissionDenied
        return
    if not (permitted(user, Capability.MANAGE_BIOBANK, location=location) or
            permitted(user, Capability.EDIT_STORAGE, location=location)):
        raise PermissionDenied


@transaction.atomic
def record_temperature(user, *, location, measured_at, value, comment='', source='MANUAL', work=None):
    if work is not None:
        work = WorkItem.objects.select_for_update().get(pk=work.pk)
    lock_tree('locations')
    location = Location.objects.select_for_update().get(pk=location.pk)
    _temperature_permission(user, location, work)
    if not location.active or not location.kind.cold_storage:
        raise ValidationError(_('Choisissez un équipement froid actif.'))
    value = Decimal(str(value))
    if not value.is_finite() or not Decimal('-273.15') <= value <= Decimal('1000') or value != value.quantize(Decimal('0.01')):
        raise ValidationError(_('La température doit être finie, comprise entre −273,15 et 1 000 °C, avec au plus deux décimales.'))
    if timezone.is_naive(measured_at) or measured_at > timezone.now():
        raise ValidationError(_('Le relevé exige une date passée ou présente avec un fuseau horaire.'))
    if source not in ('MANUAL', 'IMPORT'):
        raise ValidationError(_('Origine du relevé non reconnue.'))
    abnormal = ((location.temperature_min is not None and value < location.temperature_min) or
                (location.temperature_max is not None and value > location.temperature_max))
    incident = None
    if abnormal:
        incident = StorageIncident.objects.filter(location=location, kind='TEMPERATURE', resolved_at__isnull=True).first()
        if incident is None:
            incident = StorageIncident.objects.create(location=location, kind='TEMPERATURE', started_at=measured_at,
                description=str(_('Température relevée hors de la plage configurée.')), actor=user)
            audit(user, incident, 'incident_opened')
    reading = TemperatureReading(location=location, measured_at=measured_at, value=value,
        minimum_snapshot=location.temperature_min, maximum_snapshot=location.temperature_max,
        out_of_range=abnormal, actor=user, source=source, comment=comment, incident=incident)
    reading.full_clean()
    reading.save()
    audit(user, reading, 'temperature_recorded')
    if work is not None:
        _transition(user, work, WorkItem.Status.SUBMITTED, comment or str(_('Relevé enregistré.')))
    return reading


@transaction.atomic
def create_incident(user, *, location, kind, started_at, description):
    lock_tree('locations')
    location = Location.objects.get(pk=location.pk)
    require(user, Capability.MANAGE_BIOBANK, location=location)
    if not description.strip() or timezone.is_naive(started_at) or started_at > timezone.now():
        raise ValidationError(_('Décrivez l’incident et vérifiez sa date de début.'))
    incident = StorageIncident(location=location, kind=kind, started_at=started_at,
        description=description.strip(), actor=user)
    incident.full_clean()
    incident.save()
    audit(user, incident, 'incident_opened')
    return incident


@transaction.atomic
def resolve_incident(user, pk, *, expected, resolved_at, corrective_action):
    require_manager = is_manager(user)
    if not require_manager:
        raise PermissionDenied
    incident = StorageIncident.objects.select_for_update().get(pk=pk)
    check_version(incident, expected)
    if incident.resolved_at is not None or not corrective_action.strip() or timezone.is_naive(resolved_at) or resolved_at > timezone.now():
        raise ValidationError(_('Justifiez la clôture d’un incident ouvert et vérifiez la date de résolution.'))
    before = snapshot(incident)
    incident.resolved_at, incident.corrective_action = resolved_at, corrective_action.strip()
    incident.version += 1
    incident.full_clean()
    incident.save()
    audit(user, incident, 'incident_closed', before)
    return incident


def transfer_plan(user, source, destination):
    require(user, Capability.MANAGE_BIOBANK, location=source)
    require(user, Capability.MANAGE_BIOBANK, location=destination)
    sources = LocationClosure.objects.filter(ancestor=source).values('descendant_id')
    targets = LocationClosure.objects.filter(ancestor=destination).values('descendant_id')
    if LocationClosure.objects.filter(ancestor=source, descendant=destination).exists() or LocationClosure.objects.filter(ancestor=destination, descendant=source).exists():
        raise ValidationError(_('Les sous-arbres source et destination doivent être disjoints.'))
    samples = list(biobank_scope(user).filter(location_id__in=sources, status__in=['STORED', 'QUARANTINE']).order_by('location__code', 'position__row', 'position__column', 'code'))
    if not samples or len(samples) > 5000:
        raise ValidationError(_('Sélectionnez un stockage contenant entre 1 et 5 000 échantillons à transférer.'))
    reserved = PositionReservation.objects.filter(active=True, until__gt=timezone.now()).exclude(assignee=user).values('position_id')
    positions = list(StoragePosition.objects.filter(location_id__in=targets, active=True, location__active=True,
        occupant__isnull=True).exclude(pk__in=reserved).select_related('location').order_by('location__code', 'row', 'column')[:len(samples)])
    if len(positions) < len(samples):
        raise ValidationError(_('Le stockage de destination ne possède pas assez de positions libres et accessibles.'))
    return [{'sample': str(sample.pk), 'code': sample.code, 'version': sample.version,
        'from_location': str(sample.location_id), 'from_label': str(sample.location),
        'from_position': str(sample.position_id) if sample.position_id else None,
        'to_location': str(position.location_id), 'to_label': str(position.location),
        'to_position': str(position.pk), 'position_label': str(position.row) + ':' + str(position.column)}
        for sample, position in zip(samples, positions)]


@transaction.atomic
def apply_transfer_plan(user, *, key, source, destination, mapping, reason, incident=None):
    lock_tree('locations')
    source, destination = Location.objects.get(pk=source.pk), Location.objects.get(pk=destination.pk)
    require(user, Capability.MANAGE_BIOBANK, location=source)
    require(user, Capability.MANAGE_BIOBANK, location=destination)
    key = _key(key)
    payload = {'source': source.pk, 'destination': destination.pk, 'mapping': mapping, 'reason': reason,
               'incident': incident.pk if incident else None}
    digest = _fingerprint(payload)
    existing = StorageTransfer.objects.filter(key=key).first()
    if existing:
        if existing.actor_id != user.pk or existing.payload_hash != digest:
            raise Conflict(_('L’identifiant de transfert est déjà associé à une autre opération.'))
        return existing
    if not reason.strip() or len(reason) > 500 or not isinstance(mapping, list) or not 1 <= len(mapping) <= 5000:
        raise ValidationError(_('Le transfert exige un motif et une liste contrôlée de 1 à 5 000 échantillons.'))
    if source.pk == destination.pk or LocationClosure.objects.filter(ancestor=source, descendant=destination).exists() or LocationClosure.objects.filter(ancestor=destination, descendant=source).exists():
        raise ValidationError(_('Les sous-arbres source et destination doivent être disjoints.'))
    if incident and incident.location_id != source.pk:
        raise ValidationError(_('L’incident doit concerner le stockage source.'))
    seen_samples, seen_positions = set(), set()
    for row in mapping:
        if row['sample'] in seen_samples or row['to_position'] in seen_positions:
            raise ValidationError(_('Le plan contient un échantillon ou une position en double.'))
        seen_samples.add(row['sample'])
        seen_positions.add(row['to_position'])
        sample = BiologicalSample.objects.select_for_update().get(pk=row['sample'])
        position = StoragePosition.objects.select_related('location').get(pk=row['to_position'])
        if not LocationClosure.objects.filter(ancestor=source, descendant_id=sample.location_id).exists() or str(sample.location_id) != row['from_location']:
            raise Conflict(_('La localisation d’un échantillon a changé depuis l’aperçu.'))
        if not LocationClosure.objects.filter(ancestor=destination, descendant_id=position.location_id).exists() or str(position.location_id) != row['to_location']:
            raise Conflict(_('Une position cible n’appartient plus au stockage de destination.'))
        transfer_sample(user, sample.pk, key=uuid.uuid5(key, str(sample.pk)), destination=position.location,
            position=position, reason=reason, expected=row['version'])
    transfer = StorageTransfer.objects.create(key=key, actor=user, source=source, destination=destination,
        mapping=mapping, payload_hash=digest, reason=reason, incident=incident)
    audit(user, transfer, 'mass_transfer', reason=reason)
    return transfer
