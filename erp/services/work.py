from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from erp.models import WorkComment, WorkItem
from erp.permissions import TEAM_ROLES, is_manager, is_team, require_manager
from notifications.models import Notification
from .common import audit, check_version, snapshot


EDITABLE = (WorkItem.Status.DRAFT, WorkItem.Status.ASSIGNED,
            WorkItem.Status.IN_PROGRESS, WorkItem.Status.CHANGES_REQUESTED)


def work_scope(user):
    qs = WorkItem.objects.select_related('assignee', 'created_by', 'location', 'category')
    if not is_team(user):
        return qs.none()
    return qs if is_manager(user) else qs.filter(assignee=user).exclude(status=WorkItem.Status.CANCELLED)


def work_allowed(user, work, *, edit=False, costs=False):
    if not is_team(user):
        return False
    allowed = is_manager(user) or (work.assignee_id == user.pk and work.status != WorkItem.Status.CANCELLED)
    return bool(allowed and (not edit or work.status in EDITABLE)
                and (not costs or is_manager(user) or work.allow_costs))


def require_work(user, work, **kwargs):
    if not work_allowed(user, work, **kwargs):
        raise PermissionDenied


def _member(member):
    if member is None:
        return None
    member = get_user_model().objects.get(pk=member.pk)
    if not member.is_active or member.role not in TEAM_ROLES:
        raise ValidationError(_('Le responsable doit être un membre actif de l’équipe.'))
    return member


def _notify(work, user, message):
    if user is not None and user.is_active:
        Notification.objects.create(user=user, notification_type='ASSIGNMENT',
            message=message, link_url=reverse('erp:work-detail', args=[work.pk]),
            link_text=_('Consulter la tâche'))


@transaction.atomic
def create_work(user, *, kind, title, assignee=None, due_on=None, priority='NORMAL',
                instructions='', location=None, category=None, allow_costs=False):
    require_manager(user)
    assignee = _member(assignee)
    work = WorkItem(kind=kind, title=title.strip(), assignee=assignee, created_by=user,
        due_on=due_on, priority=priority, instructions=instructions, location=location,
        category=category, allow_costs=allow_costs,
        status=WorkItem.Status.ASSIGNED if assignee else WorkItem.Status.DRAFT)
    if allow_costs and kind not in (WorkItem.Kind.CDC, WorkItem.Kind.PLAN):
        raise ValidationError(_('Les estimations sont réservées aux dossiers d’approvisionnement.'))
    work.full_clean()
    work.save()
    audit(user, work, 'created')
    _notify(work, assignee, _('Une tâche vous a été affectée : %(title)s') % {'title': work.title})
    return work


@transaction.atomic
def delegate_work(user, pk, *, expected, assignee, due_on=None, priority='NORMAL',
                  instructions='', allow_costs=False, reason=''):
    require_manager(user)
    work = WorkItem.objects.select_for_update().get(pk=pk)
    check_version(work, expected)
    if work.status in (WorkItem.Status.APPROVED, WorkItem.Status.CANCELLED):
        raise ValidationError(_('Cette tâche est clôturée.'))
    member = _member(assignee)
    previous = work.assignee
    if previous is not None and previous != member and not reason.strip():
        raise ValidationError(_('Justifiez la réaffectation ou le retrait de la délégation.'))
    if allow_costs and work.kind not in (WorkItem.Kind.CDC, WorkItem.Kind.PLAN):
        raise ValidationError(_('Les estimations sont réservées aux dossiers d’approvisionnement.'))
    from .planning import before_delegation
    before_delegation(work, member)
    before = snapshot(work)
    work.assignee, work.due_on, work.priority = member, due_on, priority
    work.instructions, work.allow_costs = instructions, bool(member and allow_costs)
    if previous != member:
        work.status = WorkItem.Status.ASSIGNED if member else WorkItem.Status.DRAFT
        work.submitted_at = None
    work.version += 1
    work.full_clean()
    work.save()
    audit(user, work, 'delegated', before, reason)
    if previous != member:
        _notify(work, previous, _('Votre affectation a été retirée : %(title)s') % {'title': work.title})
    _notify(work, member, _('Votre affectation a été mise à jour : %(title)s') % {'title': work.title})
    return work


def _transition(user, work, state, reason=''):
    from .planning import before_transition
    before_transition(user, work, state, reason)
    before = snapshot(work)
    work.status = state
    work.version += 1
    if state == WorkItem.Status.SUBMITTED:
        work.submitted_at = timezone.now()
    if state == WorkItem.Status.APPROVED:
        work.approved_by, work.approved_at = user, timezone.now()
    work.save()
    if reason.strip():
        WorkComment.objects.create(work=work, actor=user, body=reason.strip())
    audit(user, work, 'status_changed', before, reason[:500])
    recipient = work.created_by if state == WorkItem.Status.SUBMITTED else work.assignee
    _notify(work, recipient, _('Tâche %(title)s : %(state)s') %
            {'title': work.title, 'state': work.get_status_display()})
    return work


@transaction.atomic
def transition_work(user, pk, *, expected, state, reason=''):
    work = WorkItem.objects.select_for_update().get(pk=pk)
    require_work(user, work)
    check_version(work, expected)
    if state == WorkItem.Status.IN_PROGRESS:
        require_work(user, work, edit=True)
    elif state == WorkItem.Status.SUBMITTED:
        require_work(user, work, edit=True)
        if work.kind in (WorkItem.Kind.CDC, WorkItem.Kind.INVENTORY, WorkItem.Kind.PLAN):
            raise ValidationError(_('Soumettez cette tâche depuis son dossier métier.'))
        if not reason.strip():
            raise ValidationError(_('Renseignez un compte rendu avant la soumission.'))
    elif state in (WorkItem.Status.CHANGES_REQUESTED, WorkItem.Status.APPROVED):
        require_manager(user)
        if work.status != WorkItem.Status.SUBMITTED:
            raise ValidationError(_('La tâche doit d’abord être soumise.'))
        if state == WorkItem.Status.APPROVED and work.kind in (WorkItem.Kind.CDC, WorkItem.Kind.INVENTORY, WorkItem.Kind.PLAN):
            raise ValidationError(_('Validez cette tâche depuis son dossier métier.'))
        if state == WorkItem.Status.CHANGES_REQUESTED and not reason.strip():
            raise ValidationError(_('Précisez les corrections demandées.'))
    elif state == WorkItem.Status.CANCELLED:
        require_manager(user)
        if work.status in (WorkItem.Status.APPROVED, WorkItem.Status.CANCELLED) or not reason.strip():
            raise ValidationError(_('Une annulation doit être justifiée et porter sur une tâche ouverte.'))
    else:
        raise ValidationError(_('Transition de tâche non autorisée.'))
    return _transition(user, work, state, reason)


@transaction.atomic
def comment_work(user, pk, body):
    work = WorkItem.objects.select_for_update().get(pk=pk)
    require_work(user, work)
    if not body.strip() or len(body) > 10000:
        raise ValidationError(_('Le compte rendu doit contenir entre 1 et 10 000 caractères.'))
    comment = WorkComment.objects.create(work=work, actor=user, body=body.strip())
    audit(user, work, 'commented', reason=body[:500])
    return comment
