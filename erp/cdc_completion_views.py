import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from .cdc.docengine import DocumentError
from .cdc.catalog import document, effective_edits, profile
from .cdc.schedule_adapter import managed_ids
from .cdc_completion_forms import FinancialImportForm, ReuseFilterForm, ReuseRows, ReuseSelectionForm, TableRowForm, reusable_revisions
from .cdc_exchange_views import ConfirmForm
from .models import CdcReusePreview
from .permissions import is_manager
from .services.cdc import cdc_cost_allowed, document_data, dossier_scope
from .services.cdc_finance import export_financial, financial_snapshot, preview_financial
from .services.cdc_reuse import WORKS_NOTICE, apply_reuse, preview_reuse, source_rows
from .services.cdc_tables import add_table_row, editable_table, remove_table_row
from .services.work import require_work, work_allowed
from .views import add_validation


@login_required
@require_http_methods(['GET', 'POST'])
def catalogue(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    if dossier.family == 'works':
        return render(request, 'erp/cdc_catalogue.html', {'dossier': dossier, 'limit': WORKS_NOTICE,
            'manager': is_manager(request.user)},
            status=400 if request.method == 'POST' else 200)
    revisions = reusable_revisions(request.user, dossier)
    filters = ReuseFilterForm(request.GET or None)
    filters.fields['source_revision'].queryset = revisions
    if filters.is_bound and filters.is_valid():
        selected = filters.cleaned_data['source_revision']
        search = filters.cleaned_data['q']
    else:
        selected, search = revisions.first(), ''
        filters.initial['source_revision'] = selected
    form = ReuseSelectionForm(request.POST or None, user=request.user, dossier=dossier, search=search,
        initial={'expected_version': dossier.version, 'source_revision': selected,
                 'target_lot': dossier.lots.filter(active=True).first()})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        values['source_revision'] = values['source_revision'].pk
        values['target_lot'] = values['target_lot'].pk
        try:
            preview = preview_reuse(request.user, pk, expected=values.pop('expected_version'), **values)
        except (ValidationError, DocumentError, IntegrityError) as error:
            add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)
        else:
            return redirect('erp:cdc-reuse-preview', pk=preview.pk)
    return render(request, 'erp/cdc_catalogue.html', {'dossier': dossier, 'filters': filters, 'form': form},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def reuse_preview(request, pk):
    preview = get_object_or_404(CdcReusePreview.objects.select_related('dossier__work', 'source_revision__dossier', 'target_lot'),
        pk=pk, actor=request.user, dossier__in=dossier_scope(request.user))
    require_work(request.user, preview.dossier.work, edit=True)
    source_rows(request.user, preview.source_revision_id, preview.dossier.family)
    rows = ReuseRows(request.POST or None, initial=preview.payload['rows'])
    error = None
    if request.method == 'POST':
        if request.POST.get('confirm') != 'on':
            error = _('Confirmez explicitement la copie des articles sélectionnés.')
        elif rows.is_valid():
            try:
                apply_reuse(request.user, pk, rows=rows.cleaned_data)
            except (ValidationError, DocumentError, IntegrityError) as exception:
                error = str(exception)
            else:
                messages.success(request, _('Les articles ont été copiés dans une nouvelle révision, sans les estimations historiques.'))
                return redirect('erp:cdc-detail', pk=preview.dossier_id)
    return render(request, 'erp/cdc_reuse_preview.html', {'preview': preview, 'dossier': preview.dossier,
        'rows': rows, 'error': error}, status=400 if request.method == 'POST' else 200)



@login_required
@require_http_methods(['GET', 'POST'])
def finance(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    if not cdc_cost_allowed(request.user, dossier):
        raise PermissionDenied
    form = FinancialImportForm(request.POST or None, request.FILES or None,
        initial={'expected_version': dossier.version})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            preview = preview_financial(request.user, pk, expected=values.pop('expected_version'),
                upload=values.pop('file'), **values)
        except (ValidationError, DocumentError, IntegrityError) as error:
            add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)
        else:
            return redirect('erp:cdc-workbook-preview', pk=preview.pk)
    try:
        revision, summary = financial_snapshot(dossier)
    except ValidationError as error:
        return render(request, 'erp/cdc_export_error.html', {'dossier': dossier, 'error': str(error)}, status=400)
    return render(request, 'erp/cdc_finance.html', {'dossier': dossier, 'form': form, 'summary': summary,
        'revision': revision, 'editable': dossier.archived_at is None and work_allowed(request.user, dossier.work, edit=True)},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def financial_download(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    try:
        payload = export_financial(request.user, dossier)
    except (ValidationError, DocumentError) as error:
        return render(request, 'erp/cdc_export_error.html', {'dossier': dossier, 'error': str(error)}, status=400)
    response = FileResponse(io.BytesIO(payload), as_attachment=True,
        filename='CDC-%s-R%s-finances.xlsx' % (dossier.pk, dossier.revision_number),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
@require_GET
def tables(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    data = document_data(dossier)
    projected = effective_edits(data)
    blocks = {row['id']: row for row in document(dossier.family).source_index}
    managed_paragraphs, managed_tables = managed_ids(dossier.family)
    rows = []
    search = request.GET.get('q', '').strip()[:200]
    for number, table in enumerate(profile(dossier.family)['tables'], 1):
        table_rows = []
        for row in table['rows']:
            cells = []
            for cell in row['cells']:
                paragraphs = [{'id': pid, 'text': projected.get(pid, blocks[pid]['text']),
                    'editable': not blocks[pid]['guard'] and pid not in managed_paragraphs}
                    for pid in cell['paragraph_ids']]
                cells.append({'paragraphs': paragraphs})
            table_rows.append({'index': row['index'], 'cells': cells, 'cloneable': row['index'] > 0 and row['cloneable']
                and table['id'] not in managed_tables and not table['nested'] and table['part'] == 'word/document.xml'})
        entry = {'id': table['id'], 'number': number, 'rows': table_rows,
                 'additions': data.get('rows', {}).get(table['id'], [])}
        if not search or search.casefold() in ' '.join(paragraph['text'] for row in table_rows
            for cell in row['cells'] for paragraph in cell['paragraphs']).casefold():
            rows.append(entry)
    return render(request, 'erp/cdc_tables.html', {'dossier': dossier, 'q': search,
        'page': Paginator(rows, 4).get_page(request.GET.get('page')),
        'editable': dossier.archived_at is None and work_allowed(request.user, dossier.work, edit=True)})


@login_required
@require_http_methods(['GET', 'POST'])
def table_add(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    params = request.POST if request.method == 'POST' else request.GET
    try:
        row = int(params.get('source_row', '-1'))
        table_id = params.get('table_id', '')
        table = editable_table(dossier.family, table_id, row)
    except (ValueError, ValidationError):
        raise Http404
    form = TableRowForm(request.POST or None, table=table, source_row=row,
        initial={'expected_version': dossier.version, 'table_id': table_id, 'source_row': row, 'after_row': row})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        cells = [values.pop('cell_%s' % index) for index in range(len(table['rows'][row]['cells']))]
        try:
            add_table_row(request.user, pk, expected=values.pop('expected_version'), cells=cells, **values)
        except (ValidationError, DocumentError, IntegrityError) as error:
            add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)
        else:
            return redirect('erp:cdc-tables', pk=pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Ajouter une ligne au tableau'),
        'subtitle': dossier.reference, 'cancel_url': reverse('erp:cdc-tables', args=[pk])},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def table_remove(request, pk, index):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    table_id = request.POST.get('table_id', '') if request.method == 'POST' else request.GET.get('table_id', '')
    form = ConfirmForm(request.POST or None, initial={'expected_version': dossier.version})
    form.fields['table_id'] = forms.CharField(widget=forms.HiddenInput, initial=table_id)
    if request.method == 'POST' and form.is_valid():
        try:
            remove_table_row(request.user, pk, expected=form.cleaned_data['expected_version'], table_id=table_id,
                index=index, reason=form.cleaned_data['reason'])
        except (ValidationError, DocumentError, IntegrityError) as error:
            add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)
        else:
            return redirect('erp:cdc-tables', pk=pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Retirer une ligne ajoutée'),
        'subtitle': dossier.reference, 'cancel_url': reverse('erp:cdc-tables', args=[pk])},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def import_home(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    return render(request, 'erp/cdc_import_home.html', {'dossier': dossier,
        'cost_access': cdc_cost_allowed(request.user, dossier), 'manager': is_manager(request.user),
        'work_access': work_allowed(request.user, dossier.work)})


@login_required
@require_GET
def guide(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    return render(request, 'erp/cdc_guide.html', {'dossier': dossier,
        'cost_access': cdc_cost_allowed(request.user, dossier),
        'editable': dossier.archived_at is None and work_allowed(request.user, dossier.work, edit=True)})
