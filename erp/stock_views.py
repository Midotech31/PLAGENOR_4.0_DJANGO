from decimal import Decimal
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import F, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from . import stock_forms as forms
from .models import (Article, Capability, Category, Location, LocationType, Party, StockContainer,
    LocationClosure, StockDispatch, StockDispatchLine, StockEntry, StockLot, StockMovement, StockReservation)
from .permissions import grants, has_access, is_manager, operational_scope, permitted, require_manager
from .services.stock import (control_container, control_lot, fefo, is_usable, open_container,
    receive_stock, reconcile_stock, release_stock, remove_stock, reserve_stock, reverse_stock,
    transfer_stock, usable_filter)
from .views import add_validation
from .stock_queries import category_ancestors, filter_stock, identifier
from .services.stock_reporting import dashboard_data, entry_balances, grouped_rows, with_availability


def stock_queryset(user):
    if not is_manager(user) and not grants(user, Capability.VIEW_STOCK).exists():
        raise PermissionDenied
    return operational_scope(StockContainer.objects.all(), user).select_related('lot__article__base_unit',
        'lot__article__category', 'lot__article__manufacturer', 'lot__article__preferred_supplier', 'location', 'location__kind')


@login_required
@require_GET
def stock_list(request):
    base = stock_queryset(request.user)
    qs = filter_stock(base, request.GET)
    search = request.GET.get('q', '').strip()[:200]
    state = request.GET.get('state', 'all')
    view = request.GET.get('view', 'containers')
    if view not in ('containers', 'products', 'lots', 'locations'):
        raise Http404
    descending = request.GET.get('direction') == 'desc'
    if view == 'containers':
        sort = {'code': 'code', 'article': 'lot__article__code', 'quantity': 'quantity',
            'expiry': 'stock_expiry', 'location': 'location__code'}.get(request.GET.get('sort'), 'lot__article__code')
        order = F(sort).desc(nulls_last=True) if descending else F(sort).asc(nulls_last=True)
        page = Paginator(with_availability(qs).order_by(order, 'pk'), 30).get_page(request.GET.get('page'))
        for container in page:
            container.stock_available = container.quantity - container.reserved if container.stock_usable else Decimal(0)
    else:
        field = {'products': 'lot__article', 'lots': 'lot', 'locations': 'location'}[view]
        identities = qs.order_by(('-' if descending else '') + field + '__code', field + '_id').values_list(
            field + '_id', field + '__code').distinct()
        page = Paginator(identities, 30).get_page(request.GET.get('page'))
        ids = [row[0] for row in page]
        rows = grouped_rows(qs, view, ids)
        page.object_list = [rows[pk] for pk in ids]
    columns = request.GET.getlist('columns') if 'columns_configured' in request.GET else ['lot', 'location', 'physical', 'available', 'reserved', 'expiry', 'status']
    query = request.GET.copy()
    query.pop('page', None)
    query.pop('export', None)
    filter_options = [
        {'key': 'category', 'label': _('Catégorie'), 'choices': Category.objects.filter(pk__in=category_ancestors(base.values_list('lot__article__category_id', flat=True)))},
        {'key': 'location', 'label': _('Emplacement'), 'choices': Location.objects.filter(pk__in=LocationClosure.objects.filter(
            descendant_id__in=base.values('location_id')).values('ancestor_id'))},
        {'key': 'kind', 'label': _('Type d’emplacement'), 'choices': LocationType.objects.filter(pk__in=base.values('location__kind_id'))},
        {'key': 'manufacturer', 'label': _('Fabricant'), 'choices': Party.objects.filter(pk__in=base.values('lot__article__manufacturer_id'))},
        {'key': 'supplier', 'label': _('Fournisseur'), 'choices': Party.objects.filter(Q(pk__in=base.values('lot__article__preferred_supplier_id')) |
            Q(pk__in=base.values('stockreceipt__supplier_id'))).distinct()},
    ]
    for option in filter_options:
        option['selected'] = request.GET.get(option['key'], '')
    return render(request, 'erp/stock_list.html', {'page': page, 'q': search, 'state': state, 'view': view,
        'columns': columns, 'filters': request.GET, 'export_query': query.urlencode(),
        'filter_options': filter_options, 'column_options': [('lot', _('Lot fabricant')), ('location', _('Emplacement')),
            ('physical', _('Physique')), ('available', _('Disponible')), ('reserved', _('Réservé')),
            ('expiry', _('Date limite')), ('status', _('Contrôle'))],
        'can_receive': is_manager(request.user) or grants(request.user, Capability.RECEIVE_STOCK).exists(),
        'can_dispatch': is_manager(request.user) or any(grants(request.user, cap).exists() for cap in (Capability.CONSUME_STOCK, Capability.TRANSFER_STOCK)),
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
    container = get_object_or_404(with_availability(stock_queryset(request.user)), pk=pk)
    scope = {'category': container.lot.article.category, 'location': container.location}
    permissions = {key: permitted(request.user, capability, **scope) for key, capability in (
        ('consume', Capability.CONSUME_STOCK), ('control', Capability.CONTROL_STOCK),
        ('transfer', Capability.TRANSFER_STOCK), ('reserve', Capability.RESERVE_STOCK))}
    entries = container.entries.select_related('movement__actor', 'location').order_by('-id')
    if not is_manager(request.user):
        entries = operational_scope(entries, request.user, category_field='container__lot__article__category_id')
    suggested = fefo(request.user, container.lot.article).first()
    from .services.safety import storage_compatibility
    compatibility=storage_compatibility(container.lot.article,container.location,exclude=container)
    receipt=container.stockreceipt_set.first()
    return render(request, 'erp/stock_detail.html', {'container': container, 'permissions': permissions,
        'usable': is_usable(container), 'available': max(Decimal(0), container.quantity-container.reserved) if is_usable(container) else Decimal(0),
        'entries': entry_balances(entries[:100]), 'reservations': container.reservations.filter(remaining__gt=0),
        'suggested': suggested, 'compatibility':compatibility, 'receipt':receipt, 'manager': is_manager(request.user)})


OPERATIONS = {
    'control': (forms.ControlForm, control_container, _('Contrôler le contenant'), Capability.CONTROL_STOCK),
    'open': (forms.OpenForm, open_container, _('Enregistrer l’ouverture'), Capability.CONSUME_STOCK),
    'remove': (forms.RemoveForm, remove_stock, _('Enregistrer une sortie'), None),
    'transfer': (forms.TransferForm, transfer_stock, _('Transférer le stock'), Capability.TRANSFER_STOCK),
    'reserve': (forms.ReserveForm, reserve_stock, _('Réserver du stock'), Capability.RESERVE_STOCK),
    'aliquot': (forms.AliquotForm, transfer_stock, _('Créer une aliquote'), Capability.TRANSFER_STOCK),
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
    if action in ('remove', 'transfer', 'reserve', 'aliquot'):
        kwargs.update(user=request.user, container=container)
    form = form_type(request.POST or None, **kwargs)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        if 'expected_version' in values:
            values['expected'] = values.pop('expected_version')
        if action == 'aliquot':
            values['aliquot'] = True
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
            Q(container__lot__article__code__icontains=search) | Q(location__code__icontains=search) |
            Q(container__lot__article__catalog_reference__icontains=search) | Q(container__lot__article__supplier_reference__icontains=search))
    if request.GET.get('container'):
        qs = qs.filter(container_id=identifier(request.GET['container']))
    if request.GET.get('kind'):
        qs = qs.filter(movement__kind=request.GET['kind'])
    for name, lookup in (('from', 'created_at__date__gte'), ('until', 'created_at__date__lte')):
        if request.GET.get(name):
            try:
                day = date.fromisoformat(request.GET[name])
            except ValueError:
                raise Http404
            qs = qs.filter(**{lookup: day})
    if request.GET.get('article'):
        qs = qs.filter(container__lot__article_id=identifier(request.GET['article']))
    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    page.object_list = entry_balances(page.object_list)
    return render(request, 'erp/ledger.html', {'page': page,
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


@login_required
@require_GET
def stock_dashboard(request):
    qs = filter_stock(stock_queryset(request.user), request.GET)
    try:
        days = int(request.GET.get('days', '90'))
    except ValueError:
        raise Http404
    if not 1 <= days <= 366:
        raise Http404
    include_unstocked = not any(request.GET.get(key) for key in ('q', 'article', 'lot', 'category',
        'location', 'kind', 'manufacturer', 'supplier', 'expiry', 'state'))
    context = dashboard_data(request.user, qs, days, include_unstocked=include_unstocked)
    context['filters'] = request.GET
    return render(request, 'erp/stock_dashboard.html', context)


@login_required
@require_GET
def stock_export(request):
    from .services.stock_exports import stock_pdf, stock_workbook
    qs = filter_stock(stock_queryset(request.user), request.GET)
    kind = request.GET.get('format', 'xlsx')
    if kind not in ('xlsx', 'pdf'):
        raise Http404
    try:
        data = stock_pdf(qs) if kind == 'pdf' else stock_workbook(qs)
    except ValidationError as error:
        return render(request, 'erp/stock_export_error.html', {'errors': error.messages}, status=400)
    content_type = 'application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response = HttpResponse(data, content_type=content_type)
    response['Content-Disposition'] = 'attachment; filename="PLAGENOR-inventaire.' + kind + '"'
    response['Cache-Control'] = 'private, no-store'
    return response


def dispatch_queryset(user):
    stock = stock_queryset(user)
    if is_manager(user):
        return StockDispatch.objects.select_related('actor', 'destination')
    inaccessible = StockContainer.objects.exclude(pk__in=stock.values('pk'))
    return StockDispatch.objects.filter(lines__container__in=stock).exclude(
        lines__container__in=inaccessible).select_related('actor', 'destination').distinct()


@login_required
@require_http_methods(['GET', 'POST'])
def dispatch_create(request):
    stock_queryset(request.user)
    if not is_manager(request.user) and not any(grants(request.user, cap).exists() for cap in (Capability.CONSUME_STOCK, Capability.TRANSFER_STOCK)):
        raise PermissionDenied
    form = forms.DispatchForm(request.POST or None, user=request.user)
    initial = []
    if request.GET.get('container'):
        container = get_object_or_404(stock_queryset(request.user), pk=identifier(request.GET['container']))
        initial.append({'container': container, 'unit': container.lot.article.base_unit, 'expected': container.version})
    lines = forms.DispatchLineFormSet(request.POST or None, prefix='lines', initial=initial, form_kwargs={'user': request.user})
    if request.method == 'POST' and form.is_valid() and lines.is_valid():
        try:
            from .services.distributions import distribute_stock
            dispatch = distribute_stock(request.user, lines=[line.cleaned_data for line in lines if line.cleaned_data], **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:dispatch-detail', pk=dispatch.pk)
    return render(request, 'erp/dispatch_form.html', {'form': form, 'lines': lines}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def dispatch_sources(request):
    qs = filter_stock(stock_queryset(request.user), request.GET).filter(usable_filter(), quantity__gt=F('reserved'))
    rows = [{'id': str(obj.pk), 'label': forms.ContainerChoice(queryset=qs).label_from_instance(obj),
        'version': obj.version, 'unit': str(obj.lot.article.base_unit_id)}
        for obj in qs.order_by('lot__article__code', 'code')[:40]]
    response = JsonResponse({'results': rows})
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@require_GET
def dispatch_list(request):
    return render(request, 'erp/dispatch_list.html', {'page': Paginator(dispatch_queryset(request.user), 30).get_page(request.GET.get('page'))})


@login_required
@require_GET
def dispatch_detail(request, pk):
    from .services.distributions import returnable_quantity
    dispatch = get_object_or_404(dispatch_queryset(request.user), pk=pk)
    lines = list(dispatch.lines.select_related('container__lot__article__base_unit', 'movement'))
    for line in lines:
        line.returnable = returnable_quantity(line)
    if request.GET.get('format') == 'pdf':
        from .services.stock_exports import dispatch_pdf
        try:
            data = dispatch_pdf(dispatch, lines)
        except ValidationError as error:
            return render(request, 'erp/stock_export_error.html', {'errors': error.messages}, status=400)
        response = HttpResponse(data, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="PLAGENOR-distribution.pdf"'
        response['Cache-Control'] = 'private, no-store'
        return response
    return render(request, 'erp/dispatch_detail.html', {'dispatch': dispatch, 'lines': lines})


@login_required
@require_http_methods(['GET', 'POST'])
def stock_return(request, pk):
    from .services.distributions import return_stock
    line = get_object_or_404(StockDispatchLine.objects.select_related('container__lot__article__base_unit'),
        pk=pk, dispatch__in=dispatch_queryset(request.user))
    form = forms.ReturnForm(request.POST or None, user=request.user, line=line)
    if request.method == 'POST' and form.is_valid():
        try:
            returned = return_stock(request.user, line.pk, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:stock-detail', pk=returned.container_id)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Retour au stock'),
        'cancel_url': reverse('erp:dispatch-detail', args=[line.dispatch_id])}, status=400 if request.method == 'POST' else 200)
