from decimal import Decimal, ROUND_CEILING, localcontext
import json
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import Request
from erp.models import (AnalysisRun, Article, BiologicalSample, Capability, ConsumptionProfile,
    ConsumptionRule, RunAllocation, RunBiologyEvent, RunConsumption, RunInput,
    RunOperation, RunRequirement, StockContainer, StockReservation, Unit)
from erp.permissions import is_manager, require_manager
from .biobank import _fingerprint, biobank_scope, sample_action, source_samples
from .catalog import convert_quantity
from .common import Conflict, assign, audit, check_version, lock_tree, snapshot
from .links import lock_request, request_scope, require_request
from .stock import _key, fefo, release_stock, remove_stock, reserve_stock, stock_quantity


def _assign_fields(instance, values, allowed):
    if set(values) - allowed:
        raise ValidationError(_('Champ de nomenclature non modifiable.'))
    return assign(instance, values)


@transaction.atomic
def save_profile(user, values, *, pk=None, expected=None):
    require_manager(user)
    profile = ConsumptionProfile.objects.select_for_update().get(pk=pk) if pk else ConsumptionProfile()
    if pk:
        check_version(profile, expected)
    before = snapshot(profile) if pk else None
    _assign_fields(profile, values, {'code', 'name', 'name_en', 'name_ar', 'active', 'service', 'reference_samples', 'protocol_reference', 'notes'})
    if pk:
        profile.version += 1
    profile.full_clean()
    profile.save()
    audit(user, profile, 'updated' if pk else 'created', before)
    return profile


@transaction.atomic
def save_rule(user, profile_id, values, *, expected, pk=None):
    require_manager(user)
    profile = ConsumptionProfile.objects.select_for_update().get(pk=profile_id)
    check_version(profile, expected)
    rule = ConsumptionRule.objects.get(pk=pk, profile=profile) if pk else ConsumptionRule(profile=profile)
    before = snapshot(rule) if pk else None
    _assign_fields(rule, values, {'article', 'quantity', 'unit', 'basis'})
    convert_quantity(rule.article, rule.quantity, rule.unit)
    rule.quantity = stock_quantity(rule.quantity)
    rule.full_clean()
    if pk:
        rule.version += 1
    rule.save()
    profile.version += 1
    profile.save()
    audit(user, rule, 'updated' if pk else 'created', before)
    return rule


def run_scope(user):
    return AnalysisRun.objects.filter(request__in=request_scope(user)).select_related('request', 'profile')


def _run(user, pk):
    identity = AnalysisRun.objects.get(pk=pk)
    request = lock_request(user, identity.request, allow_closed=True)
    run = AnalysisRun.objects.select_for_update().get(pk=pk)
    run.request = request
    return run


def _operation(user, run, key, kind, payload):
    key = _key(key)
    existing = RunOperation.objects.filter(key=key).first()
    if existing:
        if existing.run_id != run.pk or existing.actor_id != user.pk or existing.kind != kind or existing.payload_hash != _fingerprint(payload):
            raise Conflict(_('Cet identifiant a déjà été utilisé pour une autre opération analytique.'))
        return existing, False
    operation = RunOperation.objects.create(key=key, run=run, kind=kind, actor=user,
        payload_hash=_fingerprint(payload), data=json.loads(json.dumps(payload, default=str)))
    return operation, True


def _active(user, run, expected):
    require_request(user, run.request)
    check_version(run, expected)
    if run.status not in (AnalysisRun.Status.PLANNED, AnalysisRun.Status.RESERVED):
        raise ValidationError(_('Cette série analytique est clôturée.'))


def calculate_requirements(profile, sample_count):
    if not isinstance(sample_count, int) or isinstance(sample_count, bool) or not 1 <= sample_count <= 50000:
        raise ValidationError(_('Le nombre d’échantillons doit être compris entre 1 et 50 000.'))
    result = {}
    rules = list(profile.rules.select_related('article__base_unit', 'unit').all())
    if not profile.active or not rules:
        raise ValidationError(_('La nomenclature doit être active et comporter des consommations documentées.'))
    for rule in rules:
        if not rule.article.active:
            raise ValidationError(_('Un article de la nomenclature est désactivé.'))
        base, factor = convert_quantity(rule.article, rule.quantity, rule.unit)
        with localcontext() as context:
            context.prec = 60
            batches = Decimal(sample_count) / Decimal(profile.reference_samples)
            if rule.basis == ConsumptionRule.Basis.BATCH:
                batches = batches.to_integral_value(rounding=ROUND_CEILING)
            required = (base * batches).quantize(Decimal('0.000001'), rounding=ROUND_CEILING)
        required = stock_quantity(required)
        current = result.setdefault(rule.article_id, {'article': rule.article, 'quantity': Decimal(0), 'calculation': []})
        current['quantity'] += required
        stock_quantity(current['quantity'])
        current['calculation'].append({'basis': rule.basis, 'reference_samples': profile.reference_samples,
            'sample_count': sample_count, 'rule_quantity': str(rule.quantity), 'rule_unit': rule.unit.code,
            'conversion_factor': str(factor), 'calculated_quantity': str(required), 'rounding': 'CEILING_6_DECIMALS'})
    return list(result.values())


