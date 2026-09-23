from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import json
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (ActivityDependency, ActivitySchedule, AnalysisRun, AvailabilityBlock,
    BiologicalSample, LocationClosure, PlanningResource, RunAllocation, WorkItem)
from erp.permissions import is_manager, is_team, require_manager
from .common import Conflict, assign, audit, check_version, lock_tree, snapshot
from .links import request_scope
from .work import _member, _notify, create_work, require_work, work_scope


RELEASED = ('SUBMITTED', 'APPROVED', 'CANCELLED')
SPECIALIZED = ('CDC', 'INVENTORY', 'PLAN')
GENERIC_KINDS = tuple(code for code in WorkItem.Kind.values if code not in SPECIALIZED)


def interval(start, end):
    if not isinstance(start, datetime) or not isinstance(end, datetime) or timezone.is_naive(start) or timezone.is_naive(end):
        raise ValidationError(_('Les dates doivent comporter un fuseau horaire valide.'))
    if end <= start or end - start > timedelta(days=366):
        raise ValidationError(_('La fin doit suivre le début ; une activité ne peut pas dépasser 366 jours.'))


def schedule_scope(user):
    return ActivitySchedule.objects.filter(work__in=work_scope(user)).select_related(
        'work__assignee', 'request', 'run').prefetch_related('resources')


def conflicts(work, start, end, resource_ids, *, assignee=None):
    person = assignee if assignee is not None else work.assignee
    resource_ids = list(resource_ids)
    issues = []
    slots = ActivitySchedule.objects.filter(starts_at__lt=end, ends_at__gt=start).exclude(
        work_id=work.pk).exclude(work__status__in=RELEASED)
    now = timezone.now()
    if start <= now < end:
        live = ActivitySchedule.objects.filter(work__status='IN_PROGRESS', actual_started_at__isnull=False, actual_finished_at__isnull=True).exclude(work_id=work.pk)
        slots = ActivitySchedule.objects.filter(Q(pk__in=slots.values('pk')) | Q(pk__in=live.values('pk')))
    if person is not None:
        if slots.filter(work__assignee_id=person.pk).exists():
            issues.append(_('Le responsable est déjà affecté à une autre activité sur ce créneau.'))
        if AvailabilityBlock.objects.filter(active=True, member=person, starts_at__lt=end, ends_at__gt=start).exists():
            issues.append(_('Le responsable est indisponible sur ce créneau.'))
    if slots.filter(resources__pk__in=resource_ids).exists():
        issues.append(_('Un équipement ou une salle est déjà réservé sur ce créneau.'))
    if AvailabilityBlock.objects.filter(active=True, resource_id__in=resource_ids, starts_at__lt=end, ends_at__gt=start).exists():
        issues.append(_('Une ressource est indisponible ou en maintenance sur ce créneau.'))
    resources = PlanningResource.objects.filter(pk__in=resource_ids)
    if resources.count() != len(set(resource_ids)) or resources.filter(active=False).exists():
        issues.append(_('Une ressource sélectionnée est inconnue ou désactivée.'))
    for resource in resources.select_related('location'):
        if resource.location_id and LocationClosure.objects.filter(descendant_id=resource.location_id, ancestor__active=False).exists():
            issues.append(_('Une ressource se trouve dans un emplacement désactivé.'))
            break
    return issues


def _ordering(work, start, end):
    if work.prerequisites.filter(prerequisite__schedule__ends_at__gt=start).exists():
        raise ValidationError(_('Un prérequis est planifié après le début de cette activité.'))
    if work.successors.exclude(work__status__in=['APPROVED', 'CANCELLED']).filter(work__schedule__starts_at__lt=end).exists():
        raise ValidationError(_('Une activité dépendante commencerait avant la fin de ce créneau. Replanifiez-la explicitement.'))


def _clear_review(schedule):
    schedule.resources_checked_at = None
    schedule.resources_checked_by = None
    schedule.resource_check_note = ''


