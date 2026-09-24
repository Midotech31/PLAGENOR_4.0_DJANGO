import copy
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
from pathlib import Path
import tempfile
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pypdf import PdfReader

from documents.pdf_converter import convert_docx_to_pdf
from erp.cdc.catalog import controls, generate_document, initial_data, validate_data
from erp.cdc.consultation import FIELDS, validate_consultation
from erp.cdc.docengine import DocumentError, sha
from erp.cdc.governance_annex import append_governance_annex
from erp.cdc.lot_catalog import get_catalog, validate_catalog
from erp.cdc.word_layout import normalize_word_layout
from erp.models import (Article, CdcApproval, CdcClause, CdcClauseRevision, CdcClauseSelection,
                        CdcCriterion, CdcDossier, CdcGeneration, CdcItem, CdcLot, CdcRequirement,
                        CdcReviewDecision, CdcRevision, LocationClosure, Party, StockContainer,
                        Unit, WorkItem)
from erp.permissions import Capability, grants, is_manager, operational_scope, permitted, require, require_manager
from .catalog import convert_quantity
from .common import Conflict, audit, check_version, snapshot
from .stock import stock_quantity, usable_filter
from .work import _transition, create_work, require_work, work_allowed, work_scope


ITEM_FIELDS = {'designation', 'specifications', 'unit_label', 'packaging', 'quantity', 'details', 'active'}
ESTIMATE_FIELDS = {'estimate_supplier', 'estimated_price', 'tax_rate', 'price_source', 'currency'}
CDC_REVIEW_CAPABILITY = {
    CdcReviewDecision.Stage.TECHNICAL: Capability.REVIEW_CDC_TECHNICAL,
    CdcReviewDecision.Stage.ADMIN_LEGAL: Capability.REVIEW_CDC_ADMIN,
    CdcReviewDecision.Stage.FINANCIAL: Capability.REVIEW_CDC_FINANCIAL,
}


CDC_READ_CAPABILITIES = (
    Capability.REVIEW_CDC_TECHNICAL,
    Capability.REVIEW_CDC_ADMIN,
    Capability.REVIEW_CDC_FINANCIAL,
    Capability.APPROVE_CDC,
)


def _capability_scope(user):
    condition = Q(pk__in=[])
    for capability in CDC_READ_CAPABILITIES:
        for grant in grants(user, capability):
            scope = Q()
            if grant.category_id:
                scope &= Q(work__category_id=grant.category_id)
            if grant.location_id:
                descendants = LocationClosure.objects.filter(
                    ancestor_id=grant.location_id).values('descendant_id')
                scope &= Q(work__location_id__in=descendants)
            if not scope:
                return Q()
            condition |= scope
    return condition


def _cdc_read_allowed(user, work):
    if work_allowed(user, work):
        return True
    return any(permitted(user, capability, location=work.location, category=work.category)
               for capability in CDC_READ_CAPABILITIES)


def dossier_scope(user):
    qs = CdcDossier.objects.select_related('work', 'work__assignee')
    if is_manager(user):
        return qs
    own = Q(work__in=work_scope(user))
    review = _capability_scope(user)
    return qs.filter(own | review).distinct()


def _dossier(user, pk, *, edit=False):
    identity = CdcDossier.objects.values('work_id').get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=identity['work_id'])
    if edit:
        require_work(user, work, edit=True)
    elif not _cdc_read_allowed(user, work):
        raise PermissionDenied
    dossier = CdcDossier.objects.select_for_update().get(pk=pk)
    dossier.work = work
    if edit and dossier.archived_at is not None:
        raise ValidationError(_('Un cahier des charges archivé est en lecture seule.'))
    return dossier


def document_data(dossier):
    data = copy.deepcopy(dossier.data)
    data['reference'] = dossier.reference
    lots = []
    for position, lot in enumerate(dossier.lots.filter(active=True).prefetch_related('items').order_by('position'), 1):
        items = []
        for item in lot.items.all():
            if item.active:
                items.append({'key': item.source_key, 'position': len(items) + 1,
                    'designation': item.designation, 'specifications': item.specifications,
                    'unit': item.unit_label, 'packaging': item.packaging,
                    'quantity': format(item.quantity, 'f'), 'details': item.details})
        lots.append({'id': str(lot.pk), 'number': position, 'name': lot.name,
                     'name_ar': lot.name_ar, 'source_slot': lot.source_slot, 'items': items})
    data['lot_catalog'] = {'schema': 1, 'lots': lots}
    data['requirements'] = [
        {'item': str(requirement.item_id), 'item_key': requirement.item.source_key, 'lot': str(requirement.item.lot_id), 'position': requirement.position, 'kind': requirement.kind,
         'statement': requirement.statement, 'evidence': requirement.evidence,
         'verification_method': requirement.verification_method, 'justification': requirement.justification}
        for requirement in CdcRequirement.objects.filter(
            item__lot__dossier=dossier, item__active=True, item__lot__active=True, active=True
        ).select_related('item__lot').order_by('item__lot__position', 'item__position', 'position', 'id')
    ]
    data['criteria'] = [
        {'code': criterion.code, 'lot': str(criterion.lot_id) if criterion.lot_id else None,
         'title': criterion.title, 'method': criterion.method, 'weight': str(criterion.weight),
         'threshold': str(criterion.threshold) if criterion.threshold is not None else None,
         'eliminatory': criterion.eliminatory, 'evidence': criterion.evidence,
         'position': criterion.position}
        for criterion in dossier.criteria.filter(active=True).order_by('lot_id', 'position', 'id')
    ]
    data['clauses'] = [
        {'code': selection.revision.clause.code, 'revision': selection.revision.number, 'revision_id': str(selection.revision_id),
         'title': selection.revision.clause.title, 'text_fr': selection.revision.text_fr,
         'text_en': selection.revision.text_en, 'text_ar': selection.revision.text_ar,
         'source': selection.revision.source_reference, 'mandatory': selection.mandatory,
         'position': selection.position}
        for selection in dossier.clause_selections.filter(active=True).select_related(
            'revision__clause').order_by('position', 'id')
    ]
    data.pop('procurement', None)
    validate_data(data, dossier.family)
    return data