@transaction.atomic
def create_run(user, *, request, profile, code, name, sample_count, planned_on,
               source_keys=(), samples=(), incremental_demand=False, committed=False):
    request = lock_request(user, request)
    profile = ConsumptionProfile.objects.select_for_update().get(pk=profile.pk)
    if profile.service_id != request.service_id:
        raise ValidationError(_('La nomenclature doit correspondre au service de la demande.'))
    if committed or incremental_demand:
        require_manager(user)
    requirements = calculate_requirements(profile, sample_count)
    source = {row['key']: row for row in source_samples(user, request)}
    source_keys = list(source_keys)
    samples = list(samples)
    if len(set(source_keys)) != len(source_keys) or len({sample.pk for sample in samples}) != len(samples):
        raise ValidationError(_('Un échantillon ne peut pas être sélectionné deux fois dans la même série.'))
    inputs = []
    for key in source_keys:
        if key not in source:
            raise Conflict(_('Une identité source n’est plus présente dans la demande.'))
        row = source[key]
        inputs.append({'source_key': key, 'source_fingerprint': row['fingerprint'], 'label': row['code']})
    for sample in samples:
        sample = biobank_scope(user).get(pk=sample.pk)
        metadata = sample.shared_metadata
        if metadata.origin_request_id != request.pk or sample.status not in ('STORED', 'OUT'):
            raise ValidationError(_('Un échantillon stocké n’appartient pas à cette demande ou n’est pas disponible.'))
        if sample.parent_id is None and sample.source_key in source_keys:
            raise ValidationError(_('Ne sélectionnez pas simultanément la ligne source et sa réception physique.'))
        inputs.append({'sample': sample, 'source_key': 'stored:' + str(sample.pk), 'label': sample.code})
    if len(inputs) != sample_count:
        raise ValidationError(_('Le nombre d’identités sélectionnées doit correspondre au nombre d’échantillons de la série.'))
    run = AnalysisRun(code=code.strip().upper(), name=name.strip(), request=request, profile=profile,
        profile_snapshot=snapshot(profile), sample_count=sample_count, planned_on=planned_on,
        incremental_demand=incremental_demand, committed=committed, created_by=user)
    run.full_clean()
    run.save()
    for value in requirements:
        article = value['article']
        RunRequirement.objects.create(run=run, article=article, unit=article.base_unit,
            quantity=value['quantity'], article_snapshot=snapshot(article), calculation=value['calculation'])
    RunInput.objects.bulk_create([RunInput(run=run, **value) for value in inputs])
    audit(user, run, 'planned')
    return run


def reservation_proposal(user, run):
    require_request(user, run.request)
    proposal, shortages = [], []
    for requirement in run.requirements.select_related('article__base_unit').all():
        already = StockReservation.objects.filter(run_allocation__requirement=requirement).aggregate(total=Sum('remaining'))['total'] or Decimal(0)
        needed = max(Decimal(0), requirement.quantity - already)
        for container in fefo(user, requirement.article):
            amount = min(needed, container.quantity-container.reserved)
            if amount > 0:
                proposal.append({'requirement': str(requirement.pk), 'container': str(container.pk),
                    'article': requirement.article.code, 'label': container.code, 'quantity': str(amount),
                    'unit': requirement.unit.code, 'location': str(container.location),
                    'expires_on': str(container.use_by) if container.use_by else None})
                needed -= amount
            if needed == 0:
                break
        if needed > 0:
            shortages.append({'requirement': str(requirement.pk), 'article': requirement.article.code, 'quantity': str(needed), 'unit': requirement.unit.code})
    return {'allocations': proposal, 'shortages': shortages}


