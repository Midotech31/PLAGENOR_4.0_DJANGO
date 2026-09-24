from decimal import Decimal
import hashlib

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.translation import gettext as _

from erp.cdc.catalog import document
from erp.cdc.schedule_adapter import managed_ids
from erp.models import (CdcClause, CdcClauseSelection, CdcClauseVersion, CdcCriterion,
                        CdcReviewDecision, CdcRevision, WorkItem)
from erp.permissions import is_manager, require_manager
from notifications.models import Notification
from .common import audit, check_version
from .work import _transition, require_work


REVIEW_ORDER = (
    CdcReviewDecision.Stage.TECHNICAL,
    CdcReviewDecision.Stage.ADMIN,
    CdcReviewDecision.Stage.FINANCIAL,
)


def apply_clause_selections(dossier, data):
    """Overlay the exact selected clause versions onto the dossier document data."""
    selections = dossier.clause_selections.select_related('clause', 'selected_version')
    paragraphs = dict(data.get('paragraphs', {}))
    for selection in selections:
        clause, version = selection.clause, selection.selected_version
        if clause.family != dossier.family or version.clause_id != clause.pk:
            raise ValidationError(_('La bibliothèque de clauses contient une liaison incohérente.'))
        paragraphs[clause.paragraph_id] = version.body
    data['paragraphs'] = paragraphs
    return data


def governance_snapshot(dossier):
    clauses = [{
        'code': row.clause.code,
        'paragraph_id': row.clause.paragraph_id,
        'version': row.selected_version.number,
        'sha256': row.selected_version.sha256,
    } for row in dossier.clause_selections.select_related('clause', 'selected_version').order_by('clause__code')]
    criteria = [{
        'code': row.code, 'lot': str(row.lot_id) if row.lot_id else None,
        'category': row.category, 'title': row.title, 'description': row.description,
        'expected_evidence': row.expected_evidence,
        'min_score': str(row.min_score) if row.min_score is not None else None,
        'max_score': str(row.max_score) if row.max_score is not None else None,
        'weight': str(row.weight), 'threshold': str(row.threshold) if row.threshold is not None else None,
        'formula': row.formula, 'rounding_rule': row.rounding_rule,
        'eliminatory': row.eliminatory, 'source': row.source,
        'justification': row.justification, 'position': row.position,
    } for row in dossier.criteria.filter(active=True).order_by('position', 'code')]
    return {'clauses': clauses, 'criteria': criteria}


def criteria_findings(dossier):
    criteria = list(dossier.criteria.filter(active=True).select_related('lot'))
    findings = []
    weighted = [row for row in criteria if row.weight > 0]
    if weighted:
        total = sum((row.weight for row in weighted), Decimal('0'))
        if total != Decimal('100'):
            findings.append({'severity': 'error', 'id': 'CRITERIA_WEIGHT_TOTAL',
                'message': _('La somme des pondérations actives doit être exactement égale à 100 %.')})
    for row in criteria:
        if row.lot_id and row.lot.dossier_id != dossier.pk:
            findings.append({'severity': 'error', 'id': 'CRITERION_LOT_SCOPE',
                'message': _('Un critère est rattaché à un lot extérieur au cahier des charges.')})
        if row.threshold is not None and row.max_score is not None and row.threshold > row.max_score:
            findings.append({'severity': 'error', 'id': 'CRITERION_THRESHOLD',
                'message': _('Le seuil d’un critère dépasse sa note maximale.')})
        if row.weight > 0 and row.max_score is None and not row.formula.strip():
            findings.append({'severity': 'error', 'id': 'CRITERION_METHOD',
                'message': _('Chaque critère pondéré doit préciser une note maximale ou une formule reproductible.')})
        if not row.source.strip():
            findings.append({'severity': 'error', 'id': 'CRITERION_SOURCE',
                'message': _('Chaque critère doit conserver sa source ou sa justification institutionnelle.')})
    return findings


def _editable_paragraph(dossier, paragraph_id):
    source = document(dossier.family)
    if paragraph_id not in source.paragraphs:
        raise ValidationError(_('Paragraphe documentaire inconnu.'))
    row = next((item for item in source.source_index if item['id'] == paragraph_id), None)
    managed, _ = managed_ids(dossier.family)
    if row is None or row['guard'] or paragraph_id in managed:
        raise ValidationError(_('Ce paragraphe est géré par une donnée structurée et ne peut pas devenir une clause libre.'))
    return row


@transaction.atomic
def publish_clause(user, dossier, *, expected, paragraph_id, title, category='', body='',
                   source='', mandatory=False, reason=''):
    require_manager(user)
    require_work(user, dossier.work, edit=True)
    check_version(dossier, expected)
    if not source.strip() or not reason.strip() or not title.strip():
        raise ValidationError(_('Le titre, la source et la justification sont obligatoires.'))
    row = _editable_paragraph(dossier, paragraph_id)
    text = body.strip()
    if not text:
        raise ValidationError(_('Une clause vide ne peut pas être publiée.'))
    code = hashlib.sha256((dossier.family + ':' + paragraph_id).encode()).hexdigest()[:24].upper()
    clause, created = CdcClause.objects.select_for_update().get_or_create(
        family=dossier.family, paragraph_id=paragraph_id,
        defaults={'code': code, 'title': title.strip(), 'category': category.strip(),
                  'mandatory': mandatory, 'created_by': user})
    if not created:
        clause.title, clause.category, clause.mandatory = title.strip(), category.strip(), mandatory
    number = (clause.versions.order_by('-number').values_list('number', flat=True).first() or 0) + 1
    digest = hashlib.sha256(text.encode()).hexdigest()
    version = CdcClauseVersion.objects.create(clause=clause, number=number, body=text,
        source=source.strip(), actor=user, sha256=digest)
    clause.current_version = version
    if not created:
        clause.version += 1
    clause.save()
    CdcClauseSelection.objects.update_or_create(dossier=dossier, clause=clause,
        defaults={'selected_version': version, 'selected_by': user, 'reason': reason.strip()})
    from .cdc import _revision
    revision = _revision(user, dossier, reason)
    audit(user, dossier, 'clause_version_selected', reason=clause.code + ' v' + str(version.number) + ' — ' + reason[:400])
    return clause, version, revision