def _editable(work):
    if work.status in ('SUBMITTED', 'APPROVED', 'CANCELLED'):
        raise ValidationError(_('Le planning d’une activité soumise ou clôturée ne peut pas être modifié.'))


@transaction.atomic
def save_schedule(user, work_id, *, expected, starts_at, ends_at, resources=(), request=None, run=None, reason=''):
    require_manager(user)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=work_id)
    check_version(work, expected)
    _editable(work)
    lock_tree('planning')
    interval(starts_at, ends_at)
    schedule = ActivitySchedule.objects.filter(work=work).first()
    if schedule and not reason.strip():
        raise ValidationError(_('Justifiez la modification du planning.'))
    if run is not None:
        run = AnalysisRun.objects.get(pk=run.pk)
        if work.kind != 'ANALYSIS' or run.status in ('CANCELLED', 'COMPLETED'):
            raise ValidationError(_('Seule une activité analytique peut être rattachée à une série non annulée.'))
        if request is not None and request.pk != run.request_id:
            raise ValidationError(_('La série ne correspond pas à la demande sélectionnée.'))
        request = run.request
    if request is not None:
        from core.models import Request
        request = Request.objects.get(pk=request.pk)
        if request.archived or request.status in ('REJECTED', 'ARCHIVED'):
            raise ValidationError(_('La demande liée est rejetée ou archivée.'))
        # require_manager above grants the caller access to every request;
        # the assignee still needs their own explicit processing permission.
        if work.assignee_id and not request_scope(work.assignee, write=True).filter(pk=request.pk).exists():
            raise ValidationError(_('Le membre doit déjà être autorisé à traiter cette demande.'))
    ids = [resource.pk for resource in resources]
    failures = conflicts(work, starts_at, ends_at, ids)
    if failures:
        raise ValidationError(failures)
    _ordering(work, starts_at, ends_at)
    before = snapshot(schedule) if schedule else {}
    if schedule:
        before['resource_ids'] = sorted(str(pk) for pk in schedule.resources.values_list('pk', flat=True))
    schedule = schedule or ActivitySchedule(work=work)
    schedule.starts_at, schedule.ends_at = starts_at, ends_at
    schedule.request, schedule.run = request, run
    _clear_review(schedule)
    schedule.version += 1 if not schedule._state.adding else 0
    schedule.full_clean()
    schedule.save()
    schedule.resources.set(resources)
    work.due_on = timezone.localtime(ends_at).date()
    work.version += 1
    work.save(update_fields=['version', 'due_on', 'updated_at'])
    audit(user, schedule, 'scheduled', before, reason[:500])
    _notify(work, work.assignee, _('Le planning de votre activité a été défini ou modifié.'))
    return schedule


@transaction.atomic
def create_activity(user, *, key, kind, title, assignee, starts_at, ends_at, resources=(),
                    instructions='', priority='NORMAL', request=None, run=None, series=None):
    require_manager(user)
    try:
        key = uuid.UUID(str(key))
    except (ValueError, AttributeError, TypeError):
        raise ValidationError(_('Identifiant de création invalide.'))
    payload = {'kind': kind, 'title': title, 'assignee': assignee.pk if assignee else None,
        'start': starts_at, 'end': ends_at, 'resources': sorted(str(value.pk) for value in resources),
        'instructions': instructions, 'priority': priority,
        'request': request.pk if request else None, 'run': run.pk if run else None, 'series': series}
    digest = hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()
    lock_tree('planning-creation')
    previous = ActivitySchedule.objects.filter(creation_key=key).select_related('work').first()
    if previous:
        if previous.creation_hash != digest or previous.work.created_by_id != user.pk:
            raise Conflict(_('Cette clé de création appartient à une autre opération.'))
        return previous
    if kind not in GENERIC_KINDS:
        raise ValidationError(_('Créez le CDC, l’inventaire ou le plan depuis son module, puis planifiez sa tâche existante.'))
    interval(starts_at, ends_at)
    work = create_work(user, kind=kind, title=title, assignee=assignee,
        due_on=timezone.localtime(ends_at).date(), instructions=instructions, priority=priority)
    schedule = save_schedule(user, work.pk, expected=work.version, starts_at=starts_at, ends_at=ends_at,
        resources=resources, request=request, run=run)
    schedule.creation_key, schedule.creation_hash = key, digest
    schedule.save(update_fields=['creation_key', 'creation_hash'])
    return schedule


