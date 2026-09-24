from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Min, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (Article, CdcDossier, CdcItem, CdcLot, ForecastObservation, LocationClosure,
    ProcurementLine, ProcurementPlan, ProcurementRevision, PurchaseOrder, PurchaseOrderLine,
    PurchaseReceiptLink, RunAllocation, RunRequirement, StockContainer, StockEntry, StockReceipt, WorkItem)
from erp.permissions import Capability, permitted, require_manager
from .catalog import convert_quantity
from .common import Conflict, audit, check_version, lock_tree, snapshot
from .forecast_engine import ZERO, decimal_text, forecast_months, month_after, project_supply
from .stock import receive_stock, stock_quantity, usable_filter
from .work import _transition, create_work, require_work, work_allowed, work_scope


COST_FIELDS={'estimated_price','tax_rate','currency','supplier','price_source'}
LINE_FIELDS={'retained_quantity','included','lot_name','priority','decision_reason'}


def plan_scope(user):
    return ProcurementPlan.objects.filter(work__in=work_scope(user)).select_related('work__assignee','approved_revision','cdc')


def _plan(user,pk,*,edit=False):
    identity=ProcurementPlan.objects.values('work_id').get(pk=pk)
    work=WorkItem.objects.select_for_update(no_key=True).get(pk=identity['work_id'])
    require_work(user,work,edit=edit)
    plan=ProcurementPlan.objects.select_for_update(no_key=True).get(pk=pk)
    plan.work=work
    if edit and plan.approved_revision_id:
        raise ValidationError(_('Un plan approuvé est figé. Créez un nouveau plan pour le réviser.'))
    return plan