@transaction.atomic
def select_clause(user, dossier, *, expected, clause, version, reason):
    require_work(user, dossier.work, edit=True)
    check_version(dossier, expected)
    if clause.family != dossier.family or version.clause_id != clause.pk or not clause.active:
        raise ValidationError(_('Cette version de clause ne peut pas être utilisée dans ce dossier.'))
    if not reason.strip():
        raise ValidationError(_('Justifiez le changement de version de clause.'))
    _editable_paragraph(dossier, clause.paragraph_id)
    CdcClauseSelection.objects.update_or_create(dossier=dossier, clause=clause,
        defaults={'selected_version': version, 'selected_by': user, 'reason': reason.strip()})
    from .cdc import _revision
    revision = _revision(user, dossier, reason)
    audit(user, dossier, 'clause_version_restored', reason=clause.code + ' v' + str(version.number) + ' — ' + reason[:400])
    return revision


@transaction.atomic
def save_criterion(user, dossier, *, expected, values, pk=None, reason=''):
    require_work(user, dossier.work, edit=True)
    check_version(dossier, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez la création ou la modification du critère.'))
    criterion = CdcCriterion.objects.select_for_update().get(pk=pk, dossier=dossier) if pk else CdcCriterion(dossier=dossier)
    lot = values.get('lot')
    if lot is not None and lot.dossier_id != dossier.pk:
        raise ValidationError(_('Le lot du critère doit appartenir à ce cahier des charges.'))
    for key, value in values.items():
        setattr(criterion, key, value)
    if criterion.threshold is not None and criterion.max_score is not None and criterion.threshold > criterion.max_score:
        raise ValidationError(_('Le seuil ne peut pas dépasser la note maximale.'))
    if criterion.weight > 0 and criterion.max_score is None and not criterion.formula.strip():
        raise ValidationError(_('Un critère pondéré doit préciser une note maximale ou une formule.'))
    criterion.full_clean()
    if pk:
        criterion.version += 1
    criterion.save()
    from .cdc import _revision
    revision = _revision(user, dossier, reason)
    audit(user, dossier, 'criterion_saved', reason=criterion.code + ' — ' + reason[:430])
    return criterion, revision


@transaction.atomic
def review_revision(user, revision, *, stage, decision, comment):
    dossier = revision.dossier
    require_work(user, dossier.work)
    if revision.number != dossier.revision_number:
        raise ValidationError(_('Seule la révision courante peut être examinée.'))
    if dossier.work.status != 'SUBMITTED':
        raise ValidationError(_('Le cahier des charges doit être soumis avant les revues formelles.'))
    if stage not in REVIEW_ORDER:
        raise ValidationError(_('Étape de revue inconnue.'))
    if decision not in CdcReviewDecision.Decision.values:
        raise ValidationError(_('Décision de revue inconnue.'))
    if stage == CdcReviewDecision.Stage.TECHNICAL:
        if not (is_manager(user) or dossier.work.assignee_id == user.pk):
            raise PermissionDenied
    else:
        require_manager(user)
    index = REVIEW_ORDER.index(stage)
    previous = revision.review_decisions.filter(stage__in=REVIEW_ORDER[:index])
    if previous.count() != index or previous.exclude(decision=CdcReviewDecision.Decision.APPROVED).exists():
        raise ValidationError(_('Les étapes précédentes doivent être approuvées dans l’ordre prévu.'))
    if revision.review_decisions.filter(stage=stage).exists():
        raise ValidationError(_('Cette étape a déjà été enregistrée pour la révision courante.'))
    if not comment.strip():
        raise ValidationError(_('Un compte rendu de revue est obligatoire.'))
    result = CdcReviewDecision.objects.create(revision=revision, stage=stage,
        decision=decision, actor=user, comment=comment.strip())
    if decision == CdcReviewDecision.Decision.CHANGES:
        _transition(user, dossier.work, WorkItem.Status.CHANGES_REQUESTED, comment.strip())
    target = dossier.work.assignee if decision == CdcReviewDecision.Decision.CHANGES else dossier.work.created_by
    audit(user, dossier, 'cdc_review_' + stage.lower(), reason=result.get_decision_display() + ' — ' + comment[:450])
    if target and target != user:
        Notification.objects.create(user=target, notification_type='STATUS_CHANGE',
            message=_('Revue CDC %(stage)s : %(decision)s') % {
                'stage': result.get_stage_display(), 'decision': result.get_decision_display()},
            link_url=reverse('erp:cdc-detail', args=[dossier.pk]), link_text=_('Consulter le cahier des charges'))
    return result


def review_summary(dossier):
    revision = dossier.revisions.filter(number=dossier.revision_number).first()
    if revision is None:
        return []
    by_stage = {row.stage: row for row in revision.review_decisions.select_related('actor')}
    return [{'stage': stage, 'label': CdcReviewDecision.Stage(stage).label, 'decision': by_stage.get(stage)}
            for stage in REVIEW_ORDER]