@transaction.atomic
def set_dependencies(user, work_id, *, expected, prerequisites, reason):
    require_manager(user)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=work_id)
    check_version(work, expected)
    _editable(work)
    lock_tree('planning')
    ids = {value.pk for value in prerequisites}
    if not reason.strip() or len(ids) > 100:
        raise ValidationError(_('Justifiez les prérequis et limitez-les à 100 activités.'))
    if WorkItem.objects.filter(pk__in=ids).count() != len(ids) or work.pk in ids:
        raise ValidationError(_('Un prérequis est inconnu ou correspond à l’activité elle-même.'))
    seen, frontier = set(), set(ids)
    while frontier:
        if work.pk in frontier:
            raise ValidationError(_('Ces dépendances formeraient un cycle.'))
        seen.update(frontier)
        if len(seen) > 10000:
            raise ValidationError(_('Le graphe de dépendances dépasse la limite de vérification.'))
        frontier = set(ActivityDependency.objects.filter(work_id__in=frontier).values_list('prerequisite_id', flat=True)) - seen
    before = {'prerequisite_ids': sorted(str(pk) for pk in work.prerequisites.values_list('prerequisite_id', flat=True))}
    work.prerequisites.exclude(prerequisite_id__in=ids).delete()
    existing = set(work.prerequisites.values_list('prerequisite_id', flat=True))
    ActivityDependency.objects.bulk_create([ActivityDependency(work=work, prerequisite_id=pk) for pk in ids-existing])
    schedule = ActivitySchedule.objects.filter(work=work).first()
    if schedule:
        _ordering(work, schedule.starts_at, schedule.ends_at)
        _clear_review(schedule)
        schedule.save()
    work.version += 1
    work.save(update_fields=['version', 'updated_at'])
    audit(user, work, 'dependencies_changed', before, reason[:500])
    return work


def _run_checks(schedule, at):
    run = schedule.run
    failures = []
    if run.status == 'CANCELLED' or run.request.archived or run.request.status in ('REJECTED', 'ARCHIVED'):
        return [_('La série ou sa demande est annulée, rejetée ou archivée.')]
    if run.status == 'COMPLETED':
        return [_('Les consommations de cette série sont déjà confirmées.')]
    from .stock import is_usable
    for requirement in run.requirements.select_related('article', 'unit'):
        allocated = Decimal(0)
        for allocation in RunAllocation.objects.filter(requirement=requirement).select_related('reservation__container__lot'):
            reservation = allocation.reservation
            container = reservation.container
            if is_usable(container) and (container.use_by is None or container.use_by >= timezone.localtime(at).date()):
                allocated += min(reservation.remaining, container.quantity)
        if allocated < requirement.quantity:
            failures.append(_('Les réservations utilisables ne couvrent pas toutes les quantités prévues pour la série.'))
            break
    inputs = list(run.inputs.select_related('sample'))
    if not inputs:
        failures.append(_('Aucun échantillon n’est identifié pour cette série.'))
    for item in inputs:
        sample = item.sample if item.sample_id else BiologicalSample.objects.filter(origin_request=run.request,
            source_key=item.source_key, source_fingerprint=item.source_fingerprint, parent__isnull=True).first()
        if sample is None or sample.status not in ('STORED', 'OUT') or sample.remaining_quantity <= 0:
            failures.append(_('Un échantillon de la série n’est pas réceptionné ou n’est pas utilisable.'))
            break
    return failures


