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
from erp.cdc.lot_catalog import get_catalog, validate_catalog
from erp.cdc.word_layout import normalize_word_layout
from erp.models import (Article, CdcApproval, CdcClauseSelection, CdcDossier, CdcGeneration,
                        CdcItem, CdcLot, CdcRevision, LocationClosure, Party, StockContainer,
                        Unit, WorkItem)
from erp.permissions import Capability, grants, is_manager, operational_scope, require_manager
from .catalog import convert_quantity
from .common import Conflict, audit, check_version, snapshot
from .stock import stock_quantity, usable_filter
from .work import _transition, create_work, require_work, work_allowed, work_scope


ITEM_FIELDS = {'designation', 'specifications', 'unit_label', 'packaging', 'quantity', 'details', 'active'}
ESTIMATE_FIELDS = {'estimated_price', 'tax_rate', 'price_source', 'currency'}


def dossier_scope(user):
    return CdcDossier.objects.filter(work__in=work_scope(user)).select_related('work', 'work__assignee')


def _dossier(user, pk, *, edit=False):
    identity = CdcDossier.objects.values('work_id').get(pk=pk)
    work = WorkItem.objects.select_for_update(no_key=True).get(pk=identity['work_id'])
    require_work(user, work, edit=edit)
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
    data.pop('procurement', None)
    from .cdc_governance import apply_clause_selections
    data = apply_clause_selections(dossier, data)
    validate_data(data, dossier.family)
    return data


def _estimates(dossier):
    return [{'id': str(item.pk), 'article': str(item.article_id) if item.article_id else None,
             'article_snapshot': item.article_snapshot, 'lot': str(item.lot_id), 'active': item.active,
             'quantity': str(item.quantity), 'purchase_unit': str(item.purchase_unit_id) if item.purchase_unit_id else None,
             'base_factor': str(item.base_factor) if item.base_factor is not None else None,
             'supplier': str(item.supplier_id) if item.supplier_id else None,
             'price': str(item.estimated_price) if item.estimated_price is not None else None,
             'tax_rate': str(item.tax_rate) if item.tax_rate is not None else None,
             'currency': item.currency, 'source': item.price_source}
            for item in CdcItem.objects.filter(lot__dossier=dossier).order_by('lot__position', 'position', 'id')]


def _revision(user, dossier, reason=''):
    data, estimates = document_data(dossier), _estimates(dossier)
    from .cdc_governance import governance_snapshot
    governance = governance_snapshot(dossier)
    digest = hashlib.sha256(json.dumps({'document': data, 'estimates': estimates, 'governance': governance}, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    dossier.revision_number += 1
    dossier.version += 1
    dossier.save()
    revision = CdcRevision.objects.create(dossier=dossier, number=dossier.revision_number, actor=user,
        data=data, estimates=estimates, governance=governance, sha256=digest, reason=reason[:500])
    audit(user, dossier, 'revision_created', reason=reason[:500])
    return revision


@transaction.atomic
def create_dossier(user, *, family, reference, title, assignee=None, due_on=None,
                   priority='NORMAL', location=None, category=None, allow_costs=False, instructions=''):
    require_manager(user)
    data = initial_data(family)
    data['reference'] = reference.strip()
    validate_data(data, family)
    work = create_work(user, kind=WorkItem.Kind.CDC, title=title, assignee=assignee,
        due_on=due_on, priority=priority, location=location, category=category,
        allow_costs=allow_costs, instructions=instructions)
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
        assignee=assignee, due_on=due_on, priority=priority, location=source.work.location,
        category=source.work.category, allow_costs=allow_costs, instructions=instructions)
    CdcItem.objects.filter(lot__dossier=duplicate).delete()
    duplicate.lots.all().delete()
    duplicate.data = copy.deepcopy(source.data)
    duplicate.data['reference'] = duplicate.reference
    duplicate.data.setdefault('consultation', {})['confirmed'] = False
    duplicate.save(update_fields=['data', 'updated_at'])
    for position, original_lot in enumerate(source.lots.filter(active=True).order_by('position', 'id'), 1):
        lot = CdcLot.objects.create(dossier=duplicate, position=position, name=original_lot.name,
            name_ar=original_lot.name_ar, source_slot=original_lot.source_slot)
        for original in original_lot.items.filter(active=True).order_by('position', 'id'):
            CdcItem.objects.create(lot=lot, source_key='clone-' + str(uuid.uuid4()), position=lot.items.count() + 1,
                article=original.article, article_snapshot=copy.deepcopy(original.article_snapshot),
                designation=original.designation, specifications=original.specifications, unit_label=original.unit_label,
                purchase_unit=original.purchase_unit, base_factor=original.base_factor, packaging=original.packaging,
                quantity=original.quantity, details=original.details,
                estimated_price=original.estimated_price if copy_estimates and allow_costs else None,
                tax_rate=original.tax_rate if copy_estimates and allow_costs else None,
                supplier=original.supplier if copy_estimates and allow_costs else None,
                price_source=original.price_source if copy_estimates and allow_costs else '', currency=original.currency)
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
def save_cdc_item(user, lot_id, *, expected, values, pk=None, article=None, purchase_unit=None,
                  supplier=None, supplier_provided=False, refresh_catalog=False, reason=''):
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
    if supplier_provided:
        require_work(user, dossier.work, costs=True)
        if supplier is not None:
            supplier = Party.objects.get(pk=supplier.pk, active=True, is_supplier=True)
        item.supplier = supplier
    for key, value in values.items():
        setattr(item, key, value)
    if item.quantity is not None:
        item.quantity = stock_quantity(item.quantity)
    item.currency = item.currency.strip().upper()
    if len(item.currency) != 3 or not item.currency.isascii() or not item.currency.isalpha():
        raise ValidationError(_('Code de devise à trois lettres requis.'))
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
    if CdcClauseSelection.objects.filter(dossier=dossier, clause__paragraph_id=paragraph_id).exists():
        raise ValidationError(_('Ce paragraphe est piloté par la bibliothèque de clauses versionnées. Changez sa version depuis la bibliothèque.'))
    data = copy.deepcopy(dossier.data)
    data.setdefault('paragraphs', {})[paragraph_id] = value
    dossier.data = data
    return _revision(user, dossier, reason)


@transaction.atomic
def submit_dossier(user, pk, *, expected, reason=''):
    dossier = _dossier(user, pk, edit=True)
    check_version(dossier, expected)
    data = document_data(dossier)
    from .cdc_governance import criteria_findings
    findings = controls(data) + criteria_findings(dossier)
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
    findings = controls(data)
    if any(finding['severity'] == 'error' for finding in findings):
        raise ValidationError(_('La génération est bloquée par des incohérences du dossier.'))
    payload, report = generate_document(data)
    payload, layout = normalize_word_layout(payload)
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
    require_manager(user)
    dossier = _dossier(user, pk)
    check_version(dossier, expected)
    if dossier.work.status != WorkItem.Status.SUBMITTED:
        raise ValidationError(_('Le dossier doit être soumis avant sa validation finale.'))
    generation = CdcGeneration.objects.select_related('revision').get(pk=generation_id, revision__dossier=dossier)
    if dossier.criteria.filter(active=True).exists() or dossier.clause_selections.exists():
        from .cdc_governance import REVIEW_ORDER
        decisions = generation.revision.review_decisions.filter(decision='APPROVED')
        if set(decisions.values_list('stage', flat=True)) != set(REVIEW_ORDER):
            raise ValidationError(_('Les revues technique, administrative/juridique et financière doivent être approuvées avant la validation finale.'))
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
