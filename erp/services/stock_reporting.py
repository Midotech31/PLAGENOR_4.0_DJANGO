"""Exact quantities and operational indicators, always within the user's scope."""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING

from django.core.exceptions import ValidationError
from django.db.models import BooleanField, Case, DateField, OuterRef, Subquery, Value, When
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from erp.models import Article, Capability, StockEntry, StockReceipt
from erp.permissions import catalog_scope, operational_scope, permitted
from .catalog import convert_quantity
from .stock import usable_filter


def with_availability(queryset):
    receipts = StockReceipt.objects.filter(container_id=OuterRef('pk'), movement__reversal__isnull=True).order_by(
        'received_on', 'pk').values('received_on')[:1]
    return queryset.annotate(stock_usable=Case(When(usable_filter(), then=Value(True)),
        default=Value(False), output_field=BooleanField()),
        stock_received_on=Coalesce('fifo_received_on', Subquery(receipts, output_field=DateField()), TruncDate('created_at')))


def grouped_rows(queryset, view, identities):
    field = {'products': 'lot__article_id', 'lots': 'lot_id', 'locations': 'location_id'}[view]
    groups = {}
    for container in with_availability(queryset.filter(**{field + '__in': identities})).iterator():
        article = container.lot.article
        obj = article if view == 'products' else container.lot if view == 'lots' else container.location
        row = groups.setdefault(obj.pk, {'id': obj.pk, 'code': obj.code, 'name': str(obj),
            'article': article if view != 'locations' else None,
            'manufacturer_lot': container.lot.manufacturer_lot if view == 'lots' else '',
            'locations': set(), 'lots': set(), 'units': {}})
        row['locations'].add(container.location.code)
        row['lots'].add(container.lot_id)
        values = row['units'].setdefault(article.base_unit_id, {'unit': article.base_unit.code,
            'physical': Decimal(0), 'reserved': Decimal(0), 'available': Decimal(0)})
        values['physical'] += container.quantity
        values['reserved'] += container.reserved
        if container.stock_usable:
            values['available'] += container.quantity - container.reserved
    for row in groups.values():
        row['quantities'] = sorted(row['units'].values(), key=lambda value: value['unit'])
        row['locations'] = ', '.join(sorted(row['locations']))
        row['lot_count'] = len(row['lots'])
    return groups


