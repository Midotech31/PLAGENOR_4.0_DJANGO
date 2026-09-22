from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (InventoryCampaign, InventoryLine, LocationClosure, StockContainer,
                       StockMovement, WorkItem)
from erp.permissions import require_manager
from .common import Conflict, audit, check_version, lock_tree, snapshot
from .stock import _article, _container, _movement, _post, stock_quantity
from .work import _transition, create_work, require_work


def inventory_containers(work):
    qs = StockContainer.objects.filter(active=True)
    if work.location_id:
        qs = qs.filter(location_id__in=LocationClosure.objects.filter(ancestor_id=work.location_id).values('descendant_id'))
    if work.category_id:
        qs = qs.filter(lot__article__category_id=work.category_id)
    return qs


@transaction.atomic
def create_inventory(user, *, title, assignee=None, location=None, category=None,
                     due_on=None, priority='NORMAL', blind=True, instructions=''):
    require_manager(user)
    work = create_work(user, kind=WorkItem.Kind.INVENTORY, title=title, assignee=assignee,
        location=location, category=category, due_on=due_on, priority=priority, instructions=instructions)
    lock_tree('locations')
    campaign = InventoryCampaign.objects.create(work=work, blind=blind)
    containers = inventory_containers(work).order_by('code')
    if not containers.exists():
        raise ValidationError(_('Aucun contenant actif ne correspond au périmètre de cet inventaire.'))
    InventoryLine.objects.bulk_create([InventoryLine(campaign=campaign, container=container,
        location=container.location, theoretical_quantity=container.quantity,
        container_version=container.version) for container in containers])
    audit(user, campaign, 'created')
    return campaign


@transaction.atomic
def count_inventory(user, pk, *, expected, container_version, amount, note=''):
    line = InventoryLine.objects.select_related('campaign').get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=line.campaign.work_id)
    require_work(user, work, edit=True)
    line = InventoryLine.objects.select_for_update().get(pk=pk)
    container = _container(line.container_id)
    check_version(line, expected)
    check_version(container, container_version)
    if container.location_id != line.location_id or not inventory_containers(work).filter(pk=container.pk).exists():
        raise ValidationError(_('Le contenant a quitté le périmètre prévu. Révisez la campagne avant de compter.'))
    amount = stock_quantity(amount, zero=True)
    before = snapshot(line)
    line.theoretical_quantity, line.container_version = container.quantity, container.version
    line.counted_quantity, line.counted_by, line.counted_at = amount, user, timezone.now()
    line.needs_recount, line.note, line.version = False, note, line.version + 1
    line.full_clean()
    line.save()
    audit(user, line, 'counted', before, note)
    if work.status != WorkItem.Status.IN_PROGRESS:
        _transition(user, work, WorkItem.Status.IN_PROGRESS)
    return line


@transaction.atomic
def submit_inventory(user, pk, *, expected, reason=''):
    campaign = InventoryCampaign.objects.get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=campaign.work_id)
    require_work(user, work, edit=True)
    check_version(work, expected)
    if campaign.lines.filter(Q(counted_quantity__isnull=True) | Q(needs_recount=True)).exists():
        raise ValidationError(_('Complétez tous les comptages et recomptages avant la soumission.'))
    return _transition(user, work, WorkItem.Status.SUBMITTED, reason)


@transaction.atomic
def recount_inventory(user, pk, *, expected, line_ids, reason):
    require_manager(user)
    campaign = InventoryCampaign.objects.get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=campaign.work_id)
    check_version(work, expected)
    if work.status != WorkItem.Status.SUBMITTED or not reason.strip():
        raise ValidationError(_('Le recomptage exige un inventaire soumis et une justification.'))
    lines = list(campaign.lines.select_for_update().filter(pk__in=line_ids))
    if not lines or len(lines) != len(set(str(pk) for pk in line_ids)):
        raise ValidationError(_('Sélectionnez des lignes de cet inventaire.'))
    for line in lines:
        before = snapshot(line)
        line.needs_recount, line.version = True, line.version + 1
        line.save()
        audit(user, line, 'recount_requested', before, reason[:500])
    return _transition(user, work, WorkItem.Status.CHANGES_REQUESTED, reason)


@transaction.atomic
def approve_inventory(user, pk, *, expected, key, reason):
    require_manager(user)
    campaign = InventoryCampaign.objects.get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=campaign.work_id)
    campaign.refresh_from_db()
    payload = {'campaign': campaign.pk, 'reason': reason}
    if campaign.adjustment_id:
        move, replay_created = _movement(user, key, StockMovement.Kind.INVENTORY, payload, reason=reason)
        if move.pk != campaign.adjustment_id:
            raise Conflict(_('Cet inventaire a déjà été validé.'))
        return move
    check_version(work, expected)
    if work.status != WorkItem.Status.SUBMITTED or not reason.strip():
        raise ValidationError(_('La validation exige un inventaire soumis et une justification.'))
    lines = list(campaign.lines.select_related('container__lot').order_by('container__lot__article_id', 'container_id'))
    for article_id in sorted({line.container.lot.article_id for line in lines}):
        _article(article_id)
    containers = {obj.pk: obj for obj in StockContainer.objects.select_for_update().filter(
        pk__in=[line.container_id for line in lines]).order_by('pk')}
    move, created = _movement(user, key, StockMovement.Kind.INVENTORY, payload, reason=reason)
    if not created:
        raise Conflict(_('Identifiant d’ajustement déjà utilisé.'))
    for line in lines:
        container = containers[line.container_id]
        if line.counted_quantity is None or line.needs_recount or line.container_version != container.version or line.location_id != container.location_id:
            raise Conflict(_('Un stock a changé depuis le comptage. Demandez un recomptage avant validation.'))
        _post(move, container, line.counted_quantity - container.quantity)
    campaign.adjustment, campaign.version = move, campaign.version + 1
    campaign.save()
    _transition(user, work, WorkItem.Status.APPROVED, reason)
    audit(user, campaign, 'approved', reason=reason)
    return move
