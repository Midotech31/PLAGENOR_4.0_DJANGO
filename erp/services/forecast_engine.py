from calendar import monthrange
import heapq
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP, localcontext


ZERO = Decimal(0)
SIX = Decimal('0.000001')
LIMIT = Decimal('999999999999.999999')
METHODS = ('MEAN_12', 'RECENT_6', 'TREND_12', 'SEASONAL_NAIVE')


def number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError('Invalid quantity') from exc
    if isinstance(value, bool) or not result.is_finite() or not ZERO <= result <= LIMIT:
        raise ValueError('Quantity outside supported bounds')
    return result


def decimal_text(value):
    return format(value.quantize(SIX, rounding=ROUND_HALF_UP), 'f')


def month_after(day, offset=1):
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def _predict(values, method, horizon):
    if not values:
        return ZERO
    if method == 'SEASONAL_NAIVE':
        return values[-12 + (horizon-1) % 12]
    recent = values[-6:] if method == 'RECENT_6' else values[-12:]
    mean = sum(recent, ZERO) / len(recent)
    if method != 'TREND_12' or len(recent) < 2:
        return mean
    center = Decimal(len(recent)-1) / 2
    slope = sum(((Decimal(i)-center)*(y-mean) for i,y in enumerate(recent)), ZERO) / sum(
        ((Decimal(i)-center)**2 for i in range(len(recent))), ZERO)
    return max(ZERO, mean + slope * (Decimal(len(recent)-1+horizon)-center))


def forecast_months(observations, months):
    if type(months) is not int or not 1 <= months <= 36 or len(observations) > 120:
        raise ValueError('Unsupported forecast horizon or history size')
    values = [number(value) for value in observations]
    with localcontext() as context:
        context.prec = 48
        scores = {}
        if len(values) >= 18:
            candidates = METHODS if len(values) >= 24 else METHODS[:-1]
            for method in candidates:
                errors = []
                for origin in range(max(12, len(values)-6), len(values)):
                    for horizon in range(1, min(3,len(values)-origin)+1):
                        errors.append(abs(_predict(values[:origin], method, horizon)-values[origin+horizon-1]))
                scores[method] = sum(errors,ZERO)/len(errors)
        method = min(scores, key=scores.get) if scores else 'MEAN_12'
        predictions = [_predict(values, method, index+1) for index in range(months)]
        if any(value > LIMIT for value in predictions):
            raise ValueError('Projected quantity exceeds supported bounds')
        mean = sum(values[-12:],ZERO)/len(values[-12:]) if values else ZERO
        relative_error = scores[method]/mean if scores and mean else None
        confidence = 'LOW' if len(values) < 12 else 'MEDIUM'
        if len(values) >= 24 and relative_error is not None and relative_error <= Decimal('0.30'):
            confidence = 'HIGH'
        return {'method': method, 'history_months':len(values), 'confidence':confidence,
            'confidence_is_probability':False, 'monthly_mean':decimal_text(mean),
            'backtest_mae':{key:decimal_text(value) for key,value in scores.items()},
            'backtest_horizons':[1,2,3] if scores else [],
            'relative_backtest_error':decimal_text(relative_error) if relative_error is not None else None,
            'forecast':[decimal_text(value) for value in predictions],
            'history':[decimal_text(value) for value in values]}


