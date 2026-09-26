from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from .inventory_forms import LegacyInventoryReviewForm
from .models import InventoryCampaign, InventoryLine, LegacyInventoryRecord, WorkItem
from .permissions import is_manager, require_manager
from .services.inventory import (approve_inventory, count_inventory, create_inventory,
                                 recount_inventory, submit_inventory)
from .services.legacy_inventory import review_legacy_record
from .services.work import require_work, work_allowed, work_scope
from .stock_forms import CountForm, InventoryDecisionForm, InventoryForm
from .views import add_validation


def campaigns(user):
    return InventoryCampaign.objects.filter(work__in=work_scope(user)).select_related('work', 'work__assignee')


@login_required
@require_GET
def inventory_list(request):
    return render(request, 'erp/inventory_list.html', {'page': Paginator(campaigns(request.user).order_by('-created_at'), 30).get_page(request.GET.get('page')),
        'manager': is_manager(request.user)})


@login_required
@require_GET
def initial_inventory_trace(request):
    require_manager(request.user)
    records = LegacyInventoryRecord.objects.select_related('reviewed_by').all().order_by(
        'resolution', 'review_status', 'kind', 'source_file', 'source_section', 'source_row'
    )
    kind = request.GET.get('kind', '').strip()
    resolution = request.GET.get('resolution', '').strip()
    review_status = request.GET.get('review_status', '').strip()
    search = request.GET.get('q', '').strip()[:200]
    if kind in LegacyInventoryRecord.Kind.values:
        records = records.filter(kind=kind)
    else:
        kind = ''
    if resolution in LegacyInventoryRecord.Resolution.values:
        records = records.filter(resolution=resolution)
    else:
        resolution = ''
    if review_status in LegacyInventoryRecord.ReviewStatus.values:
        records = records.filter(review_status=review_status)
    else:
        review_status = ''
    if search:
        records = records.filter(
            Q(source_file__icontains=search)
            | Q(source_section__icontains=search)
            | Q(note__icontains=search)
            | Q(review_note__icontains=search)
        )
    summary = {
        row['resolution']: row['n']
        for row in LegacyInventoryRecord.objects.values('resolution').annotate(n=Count('id'))
    }
    review_summary = {
        row['review_status']: row['n']
        for row in LegacyInventoryRecord.objects.filter(
            resolution=LegacyInventoryRecord.Resolution.REVIEW
        ).values('review_status').annotate(n=Count('id'))
    }
    return render(
        request,
        'erp/initial_inventory_trace.html',
        {
            'page': Paginator(records, 50).get_page(request.GET.get('page')),
            'kind': kind,
            'resolution': resolution,
            'review_status': review_status,
            'q': search,
            'kinds': LegacyInventoryRecord.Kind.choices,
            'resolutions': LegacyInventoryRecord.Resolution.choices,
            'review_statuses': LegacyInventoryRecord.ReviewStatus.choices,
            'summary': summary,
            'review_summary': review_summary,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def initial_inventory_review(request, pk):
    require_manager(request.user)
    record = get_object_or_404(
        LegacyInventoryRecord.objects.select_related('reviewed_by'),
        pk=pk,
        resolution=LegacyInventoryRecord.Resolution.REVIEW,
    )
    initial = {
        'expected_version': record.version,
        'review_status': (
            record.review_status
            if record.review_status != LegacyInventoryRecord.ReviewStatus.OPEN
            else LegacyInventoryRecord.ReviewStatus.CONFIRMED
        ),
        'review_note': record.review_note,
    }
    form = LegacyInventoryReviewForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            review_legacy_record(
                request.user,
                record.pk,
                expected=values.pop('expected_version'),
                **values,
            )
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:initial-inventory-trace')
    raw_rows = sorted(
        ((key, value) for key, value in record.raw_data.items() if not key.startswith('__')),
        key=lambda item: item[0].casefold(),
    )
    return render(
        request,
        'erp/initial_inventory_review.html',
        {
            'record': record,
            'form': form,
            'raw_rows': raw_rows,
            'cancel_url': reverse('erp:initial-inventory-trace'),
        },
        status=400 if request.method == 'POST' else 200,
    )

@login_required
@require_http_methods(['GET', 'POST'])
def inventory_create(request):
    require_manager(request.user)
    form = InventoryForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        values.pop('expected_version')
        try:
            campaign = create_inventory(request.user, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:inventory-detail', pk=campaign.pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Créer et affecter un inventaire'),
        'cancel_url': reverse('erp:inventory-list')}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def inventory_detail(request, pk):
    campaign = get_object_or_404(campaigns(request.user), pk=pk)
    work = campaign.work
    form = InventoryDecisionForm(request.POST or None, initial={'expected_version': work.version})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected, key = values.pop('expected_version'), values.pop('key')
        try:
            action = request.POST.get('action')
            if action == 'submit':
                submit_inventory(request.user, pk, expected=expected, **values)
            elif action == 'approve':
                approve_inventory(request.user, pk, expected=expected, key=key, **values)
            elif action == 'recount':
                ids = request.POST.getlist('lines')
                if len(ids) > 10000:
                    raise ValidationError(_('Sélection trop volumineuse.'))
                recount_inventory(request.user, pk, expected=expected, line_ids=ids, **values)
            else:
                return HttpResponseBadRequest(_('Action inconnue.'))
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:inventory-detail', pk=pk)
    lines = campaign.lines.select_related('container__lot__article__base_unit', 'location', 'counted_by')
    search = request.GET.get('q', '').strip()[:200]
    if search:
        from django.db.models import Q
        lines = lines.filter(Q(container__code__icontains=search) | Q(container__lot__article__name__icontains=search))
    page = Paginator(lines, 50).get_page(request.GET.get('page'))
    reveal = is_manager(request.user) or not campaign.blind or work.status == WorkItem.Status.APPROVED
    rows = [{'line': line, 'difference': line.counted_quantity - line.theoretical_quantity if reveal and line.counted_quantity is not None else None} for line in page]
    return render(request, 'erp/inventory_detail.html', {'campaign': campaign, 'work': work,
        'form': form, 'rows': rows, 'page': page, 'q': search, 'reveal': reveal,
        'manager': is_manager(request.user), 'editable': work_allowed(request.user, work, edit=True)},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def inventory_count(request, pk):
    line = get_object_or_404(InventoryLine.objects.select_related('campaign__work', 'container__lot__article__base_unit'),
        pk=pk, campaign__in=campaigns(request.user))
    require_work(request.user, line.campaign.work, edit=True)
    form = CountForm(request.POST or None, initial={'expected_version': line.version,
        'container_version': line.container.version, 'amount': line.counted_quantity, 'note': line.note})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            count_inventory(request.user, pk, expected=values.pop('expected_version'), **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:inventory-detail', pk=line.campaign_id)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Compter un contenant'),
        'subtitle': line.container.code + ' — ' + str(line.container.lot.article) + ' (' + str(line.container.lot.article.base_unit) + ')',
        'cancel_url': reverse('erp:inventory-detail', args=[line.campaign_id])},
        status=400 if request.method == 'POST' else 200)
