"""Shared scoped filtering for inventory, grouped views and exports."""
from datetime import timedelta
import uuid

from django.db.models import F, Q
from django.http import Http404
from django.utils import timezone

from .models import Category, LocationClosure
from .services.stock import usable_filter


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise Http404 from error


def descendants(category):
    found = {category}
    parents = list(Category.objects.values_list('pk', 'parent_id'))
    pending = {category}
    while pending:
        pending = {pk for pk, parent in parents if parent in pending and pk not in found}
        found.update(pending)
    return found


def category_ancestors(categories):
    found = set(categories)
    parents = dict(Category.objects.values_list('pk', 'parent_id'))
    pending = found.copy()
    while pending:
        pending = {parents.get(pk) for pk in pending} - found - {None}
        found.update(pending)
    return found


def filter_stock(queryset, values):
    search = values.get('q', '').strip()[:255]
    if search:
        token = search.split('|')
        if len(token) == 3 and token[0] == 'PLAGENOR' and token[1] in ('article', 'lot', 'container', 'location'):
            field = {'article': 'lot__article_id', 'lot': 'lot_id', 'container': 'pk', 'location': 'location_id'}[token[1]]
            queryset = queryset.filter(**{field: identifier(token[2])})
        else:
            condition = Q()
            for field in ('code', 'lot__code', 'lot__manufacturer_lot', 'lot__serial_number', 'lot__barcode',
                    'lot__article__code', 'lot__article__name', 'lot__article__name_en', 'lot__article__name_ar',
                    'lot__article__cas', 'lot__article__catalog_reference', 'lot__article__manufacturer_reference',
                    'lot__article__supplier_reference', 'lot__article__brand', 'lot__article__manufacturer__name',
                    'lot__article__preferred_supplier__name', 'stockreceipt__supplier__name', 'location__code', 'location__name'):
                condition |= Q(**{field + '__icontains': search})
            try:
                pk = uuid.UUID(search)
            except ValueError:
                pass
            else:
                condition |= Q(pk=pk) | Q(lot_id=pk) | Q(lot__article_id=pk)
            queryset = queryset.filter(condition).distinct()
    for parameter, field in (('article', 'lot__article_id'), ('lot', 'lot_id'),
            ('manufacturer', 'lot__article__manufacturer_id'), ('kind', 'location__kind_id')):
        if values.get(parameter):
            queryset = queryset.filter(**{field: identifier(values[parameter])})
    if values.get('supplier'):
        pk = identifier(values['supplier'])
        queryset = queryset.filter(Q(lot__article__preferred_supplier_id=pk) | Q(stockreceipt__supplier_id=pk)).distinct()
    if values.get('category'):
        queryset = queryset.filter(lot__article__category_id__in=descendants(identifier(values['category'])))
    if values.get('location'):
        locations = LocationClosure.objects.filter(ancestor_id=identifier(values['location'])).values('descendant_id')
        queryset = queryset.filter(location_id__in=locations)
    state = values.get('state', 'all')
    if state == 'usable':
        queryset = queryset.filter(usable_filter(), quantity__gt=F('reserved'))
    elif state == 'blocked':
        queryset = queryset.exclude(usable_filter()).filter(quantity__gt=0)
    elif state == 'empty':
        queryset = queryset.filter(quantity=0)
    elif state == 'reserved':
        queryset = queryset.filter(reserved__gt=0)
    expiry = values.get('expiry', '')
    today = timezone.localdate()
    if expiry == 'expired':
        queryset = queryset.filter(Q(use_by__lt=today) | Q(lot__expires_on__lt=today))
    elif expiry == '30':
        until = today + timedelta(days=30)
        queryset = queryset.filter(Q(use_by__range=(today, until)) | Q(lot__expires_on__range=(today, until)))
    elif expiry == 'none':
        queryset = queryset.filter(use_by__isnull=True, lot__expires_on__isnull=True)
    return queryset
