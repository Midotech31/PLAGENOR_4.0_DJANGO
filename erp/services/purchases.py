from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import (Capability, ProcurementLine, PurchaseOrder, PurchaseOrderLine,
    PurchaseReceiptLink, StockMovement)
from erp.permissions import permitted, require_manager
from .common import Conflict, audit, check_version, snapshot
from .procurement import _plan, plan_scope
from .stock import _key, receive_stock, stock_quantity
from .work import require_work


ZERO=Decimal(0)


def order_scope(user):
    return PurchaseOrder.objects.filter(plan__in=plan_scope(user)).select_related('plan__work','supplier')


def received_quantity(line):
    return line.deliveries.filter(receipt__movement__reversal__isnull=True).aggregate(total=Sum('purchase_quantity'))['total'] or ZERO


def _order(user,pk):
    identity=PurchaseOrder.objects.values('plan_id').get(pk=pk)
    plan=_plan(user,identity['plan_id'])
    order=PurchaseOrder.objects.select_for_update(no_key=True).get(pk=pk)
    order.plan=plan
    return order


@transaction.atomic
def create_order(user,plan_id,*,expected,reference,supplier,ordered_on,expected_on,notes=''):
    require_manager(user)
    plan=_plan(user,plan_id)
    check_version(plan,expected)
    if not plan.approved_revision_id or plan.work.status!='APPROVED':
        raise ValidationError(_('Une commande doit être rattachée à un plan approuvé.'))
    if not supplier.active or not supplier.is_supplier:
        raise ValidationError(_('Sélectionnez un fournisseur actif.'))
    if ordered_on>timezone.localdate():
        raise ValidationError(_('La date d’une commande enregistrée ne peut pas être future.'))
    order=PurchaseOrder(plan=plan,reference=reference.strip(),supplier=supplier,ordered_on=ordered_on,
        expected_on=expected_on,notes=notes,created_by=user)
    order.full_clean()
    order.save()
    audit(user,order,'order_created')
    return order


@transaction.atomic
def save_order_line(user,order_id,*,expected,plan_line,quantity,unit_price,tax_rate,currency,variance_reason='',pk=None):
    require_manager(user)
    order=_order(user,order_id)
    check_version(order,expected)
    if order.status!='DRAFT':
        raise ValidationError(_('Les lignes d’une commande confirmée sont figées.'))
    approved=next((row for row in order.plan.approved_revision.data['lines'] if row['id']==str(plan_line.pk) and row['included']),None)
    if approved is None:
        raise ValidationError(_('Cet article ne figure pas dans le plan approuvé.'))
    line=PurchaseOrderLine.objects.get(pk=pk,order=order) if pk else PurchaseOrderLine(order=order)
    before=snapshot(line) if pk else {}
    line.plan_line=plan_line
    line.article_snapshot=approved['article_snapshot']
    line.unit_id=approved['purchase_unit']
    line.factor=Decimal(approved['purchase_factor'])
    line.quantity=stock_quantity(quantity)
    stock_quantity(line.quantity*line.factor)
    line.unit_price,line.tax_rate,line.currency=unit_price,tax_rate,currency.strip().upper()
    if len(line.currency)!=3 or not line.currency.isascii() or not line.currency.isalpha():
        raise ValidationError(_('Code de devise à trois lettres requis.'))
    other=PurchaseOrderLine.objects.filter(plan_line=plan_line).exclude(pk=line.pk).select_related('order')
    ordered=sum((received_quantity(value) if value.order.status=='CANCELLED' else value.quantity for value in other),ZERO)
    changed=ordered+line.quantity>Decimal(approved['retained_quantity']) or Decimal(unit_price)!=Decimal(approved['estimated_price']) or Decimal(tax_rate)!=Decimal(approved['tax_rate']) or line.currency!=approved['currency']
    if changed and not variance_reason.strip():
        raise ValidationError(_('Justifiez tout dépassement de quantité ou écart de prix, de taxe ou de devise au plan.'))
    line.variance_reason=variance_reason.strip()
    line.version+=1 if pk else 0
    line.full_clean()
    line.save()
    order.version+=1
    order.save()
    audit(user,line,'order_line_saved',before,variance_reason)
    return line


@transaction.atomic
def confirm_order(user,pk,*,expected,reason):
    require_manager(user)
    order=_order(user,pk)
    check_version(order,expected)
    if order.status!='DRAFT' or not order.lines.exists() or not reason.strip():
        raise ValidationError(_('La confirmation exige une commande préparée et une justification.'))
    before=snapshot(order)
    order.status='CONFIRMED'
    order.confirmed_by,order.confirmed_at=user,timezone.now()
    order.version+=1
    order.save()
    audit(user,order,'order_confirmed',before,reason[:500])
    return order