def readiness(user, work, *, include_confirmation=True):
    require_work(user, work)
    schedule = ActivitySchedule.objects.filter(work=work).select_related('run__request', 'request').first()
    failures = []
    if schedule is None:
        return {'ready': False, 'issues': [_('Cette activité n’a pas encore de créneau.')], 'schedule': None}
    if work.assignee_id is None or not is_team(work.assignee):
        failures.append(_('Aucun responsable actif n’est affecté.'))
    elif schedule.request_id and not request_scope(work.assignee, write=True).filter(pk=schedule.request_id).exists():
        failures.append(_('Le responsable n’est plus autorisé à traiter la demande liée.'))
    if schedule.ends_at <= timezone.now() and work.status != 'IN_PROGRESS':
        failures.append(_('Le créneau prévu est terminé. Une replanification est nécessaire.'))
    if work.prerequisites.exclude(prerequisite__status='APPROVED').exists():
        failures.append(_('Un prérequis n’est pas encore validé.'))
    failures += conflicts(work, schedule.starts_at, schedule.ends_at, schedule.resources.values_list('pk', flat=True))
    if schedule.request_id and (schedule.request.archived or schedule.request.status in ('REJECTED', 'ARCHIVED')):
        failures.append(_('La demande liée est rejetée ou archivée.'))
    if schedule.run_id:
        failures += _run_checks(schedule, max(timezone.now(), schedule.ends_at))
    if include_confirmation and schedule.resources_checked_at is None:
        failures.append(_('La vérification des ressources et des documents requis reste à confirmer.'))
    return {'ready': not failures, 'issues': failures, 'schedule': schedule}


@transaction.atomic
def confirm_resources(user, work_id, *, expected, note):
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=work_id)
    require_work(user, work, edit=True)
    check_version(work, expected)
    lock_tree('locations')
    lock_tree('planning')
    result = readiness(user, work, include_confirmation=False)
    if result['issues']:
        raise ValidationError(result['issues'])
    if not note.strip() or len(note) > 2000:
        raise ValidationError(_('Décrivez la vérification des ressources et documents en 1 à 2 000 caractères.'))
    schedule = result['schedule']
    before = snapshot(schedule)
    schedule.resource_check_note, schedule.resources_checked_by = note.strip(), user
    schedule.resources_checked_at = timezone.now()
    schedule.save()
    work.version += 1
    work.save(update_fields=['version', 'updated_at'])
    audit(user, schedule, 'resources_checked', before)
    return schedule


def before_transition(user, work, state, reason):
    schedule = ActivitySchedule.objects.filter(work=work).first()
    if schedule is None:
        return
    lock_tree('locations')
    lock_tree('planning')
    if state == 'IN_PROGRESS' and work.status != 'IN_PROGRESS':
        result = readiness(user, work)
        if result['issues']:
            raise ValidationError(result['issues'])
        now = timezone.now()
        if not schedule.starts_at <= now < schedule.ends_at:
            raise ValidationError(_('Le démarrage est hors du créneau prévu. Faites replanifier l’activité.'))
        schedule.actual_started_at = schedule.actual_started_at or now
    elif state == 'SUBMITTED':
        if work.status != 'IN_PROGRESS' or not reason.strip():
            raise ValidationError(_('Une activité planifiée doit être démarrée puis accompagnée d’un compte rendu.'))
        if schedule.run_id and schedule.run.status != 'COMPLETED':
            raise ValidationError(_('Confirmez d’abord les consommations réelles dans la série analytique.'))
        schedule.actual_finished_at = timezone.now()
    elif state == 'CHANGES_REQUESTED':
        _clear_review(schedule)
        schedule.actual_finished_at = None
    schedule.save()


