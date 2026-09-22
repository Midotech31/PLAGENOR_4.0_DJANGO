from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from erp.models import Article,Capability,InternalPreparation,StockContainer,StockLot,StockMovement
from erp.permissions import require
from .catalog import convert_quantity
from .common import audit,lock_tree,snapshot
from .safety import enforce_storage
from .stock import _article,_container,_location,_movement,_post,is_usable,require_container,stock_quantity


@transaction.atomic
def prepare_stock(user,*,key,article,location,lot_code,container_code,amount,unit,prepared_on,
                  protocol_reference,reason,ingredients,expires_on=None,concentration='',
                  concentration_value=None,concentration_unit=None):
    lock_tree('locations')
    article=_article(article.pk)
    location=_location(location.pk)
    require(user,Capability.RECEIVE_STOCK,category=article.category,location=location)
    if not isinstance(ingredients,list) or not 1<=len(ingredients)<=50:
        raise ValidationError(_('Une préparation doit référencer de 1 à 50 prélèvements sources.'))
    if not reason.strip() or len(reason)>500 or not protocol_reference.strip():
        raise ValidationError(_('Un protocole et une justification de préparation sont obligatoires.'))
    if prepared_on>timezone.localdate() or expires_on is not None and expires_on<prepared_on:
        raise ValidationError(_('Vérifiez les dates de préparation et de péremption.'))
    seen=set()
    normalized=[]
    for row in ingredients:
        container=_container(row['container'].pk)
        require_container(user,Capability.CONSUME_STOCK,container)
        if container.pk in seen:
            raise ValidationError(_('Un contenant source ne peut être sélectionné deux fois.'))
        seen.add(container.pk)
        quantity=stock_quantity(convert_quantity(container.lot.article,row['amount'],row['unit'])[0])
        normalized.append({'container':container,'amount':quantity,'unit':container.lot.article.base_unit,
            'original_unit':row['unit'],'original_quantity':str(row['amount'])})
    output_amount=stock_quantity(convert_quantity(article,amount,unit)[0])
    payload={'article':article.pk,'location':location.pk,'lot_code':lot_code,'container_code':container_code,
        'amount':str(output_amount),'prepared_on':prepared_on,'expires_on':expires_on,
        'protocol_reference':protocol_reference,'reason':reason,'concentration':concentration,
        'concentration_value':str(concentration_value) if concentration_value is not None else None,
        'concentration_unit':concentration_unit.pk if concentration_unit else None,
        'ingredients':[{'container':row['container'].pk,'amount':str(row['amount']),'unit':row['unit'].pk} for row in normalized]}
    move,created=_movement(user,key,StockMovement.Kind.PREPARATION,payload,reason=reason)
    if not created:
        return InternalPreparation.objects.get(movement=move)
    enforce_storage(article,location)
    sources=[]
    for row in normalized:
        container=row['container']
        if not is_usable(container) or row['amount']>container.quantity-container.reserved:
            raise ValidationError(_('Un contenant source est indisponible ou sa quantité libre est insuffisante.'))
        if container.lot.manufactured_on and container.lot.manufactured_on>prepared_on:
            raise ValidationError(_('Un lot source est postérieur à la date de préparation indiquée.'))
        sources.append({'container':str(container.pk),'code':container.code,'lot':str(container.lot_id),
            'manufacturer_lot':container.lot.manufacturer_lot,'article':str(container.lot.article_id),
            'designation':container.lot.specifications_snapshot.get('name',container.lot.article.name),
            'location':str(container.location_id),'amount':str(row['amount']),'unit':row['unit'].code,
            'original_unit':row['original_unit'].code,'original_quantity':row['original_quantity']})
    lot=StockLot(code=lot_code.strip().upper(),name=article.name+' — '+lot_code.strip().upper(),article=article,
        manufacturer_lot=lot_code.strip().upper(),manufactured_on=prepared_on,expires_on=expires_on,
        origin='PREPARATION',status='AVAILABLE',specifications_snapshot=snapshot(article))
    lot.full_clean()
    lot.save()
    output=StockContainer(code=container_code.strip().upper(),name=lot.name,lot=lot,location=location,
        status='PENDING',use_by=expires_on)
    output.full_clean()
    output.save()
    for row in normalized:
        _post(move,row['container'],-row['amount'])
        audit(user,row['container'],'used_in_preparation',reason=reason)
    _post(move,output,output_amount)
    preparation=InternalPreparation(output_lot=lot,movement=move,prepared_on=prepared_on,
        protocol_reference=protocol_reference,concentration=concentration,concentration_value=concentration_value,
        concentration_unit=concentration_unit,sources=sources)
    preparation.full_clean()
    preparation.save()
    audit(user,preparation,'internal_preparation_created',reason=reason)
    return preparation