def _digest(value):
    return hashlib.sha256(json.dumps(value,default=str,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _revision(user,plan,reason):
    data={'reference':plan.reference,'year':plan.year,'starts_on':str(plan.starts_on),'ends_on':str(plan.ends_on),
        'lines':[snapshot(row) for row in plan.lines.order_by('lot_name','article__code')]}
    plan.version+=1
    plan.revision_number+=1
    plan.save()
    revision=ProcurementRevision.objects.create(plan=plan,number=plan.revision_number,actor=user,
        data=data,sha256=_digest(data),reason=reason[:500])
    audit(user,plan,'plan_revised',reason=reason[:500])
    return revision


@transaction.atomic
def create_plan(user,*,reference,year,title,assignee=None,allow_costs=False,instructions='',category=None,location=None,due_on=None):
    require_manager(user)
    today=timezone.localdate()
    if type(year) is not int or not today.year<=year<=today.year+2:
        raise ValidationError(_('Le plan doit concerner l’année actuelle ou les deux années suivantes.'))
    work=create_work(user,kind='PLAN',title=title,assignee=assignee,allow_costs=allow_costs,
        instructions=instructions,category=category,location=location,due_on=due_on)
    plan=ProcurementPlan(work=work,reference=reference.strip(),year=year,
        starts_on=max(today,date(year,1,1)),ends_on=date(year,12,31))
    plan.full_clean()
    plan.save()
    _revision(user,plan,str(_('Création du plan.')))
    return plan


def _stock_scope(plan,qs,location_field='location_id'):
    if plan.work.location_id:
        qs=qs.filter(**{location_field+'__in':LocationClosure.objects.filter(ancestor_id=plan.work.location_id).values('descendant_id')})
    return qs


def forecast_inputs(plan,article,as_of):
    if plan.work.category_id and article.category_id!=plan.work.category_id:
        raise PermissionDenied
    containers=_stock_scope(plan,StockContainer.objects.filter(lot__article=article)).select_related('lot')
    evidence_entries=_stock_scope(plan,StockEntry.objects.filter(container__lot__article=article))
    first_recorded=evidence_entries.aggregate(first=Min('created_at'))['first']
    first=timezone.localtime(first_recorded).date() if first_recorded else None
    history_start=max(month_after(first),month_after(as_of,-36)) if first else as_of.replace(day=1)
    history_end=as_of.replace(day=1)
    stamps=_stock_scope(plan,StockEntry.objects.filter(container__lot__article=article,movement__kind__in=['CONSUMPTION','PREPARATION'],quantity_delta__lt=0,movement__reversal__isnull=True,
        created_at__gte=timezone.make_aware(datetime.combine(history_start,time.min)),
        created_at__lt=timezone.make_aware(datetime.combine(history_end,time.min))))
    history_map={row['month'].date():-row['total'] for row in stamps.annotate(month=TruncMonth('created_at')).values('month').annotate(total=Sum('quantity_delta'))}
    months=[]
    cursor=history_start
    while cursor<history_end:
        months.append({'month':cursor.strftime('%Y-%m'),'quantity':decimal_text(history_map.get(cursor,ZERO))})
        cursor=month_after(cursor)
    requirements=RunRequirement.objects.filter(article=article,run__committed=True,
        run__status__in=['PLANNED','RESERVED'],run__planned_on__gte=as_of,run__planned_on__lte=plan.ends_on,
        run__request__archived=False).exclude(run__request__status__in=['REJECTED','ARCHIVED']).select_related('run')
    if plan.work.location_id:
        requirements=requirements.filter(run__schedule__work__location_id__in=LocationClosure.objects.filter(
            ancestor_id=plan.work.location_id).values('descendant_id'))
    requirements=list(requirements)
    allocated={row['reservation__container_id']:row['total'] for row in RunAllocation.objects.filter(
        requirement__in=requirements,reservation__container__in=containers).values('reservation__container_id').annotate(total=Sum('reservation__remaining'))}
    usable=list(containers.filter(usable_filter(as_of)))
    supply=[]
    reserved_total=ZERO
    for container in usable:
        reserved_total+=container.reserved
        expiry=min((day for day in (container.use_by,container.lot.expires_on) if day is not None),default=None)
        supply.append({'id':str(container.pk),'quantity':decimal_text(container.quantity-container.reserved+allocated.get(container.pk,ZERO)),
            'expires_on':str(expiry) if expiry else None,'version':container.version})
    order_lines=PurchaseOrderLine.objects.filter(plan_line__article=article,order__status__in=['CONFIRMED','PARTIAL']).select_related('order')
    if plan.work.location_id:
        order_lines=order_lines.filter(order__plan__work__location_id=plan.work.location_id)
    incoming=[]
    overdue=[]
    for row in order_lines:
        delivered=row.deliveries.filter(receipt__movement__reversal__isnull=True).aggregate(total=Sum('purchase_quantity'))['total'] or ZERO
        remaining=max(ZERO,row.quantity-delivered)
        if remaining and row.order.expected_on<as_of:
            overdue.append(row.order.reference)
        elif remaining and row.order.expected_on<=plan.ends_on:
            incoming.append({'id':str(row.pk),'quantity':decimal_text(remaining*row.factor),
                'available_on':str(row.order.expected_on),'expires_on':None,'order':row.order.reference})
    losses=_stock_scope(plan,StockEntry.objects.filter(container__lot__article=article,movement__kind__in=['LOSS','BREAKAGE','CONTAMINATION','EXPIRY','DESTRUCTION'],
        movement__reversal__isnull=True,created_at__date__gte=history_start,created_at__date__lt=as_of)).aggregate(total=Sum('quantity_delta'))['total'] or ZERO
    return {'article':snapshot(article),'as_of':str(as_of),'history_start':str(history_start),'history':months,
        'stock':supply,'physical_usable':decimal_text(sum((row.quantity for row in usable),ZERO)),
        'reserved_total':decimal_text(reserved_total),'incoming':incoming,'overdue_orders':sorted(set(overdue)),
        'commitments':[{'id':str(row.run_id),'on':str(row.run.planned_on),'quantity':decimal_text(row.quantity),
            'incremental':row.run.incremental_demand} for row in requirements],
        'historical_losses':decimal_text(-losses),'losses_are_automatically_projected':False,
        'history_assumption':'COMPLETE_MONTHS_AFTER_FIRST_RECORDED_LEDGER_ENTRY_IN_SCOPE'}


@transaction.atomic
def add_plan_article(user,pk,*,expected,article,lot_name,_record_revision=True):
    plan=_plan(user,pk,edit=True)
    check_version(plan,expected)
    article=Article.objects.get(pk=article.pk,active=True)
    if plan.work.category_id and article.category_id!=plan.work.category_id:
        raise PermissionDenied
    unit=article.purchase_unit or article.base_unit
    base,factor=convert_quantity(article,1,unit)
    line=ProcurementLine(plan=plan,article=article,article_snapshot={**snapshot(article),'purchase_unit_name':unit.name,'purchase_unit_code':unit.code},
        purchase_unit=unit,purchase_factor=factor,lot_name=lot_name.strip(),priority=article.criticality)
    line.full_clean()
    line.save()
    if _record_revision:
        _revision(user,plan,str(_('Ajout d’un article au plan.')))
    return line


@transaction.atomic
def refresh_forecast(user,line_id,*,expected):
    line=ProcurementLine.objects.get(pk=line_id)
    plan=_plan(user,line.plan_id,edit=True)
    check_version(plan,expected)
    lock_tree('locations')
    article=Article.objects.select_for_update().get(pk=line.article_id)
    as_of=timezone.localdate()
    if as_of>plan.ends_on:
        raise ValidationError(_('La période du plan est terminée.'))
    inputs=forecast_inputs(plan,article,as_of)
    count=(plan.ends_on.year-as_of.year)*12+plan.ends_on.month-as_of.month+1
    try:
        model=forecast_months([row['quantity'] for row in inputs['history']],count)
        periods={month_after(as_of,index).strftime('%Y-%m'):amount for index,amount in enumerate(model['forecast'])}
        stocks=[{**row,'expires_on':date.fromisoformat(row['expires_on']) if row['expires_on'] else None} for row in inputs['stock']]
        orders=[{**row,'available_on':date.fromisoformat(row['available_on'])} for row in inputs['incoming']]
        commitments=[{**row,'on':date.fromisoformat(row['on'])} for row in inputs['commitments']]
        projection=project_supply(as_of=as_of,starts_on=max(as_of,plan.starts_on),ends_on=plan.ends_on,
            monthly_forecast=periods,stock=stocks,incoming=orders,commitments=commitments,
            safety_stock=article.safety_stock,purchase_factor=line.purchase_factor,order_multiple=article.order_multiple,
            minimum_order=article.minimum_order_quantity)
    except ValueError as exc:
        raise ValidationError(_('Les données ne permettent pas une prévision valide : %(reason)s') % {'reason':str(exc)})
    result={'model':model,'projection':projection,'warnings':[]}
    if model['history_months']<12:
        result['warnings'].append('SHORT_HISTORY')
    if inputs['overdue_orders']:
        result['warnings'].append('OVERDUE_DELIVERIES_EXCLUDED')
    if orders:
        result['warnings'].append('FUTURE_RECEIPTS_REQUIRE_ACCEPTANCE_AND_EXPIRY_REVIEW')
    if article.lead_time_days is None:
        result['warnings'].append('LEAD_TIME_UNKNOWN')
    first=date.fromisoformat(projection['first_shortage']) if projection['first_shortage'] else None
    if first and article.lead_time_days is not None and first<as_of+timedelta(days=article.lead_time_days):
        result['warnings'].append('SHORTAGE_BEFORE_NORMAL_DELIVERY')
    observation=ForecastObservation.objects.create(plan=plan,article=article,actor=user,as_of=as_of,
        input_data=inputs,result=result,sha256=_digest({'inputs':inputs,'result':result}))
    line.forecast=observation
    line.proposed_quantity=Decimal(projection['purchase_quantity'])
    line.reviewed_at,line.reviewed_by=None,None
    line.version+=1
    line.save()
    _revision(user,plan,str(_('Prévision recalculée ; décision humaine à confirmer.')))
    return observation


@transaction.atomic
def decide_plan_line(user,line_id,*,expected,values,_record_revision=True):
    line=ProcurementLine.objects.get(pk=line_id)
    plan=_plan(user,line.plan_id,edit=True)
    check_version(plan,expected)
    if set(values)-LINE_FIELDS-COST_FIELDS:
        raise ValidationError(_('Champ de plan non autorisé.'))
    if set(values)&COST_FIELDS:
        require_work(user,plan.work,costs=True)
    for key,value in values.items():
        setattr(line,key,value)
    if not line.decision_reason.strip():
        raise ValidationError(_('Justifiez la quantité retenue ou l’exclusion.'))
    if line.included:
        line.retained_quantity=stock_quantity(line.retained_quantity)
        stock_quantity(line.retained_quantity*line.purchase_factor)
    elif line.retained_quantity is not None:
        line.retained_quantity=stock_quantity(line.retained_quantity,zero=True)
    line.currency=line.currency.strip().upper()
    if len(line.currency)!=3 or not line.currency.isascii() or not line.currency.isalpha():
        raise ValidationError(_('Code de devise à trois lettres requis.'))
    if line.estimated_price is not None and not line.price_source.strip():
        raise ValidationError(_('Renseignez la source du prix estimatif.'))
    if line.supplier and (not line.supplier.active or not line.supplier.is_supplier):
        raise ValidationError(_('Sélectionnez un fournisseur actif.'))
    line.reviewed_by,line.reviewed_at=user,timezone.now()
    line.version+=1
    line.full_clean()
    line.save()
    if _record_revision:
        _revision(user,plan,line.decision_reason)
    return line


def validate_plan(plan):
    lines=list(plan.lines.all())
    if not lines or not any(row.included for row in lines):
        raise ValidationError(_('Le plan doit comporter au moins un article retenu.'))
    for row in lines:
        if not row.reviewed_at or not row.decision_reason.strip():
            raise ValidationError(_('Chaque article doit avoir une décision humaine justifiée.'))
        if row.included and (not row.retained_quantity or row.estimated_price is None or row.tax_rate is None or not row.price_source):
            raise ValidationError(_('Complétez les quantités, prix, taxes et sources de tous les articles retenus.'))
    return lines


@transaction.atomic
def submit_plan(user,pk,*,expected,reason):
    plan=_plan(user,pk,edit=True)
    check_version(plan,expected)
    validate_plan(plan)
    if not reason.strip():
        raise ValidationError(_('Un compte rendu de préparation est requis.'))
    _transition(user,plan.work,'SUBMITTED',reason)
    return plan


@transaction.atomic
def approve_plan(user,pk,*,expected,reason):
    require_manager(user)
    plan=_plan(user,pk)
    check_version(plan,expected)
    if plan.approved_revision_id or plan.work.status!='SUBMITTED' or not reason.strip():
        raise ValidationError(_('La validation exige un plan soumis et une justification.'))
    validate_plan(plan)
    revision=_revision(user,plan,reason)
    plan.approved_revision=revision
    plan.save(update_fields=['approved_revision'])
    _transition(user,plan.work,'APPROVED',reason)
    return revision


def plan_totals(user,plan):
    require_work(user,plan.work,costs=True)
    rows=plan.approved_revision.data['lines'] if plan.approved_revision_id else [snapshot(row) for row in plan.lines.all()]
    currencies,missing={},0
    for row in rows:
        if not row['included']:
            continue
        if row['retained_quantity'] is None or row['estimated_price'] is None or row['tax_rate'] is None:
            missing+=1
            continue
        net=(Decimal(row['retained_quantity'])*Decimal(row['estimated_price'])).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        tax=(net*Decimal(row['tax_rate'])/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        amount=currencies.setdefault(row['currency'],{'net':ZERO,'tax':ZERO,'gross':ZERO,'lots':{}})
        for key,value in (('net',net),('tax',tax),('gross',net+tax)):
            amount[key]+=value
            lot=amount['lots'].setdefault(row['lot_name'],{'net':ZERO,'tax':ZERO,'gross':ZERO})
            lot[key]+=value
    return {'currencies':currencies,'incomplete_lines':missing}


@transaction.atomic
def plan_to_cdc(user,pk,*,expected,reference,family,assignee=None):
    require_manager(user)
    plan=_plan(user,pk)
    check_version(plan,expected)
    if not plan.approved_revision_id or plan.work.status!='APPROVED':
        raise ValidationError(_('Approuvez le plan avant de préparer le cahier des charges.'))
    if plan.cdc_id:
        if plan.cdc.reference!=reference or plan.cdc.family!=family:
            raise Conflict(_('Ce plan est déjà rattaché à un cahier des charges.'))
        return plan.cdc
    from .cdc import _revision as cdc_revision, create_dossier
    dossier=create_dossier(user,family=family,reference=reference,title=plan.work.title,assignee=assignee,
        allow_costs=plan.work.allow_costs,instructions=plan.work.instructions)
    CdcItem.objects.filter(lot__dossier=dossier).delete()
    dossier.lots.all().delete()
    lots={}
    for row in plan.approved_revision.data['lines']:
        if not row['included']:
            continue
        label=row['lot_name']
        if label not in lots:
            lots[label]=CdcLot.objects.create(dossier=dossier,position=len(lots)+1,name=label,source_slot=0)
        lot=lots[label]
        article=row['article_snapshot']
        CdcItem.objects.create(lot=lot,source_key='new-'+str(uuid.uuid4()),position=lot.items.count()+1,
            article_id=row['article'],article_snapshot=article,designation=article['name'],
            specifications=article.get('specifications',''),packaging=article.get('packaging',''),
            unit_label=article['purchase_unit_name'],purchase_unit_id=row['purchase_unit'],
            base_factor=Decimal(row['purchase_factor']),quantity=Decimal(row['retained_quantity']),
            estimated_price=Decimal(row['estimated_price']),tax_rate=Decimal(row['tax_rate']),
            price_source=row['price_source'],currency=row['currency'])
    cdc_revision(user,dossier,str(_('Besoins repris du plan approuvé %(reference)s.')) % {'reference':plan.reference})
    plan.cdc=dossier
    plan.version+=1
    plan.save(update_fields=['cdc','version','updated_at'])
    audit(user,plan,'cdc_prepared')
    return dossier