def before_delegation(work, member):
    schedule = ActivitySchedule.objects.filter(work=work).first()
    if schedule is None:
        return
    lock_tree('planning')
    if member is not None:
        failures = conflicts(work, schedule.starts_at, schedule.ends_at,
            schedule.resources.values_list('pk', flat=True), assignee=member)
        if failures:
            raise ValidationError(failures)
        if schedule.request_id and not request_scope(member, write=True).filter(pk=schedule.request_id).exists():
            raise ValidationError(_('Le nouveau responsable n’est pas autorisé à traiter la demande liée.'))
    _clear_review(schedule)
    schedule.save()


@transaction.atomic
def save_resource(user, values, *, pk=None, expected=None):
    require_manager(user)
    lock_tree('planning')
    resource = PlanningResource.objects.get(pk=pk) if pk else PlanningResource()
    if pk:
        check_version(resource, expected)
    before = snapshot(resource) if pk else None
    assign(resource, values)
    resource.full_clean()
    resource.version += 1 if pk else 0
    resource.save()
    if pk:
        for schedule in resource.schedules.exclude(work__status__in=RELEASED):
            _clear_review(schedule)
            schedule.version += 1
            schedule.save()
    audit(user, resource, 'resource_updated' if pk else 'resource_created', before)
    return resource


@transaction.atomic
def save_unavailability(user, *, starts_at, ends_at, reason, member=None, resource=None):
    require_manager(user)
    interval(starts_at, ends_at)
    member = _member(member)
    lock_tree('planning')
    block = AvailabilityBlock(starts_at=starts_at, ends_at=ends_at, member=member,
        resource=resource, reason=reason.strip(), created_by=user)
    block.full_clean()
    block.save()
    audit(user, block, 'unavailability_created')
    affected = ActivitySchedule.objects.filter(starts_at__lt=ends_at, ends_at__gt=starts_at).exclude(work__status__in=RELEASED)
    affected = affected.filter(work__assignee=member) if member else affected.filter(resources=resource)
    for slot in affected.select_related('work__assignee').distinct():
        _clear_review(slot)
        slot.version += 1
        slot.save()
        _notify(slot.work, slot.work.assignee, _('Une indisponibilité affecte votre activité. Son horaire n’a pas été déplacé automatiquement.'))
    return block


@transaction.atomic
def cancel_unavailability(user, pk, *, expected, reason):
    require_manager(user)
    lock_tree('planning')
    block = AvailabilityBlock.objects.get(pk=pk)
    check_version(block, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez la levée de l’indisponibilité.'))
    before = snapshot(block)
    block.active, block.version = False, block.version + 1
    block.save()
    audit(user, block, 'unavailability_cleared', before, reason[:500])
    return block


@transaction.atomic
def create_activity_series(user, *, frequency='ONCE', occurrences=1, **values):
    require_manager(user)
    if frequency not in ('ONCE', 'DAILY', 'WEEKLY') or type(occurrences) is not int or not 1 <= occurrences <= 60:
        raise ValidationError(_('Définissez une répétition valide de 1 à 60 occurrences.'))
    if (frequency == 'ONCE' and occurrences != 1) or (occurrences > 1 and values.get('run') is not None):
        raise ValidationError(_('Une série analytique doit être planifiée individuellement.'))
    try:
        key = uuid.UUID(str(values['key']))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_('Identifiant de création invalide.'))
    interval(values['starts_at'], values['ends_at'])
    results = []
    step = 7 if frequency == 'WEEKLY' else 1
    for index in range(occurrences):
        item = dict(values)
        item['key'] = key if index == 0 else uuid.uuid5(key, 'occurrence:' + str(index))
        item['series'] = {'frequency': frequency, 'occurrences': occurrences, 'index': index}
        item['starts_at'] = timezone.localtime(values['starts_at']) + timedelta(days=index*step)
        item['ends_at'] = timezone.localtime(values['ends_at']) + timedelta(days=index*step)
        results.append(create_activity(user, **item))
    return results
