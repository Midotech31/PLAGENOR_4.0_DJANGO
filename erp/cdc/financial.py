"""One decimal calculation for internal CDC screens and signed financial exchange."""
from decimal import Decimal, ROUND_HALF_UP, localcontext


def summarize(rows):
    currencies, lots, missing = {}, {}, 0
    with localcontext() as context:
        context.prec = 64
        for row in rows:
            row.update(net=None, tax=None, gross=None)
            group = lots.setdefault(row['lot'], {'name': row['lot_name'], 'currencies': {}, 'incomplete_lines': 0})
            if row['price'] is None or row['tax_rate'] is None:
                missing += 1
                group['incomplete_lines'] += 1
                continue
            row['net'] = (row['quantity'] * row['price']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            row['tax'] = (row['net'] * row['tax_rate'] / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            row['gross'] = row['net'] + row['tax']
            for aggregate in (currencies, group['currencies']):
                total = aggregate.setdefault(row['currency'], {'net': Decimal(0), 'tax': Decimal(0), 'gross': Decimal(0)})
                for field in ('net', 'tax', 'gross'):
                    total[field] += row[field]
    return {'currencies': currencies, 'lots': list(lots.values()), 'incomplete_lines': missing, 'lines': rows}


def excel_number(value):
    # Excel numeric cells have only 15 significant digits; retain larger amounts exactly as text.
    return str(value) if isinstance(value, Decimal) and len(value.as_tuple().digits) > 15 else value
