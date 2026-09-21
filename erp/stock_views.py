from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import F, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from . import stock_forms as forms
from .models import Capability, StockContainer, StockEntry, StockLot, StockMovement, StockReservation
from .permissions import grants, has_access, is_manager, operational_scope, permitted, require_manager
from .services.stock import (control_container, control_lot, fefo, is_usable, open_container,
    receive_stock, reconcile_stock, release_stock, remove_stock, reserve_stock, reverse_stock,
    transfer_stock, usable_filter)
from .views import add_validation


def stock_queryset(user):
    if not is_manager(user) and not grants(user, Capability.VIEW_STOCK).exists():
        raise PermissionDenied
    return operational_scope(StockContainer.objects.all(), user).select_related('lot__article__base_unit', 'lot__article__category', 'location', 'location__kind')


@login_required
@require_GET
def stock_list(request):
    qs = stock_queryset(request.user)
    search = request.GET.get('q', '').strip()[:200]
    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(lot__code__icontains=search) |
            Q(lot__manufacturer_lot__icontains=search) | Q(lot__article__name__icontains=search) |
            Q(lot__article__code__icontains=search) | Q(lot__article__cas__icontains=search) |
            Q(lot__article__manufacturer_reference__icontains=search) | Q(lot__barcode__icontains=search) |
            Q(location__code__icontains=search))
    state = request.GET.get('state', 'all')
    if state == 'usable':
        qs = qs.filter(usable_filter(), quantity__gt=F('reserved'))
    elif state == 'blocked':
        qs = qs.exclude(usable_filter()).filter(quantity__gt=0)
    elif state == 'empty':
        qs = qs.filter(quantity=0)
    elif state == 'reserved':
        qs = qs.filter(reserved__gt=0)
    page = Paginator(qs.order_by('lot__article__code', 'code'), 30).get_page(request.GET.get('page'))
    return render(request, 'erp/stock_list.html', {'page': page, 'q': search, 'state': state,
        'can_receive': is_manager(request.user) or grants(request.user, Capability.RECEIVE_STOCK).exists(),
        'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def receipt_create(request):
    if not is_manager(request.user) and not grants(request.user, Capability.RECEIVE_STOCK).exists():
        raise PermissionDenied
    form = forms.ReceiptForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            movement = receive_stock(request.user, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            messages.success(request, _('Réception enregistrée. Le stock reste bloqué jusqu’au contrôle.'))
            return redirect('erp:stock-detail', pk=movement.receipt.container_id)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Réceptionner un lot'),
        'cancel_url': reverse('erp:stock-list')}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def stock_detail(request, pk):
    container = get_object_or_404(stock_queryset(request.user), pk=pk)
    scope = {'category': container.lot.article.category, 'location': container.location}
    permissions = {key: permitted(request.user, capability, **scope) for key, capability in (
        ('consume', Capability.CONSUME_STOCK), ('control', Capability.CONTROL_STOCK),
        ('transfer', Capability.TRANSFER_STOCK), ('reserve', Capability.RESERVE_STOCK))}
    entries = container.entries.select_related('movement__actor', 'location').order_by('-id')
    if not is_manager(request.user):
        entries = operational_scope(entries, request.user, category_field='container__lot__article__category_id')
    suggested = fefo(request.user, container.lot.article).first()
    return render(request, 'erp/stock_detail.html', {'container': container, 'permissions': permissions,
        'usable': is_usable(container), 'available': max(Decimal(0), container.quantity-container.reserved) if is_usable(container) else Decimal(0),
        'entries': entries[:100], 'reservations': container.reservations.filter(remaining__gt=0),
        'suggested': suggested, 'manager': is_manager(request.user)})


OPERATIONS = {
    'control': (forms.ControlForm, control_container, _('Contrôler le contenant'), Capability.CONTROL_STOCK),
    'open': (forms.OpenForm, open_container, _('Enregistrer l’ouverture'), Capability.CONSUME_STOCK),
    'remove': (forms.RemoveForm, remove_stock, _('Enregistrer une sortie'), None),
    'transfer': (forms.TransferForm, transfer_stock, _('Transférer le stock'), Capability.TRANSFER_STOCK),
    'reserve': (forms.ReserveForm, reserve_stock, _('Réserver du stock'), Capability.RESERVE_STOCK),
}


@login_required
@require_http_methods(['GET', 'POST'])
def stock_action(request, pk, action):
    if action not in OPERATIONS:
        raise Http404
    container = get_object_or_404(stock_queryset(request.user), pk=pk)
    form_type, service, title, capability = OPERATIONS[action]
    scope = {'category': container.lot.article.category, 'location': container.location}
    if capability and not permitted(request.user, capability, **scope):
        raise PermissionDenied
    if action == 'remove' and not any(permitted(request.user, cap, **scope) for cap in (Capability.CONSUME_STOCK, Capability.CONTROL_STOCK)):
        raise PermissionDenied
    kwargs = {'initial': {'expected_version': container.version}}
    if action in ('remove', 'transfer', 'reserve'):
        kwargs.update(user=request.user, container=container)
    form = form_type(request.POST or None, **kwargs)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        if 'expected_version' in values:
            values['expected'] = values.pop('expected_version')
        try:
            service(request.user, pk, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:stock-detail', pk=pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': title,
        'subtitle': container.code + ' — ' + str(container.lot.article),
        'cancel_url': reverse('erp:stock-detail', args=[pk])}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def reservation_release(request, pk):
    reservation = get_object_or_404(StockReservation, pk=pk, container__in=stock_queryset(request.user))
    container = reservation.container
    if not permitted(request.user, Capability.RESERVE_STOCK, category=container.lot.article.category, location=container.location):
        raise PermissionDenied
    form = forms.ReasonForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            release_stock(request.user, pk, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:stock-detail', pk=container.pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Libérer une réservation'),
        'cancel_url': reverse('erp:stock-detail', args=[container.pk])}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def movement_reverse(request, pk):
    require_manager(request.user)
    movement = get_object_or_404(StockMovement, pk=pk)
    form = forms.ReasonForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            reverse_stock(request.user, movement.pk, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:stock-list')
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Contre-passer un mouvement'),
        'cancel_url': reverse('erp:stock-list')}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def ledger(request):
    stock_queryset(request.user)
    qs = operational_scope(StockEntry.objects.select_related('movement__actor', 'container__lot__article__base_unit', 'location'),
        request.user, category_field='container__lot__article__category_id').order_by('-id')
    search = request.GET.get('q', '').strip()[:200]
    if search:
        qs = qs.filter(Q(container__code__icontains=search) | Q(container__lot__manufacturer_lot__icontains=search) |
            Q(container__lot__article__code__icontains=search) | Q(location__code__icontains=search))
    return render(request, 'erp/ledger.html', {'page': Paginator(qs, 40).get_page(request.GET.get('page')),
        'q': search, 'manager': is_manager(request.user)})


@login_required
@require_GET
def reconcile(request):
    require_manager(request.user)
    errors = reconcile_stock(request.user)
    return render(request, 'erp/reconcile.html', {'errors': errors, 'count': StockContainer.objects.count()})


@login_required
@require_http_methods(['GET', 'POST'])
def lot_control(request, pk):
    require_manager(request.user)
    lot = get_object_or_404(StockLot, pk=pk)
    form = forms.ControlForm(request.POST or None, initial={'expected_version': lot.version, 'status': lot.status})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            control_lot(request.user, pk, expected=values.pop('expected_version'), **values)
        except ValidationError as error:
            add_validation(form, error)
        else:
            return redirect('erp:stock-list')
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Rappeler / contrôler l’ensemble du lot'),
        'subtitle': lot.code, 'cancel_url': reverse('erp:stock-list')}, status=400 if request.method == 'POST' else 200)