@transaction.atomic
def reserve_run(user, pk, *, expected, key, allocations, reason):
    run = _run(user, pk)
    payload = {'allocations': allocations, 'reason': reason}
    operation, created = _operation(user, run, key, 'RESERVE', payload)
    if not created:
        return operation
    _active(user, run, expected)
    if not isinstance(allocations, list) or not 1 <= len(allocations) <= 2000 or not reason.strip() or len(reason) > 500:
        raise ValidationError(_('La réservation exige des quantités et une justification explicites.'))
    lock_tree('locations')
    requirements = {str(row.pk): row for row in run.requirements.select_related('article', 'unit')}
    seen = set()
    for index, value in enumerate(allocations):
        if not isinstance(value, dict) or not {'requirement', 'container', 'quantity'} <= value.keys():
            raise ValidationError(_('Une ligne de réservation est incomplète.'))
        requirement = requirements.get(str(value['requirement']))
        if requirement is None:
            raise ValidationError(_('Un besoin ne correspond pas à cette série.'))
        container = StockContainer.objects.select_related('lot').get(pk=value['container'])
        if container.lot.article_id != requirement.article_id or container.pk in seen:
            raise ValidationError(_('Un contenant est incohérent ou sélectionné plusieurs fois.'))
        seen.add(container.pk)
        amount = stock_quantity(value['quantity'])
        reservation = reserve_stock(user, container.pk, key=uuid.uuid5(_key(key), str(index)), amount=amount,
            unit=requirement.unit, reference=run.code + ' — ' + reason[:200], request=run.request)
        RunAllocation.objects.create(requirement=requirement, reservation=reservation, operation=operation, quantity=amount)
    run.status, run.version = AnalysisRun.Status.RESERVED, run.version + 1
    run.save()
    audit(user, run, 'stock_reserved', reason=reason)
    return operation


@transaction.atomic
def confirm_run(user, pk, *, expected, key, actuals, biological_quantities=None, reason, confirmed):
    run = _run(user, pk)
    biological_quantities = biological_quantities or {}
    payload = {'actuals': actuals, 'biological_quantities': biological_quantities, 'reason': reason, 'confirmed': confirmed}
    operation, created = _operation(user, run, key, 'CONFIRM', payload)
    if not created:
        return operation
    _active(user, run, expected)
    if confirmed is not True or not reason.strip() or len(reason) > 500:
        raise ValidationError(_('Confirmez les consommations réelles et renseignez le compte rendu.'))
    allocations = {str(value.pk): value for value in RunAllocation.objects.filter(requirement__run=run).select_related(
        'requirement__unit', 'reservation__container')}
    if not allocations or not isinstance(actuals, dict) or not isinstance(biological_quantities, dict) or set(actuals) != set(allocations):
        raise ValidationError(_('Renseignez toutes les réservations de la série, y compris les quantités nulles.'))
    amounts = {key: stock_quantity(value, zero=True) for key, value in actuals.items()}
    if not any(amounts.values()):
        raise ValidationError(_('Une série sans consommation doit être annulée plutôt que déclarée réalisée.'))
    inputs = list(run.inputs.select_related('sample__unit').all())
    if set(biological_quantities) - {str(value.pk) for value in inputs if value.sample_id}:
        raise ValidationError(_('Une consommation biologique ne correspond pas à une entrée de la série.'))
    current_source = {value['key']: value['fingerprint'] for value in source_samples(user, run.request)}
    for value in inputs:
        if value.sample_id is None and current_source.get(value.source_key) != value.source_fingerprint:
            raise Conflict(_('Les informations d’un échantillon source ont changé depuis la planification.'))
    lock_tree('locations')
    for identity, allocation in allocations.items():
        amount = amounts[identity]
        reservation = allocation.reservation
        if amount > reservation.remaining:
            raise ValidationError(_('La consommation réelle dépasse la réservation. Complétez d’abord les allocations.'))
        if amount:
            movement = remove_stock(user, reservation.container_id, key=uuid.uuid5(_key(key), 'consume:' + identity),
                amount=amount, unit=allocation.requirement.unit, request=run.request, reservation=reservation,
                reason=(run.code + ' — ' + reason)[:500])
            RunConsumption.objects.create(run=run, requirement=allocation.requirement, container=reservation.container,
                quantity=amount, movement=movement, operation=operation)
        reservation.refresh_from_db()
        if reservation.remaining:
            release_stock(user, reservation.pk, key=uuid.uuid5(_key(key), 'release:' + identity),
                reason=(run.code + ' — ' + str(_('Solde de réservation libéré après confirmation.')))[:500])
    for value in inputs:
        if value.sample_id:
            amount = stock_quantity(biological_quantities.get(str(value.pk), 0), zero=True)
            event = sample_action(user, value.sample_id, key=uuid.uuid5(_key(key), 'sample:' + str(value.pk)),
                action='CONSUMPTION' if amount else 'ANALYSIS', reason=(run.code + ' — ' + reason)[:500],
                amount=amount if amount else None, unit=value.sample.unit if amount else None, request=run.request)
            RunBiologyEvent.objects.create(input=value, event=event, operation=operation)
    run.status, run.confirmed_by, run.confirmed_at = AnalysisRun.Status.COMPLETED, user, timezone.now()
    run.version += 1
    run.save()
    audit(user, run, 'consumption_confirmed', reason=reason)
    return operation


