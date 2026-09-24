import io

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from .cdc.docengine import DocumentError
from .cdc_forms import CdcLotForm
from .models import CdcLot, CdcRevision, CdcWorkbookPreview
from .services.cdc import document_data, dossier_scope
from .services.cdc_exchange import (add_lot, apply_workbook, export_workbook, preview_workbook,
                                   restore_revision, set_lot_active)
from .services.work import require_work, work_allowed
from .views import add_validation
from .work_forms import OperationForm


class WorkbookForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    file = forms.FileField(label=_('Classeur Excel du dossier'))
    mode = forms.ChoiceField(label=_('Mode d’import'), choices=[('merge', _('Mettre à jour et ajouter, conserver les absents')),
        ('replace', _('Remplacer les articles des lots, retirer les absents'))])
    import_prices = forms.BooleanField(label=_('Importer aussi les estimations en DZD'), required=False)
    reason = forms.CharField(label=_('Justification et source des prix'), max_length=500)


class LotCreateForm(CdcLotForm):
    source = forms.ModelChoiceField(queryset=CdcLot.objects.none(), required=False,
        label=_('Réutiliser les articles d’un lot existant'))


class ConfirmForm(OperationForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(label=_('Justification'), max_length=500)
    confirm = forms.BooleanField(label=_('Je confirme cette opération'))


def _error(form, error):
    add_validation(form, ValidationError(str(error)) if isinstance(error, DocumentError) else error)


def _form(request, form, dossier, title):
    return render(request, 'erp/operation_form.html', {'form': form, 'title': title,
        'subtitle': dossier.reference, 'cancel_url': reverse('erp:cdc-detail', args=[dossier.pk])},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def workbook(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    editable = work_allowed(request.user, dossier.work, edit=True)
    cost_access = work_allowed(request.user, dossier.work, costs=True)
    form = WorkbookForm(request.POST or None, request.FILES or None,
        initial={'expected_version': dossier.version, 'mode': 'merge'})
    if not cost_access:
        form.fields.pop('import_prices')
    if request.method == 'POST':
        require_work(request.user, dossier.work, edit=True)
        if form.is_valid():
            values = dict(form.cleaned_data)
            try:
                preview = preview_workbook(request.user, dossier.pk, expected=values.pop('expected_version'),
                    upload=values.pop('file'), **values)
            except (ValidationError, DocumentError, IntegrityError) as error:
                _error(form, error)
            else:
                return redirect('erp:cdc-workbook-preview', pk=preview.pk)
    return render(request, 'erp/cdc_workbook.html', {'dossier': dossier, 'form': form,
        'editable': editable, 'cost_access': cost_access}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def workbook_download(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    try:
        data = export_workbook(request.user, dossier, filled=request.GET.get('blank') != '1',
            prices=request.GET.get('prices') == '1')
    except (ValidationError, DocumentError) as error:
        form = WorkbookForm(data={})
        _error(form, error)
        response = _form(request, form, dossier, _('Export Excel impossible'))
        response.status_code = 400
        return response
    return FileResponse(io.BytesIO(data), as_attachment=True,
        filename=f'CDC-{dossier.pk}-r{dossier.revision_number}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@login_required
@require_http_methods(['GET', 'POST'])
def workbook_preview(request, pk):
    preview = get_object_or_404(CdcWorkbookPreview.objects.select_related('dossier__work'), pk=pk,
        actor=request.user, dossier__in=dossier_scope(request.user))
    require_work(request.user, preview.dossier.work, costs=preview.import_prices)
    error = None
    if request.method == 'POST':
        try:
            apply_workbook(request.user, pk)
        except (ValidationError, DocumentError, IntegrityError) as exc:
            error = str(exc)
        else:
            messages.success(request, _('Import enregistré dans une nouvelle révision.'))
            return redirect('erp:cdc-detail', pk=preview.dossier_id)
    price_rows = []
    if preview.import_prices:
        for lot in preview.payload['data']['lot_catalog']['lots']:
            for item in lot['items']:
                if item['key'] in preview.payload['financial']:
                    price_rows.append({'lot': lot['name'], 'designation': item['designation'],
                        'price': preview.payload['financial'][item['key']]})
    return render(request, 'erp/cdc_workbook_preview.html', {'preview': preview,
        'diff': preview.payload['diff'], 'error': error,
        'financial': price_rows}, status=400 if error else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def lot_create(request, pk):
    dossier = get_object_or_404(dossier_scope(request.user), pk=pk)
    require_work(request.user, dossier.work, edit=True)
    form = LotCreateForm(request.POST or None, initial={'expected_version': dossier.version})
    form.fields['source'].queryset = CdcLot.objects.filter(dossier__in=dossier_scope(request.user),
        dossier__family=dossier.family, active=True).select_related('dossier').order_by('dossier__reference', 'position')
    form.fields['source'].label_from_instance = lambda lot: f'{lot.dossier.reference} — {lot.name}'
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            add_lot(request.user, pk, expected=values.pop('expected_version'), **values)
        except (ValidationError, DocumentError, IntegrityError) as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=pk)
    return _form(request, form, dossier, _('Ajouter ou réutiliser un lot'))


@login_required
@require_http_methods(['GET', 'POST'])
def lot_toggle(request, pk):
    lot = get_object_or_404(CdcLot.objects.select_related('dossier__work'), pk=pk,
        dossier__in=dossier_scope(request.user))
    require_work(request.user, lot.dossier.work, edit=True)
    form = ConfirmForm(request.POST or None, initial={'expected_version': lot.dossier.version})
    if request.method == 'POST' and form.is_valid():
        try:
            set_lot_active(request.user, pk, expected=form.cleaned_data['expected_version'],
                active=not lot.active, reason=form.cleaned_data['reason'])
        except (ValidationError, DocumentError, IntegrityError) as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=lot.dossier_id)
    return _form(request, form, lot.dossier, _('Retirer ou réintégrer le lot : %(name)s') % {'name': lot.name})


@login_required
@require_http_methods(['GET', 'POST'])
def revision_restore(request, pk):
    revision = get_object_or_404(CdcRevision.objects.select_related('dossier__work'), pk=pk,
        dossier__in=dossier_scope(request.user))
    require_work(request.user, revision.dossier.work, edit=True)
    from .permissions import require_manager
    require_manager(request.user)
    form = ConfirmForm(request.POST or None, initial={'expected_version': revision.dossier.version})
    if request.method == 'POST' and form.is_valid():
        try:
            restore_revision(request.user, pk, expected=form.cleaned_data['expected_version'], reason=form.cleaned_data['reason'])
        except (ValidationError, DocumentError, IntegrityError) as error:
            _error(form, error)
        else:
            return redirect('erp:cdc-detail', pk=revision.dossier_id)
    return _form(request, form, revision.dossier, _('Reprendre la révision %(number)s dans une nouvelle révision') % {'number': revision.number})