@transaction.atomic
def cancel_order(user,pk,*,expected,reason):
    require_manager(user)
    order=_order(user,pk)
    check_version(order,expected)
    if order.status not in ('DRAFT','CONFIRMED','PARTIAL') or not reason.strip():
        raise ValidationError(_('Justifiez l’annulation d’une commande ouverte ou de son solde.'))
    before=snapshot(order)
    order.status='CANCELLED'
    order.version+=1
    order.save()
    audit(user,order,'order_cancelled',before,reason[:500])
    return order


@transaction.atomic
def revise_delivery_date(user,pk,*,expected,expected_on,reason):
    require_manager(user)
    order=_order(user,pk)
    check_version(order,expected)
    if order.status not in ('CONFIRMED','PARTIAL') or not reason.strip():
        raise ValidationError(_('Une nouvelle date de livraison exige une commande ouverte et une justification.'))
    before=snapshot(order)
    order.expected_on=expected_on
    order.version+=1
    order.full_clean()
    order.save()
    audit(user,order,'delivery_rescheduled',before,reason[:500])
    return order


@transaction.atomic
def receive_order_line(user,line_id,*,expected,key,amount,location,lot_code,manufacturer_lot,container_code,
                       received_on,condition,expires_on=None,manufactured_on=None,serial_number='',
                       cold_chain_ok=None,control_notes='',actual_unit_price=None,variance_reason=''):
    identity=PurchaseOrderLine.objects.values('order_id').get(pk=line_id)
    order=_order(user,identity['order_id'])
    line=PurchaseOrderLine.objects.select_for_update().get(pk=line_id)
    article=line.plan_line.article
    amount=stock_quantity(amount)
    base_amount=stock_quantity(amount*line.factor)
    cost_allowed=permitted(user,Capability.EDIT_COST,category=article.category)
    if actual_unit_price is not None and not cost_allowed:
        raise PermissionDenied
    actual=line.unit_price if actual_unit_price is None else actual_unit_price
    if Decimal(actual)!=line.unit_price and not variance_reason.strip():
        raise ValidationError(_('Justifiez la différence entre le prix réceptionné et le prix commandé.'))
    replay=PurchaseReceiptLink.objects.filter(receipt__movement__key=_key(key)).select_related('receipt').first()
    if replay and replay.line_id!=line.pk:
        raise Conflict(_('Cet identifiant de réception appartient à une autre ligne de commande.'))
    if not replay:
        check_version(order,expected)
        if order.status not in ('CONFIRMED','PARTIAL') or amount>line.quantity-received_quantity(line):
            raise ValidationError(_('La réception dépasse le solde ou la commande n’est pas ouverte.'))
    base_price=Decimal(actual)/line.factor
    rounded=base_price.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    movement=receive_stock(user,key=key,article=article,location=location,manufacturer_lot=manufacturer_lot,
        lot_code=lot_code,container_code=container_code,amount=base_amount,unit=article.base_unit,
        received_on=received_on,supplier=order.supplier,order_reference=order.reference,ordered_on=order.ordered_on,
        ordered_quantity=stock_quantity(line.quantity*line.factor),expires_on=expires_on,manufactured_on=manufactured_on,
        serial_number=serial_number,condition=condition,cold_chain_ok=cold_chain_ok,
        control_notes=control_notes,unit_price=rounded if cost_allowed and base_price==rounded else None,currency=line.currency)
    if replay:
        if replay.purchase_quantity!=amount or replay.actual_unit_price!=Decimal(actual) or replay.variance_reason!=variance_reason:
            raise Conflict(_('La répétition de réception comporte des informations différentes.'))
        return replay
    link=PurchaseReceiptLink(line=line,receipt=movement.receipt,actor=user,purchase_quantity=amount,
        actual_unit_price=actual,expected_delivery_snapshot=order.expected_on,variance_reason=variance_reason)
    link.full_clean()
    link.save()
    before=snapshot(order)
    order.status='RECEIVED' if all(received_quantity(row)>=row.quantity for row in order.lines.all()) else 'PARTIAL'
    order.version+=1
    order.save()
    audit(user,order,'purchase_received',before,variance_reason[:500])
    return link


@transaction.atomic
def reverse_delivery(user,link_id,*,key,reason):
    require_manager(user)
    identity=PurchaseReceiptLink.objects.select_related('line').get(pk=link_id)
    order=_order(user,identity.line.order_id)
    from .stock import reverse_stock
    already_reversed=StockMovement.objects.filter(reverses_id=identity.receipt.movement_id).exists()
    movement=reverse_stock(user,identity.receipt.movement_id,key=key,reason=reason,_purchase_context=True)
    if already_reversed:
        return movement
    before=snapshot(order)
    if order.status!='CANCELLED':
        total=sum((received_quantity(row) for row in order.lines.all()),ZERO)
        order.status='PARTIAL' if total else 'CONFIRMED'
    order.version+=1
    order.save()
    audit(user,order,'purchase_reversed',before,reason[:500])
    return movement