@transaction.atomic
def cancel_run(user, pk, *, expected, key, reason, allow_closed=False):
    run = _run(user, pk)
    operation, created = _operation(user, run, key, 'CANCEL', {'reason': reason})
    if not created:
        return operation
    check_version(run, expected)
    if not allow_closed:
        require_request(user, run.request)
    if run.status not in (AnalysisRun.Status.PLANNED, AnalysisRun.Status.RESERVED) or not reason.strip() or len(reason) > 500:
        raise ValidationError(_('Seule une série ouverte peut être annulée avec une justification.'))
    allocations = list(RunAllocation.objects.filter(requirement__run=run).select_related('reservation'))
    for allocation in allocations:
        if allocation.reservation.remaining:
            release_stock(user, allocation.reservation_id, key=uuid.uuid5(_key(key), str(allocation.pk)), reason=reason)
    run.status, run.version = AnalysisRun.Status.CANCELLED, run.version + 1
    run.save()
    audit(user, run, 'cancelled', reason=reason)
    return operation


@transaction.atomic
def close_request_resources(user, request, reason):
    reservations = StockReservation.objects.filter(request=request, remaining__gt=0)
    open_runs = AnalysisRun.objects.filter(request=request, status__in=[AnalysisRun.Status.PLANNED, AnalysisRun.Status.RESERVED])
    if not reservations.exists() and not open_runs.exists():
        return
    request = Request.objects.select_for_update().get(pk=request.pk)
    if request.status not in ('REJECTED', 'ARCHIVED') and not request.archived:
        raise ValidationError(_('La libération de clôture exige une demande rejetée ou archivée.'))
    if user is None or not user.is_authenticated or not user.is_active:
        raise PermissionDenied
    from .stock import _container, _movement, _post
    runs = list(open_runs.select_for_update().order_by('pk'))
    lock_tree('locations')
    for reservation in reservations.select_related('container__lot').order_by('container__lot__article_id', 'pk'):
        container = _container(reservation.container_id)
        reservation = StockReservation.objects.select_for_update().get(pk=reservation.pk)
        if reservation.remaining:
            before = snapshot(reservation)
            movement, created = _movement(user, uuid.uuid5(request.pk, 'close-reservation:' + str(reservation.pk)),
                'RELEASE', {'reservation': str(reservation.pk), 'closed_request': str(request.pk)},
                request=request, reason=reason[:500])
            if not created:
                raise Conflict(_('Une libération de clôture a déjà été enregistrée pour cette réservation.'))
            _post(movement, container, reserved=-reservation.remaining)
            reservation.remaining, reservation.version = Decimal(0), reservation.version + 1
            reservation.save()
            audit(user, reservation, 'released_on_request_closure', before, reason[:500])
    for run in runs:
        before = snapshot(run)
        _operation(user, run, uuid.uuid5(request.pk, 'close-run:' + str(run.pk)), 'CANCEL',
                   {'closed_request': str(request.pk), 'reason': reason[:500]})
        run.status, run.version = AnalysisRun.Status.CANCELLED, run.version + 1
        run.save()
        audit(user, run, 'cancelled_on_request_closure', before, reason[:500])


def lot_trace(user, lot):
    from erp.permissions import operational_scope
    containers = operational_scope(StockContainer.objects.filter(lot=lot), user)
    return RunConsumption.objects.filter(container__in=containers, run__request__in=request_scope(user)).select_related(
        'run__request', 'container', 'movement__actor').prefetch_related('run__inputs')