def project_supply(*, as_of, starts_on, ends_on, monthly_forecast, stock, incoming=(),
                   commitments=(), safety_stock=0, purchase_factor=1, order_multiple=1, minimum_order=0):
    if not as_of <= starts_on <= ends_on or (ends_on-as_of).days > 1096:
        raise ValueError('Invalid planning dates')
    factor, multiple, safety = number(purchase_factor), number(order_multiple), number(safety_stock)
    minimum_order=number(minimum_order)
    if not factor or not multiple:
        raise ValueError('Purchase conversion and multiple must be positive')
    if len(stock)+len(incoming) > 10000 or len(commitments) > 10000:
        raise ValueError('Projection input exceeds bounded capacity')
    batches = []
    for origin, rows in (('STOCK',stock),('ORDER',incoming)):
        for row in rows:
            available = as_of if origin == 'STOCK' else row['available_on']
            expiry = row.get('expires_on')
            if available < as_of:
                raise ValueError('Overdue delivery requires a revised confirmed delivery date')
            if expiry is not None and expiry < available:
                continue
            batches.append({'id':str(row['id']), 'origin':origin, 'available':available,
                'expiry':expiry, 'remaining':number(row['quantity'])})
    batches.sort(key=lambda row:(row['expiry'] or date.max,row['available'],row['id']))
    arrivals=sorted(enumerate(batches),key=lambda pair:(pair[1]['available'],pair[0]))
    available_heap=[]
    arrival_index=0
    regular, extra, regular_monthly = {}, {}, {}
    for row in commitments:
        day = row['on']
        if not as_of <= day <= ends_on:
            continue
        group = extra if row['incremental'] else regular
        amount=number(row['quantity'])
        group[day] = group.get(day,ZERO)+amount
        if not row['incremental']:
            key=day.strftime('%Y-%m')
            regular_monthly[key]=regular_monthly.get(key,ZERO)+amount
    periods, first_shortage, short_before = {}, None, ZERO
    used, expiry_loss = {'STOCK':ZERO,'ORDER':ZERO}, ZERO
    with localcontext() as context:
        context.prec = 48
        day = as_of
        while day <= ends_on:
            key=day.strftime('%Y-%m')
            month_start=day.replace(day=1)
            month_end=month_after(day)-timedelta(days=1)
            if key not in monthly_forecast:
                raise ValueError('Missing monthly forecast')
            baseline=number(monthly_forecast[key])
            expected_regular=regular_monthly.get(key,ZERO)
            left=max(as_of,month_start)
            right=min(ends_on,month_end)
            span=Decimal((right-left).days+1)
            baseline=(baseline*span/Decimal(monthrange(day.year,day.month)[1])).quantize(SIX)
            residual=max(ZERO,baseline-expected_regular)
            elapsed=Decimal((day-left).days)
            daily=(residual*(elapsed+1)/span).quantize(SIX)-(residual*elapsed/span).quantize(SIX)
            demand=daily+regular.get(day,ZERO)+extra.get(day,ZERO)
            in_period=day>=starts_on
            summary=periods.setdefault(key,{'demand':ZERO,'covered':ZERO,'shortage':ZERO,'expired':ZERO})
            while arrival_index<len(arrivals) and arrivals[arrival_index][1]['available']<=day:
                index,batch=arrivals[arrival_index]
                heapq.heappush(available_heap,(batch['expiry'] or date.max,index))
                arrival_index+=1
            while available_heap and available_heap[0][0]<day:
                expiry,index=heapq.heappop(available_heap)
                batch=batches[index]
                if in_period:
                    expiry_loss+=batch['remaining']
                    summary['expired']+=batch['remaining']
                batch['remaining']=ZERO
            remaining=demand
            while remaining and available_heap:
                expiry,index=heapq.heappop(available_heap)
                batch=batches[index]
                take=min(remaining,batch['remaining'])
                batch['remaining']-=take
                remaining-=take
                if in_period:
                    used[batch['origin']]+=take
                if batch['remaining']:
                    heapq.heappush(available_heap,(expiry,index))
            if in_period:
                summary['demand']+=demand
                summary['covered']+=demand-remaining
                summary['shortage']+=remaining
                if remaining and first_shortage is None:
                    first_shortage=day
            else:
                short_before+=remaining
            day+=timedelta(days=1)
        balance=sum((row['remaining'] for row in batches if row['available']<=ends_on and
            (row['expiry'] is None or row['expiry']>=ends_on)),ZERO)
        shortage=sum((row['shortage'] for row in periods.values()),ZERO)
        safety_gap=max(ZERO,safety-balance)
        need=shortage+safety_gap
        packs=(max(need/factor,minimum_order)/multiple).to_integral_value(rounding=ROUND_CEILING)*multiple if need else ZERO
        if packs>LIMIT or packs*factor>LIMIT:
            raise ValueError('Purchase proposal exceeds supported bounds')
        return {'monthly':{key:{field:decimal_text(value) for field,value in row.items()} for key,row in periods.items()},
            'covered_by_stock':decimal_text(used['STOCK']), 'covered_by_orders':decimal_text(used['ORDER']),
            'expired_unconsumed':decimal_text(expiry_loss), 'shortage_before_horizon':decimal_text(short_before),
            'shortage_in_horizon':decimal_text(shortage), 'projected_end_balance':decimal_text(balance),
            'safety_gap':decimal_text(safety_gap), 'net_requirement':decimal_text(need),
            'purchase_quantity':decimal_text(packs), 'base_quantity':decimal_text(packs*factor),
            'first_shortage':str(first_shortage) if first_shortage else None,
            'purchase_factor':decimal_text(factor),'order_multiple':decimal_text(multiple),
            'assumption':'BASELINE_SPREAD_UNIFORMLY_WITH_CONFIRMED_RUNS_ON_PLANNED_DATES'}
