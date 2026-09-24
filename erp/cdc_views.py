import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import cdc_forms as forms
from .cdc.catalog import controls, document, effective_edits
from .cdc.docengine import DocumentError
from .models import (CdcClause, CdcCriterion, CdcDossier, CdcGeneration, CdcItem, CdcLot,
                     CdcRevision, ProcurementPlan, WorkItem)
from .permissions import has_access, is_manager, require_manager
from .services.cdc import (approve_dossier, archive_dossier, create_dossier, document_data, dossier_scope,
    duplicate_dossier, edit_cdc_paragraph, estimate_totals, generate_cdc, save_cdc_item, save_cdc_lot,
    save_consultation, stock_status, submit_dossier)
from .services.cdc_governance import (criteria_findings, publish_clause, review_revision,
    review_summary, save_criterion, select_clause)
from .services.work import require_work, work_allowed
from .views import add_validation


ERRORS = (ValidationError, DocumentError, IntegrityError)


def _error(form, error):
    add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)


def _form_response(request, form, dossier, title):
    return render(request, 'erp/operation_form.html', {'form': form, 'title': title,
        'subtitle': dossier.reference, 'cancel_url': reverse('erp:cdc-detail', args=[dossier.pk])},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def cdc_list(request):
    if not has_access(request.user):
        raise PermissionDenied
    qs = dossier_scope(request.user).order_by('-created_at')
    search = request.GET.get('q', '').strip()[:200]
    if search:
        qs = qs.filter(Q(reference__icontains=search) | Q(work__title__icontains=search))
    state=request.GET.get('state','active')
    if state=='archived':
        qs=qs.filter(archived_at__isnull=False)
    elif state=='all':
        pass
    else:
        state='active';qs=qs.filter(archived_at__isnull=True)
    return render(request, 'erp/cdc_list.html', {'page': Paginator(qs, 30).get_page(request.GET.get('page')),
        'q': search, 'state':state, 'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_create(request):
    require_manager(request.user)
    form = forms.CdcCreateForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        values.pop('expected_version')
        try:
            dossier = create_dossier(request.user, **values)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=dossier.pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Créer et déléguer un cahier des charges'),
        'subtitle': _('Le modèle institutionnel sert de base. Les informations variables doivent être revues pour chaque dossier.'),
        'cancel_url': reverse('erp:cdc-list')}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_detail(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    form = forms.CdcDecisionForm(request.POST or None, initial={'expected_version': dossier.version})
    if request.method == 'POST' and form.is_valid():
        try:
            action = request.POST.get('action')
            if action == 'submit':
                submit_dossier(request.user, pk, expected=form.cleaned_data['expected_version'], reason=form.cleaned_data['reason'])
            elif action == 'generate':
                if form.cleaned_data['expected_version'] != dossier.version:
                    raise ValidationError(_('Le dossier a été modifié. Rechargez la page.'))
                revision = dossier.revisions.get(number=dossier.revision_number)
                generate_cdc(request.user, revision.pk)
                messages.success(request, _('Le DOCX et le PDF ont été générés. La revue de toutes les pages reste nécessaire avant validation finale.'))
            else:
                return HttpResponseBadRequest(_('Action inconnue.'))
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=pk)
    data = document_data(dossier)
    findings = controls(data) + criteria_findings(dossier)
    cost_access = work_allowed(request.user, dossier.work, costs=True)
    generation = CdcGeneration.objects.filter(revision__dossier=dossier,
        revision__number=dossier.revision_number).defer('docx', 'pdf', 'checks').first()
    return render(request, 'erp/cdc_detail.html', {'dossier': dossier, 'work': dossier.work,
        'lots': dossier.lots.filter(active=True).annotate(item_count=Count('items', filter=Q(items__active=True))),
        'form': form, 'findings': findings, 'generation': generation,
        'revisions': dossier.revisions.defer('data', 'estimates').order_by('-number')[:50],
        'editable': dossier.archived_at is None and work_allowed(request.user, dossier.work, edit=True), 'manager': is_manager(request.user),
        'costs': estimate_totals(request.user, dossier) if cost_access else None,
        'stock_status': stock_status(request.user,dossier), 'procurement_plan': ProcurementPlan.objects.filter(cdc=dossier).first(),
        'inactive_lots': dossier.lots.filter(active=False), 'source_confirmed': data.get('consultation', {}).get('confirmed', False),
        'criteria_count': dossier.criteria.filter(active=True).count(), 'review_summary': review_summary(dossier)},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_consultation(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    initial = {key: value for key, value in dossier.data['consultation'].items() if key != 'schema'}
    initial.update(expected_version=dossier.version, reference=dossier.reference)
    form = forms.ConsultationForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected, reference, reason = values.pop('expected_version'), values.pop('reference'), values.pop('reason')
        try:
            save_consultation(request.user, pk, expected=expected, values=values, reference=reference, reason=reason)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=pk)
    return _form_response(request, form, dossier, _('Informations propres au cahier des charges'))


@login_required
@require_GET
def cdc_lot(request, pk):
    lot = get_object_or_404(CdcLot.objects.select_related('dossier__work'), pk=pk, dossier__in=dossier_scope(request.user))
    search = request.GET.get('q', '').strip()[:200]
    items = lot.items.select_related('article', 'purchase_unit').order_by('position', 'id')
    if search:
        items = items.filter(Q(designation__icontains=search) | Q(specifications__icontains=search) |
            Q(details__icontains=search) | Q(article__code__icontains=search))
    return render(request, 'erp/cdc_lot.html', {'lot': lot, 'dossier': lot.dossier,
        'q': search, 'page': Paginator(items, 30).get_page(request.GET.get('page')),
        'editable': work_allowed(request.user, lot.dossier.work, edit=True),
        'cost_access': work_allowed(request.user, lot.dossier.work, costs=True)})


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_lot_edit(request, pk):
    lot = get_object_or_404(CdcLot.objects.select_related('dossier__work'), pk=pk, dossier__in=dossier_scope(request.user))
    require_work(request.user, lot.dossier.work, edit=True)
    form = forms.CdcLotForm(request.POST or None, initial={'expected_version': lot.dossier.version,
        'name': lot.name, 'name_ar': lot.name_ar, 'source_slot': lot.source_slot})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            save_cdc_lot(request.user, pk, expected=values.pop('expected_version'), **values)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-lot', pk=pk)
    return _form_response(request, form, lot.dossier, _('Intitulé bilingue du lot'))


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_item_edit(request, lot_id, pk=None):
    lot = get_object_or_404(CdcLot.objects.select_related('dossier__work'), pk=lot_id, dossier__in=dossier_scope(request.user))
    dossier = lot.dossier
    require_work(request.user, dossier.work, edit=True)
    item = get_object_or_404(CdcItem, pk=pk, lot=lot) if pk else CdcItem(lot=lot)
    form = forms.CdcItemForm(request.POST or None, instance=item, user=request.user, dossier=dossier)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        article, unit = values.pop('article'), values.pop('purchase_unit')
        supplier_provided = 'supplier' in values
        supplier = values.pop('supplier', None)
        reason, refresh = values.pop('reason'), values.pop('refresh_catalog')
        try:
            save_cdc_item(request.user, lot.pk, expected=expected, pk=pk, values=values,
                article=article, purchase_unit=unit, supplier=supplier, supplier_provided=supplier_provided,
                refresh_catalog=refresh, reason=reason)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-lot', pk=lot.pk)
    return _form_response(request, form, dossier, _('Article et spécifications du lot'))


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_approve(request, pk):
    require_manager(request.user)
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    form = forms.CdcApprovalForm(request.POST or None, dossier=dossier, initial={'expected_version': dossier.version})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        generation = values.pop('generation')
        try:
            approve_dossier(request.user, pk, expected=values.pop('expected_version'), generation_id=generation.pk, **values)
        except ERRORS as error:
            _error(form, error)
        else:
            messages.success(request, _('Le cahier des charges et sa génération examinée ont été figés.'))
            return redirect('erp:cdc-detail', pk=pk)
    return _form_response(request, form, dossier, _('Validation finale du cahier des charges'))


@login_required
@require_GET
def cdc_download(request, pk, extension):
    if extension not in ('pdf', 'docx'):
        raise Http404
    generation = get_object_or_404(CdcGeneration.objects.select_related('revision__dossier__work'),
        pk=pk, revision__dossier__in=dossier_scope(request.user))
    payload = bytes(generation.pdf if extension == 'pdf' else generation.docx)
    filename = 'CDC-' + str(generation.revision.dossier_id) + '-R' + str(generation.revision.number) + '.' + extension
    response = FileResponse(io.BytesIO(payload), as_attachment=request.GET.get('inline') != '1' or extension != 'pdf', filename=filename,
        content_type='application/pdf' if extension == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def cdc_revision(request, pk):
    revision = get_object_or_404(CdcRevision.objects.select_related('dossier__work', 'actor'), pk=pk,
        dossier__in=dossier_scope(request.user))
    return render(request, 'erp/cdc_revision.html', {'revision': revision,
        'generation': revision.generations.defer('docx', 'pdf', 'checks').first(),
        'lots': revision.data['lot_catalog']['lots']})


@login_required
@require_GET
def cdc_clauses(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    data = document_data(dossier)
    projected = effective_edits(data)
    from .cdc.schedule_adapter import managed_ids
    managed, tables = managed_ids(dossier.family)
    search = request.GET.get('q', '').casefold().strip()[:200]
    selected = {row.clause.paragraph_id: row for row in dossier.clause_selections.select_related('clause', 'selected_version')}
    blocks = [{'id': row['id'], 'text': projected.get(row['id'], row['text']),
               'editable': not row['guard'] and row['id'] not in managed,
               'library_managed': row['id'] in selected,
               'library_clause_id': selected[row['id']].clause_id if row['id'] in selected else None,
               'library_version': selected[row['id']].selected_version.number if row['id'] in selected else None}
              for row in document(dossier.family).source_index if row['text'].strip()]
    if search:
        blocks = [block for block in blocks if search in block['text'].casefold()]
    return render(request, 'erp/cdc_clauses.html', {'dossier': dossier, 'q': request.GET.get('q', '')[:200],
        'page': Paginator(blocks, 40).get_page(request.GET.get('page')),
        'editable': work_allowed(request.user, dossier.work, edit=True), 'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_paragraph(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    pid = request.POST.get('paragraph_id') if request.method == 'POST' else request.GET.get('paragraph_id')
    source = document(dossier.family)
    if pid not in source.paragraphs:
        raise Http404
    text = effective_edits(document_data(dossier)).get(pid)
    if text is None:
        text = next(row['text'] for row in source.source_index if row['id'] == pid)
    form = forms.CdcParagraphForm(request.POST or None, initial={'expected_version': dossier.version,
        'paragraph_id': pid, 'value': text})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            edit_cdc_paragraph(request.user, pk, expected=values.pop('expected_version'), **values)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-clauses', pk=pk)
    return _form_response(request, form, dossier, _('Modifier une clause source'))


@login_required
@require_http_methods(['GET','POST'])
def cdc_duplicate(request,pk):
    require_manager(request.user);dossier=get_object_or_404(dossier_scope(request.user),pk=pk)
    initial={'expected_version':dossier.version,'title':dossier.work.title,'assignee':dossier.work.assignee,'due_on':dossier.work.due_on,'priority':dossier.work.priority,'instructions':dossier.work.instructions,'allow_costs':dossier.work.allow_costs}
    form=forms.CdcDuplicateForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:created=duplicate_dossier(request.user,pk,expected=values.pop('expected_version'),**values)
        except ERRORS as error:_error(form,error)
        else:return redirect('erp:cdc-detail',pk=created.pk)
    return _form_response(request,form,dossier,_('Dupliquer ce cahier des charges'))

@login_required
@require_http_methods(['GET','POST'])
def cdc_archive(request,pk):
    require_manager(request.user);dossier=get_object_or_404(dossier_scope(request.user),pk=pk)
    form=forms.CdcArchiveForm(request.POST or None,initial={'expected_version':dossier.version})
    if request.method=='POST' and form.is_valid():
        try:archive_dossier(request.user,pk,expected=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except ERRORS as error:_error(form,error)
        else:messages.success(request,_('Le cahier des charges est archivé et reste consultable en lecture seule.'));return redirect('erp:cdc-detail',pk=pk)
    return _form_response(request,form,dossier,_('Archiver ce cahier des charges'))

@login_required
@require_http_methods(['GET','POST'])
def cdc_procurement(request,pk):
    require_manager(request.user);dossier=get_object_or_404(dossier_scope(request.user),pk=pk)
    existing=ProcurementPlan.objects.filter(cdc=dossier).first()
    if existing:return redirect('erp:procurement-detail',pk=existing.pk)
    form=forms.CdcProcurementForm(request.POST or None,initial={'expected_version':dossier.version})
    if request.method=='POST' and form.is_valid():
        from .services.procurement import plan_from_cdc
        values=dict(form.cleaned_data)
        try:plan=plan_from_cdc(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError) as error:_error(form,error)
        else:return redirect('erp:procurement-detail',pk=plan.pk)
    return _form_response(request,form,dossier,_('Créer un plan d’approvisionnement à partir du CDC'))


@login_required
@require_GET
def cdc_criteria(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    rows = dossier.criteria.select_related('lot').order_by('position', 'code')
    return render(request, 'erp/cdc_criteria.html', {
        'dossier': dossier, 'criteria': rows, 'findings': criteria_findings(dossier),
        'editable': dossier.archived_at is None and work_allowed(request.user, dossier.work, edit=True),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_criterion_edit(request, pk, criterion_id=None):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    criterion = get_object_or_404(CdcCriterion, pk=criterion_id, dossier=dossier) if criterion_id else CdcCriterion(dossier=dossier)
    form = forms.CdcCriterionForm(request.POST or None, instance=criterion, user=request.user, dossier=dossier)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected, reason = values.pop('expected_version'), values.pop('reason')
        try:
            save_criterion(request.user, dossier, expected=expected, values=values,
                pk=criterion.pk if criterion_id else None, reason=reason)
        except ERRORS as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-criteria', pk=dossier.pk)
    return _form_response(request, form, dossier, _('Critère et méthode d’évaluation'))


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_clause_publish(request, pk):
    require_manager(request.user)
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    paragraph_id = request.POST.get('paragraph_id') if request.method == 'POST' else request.GET.get('paragraph_id')
    source = document(dossier.family)
    if paragraph_id not in source.paragraphs:
        raise Http404
    current = effective_edits(document_data(dossier)).get(paragraph_id)
    if current is None:
        current = next(row['text'] for row in source.source_index if row['id'] == paragraph_id)
    form = forms.CdcClausePublishForm(request.POST or None, initial={
        'expected_version': dossier.version, 'paragraph_id': paragraph_id,
        'title': current[:250], 'body': current,
    })
    if request.method == 'POST' and form.is_valid():
        try:
            publish_clause(request.user, dossier, **form.cleaned_data)
        except ERRORS as error:
            _error(form, error)
        else:
            messages.success(request, _('La clause versionnée est maintenant la source canonique de ce paragraphe pour ce dossier.'))
            return redirect('erp:cdc-clauses', pk=dossier.pk)
    return _form_response(request, form, dossier, _('Versionner cette clause dans la bibliothèque CDC'))


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_review(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    revision = get_object_or_404(CdcRevision, dossier=dossier, number=dossier.revision_number)
    form = forms.CdcReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            review_revision(request.user, revision, **form.cleaned_data)
        except ERRORS as error:
            _error(form, error)
        else:
            messages.success(request, _('La décision de revue a été enregistrée dans l’historique de cette révision.'))
            return redirect('erp:cdc-detail', pk=dossier.pk)
    return _form_response(request, form, dossier, _('Revue structurée du cahier des charges'))


@login_required
@require_http_methods(['GET', 'POST'])
def cdc_clause_select(request, pk, clause_id):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    clause = get_object_or_404(CdcClause, pk=clause_id, family=dossier.family, active=True)
    current = dossier.clause_selections.filter(clause=clause).select_related('selected_version').first()
    form = forms.CdcClauseSelectForm(request.POST or None, clause=clause, initial={
        'expected_version': dossier.version,
        'version': current.selected_version_id if current else clause.current_version_id,
    })
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            select_clause(request.user, dossier, expected=values.pop('expected_version'),
                clause=clause, version=values.pop('version'), reason=values.pop('reason'))
        except ERRORS as error:
            _error(form, error)
        else:
            messages.success(request, _('La version de clause sélectionnée est figée dans une nouvelle révision du CDC.'))
            return redirect('erp:cdc-clauses', pk=dossier.pk)
    return _form_response(request, form, dossier, _('Choisir une version approuvée de la clause'))


@login_required
@require_GET
def cdc_criteria_export(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    revision = get_object_or_404(CdcRevision.objects.select_related('dossier', 'actor'),
        dossier=dossier, number=dossier.revision_number)
    from .services.cdc_exports import criteria_workbook
    payload = criteria_workbook(revision)
    response = FileResponse(io.BytesIO(payload), as_attachment=True,
        filename='CDC-' + dossier.reference.replace('/', '-') + '-R' + str(revision.number) + '-criteres.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