def dashboard_data(user, queryset, days=90, *, include_unstocked=True):
    today = timezone.localdate()
    products, units, locations = {}, {}, {}
    soon, blocked = 0, 0
    lots, lot_quantities = set(), {}
    containers = with_availability(queryset)
    for container in containers.iterator():
        article = container.lot.article
        available = container.quantity - container.reserved if container.stock_usable else Decimal(0)
        row = products.setdefault(article.pk, {'article': article, 'physical': Decimal(0),
            'reserved': Decimal(0), 'available': Decimal(0), 'consumed': Decimal(0), 'suggested': Decimal(0)})
        for key, amount in (('physical', container.quantity), ('reserved', container.reserved), ('available', available)):
            row[key] += amount
        key = article.base_unit.code
        summary = units.setdefault(key, {'unit': key, 'physical': Decimal(0), 'available': Decimal(0), 'reserved': Decimal(0)})
        for field in ('physical', 'reserved', 'available'):
            summary[field] += {'physical': container.quantity, 'reserved': container.reserved, 'available': available}[field]
        location = locations.setdefault((container.location_id, key), {'id': container.location_id,
            'location': str(container.location), 'unit': key, 'available': Decimal(0)})
        location['available'] += available
        lots.add(container.lot_id)
        lot_quantities[container.lot_id] = lot_quantities.get(container.lot_id, Decimal(0)) + container.quantity
        if container.quantity:
            limit = min((value for value in (container.use_by, container.lot.expires_on) if value), default=None)
            soon += bool(limit and today <= limit <= today + timedelta(days=30))
            blocked += not container.stock_usable
    entries = operational_scope(StockEntry.objects.filter(container__in=queryset,
        created_at__date__gte=today - timedelta(days=days - 1)), user,
        category_field='container__lot__article__category_id').select_related('movement__reversal', 'container__lot__article__base_unit')
    flows = {}
    for entry in entries.iterator():
        article = entry.container.lot.article
        key = (entry.movement.kind, article.base_unit.code)
        row = flows.setdefault(key, {'kind': entry.movement.get_kind_display(), 'kind_code': key[0], 'unit': key[1],
            'quantity': Decimal(0), 'count': 0})
        row['quantity'] += entry.quantity_delta
        row['count'] += 1
        if entry.movement.kind in ('CONSUMPTION', 'EXIT') and not hasattr(entry.movement, 'reversal'):
            products[article.pk]['consumed'] += max(Decimal(0), -entry.quantity_delta)
    if include_unstocked:
        absent = catalog_scope(Article.objects.filter(active=True).exclude(pk__in=products), user,
            capability=Capability.VIEW_STOCK).select_related('base_unit', 'purchase_unit', 'category')
        for article in absent:
            products[article.pk] = {'article': article, 'physical': Decimal(0), 'reserved': Decimal(0),
                'available': Decimal(0), 'consumed': Decimal(0), 'suggested': Decimal(0)}
    for row in products.values():
        article = row['article']
        threshold = max(article.minimum_stock, article.reorder_point, article.safety_stock)
        if article.lead_time_days is not None:
            threshold = max(threshold, row['consumed'] / Decimal(days) * article.lead_time_days + article.safety_stock)
        row['low'] = row['available'] < threshold
        row['overstock'] = bool(article.target_stock and row['available'] > article.target_stock)
        if row['low']:
            need = max(Decimal(0), max(article.target_stock, threshold) - row['available'])
            row['purchase_unit'] = article.purchase_unit or article.base_unit
            try:
                factor = convert_quantity(article, 1, row['purchase_unit'])[1]
            except ValidationError:
                row['purchase_missing'] = True
                row['suggested'] = need
            else:
                purchase = max(need / factor, article.minimum_order_quantity)
                row['purchase_suggested'] = (purchase / article.order_multiple).to_integral_value(rounding=ROUND_CEILING) * article.order_multiple
                row['suggested'] = row['purchase_suggested'] * factor
    costs, priced_lots, cost_permissions = {}, set(), {}
    receipts = StockReceipt.objects.filter(container__lot_id__in=lots,
        movement__reversal__isnull=True, unit_price__isnull=False).select_related('container__lot__article').order_by(
            '-received_on', '-created_at', '-pk')
    for receipt in receipts:
        lot_id = receipt.container.lot_id
        article = receipt.container.lot.article
        if article.category_id not in cost_permissions:
            cost_permissions[article.category_id] = permitted(user, Capability.VIEW_COST, category=article.category)
        if lot_id in priced_lots or not cost_permissions[article.category_id]:
            continue
        quantity = lot_quantities[lot_id]
        costs[receipt.currency] = costs.get(receipt.currency, Decimal(0)) + quantity * receipt.unit_price
        priced_lots.add(lot_id)
    return {'products': sorted(products.values(), key=lambda row: row['article'].code),
        'units': sorted(units.values(), key=lambda row: row['unit']), 'locations': sorted(locations.values(), key=lambda row: (row['location'], row['unit'])),
        'flows': sorted(flows.values(), key=lambda row: (row['kind'], row['unit'])),
        'references': len(products), 'lot_count': len(lots), 'soon': soon, 'blocked': blocked,
        'empty': sum(row['available'] == 0 for row in products.values()),
        'low': sum(row['low'] for row in products.values()), 'costs': costs,
        'unpriced_lots': len(lots - priced_lots), 'days': days, 'period_start': today - timedelta(days=days - 1)}


def entry_balances(entries):
    """Derive legacy before/after balances without changing historical JSON."""
    entries = list(entries)
    container_ids = {entry.container_id for entry in entries}
    balances, selected = {}, {entry.pk: entry for entry in entries}
    for pk, container_id, physical, reserved in StockEntry.objects.filter(container_id__in=container_ids,
            pk__lte=max(selected, default=0)).order_by('pk').values_list('pk', 'container_id', 'quantity_delta', 'reserved_delta'):
        balance = balances.setdefault(container_id, [Decimal(0), Decimal(0)])
        before = tuple(balance)
        balance[0] += physical
        balance[1] += reserved
        if pk in selected:
            entry = selected[pk]
            entry.physical_before, entry.reserved_before = before
            entry.physical_after, entry.reserved_after = balance
    return entries