def _estimates(dossier):
    return [{'id': str(item.pk), 'article': str(item.article_id) if item.article_id else None,
             'article_snapshot': item.article_snapshot, 'lot': str(item.lot_id), 'active': item.active,
             'quantity': str(item.quantity), 'purchase_unit': str(item.purchase_unit_id) if item.purchase_unit_id else None,
             'base_factor': str(item.base_factor) if item.base_factor is not None else None,
             'supplier': str(item.estimate_supplier_id) if item.estimate_supplier_id else None,
             'supplier_snapshot': snapshot(item.estimate_supplier) if item.estimate_supplier_id else None,
             'price': str(item.estimated_price) if item.estimated_price is not None else None,
             'tax_rate': str(item.tax_rate) if item.tax_rate is not None else None,
             'currency': item.currency, 'source': item.price_source}
            for item in CdcItem.objects.filter(lot__dossier=dossier).order_by('lot__position', 'position', 'id')]


def _revision(user, dossier, reason=''):
    data, estimates = document_data(dossier), _estimates(dossier)
    digest = hashlib.sha256(json.dumps({'document': data, 'estimates': estimates}, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    dossier.revision_number += 1
    dossier.version += 1
    dossier.save()
    revision = CdcRevision.objects.create(dossier=dossier, number=dossier.revision_number, actor=user,
        data=data, estimates=estimates, sha256=digest, reason=reason[:500])
    audit(user, dossier, 'revision_created', reason=reason[:500])
    return revision




def governance_snapshot_findings(data):
    """Validate only the immutable CDC Toolkit payload stored in one revision."""
    findings = []
    requirements = data.get('requirements', [])
    criteria = data.get('criteria', [])
    clauses = data.get('clauses', [])
    if not all(isinstance(value, list) for value in (requirements, criteria, clauses)):
        return [{'severity': 'error', 'code': 'governance-structure', 'field': 'governance',
            'source': 'CDC Toolkit', 'message': str(_('Les données CDC structurées de la révision sont invalides.'))}]
    if len(requirements) + len(criteria) + len(clauses) > 5000:
        findings.append({'severity': 'error', 'code': 'governance-size', 'field': 'governance',
            'source': 'CDC Toolkit', 'message': str(_('Les données CDC structurées dépassent la limite autorisée.'))})
        return findings

    allowed_kinds = {value for value, _ in CdcRequirement.Kind.choices}
    for row in requirements:
        if not isinstance(row, dict) or row.get('kind') not in allowed_kinds or not str(row.get('statement', '')).strip():
            findings.append({'severity': 'error', 'code': 'requirement-structure', 'field': 'requirements',
                'source': 'CDC Toolkit', 'message': str(_('Une exigence structurée de la révision est invalide.'))})
            continue
        if row['kind'] != CdcRequirement.Kind.INFORMATIONAL:
            if not str(row.get('evidence', '')).strip():
                findings.append({'severity': 'error', 'code': 'requirement-evidence',
                    'field': 'requirements', 'source': 'CDC Toolkit',
                    'message': str(_('Une exigence non informative doit préciser la preuve attendue.'))})
            if not str(row.get('verification_method', '')).strip():
                findings.append({'severity': 'error', 'code': 'requirement-verification',
                    'field': 'requirements', 'source': 'CDC Toolkit',
                    'message': str(_('Une exigence non informative doit préciser sa méthode de vérification.'))})
        if row['kind'] == CdcRequirement.Kind.ELIMINATORY and not str(row.get('justification', '')).strip():
            findings.append({'severity': 'error', 'code': 'requirement-eliminatory-justification',
                'field': 'requirements', 'source': 'CDC Toolkit',
                'message': str(_('Une exigence éliminatoire doit être explicitement justifiée.'))})

    allowed_methods = {value for value, _ in CdcCriterion.Method.choices}
    scopes = {}
    global_seen = lot_seen = False
    for row in criteria:
        try:
            weight = Decimal(str(row['weight']))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            weight = Decimal('-1')
        if (not isinstance(row, dict) or not str(row.get('code', '')).strip()
                or not str(row.get('title', '')).strip() or row.get('method') not in allowed_methods
                or weight < 0 or weight > 100):
            findings.append({'severity': 'error', 'code': 'criterion-structure', 'field': 'criteria',
                'source': 'CDC Toolkit', 'message': str(_('Un critère structuré de la révision est invalide.'))})
            continue
        scope = row.get('lot')
        global_seen = global_seen or scope is None
        lot_seen = lot_seen or scope is not None
        scopes[scope] = scopes.get(scope, Decimal(0)) + weight
        if row.get('eliminatory') and not str(row.get('evidence', '')).strip():
            findings.append({'severity': 'error', 'code': 'criterion-evidence', 'field': 'criteria',
                'source': 'CDC Toolkit',
                'message': str(_('Un critère éliminatoire doit préciser le justificatif attendu.'))})
    if global_seen and lot_seen:
        findings.append({'severity': 'error', 'code': 'criteria-scope-mixed', 'field': 'criteria',
            'source': 'CDC Toolkit', 'message': str(_('Ne mélangez pas une grille globale avec des grilles par lot.'))})
    for scope, total in scopes.items():
        if total != Decimal('100'):
            findings.append({'severity': 'error', 'code': 'criteria-total',
                'field': 'criteria' if scope is None else f'lot:{scope}', 'source': 'CDC Toolkit',
                'message': str(_('Les pondérations actives doivent totaliser exactement 100 points par périmètre.'))})

    for row in clauses:
        if (not isinstance(row, dict) or not str(row.get('code', '')).strip()
                or not isinstance(row.get('revision'), int) or row['revision'] < 1
                or not str(row.get('text_fr', '')).strip() or not str(row.get('source', '')).strip()):
            findings.append({'severity': 'error', 'code': 'clause-structure', 'field': 'clauses',
                'source': 'CDC Toolkit', 'message': str(_('Une clause versionnée de la révision est invalide.'))})
    return findings


def governance_findings(dossier):
    """Validate the current dossier and current clause-governance state."""
    data = document_data(dossier)
    findings = governance_snapshot_findings(data)
    for selection in dossier.clause_selections.filter(active=True).select_related('revision'):
        if selection.revision.status != CdcClauseRevision.Status.ACTIVE:
            findings.append({'severity': 'error', 'code': 'clause-not-active',
                'field': f'clause:{selection.pk}', 'source': 'CDC Toolkit',
                'message': str(_('Une clause retenue doit pointer vers une révision validée et active.'))})
    return findings

def dossier_findings(dossier):
    data = document_data(dossier)
    findings = [*controls(data), *governance_snapshot_findings(data)]
    for selection in dossier.clause_selections.filter(active=True).select_related('revision'):
        if selection.revision.status != CdcClauseRevision.Status.ACTIVE:
            findings.append({'severity': 'error', 'code': 'clause-not-active',
                'field': f'clause:{selection.pk}', 'source': 'CDC Toolkit',
                'message': str(_('Une clause retenue doit pointer vers une révision validée et active.'))})
    return findings


@transaction.atomic
def save_requirement(user, item_id, *, expected, values, pk=None, reason=''):
    item = CdcItem.objects.select_related('lot__dossier__work').get(pk=item_id)
    dossier = _dossier(user, item.lot.dossier_id, edit=True)
    check_version(dossier, expected)
    requirement = CdcRequirement.objects.get(pk=pk, item=item) if pk else CdcRequirement(item=item)
    for key in ('position', 'kind', 'statement', 'evidence', 'verification_method', 'justification', 'active'):
        if key in values:
            setattr(requirement, key, values[key])
    if requirement.kind != CdcRequirement.Kind.INFORMATIONAL:
        if not requirement.evidence.strip() or not requirement.verification_method.strip():
            raise ValidationError(_('Une exigence non informative exige une preuve et une méthode de vérification.'))
    if requirement.kind == CdcRequirement.Kind.ELIMINATORY and not requirement.justification.strip():
        raise ValidationError(_('Justifiez toute exigence éliminatoire.'))
    if pk:
        requirement.version += 1
    requirement.full_clean()
    requirement.save()
    audit(user, dossier, 'cdc_requirement_saved', reason=reason[:500])
    return _revision(user, dossier, reason)


@transaction.atomic
def save_criterion(user, dossier_id, *, expected, values, pk=None, reason=''):
    dossier = _dossier(user, dossier_id, edit=True)
    check_version(dossier, expected)
    criterion = CdcCriterion.objects.get(pk=pk, dossier=dossier) if pk else CdcCriterion(dossier=dossier)
    lot = values.get('lot')
    if lot is not None and lot.dossier_id != dossier.pk:
        raise ValidationError(_('Le lot sélectionné ne correspond pas à ce cahier des charges.'))
    for key in ('lot', 'code', 'title', 'method', 'weight', 'threshold',
                'eliminatory', 'evidence', 'position', 'active'):
        if key in values:
            setattr(criterion, key, values[key])
    if criterion.eliminatory and not criterion.evidence.strip():
        raise ValidationError(_('Un critère éliminatoire doit préciser le justificatif attendu.'))
    if pk:
        criterion.version += 1
    criterion.full_clean()
    criterion.save()
    audit(user, dossier, 'cdc_criterion_saved', reason=reason[:500])
    return _revision(user, dossier, reason)




@transaction.atomic
def save_clause(user, *, values, pk=None, reason=''):
    require_manager(user)
    clause = CdcClause.objects.select_for_update().get(pk=pk) if pk else CdcClause()
    before = snapshot(clause) if pk else {}
    for key in ('code', 'name', 'name_en', 'name_ar', 'title', 'active'):
        if key in values:
            setattr(clause, key, values[key])
    clause.code = clause.code.strip().upper()
    clause.name = clause.name.strip()
    clause.title = clause.title.strip()
    if not clause.code or not clause.name or not clause.title:
        raise ValidationError(_('Le code, la désignation et l’intitulé de la clause sont obligatoires.'))
    if pk:
        clause.version += 1
    clause.full_clean()
    clause.save()
    audit(user, clause, 'clause_saved', before, reason[:500])
    return clause


@transaction.atomic
def create_clause_revision(user, clause, *, text_fr, source_reference, text_en='', text_ar='',
                           activate=False):
    require_manager(user)
    clause = CdcClause.objects.select_for_update().get(pk=clause.pk)
    text_fr, source_reference = text_fr.strip(), source_reference.strip()
    if not text_fr or not source_reference:
        raise ValidationError(_('Le texte français et la source de la clause sont obligatoires.'))
    number = (clause.revisions.order_by('-number').values_list('number', flat=True).first() or 0) + 1
    digest = hashlib.sha256(json.dumps(
        {'text_fr': text_fr, 'text_en': text_en.strip(), 'text_ar': text_ar.strip(),
         'source': source_reference}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    revision = CdcClauseRevision.objects.create(clause=clause, number=number, actor=user,
        text_fr=text_fr, text_en=text_en.strip(), text_ar=text_ar.strip(),
        source_reference=source_reference,
        status=CdcClauseRevision.Status.ACTIVE if activate else CdcClauseRevision.Status.DRAFT,
        sha256=digest)
    if activate:
        clause.active_revision = revision
        clause.version += 1
        clause.save(update_fields=['active_revision', 'version', 'updated_at'])
    audit(user, clause, 'clause_revision_created', reason=str(number))
    return revision


@transaction.atomic
def select_clause(user, dossier_id, *, expected, revision, position=1, mandatory=False, note='', active=True, reason=''):
    dossier = _dossier(user, dossier_id, edit=True)
    check_version(dossier, expected)
    revision = CdcClauseRevision.objects.select_related('clause').get(pk=revision.pk)
    if revision.status != CdcClauseRevision.Status.ACTIVE or revision.clause.active_revision_id != revision.pk:
        raise ValidationError(_('Sélectionnez uniquement la révision active et validée de la clause.'))
    selection, created = CdcClauseSelection.objects.get_or_create(dossier=dossier, revision=revision,
        defaults={'position': position, 'mandatory': mandatory, 'note': note, 'active': active})
    if not created:
        selection.position, selection.mandatory, selection.note, selection.active = position, mandatory, note, active
        selection.version += 1
        selection.save()
    audit(user, dossier, 'cdc_clause_selected', reason=reason[:500])
    return _revision(user, dossier, reason)


@transaction.atomic
def review_dossier(user, dossier_id, *, expected, stage, outcome, comment):
    capability = CDC_REVIEW_CAPABILITY.get(stage)
    if capability is None:
        raise ValidationError(_('Étape de revue CDC inconnue.'))
    dossier = _dossier(user, dossier_id)
    if not permitted(user, capability, location=dossier.work.location, category=dossier.work.category):
        raise PermissionDenied
    check_version(dossier, expected)
    if dossier.work.status != WorkItem.Status.SUBMITTED:
        raise ValidationError(_('Le cahier des charges doit être soumis avant sa revue.'))
    comment = comment.strip()
    if not comment:
        raise ValidationError(_('Le compte rendu de revue est obligatoire.'))
    revision = dossier.revisions.get(number=dossier.revision_number)
    if CdcReviewDecision.objects.filter(revision=revision, stage=stage).exists():
        raise ValidationError(_('Cette étape de revue a déjà été enregistrée pour la révision courante.'))
    decision = CdcReviewDecision.objects.create(dossier=dossier, revision=revision, stage=stage,
        outcome=outcome, actor=user, comment=comment)
    audit(user, dossier, 'cdc_review_recorded', reason=f'{stage}:{outcome}')
    if outcome == CdcReviewDecision.Outcome.CHANGES:
        _transition(user, dossier.work, WorkItem.Status.CHANGES_REQUESTED, comment)
    else:
        from .work import _notify
        if dossier.work.assignee_id:
            _notify(dossier.work, dossier.work.assignee, _('Une étape de revue du cahier des charges a été validée.'))
    return decision


def review_state(dossier):
    revision = dossier.revisions.filter(number=dossier.revision_number).first()
    decisions = {row.stage: row for row in CdcReviewDecision.objects.filter(revision=revision)} if revision else {}
    required = [CdcReviewDecision.Stage.TECHNICAL, CdcReviewDecision.Stage.ADMIN_LEGAL]
    if dossier.work.allow_costs:
        required.append(CdcReviewDecision.Stage.FINANCIAL)
    return {'revision': revision, 'decisions': decisions, 'required': required,
            'complete': all(stage in decisions and decisions[stage].outcome == CdcReviewDecision.Outcome.APPROVED
                            for stage in required)}




def restore_governance_snapshot(user, dossier, data):
    """Restore the current structured CDC state from one immutable revision snapshot."""
    CdcRequirement.objects.filter(item__lot__dossier=dossier, active=True).update(active=False)
    item_by_key = {item.source_key: item for item in CdcItem.objects.filter(
        lot__dossier=dossier, lot__active=True, active=True).select_related('lot')}
    for row in data.get('requirements', []):
        item = item_by_key.get(row.get('item_key'))
        if item is None:
            continue
        CdcRequirement.objects.update_or_create(item=item, position=row['position'], defaults={
            'kind': row['kind'], 'statement': row['statement'], 'evidence': row.get('evidence', ''),
            'verification_method': row.get('verification_method', ''), 'justification': row.get('justification', ''),
            'active': True})

    dossier.criteria.update(active=False)
    active_lots = {str(lot.pk): lot for lot in dossier.lots.filter(active=True)}
    for row in data.get('criteria', []):
        lot = active_lots.get(row.get('lot')) if row.get('lot') else None
        CdcCriterion.objects.update_or_create(dossier=dossier, code=row['code'], defaults={
            'lot': lot, 'title': row['title'], 'method': row['method'], 'weight': Decimal(row['weight']),
            'threshold': Decimal(row['threshold']) if row.get('threshold') is not None else None,
            'eliminatory': bool(row.get('eliminatory')), 'evidence': row.get('evidence', ''),
            'position': row.get('position', 1), 'active': True})

    dossier.clause_selections.update(active=False)
    for row in data.get('clauses', []):
        revision = None
        if row.get('revision_id'):
            revision = CdcClauseRevision.objects.filter(pk=row['revision_id']).first()
        if revision is None:
            revision = CdcClauseRevision.objects.filter(
                clause__code=row.get('code'), number=row.get('revision')).first()
        if revision is None:
            continue
        CdcClauseSelection.objects.update_or_create(dossier=dossier, revision=revision, defaults={
            'position': row.get('position', 1), 'mandatory': bool(row.get('mandatory')),
            'note': '', 'active': True})
    audit(user, dossier, 'cdc_governance_restored')


@transaction.atomic
def create_dossier(user, *, family, reference, title, assignee=None, due_on=None,
                   priority='NORMAL', allow_costs=False, instructions=''):
    require_manager(user)
    data = initial_data(family)
    data['reference'] = reference.strip()
    validate_data(data, family)
    work = create_work(user, kind=WorkItem.Kind.CDC, title=title, assignee=assignee,
        due_on=due_on, priority=priority, allow_costs=allow_costs, instructions=instructions)
    dossier = CdcDossier(work=work, family=family, reference=reference.strip(), data=data)
    dossier.full_clean()
    dossier.save()
    for value in get_catalog(data)['lots']:
        lot = CdcLot.objects.create(dossier=dossier, position=value['number'], name=value['name'],
            name_ar=value['name_ar'], source_slot=value['source_slot'])
        for row in value['items']:
            CdcItem.objects.create(lot=lot, source_key=row['key'], position=row['position'],
                designation=row['designation'], specifications=row['specifications'],
                unit_label=row['unit'], packaging=row['packaging'], quantity=Decimal(row['quantity'].replace(',', '.')),
                details=row['details'])
    _revision(user, dossier)
    return dossier


@transaction.atomic
def duplicate_dossier(user, pk, *, expected, reference, title, assignee=None, due_on=None,
                      priority='NORMAL', allow_costs=False, instructions='', copy_estimates=False, reason=''):
    require_manager(user)
    source = _dossier(user, pk)
    check_version(source, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez la duplication du cahier des charges.'))
    duplicate = create_dossier(user, family=source.family, reference=reference, title=title,
        assignee=assignee, due_on=due_on, priority=priority, allow_costs=allow_costs, instructions=instructions)
    CdcItem.objects.filter(lot__dossier=duplicate).delete()
    duplicate.lots.all().delete()
    duplicate.data = copy.deepcopy(source.data)
    duplicate.data['reference'] = duplicate.reference
    duplicate.data.setdefault('consultation', {})['confirmed'] = False
    duplicate.save(update_fields=['data', 'updated_at'])
    lot_map = {}
    for position, original_lot in enumerate(source.lots.filter(active=True).order_by('position', 'id'), 1):
        lot = CdcLot.objects.create(dossier=duplicate, position=position, name=original_lot.name,
            name_ar=original_lot.name_ar, source_slot=original_lot.source_slot)
        lot_map[original_lot.pk] = lot
        for original in original_lot.items.filter(active=True).prefetch_related('requirements').order_by('position', 'id'):
            cloned = CdcItem.objects.create(lot=lot, source_key='clone-' + str(uuid.uuid4()), position=lot.items.count() + 1,
                article=original.article, article_snapshot=copy.deepcopy(original.article_snapshot),
                designation=original.designation, specifications=original.specifications, unit_label=original.unit_label,
                purchase_unit=original.purchase_unit, base_factor=original.base_factor, packaging=original.packaging,
                quantity=original.quantity, details=original.details,
                estimate_supplier=original.estimate_supplier if copy_estimates and allow_costs else None,
                estimated_price=original.estimated_price if copy_estimates and allow_costs else None,
                tax_rate=original.tax_rate if copy_estimates and allow_costs else None,
                price_source=original.price_source if copy_estimates and allow_costs else '', currency=original.currency)
            for requirement in original.requirements.filter(active=True):
                CdcRequirement.objects.create(item=cloned, position=requirement.position, kind=requirement.kind,
                    statement=requirement.statement, evidence=requirement.evidence,
                    verification_method=requirement.verification_method, justification=requirement.justification,
                    active=True)
    for criterion in source.criteria.filter(active=True).order_by('position', 'id'):
        CdcCriterion.objects.create(dossier=duplicate, lot=lot_map.get(criterion.lot_id),
            code=criterion.code, title=criterion.title, method=criterion.method, weight=criterion.weight,
            threshold=criterion.threshold, eliminatory=criterion.eliminatory, evidence=criterion.evidence,
            position=criterion.position, active=True)
    for selection in source.clause_selections.filter(active=True).select_related('revision'):
        CdcClauseSelection.objects.create(dossier=duplicate, revision=selection.revision,
            position=selection.position, mandatory=selection.mandatory, note=selection.note, active=True)
    _revision(user, duplicate, reason)
    audit(user, source, 'duplicated_to', reason=str(duplicate.pk))
    audit(user, duplicate, 'duplicated_from', reason=str(source.pk))
    return duplicate


@transaction.atomic
def archive_dossier(user, pk, *, expected, reason):
    require_manager(user)
    dossier = _dossier(user, pk)
    check_version(dossier, expected)
    if dossier.archived_at is not None:
        raise ValidationError(_('Ce cahier des charges est déjà archivé.'))
    if dossier.work.status not in (WorkItem.Status.APPROVED, WorkItem.Status.CANCELLED):
        raise ValidationError(_('Seul un cahier des charges clôturé ou annulé peut être archivé.'))
    if not reason.strip():
        raise ValidationError(_('Une justification d’archivage est obligatoire.'))
    dossier.archived_at, dossier.archived_by, dossier.archive_reason = timezone.now(), user, reason.strip()
    dossier.version += 1
    dossier.save(update_fields=['archived_at', 'archived_by', 'archive_reason', 'version', 'updated_at'])
    audit(user, dossier, 'archived', reason=dossier.archive_reason)
    return dossier


def stock_status(user, dossier):
    require_work(user, dossier.work)
    if not is_manager(user) and not grants(user, Capability.VIEW_STOCK).exists():
        return None
    grouped, unlinked = {}, 0
    for item in CdcItem.objects.filter(lot__dossier=dossier, lot__active=True, active=True).select_related('article__base_unit'):
        if item.article_id is None or item.base_factor is None:
            unlinked += 1
            continue
        row = grouped.setdefault(item.article_id, {'article': item.article, 'required': Decimal(0)})
        row['required'] += stock_quantity(item.quantity * item.base_factor)
    rows = []
    for row in grouped.values():
        containers = operational_scope(StockContainer.objects.filter(lot__article=row['article']), user)
        if dossier.work.location_id:
            containers = containers.filter(location_id__in=LocationClosure.objects.filter(
                ancestor_id=dossier.work.location_id).values('descendant_id'))
        containers = containers.filter(usable_filter(timezone.localdate()))
        available = sum((container.quantity - container.reserved for container in containers), Decimal(0))
        shortage = max(Decimal(0), row['required'] - available)
        state = 'AVAILABLE' if shortage == 0 else ('INSUFFICIENT' if available > 0 else 'ABSENT')
        rows.append({**row, 'available': available, 'shortage': shortage, 'status': state})
    rows.sort(key=lambda row: row['article'].code)
    return {'rows': rows, 'unlinked': unlinked}


@transaction.atomic
def save_consultation(user, pk, *, expected, values, reference=None, reason=''):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    if set(values) != set(FIELDS):
        raise ValidationError(_('La fiche de consultation doit comporter toutes les rubriques prévues.'))
    value = {'schema': 2, **values}
    validate_consultation(value, dossier.family)
    if reference is not None:
        dossier.reference = reference.strip()
    dossier.data = {**dossier.data, 'reference': dossier.reference, 'consultation': value}
    dossier.full_clean()
    return _revision(user, dossier, reason)


@transaction.atomic
def save_cdc_lot(user, pk, *, expected, name, name_ar, reason='', source_slot=None):
    lot = CdcLot.objects.get(pk=pk)
    dossier = _dossier(user, lot.dossier_id, edit=True)
    check_version(dossier, expected)
    lot.name, lot.name_ar, lot.version = name.strip(), name_ar.strip(), lot.version + 1
    if source_slot is not None:
        lot.source_slot = source_slot
    lot.full_clean()
    lot.save()
    return _revision(user, dossier, reason)


@transaction.atomic
def save_cdc_item(user, lot_id, *, expected, values, pk=None, article=None, purchase_unit=None, refresh_catalog=False, reason=''):
    lot = CdcLot.objects.get(pk=lot_id)
    dossier = _dossier(user, lot.dossier_id, edit=True)
    check_version(dossier, expected)
    if set(values) - ITEM_FIELDS - ESTIMATE_FIELDS:
        raise ValidationError(_('Champ de besoin ou d’estimation non autorisé.'))
    if set(values) & ESTIMATE_FIELDS:
        require_work(user, dossier.work, costs=True)
    item = CdcItem.objects.get(pk=pk, lot=lot) if pk else CdcItem(lot=lot,
        source_key='new-' + str(uuid.uuid4()), position=lot.items.count() + 1)
    if article is not None:
        article = Article.objects.get(pk=article.pk, active=True)
        if dossier.work.category_id and article.category_id != dossier.work.category_id:
            raise PermissionDenied
        if purchase_unit is None:
            raise ValidationError(_('Sélectionnez explicitement l’unité d’achat du catalogue commun.'))
        if item.article_id != article.pk or item.purchase_unit_id != purchase_unit.pk or refresh_catalog:
            item.base_factor = convert_quantity(article, 1, purchase_unit)[1]
            item.article, item.purchase_unit = article, purchase_unit
            item.article_snapshot = snapshot(article)
            item.designation, item.specifications = article.name, article.specifications
            item.packaging, item.unit_label = article.packaging, purchase_unit.name
            values = {key: value for key, value in values.items() if key not in ('designation', 'specifications', 'packaging', 'unit_label')}
    elif purchase_unit is not None:
        raise ValidationError(_('Une unité structurée doit être associée à un article du catalogue.'))
    for key, value in values.items():
        setattr(item, key, value)
    if item.quantity is not None:
        item.quantity = stock_quantity(item.quantity)
    item.currency = item.currency.strip().upper()
    if len(item.currency) != 3 or not item.currency.isascii() or not item.currency.isalpha():
        raise ValidationError(_('Code de devise à trois lettres requis.'))
    if item.estimate_supplier_id:
        supplier = Party.objects.get(pk=item.estimate_supplier_id)
        if not supplier.active or not supplier.is_supplier:
            raise ValidationError(_('Sélectionnez un fournisseur actif du référentiel commun.'))
    if item.estimated_price is not None and not item.price_source.strip():
        raise ValidationError(_('Renseignez la source du prix estimatif.'))
    if item.article_id and item.unit_label != item.purchase_unit.name:
        raise ValidationError(_('L’unité documentaire doit correspondre à l’unité structurée retenue.'))
    item.full_clean()
    if pk:
        item.version += 1
    item.save()
    return _revision(user, dossier, reason)


@transaction.atomic
def edit_cdc_paragraph(user, pk, *, expected, paragraph_id, value, reason):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    if not reason.strip():
        raise ValidationError(_('Justifiez la modification de cette clause documentaire.'))
    data = copy.deepcopy(dossier.data)
    data.setdefault('paragraphs', {})[paragraph_id] = value
    dossier.data = data
    return _revision(user, dossier, reason)


@transaction.atomic
def submit_dossier(user, pk, *, expected, reason=''):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    data = document_data(dossier)
    findings = dossier_findings(dossier)
    errors = [finding for finding in findings if finding['severity'] == 'error']
    if errors or not data.get('consultation', {}).get('confirmed'):
        raise ValidationError(_('Corrigez les contrôles bloquants et confirmez les variables du dossier avant soumission.'))
    revision = dossier.revisions.get(number=dossier.revision_number)
    if not revision.generations.exists():
        raise ValidationError(_('Générez et consultez le PDF de cette révision avant soumission.'))
    return _transition(user, dossier.work, WorkItem.Status.SUBMITTED, reason)


def generate_cdc(user, revision_id):
    revision = CdcRevision.objects.select_related('dossier__work').get(pk=revision_id)
    require_work(user, revision.dossier.work)
    if revision.dossier.archived_at is not None:
        raise ValidationError(_('Un cahier des charges archivé ne peut plus produire de nouvelle génération.'))
    if revision.generations.exists():
        return revision.generations.order_by('-created_at', '-id').first()
    data = copy.deepcopy(revision.data)
    findings = [*controls(data), *governance_snapshot_findings(data)]
    if any(finding['severity'] == 'error' for finding in findings):
        raise ValidationError(_('La génération est bloquée par des incohérences du dossier.'))
    payload, report = generate_document(data)
    payload, annex = append_governance_annex(payload, data, revision.number)
    report['governance_annex'] = annex
    if annex['status'] == 'GENERATED':
        if 'word/document.xml' not in report.get('changed_parts', []):
            report.setdefault('changed_parts', []).append('word/document.xml')
        report.get('preserved_parts', {}).pop('word/document.xml', None)
        report.setdefault('changes', []).append({
            'kind': 'cdc_governance_annex',
            'requirements': annex['requirements'],
            'criteria': annex['criteria'],
            'clauses': annex['clauses'],
        })
        report['output_sha256'] = sha(payload)
    payload, layout = normalize_word_layout(payload)
    report['output_sha256'] = sha(payload)
    with tempfile.TemporaryDirectory(prefix='plagenor-cdc-') as directory:
        source = Path(directory) / ('cdc-' + str(revision.pk) + '.docx')
        source.write_bytes(payload)
        result = convert_docx_to_pdf(source)
        if result.suffix.lower() != '.pdf' or not result.exists():
            raise ValidationError(_('La conversion PDF a échoué. Aucun document n’a été déclaré valide.'))
        pdf = result.read_bytes()
    reader = PdfReader(io.BytesIO(pdf), strict=True)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 1000:
        raise ValidationError(_('Le document PDF généré est invalide.'))
    sizes = [(float(page.mediabox.width), float(page.mediabox.height)) for page in reader.pages]
    if any(min(abs(width-595.28) + abs(height-841.89), abs(width-841.89) + abs(height-595.28)) > 8 for width, height in sizes):
        raise ValidationError(_('Toutes les pages du cahier des charges doivent être au format A4.'))
    checks = {'source_report': report, 'layout': layout, 'findings': findings,
              'pdf_page_sizes': sizes, 'visual_review': 'PENDING', 'legal_review': 'PENDING'}
    with transaction.atomic():
        dossier = _dossier(user, revision.dossier_id)
        generation = revision.generations.first()
        if generation:
            return generation
        generation = CdcGeneration.objects.create(revision=revision, actor=user, docx=payload, pdf=pdf,
            docx_sha256=sha(payload), pdf_sha256=sha(pdf), pages=len(reader.pages), checks=checks)
        audit(user, dossier, 'document_generated', reason=str(generation.pk))
        return generation


@transaction.atomic
def approve_dossier(user, pk, *, expected, generation_id, reviewed_pages, statement,
                    visual_review, content_review):
    dossier = _dossier(user, pk)
    require(user, Capability.APPROVE_CDC, location=dossier.work.location, category=dossier.work.category)
    check_version(dossier, expected)
    if dossier.work.status != WorkItem.Status.SUBMITTED:
        raise ValidationError(_('Le dossier doit être soumis avant sa validation finale.'))
    if not review_state(dossier)['complete']:
        raise ValidationError(_('Toutes les revues obligatoires de la révision courante doivent être approuvées avant validation finale.'))
    generation = CdcGeneration.objects.select_related('revision').get(pk=generation_id, revision__dossier=dossier)
    if generation.revision.number != dossier.revision_number:
        raise Conflict(_('Cette génération ne correspond plus à la dernière révision du dossier.'))
    if visual_review is not True or content_review is not True or reviewed_pages != generation.pages or not statement.strip():
        raise ValidationError(_('Confirmez la revue du contenu et de toutes les pages du PDF, avec une justification.'))
    approval = CdcApproval(dossier=dossier, generation=generation, actor=user,
        statement=statement.strip(), reviewed_pages=reviewed_pages)
    approval.full_clean()
    approval.save()
    _transition(user, dossier.work, WorkItem.Status.APPROVED, statement)
    audit(user, dossier, 'approved', reason=statement)
    return approval


def estimate_totals(user, dossier):
    require_work(user, dossier.work, costs=True)
    totals, missing = {}, 0
    for item in CdcItem.objects.filter(lot__dossier=dossier, lot__active=True, active=True):
        if item.estimated_price is None or item.tax_rate is None:
            missing += 1
            continue
        line = (item.quantity * item.estimated_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        tax = (line * item.tax_rate / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        current = totals.setdefault(item.currency, {'net': Decimal(0), 'tax': Decimal(0), 'gross': Decimal(0)})
        current['net'] += line
        current['tax'] += tax
        current['gross'] += line + tax
    return {'currencies': totals, 'incomplete_lines': missing}
