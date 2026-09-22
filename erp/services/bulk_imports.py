from datetime import date,datetime,timedelta
from decimal import Decimal,InvalidOperation
from pathlib import PurePath
import hashlib
import json
import uuid

from django.core.exceptions import ObjectDoesNotExist,PermissionDenied,ValidationError
from django.db import IntegrityError,transaction
from django.utils import timezone,translation
from django.utils.translation import gettext_lazy as _

from core.models import Request
from erp.models import (Article,Category,ImportBatch,Location,LocationClosure,LocationType,Party,
    PriceObservation,ProcurementLine,ProcurementPlan,StoragePosition,TemperatureReading,Unit,WorkItem)
from erp.permissions import Capability,grants,is_manager,is_team,permitted,require
from .catalog import record_price,save_article
from .common import Conflict,audit,check_version,lock_tree,snapshot
from .stock import _key,receive_stock,stock_quantity
from .table_intake import LABELS,SCHEMAS,parse_table
from .work import require_work


CAPABILITIES={'CATALOG':Capability.EDIT_CATALOG,'INITIAL':Capability.RECEIVE_STOCK,
    'RECEIPTS':Capability.RECEIVE_STOCK,'LOCATIONS':Capability.EDIT_STORAGE,
    'SAMPLES':Capability.MANAGE_BIOBANK,'PRICES':Capability.EDIT_COST}
REFERENCE_FIELDS={'category_code':Category,'new_category_code':Category,'base_unit_code':Unit,
    'new_base_unit_code':Unit,'purchase_unit_code':Unit,'unit_code':Unit,
    'manufacturer_code':Party,'supplier_code':Party,'location_code':Location,'parent_code':Location,
    'kind_code':LocationType,'article_code':Article}
BASELINE_MODELS={model._meta.label_lower:model for model in (Article,Category,Unit,Party,Location,LocationType,ProcurementPlan,WorkItem)}


def _hash(value):
    return hashlib.sha256(json.dumps(value,default=str,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def require_kind(user,kind,plan=None):
    if not is_team(user):
        raise PermissionDenied
    if kind=='PLAN':
        if plan is None:
            raise ValidationError(_('Sélectionnez le plan à compléter.'))
        require_work(user,plan.work,edit=True)
    elif kind=='TEMPERATURE':
        if not is_manager(user) and not any(grants(user,cap).exists() for cap in (Capability.MANAGE_BIOBANK,Capability.EDIT_STORAGE)):
            raise PermissionDenied
    elif kind not in CAPABILITIES:
        raise ValidationError(_('Domaine d’import inconnu.'))
    elif not is_manager(user) and not grants(user,CAPABILITIES[kind]).exists():
        raise PermissionDenied


def _get(model,code,*,optional=False):
    if optional and not code:
        return None
    obj=model.objects.filter(code=str(code).strip().upper()).first()
    if obj is None or not obj.active:
        raise ValidationError(_('Code %(code)s inconnu ou inactif dans le référentiel %(reference)s.') %
            {'code':str(code)[:120],'reference':str(model._meta.verbose_name)})
    return obj


def _decimal(value,*,signed=False):
    try:
        text=str(value).strip().replace(chr(160),'').replace(' ','').replace(',','.')
        if not text or len(text)>64:
            raise InvalidOperation
        number=Decimal(text)
        if not number.is_finite() or abs(number)>Decimal('999999999999.999999') or not signed and number<0:
            raise InvalidOperation
    except (InvalidOperation,TypeError,ValueError) as exc:
        raise ValidationError(_('Nombre décimal invalide ou hors limites.')) from exc
    return number


def _integer(value):
    number=_decimal(value)
    if number!=number.to_integral_value():
        raise ValidationError(_('Un nombre entier est requis.'))
    return int(number)


def _date(value):
    text=str(value).strip()
    try:
        if len(text)==10:
            return date.fromisoformat(text)
        moment=datetime.fromisoformat(text)
        if moment.hour or moment.minute or moment.second or moment.microsecond or moment.tzinfo:
            raise ValueError
        return moment.date()
    except ValueError as exc:
        raise ValidationError(_('Indiquez une date au format AAAA-MM-JJ.')) from exc


def _moment(value):
    try:
        if len(str(value))<=10:
            raise ValueError
        moment=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return timezone.make_aware(moment) if timezone.is_naive(moment) else moment
    except ValueError as exc:
        raise ValidationError(_('Indiquez une date et une heure valides dans le fuseau de la plateforme.')) from exc


def _boolean(value):
    text=str(value).strip().casefold()
    if text in ('true','1','oui','yes','نعم'):
        return True
    if text in ('false','0','non','no','لا'):
        return False
    if text in ('','unknown','inconnu','غير معروف'):
        return None
    raise ValidationError(_('Indiquez oui, non ou laissez vide si l’information est inconnue.'))


def _criticality(value):
    choices={code.casefold():code for code,label in Article.Criticality.choices}
    for language in ('fr','en','ar'):
        with translation.override(language):
            choices.update({str(label).casefold():code for code,label in Article.Criticality.choices})
    result=choices.get(str(value).strip().casefold())
    if result is None:
        raise ValidationError(_('Criticité non reconnue.'))
    return result


def _remember(baselines,obj):
    if obj is not None:
        identity=obj._meta.label_lower+':'+str(obj.pk)
        baselines[identity]={'model':obj._meta.label_lower,'id':str(obj.pk),'version':obj.version,'hash':_hash(snapshot(obj))}
        if isinstance(obj,Location):
            for ancestor in Location.objects.filter(pk__in=LocationClosure.objects.filter(descendant=obj).values('ancestor_id')):
                baselines.setdefault('erp.location:'+str(ancestor.pk),{'model':'erp.location','id':str(ancestor.pk),
                    'version':ancestor.version,'hash':_hash(snapshot(ancestor))})


def _prepare(user,kind,rows,plan):
    baselines={}
    primary={'CATALOG':Article,'LOCATIONS':Location}.get(kind)
    seen=set()
    for item in rows:
        data=item['data']
        missing=[str(LABELS[name]) for name,value in data.items() if name in SCHEMAS[kind]['required'] and not value]
        if missing:
            item['preparation_error']=str(_('Champs obligatoires vides : %(fields)s')) % {'fields':', '.join(missing)}
        identifier=data.get('container_code') or data.get('code') or data.get('article_code') if kind in ('CATALOG','LOCATIONS','SAMPLES','INITIAL','RECEIPTS','PLAN') else _hash(data)
        if identifier in seen:
            item['preparation_error']=str(_('Identifiant ou ligne dupliqué dans le fichier.'))
        seen.add(identifier)
        if kind=='INITIAL' and data.get('new_name'):
            item['create_article']=not Article.objects.filter(code=data.get('article_code','').upper()).exists()
        for name,model in REFERENCE_FIELDS.items():
            if data.get(name):
                _remember(baselines,model.objects.filter(code=data[name].strip().upper()).first())
        if primary:
            obj=primary.objects.filter(code=data.get('code','').strip().upper()).first()
            item['expected']=obj.version if obj else None
            item['existing_id']=str(obj.pk) if obj else None
            _remember(baselines,obj)
        if kind=='SAMPLES' and data.get('request_reference'):
            try:
                try:
                    request_id=uuid.UUID(data['request_reference'])
                except ValueError:
                    req=Request.objects.get(display_id=data['request_reference'])
                else:
                    req=Request.objects.get(pk=request_id)
                from .biobank import source_samples
                source=next((row for row in source_samples(user,req) if row['code']==data.get('source_code')),None)
                if source is None:
                    raise ValidationError(_('Le code échantillon ne correspond pas à une ligne de cette demande.'))
                item['source']={'request_id':str(req.pk),'key':source['key'],'fingerprint':source['fingerprint']}
            except (ObjectDoesNotExist,ValidationError,PermissionDenied):
                item['preparation_error']=str(_('Demande ou échantillon source introuvable dans votre périmètre.'))
    if plan:
        _remember(baselines,plan)
        _remember(baselines,plan.work)
    return rows,list(baselines.values())


def _catalog(user,item):
    data=item['data']
    obj=Article.objects.filter(code=data['code'].strip().upper()).first()
    if (str(obj.pk) if obj else None)!=item.get('existing_id'):
        raise Conflict(_('La présence de cet article a changé depuis l’aperçu.'))
    values={'code':data['code'],'name':data['name'],'category':_get(Category,data['category_code']),
        'base_unit':_get(Unit,data['base_unit_code'])}
    for name in ('name_en','name_ar','manufacturer_reference','cas','packaging','specifications'):
        if data.get(name):
            values[name]=data[name]
    for name in ('minimum_stock','safety_stock','reorder_point','target_stock','order_multiple','minimum_order_quantity'):
        if data.get(name):
            values[name]=_decimal(data[name])
    for field,model,key in (('purchase_unit',Unit,'purchase_unit_code'),('manufacturer',Party,'manufacturer_code'),
        ('preferred_supplier',Party,'supplier_code')):
        if data.get(key):
            values[field]=_get(model,data[key])
    if data.get('lead_time_days'):
        values['lead_time_days']=_integer(data['lead_time_days'])
    if data.get('criticality'):
        values['criticality']=_criticality(data['criticality'])
    return save_article(user,values,pk=obj.pk if obj else None,expected=item.get('expected'))


def _location(user,item):
    from .storage import save_location
    data=item['data']
    obj=Location.objects.filter(code=data['code'].strip().upper()).first()
    if (str(obj.pk) if obj else None)!=item.get('existing_id'):
        raise Conflict(_('La présence de cet emplacement a changé depuis l’aperçu.'))
    values={'code':data['code'],'name':data['name'],'kind':_get(LocationType,data['kind_code'])}
    if data.get('parent_code'):
        values['parent']=_get(Location,data['parent_code'])
    for field in ('name_en','name_ar'):
        if data.get(field):
            values[field]=data[field]
    for field in ('grid_rows','grid_columns','capacity'):
        if data.get(field):
            values[field]=_integer(data[field])
    for field in ('temperature_target','temperature_min','temperature_max'):
        if data.get(field):
            values[field]=_decimal(data[field],signed=True)
    return save_location(user,values,pk=obj.pk if obj else None,expected=item.get('expected'))


def _receipt(user,batch,item):
    data=item['data']
    article=Article.objects.filter(code=data['article_code'].strip().upper()).first()
    if item.get('create_article') and article is not None and article.code not in getattr(batch,'_created_article_codes',set()):
        raise Conflict(_('Un article prévu comme nouveau a été créé depuis l’aperçu. Analysez à nouveau le fichier.'))
    if article is None and batch.kind=='INITIAL':
        if not all(data.get(name) for name in ('new_name','new_category_code','new_base_unit_code')):
            raise ValidationError(_('Le nouvel article exige une désignation, une catégorie et une unité de gestion explicites.'))
        article=save_article(user,{'code':data['article_code'],'name':data['new_name'],
            'category':_get(Category,data['new_category_code']),'base_unit':_get(Unit,data['new_base_unit_code'])})
        batch._created_article_codes.add(article.code)
    if article is None:
        raise ValidationError(_('Créez ou importez l’article dans le catalogue avant la réception.'))
    if data.get('new_name') and (article.name!=data['new_name'] or article.category.code!=data.get('new_category_code') or article.base_unit.code!=data.get('new_base_unit_code')):
        raise ValidationError(_('Les informations du nouvel article contredisent le catalogue ou une autre ligne du fichier.'))
    values={'article':article,'location':_get(Location,data['location_code']),'lot_code':data['lot_code'],
        'manufacturer_lot':data['manufacturer_lot'],'container_code':data['container_code'],'amount':_decimal(data['amount']),
        'unit':_get(Unit,data['unit_code']),'received_on':_date(data['received_on']),'condition':data['condition'],
        'supplier':_get(Party,data.get('supplier_code',''),optional=True),'currency':data.get('currency') or 'DZD',
        'initial':batch.kind=='INITIAL','order_reference':data.get('order_reference',''),
        'cold_chain_ok':_boolean(data.get('cold_chain_ok',''))}
    for field in ('expires_on','manufactured_on'):
        if data.get(field):
            values[field]=_date(data[field])
    if data.get('unit_price_base'):
        values['unit_price']=_decimal(data['unit_price_base'])
    return receive_stock(user,key=uuid.uuid5(batch.id,str(item['row'])),**values)


def _sample(user,batch,item):
    from .biobank import receive_sample
    data=item['data']
    location=_get(Location,data['location_code'])
    position=None
    if data.get('position_row') or data.get('position_column'):
        try:
            position=StoragePosition.objects.get(location=location,row=_integer(data.get('position_row','')),
                column=_integer(data.get('position_column','')))
        except ObjectDoesNotExist as exc:
            raise ValidationError(_('Cette position n’existe pas dans l’emplacement sélectionné.')) from exc
    source=item.get('source')
    if data.get('source_code') and not source:
        raise ValidationError(_('Associez le code source à sa demande PLAGENOR.'))
    return receive_sample(user,key=uuid.uuid5(batch.id,str(item['row'])),code=data['code'],amount=_decimal(data['amount']),
        unit=_get(Unit,data['unit_code']),location=location,position=position,received_on=_date(data['received_on']),
        reason=batch.reason,request=Request.objects.get(pk=source['request_id']) if source else None,
        source_key=source['key'] if source else '',source_fingerprint=source['fingerprint'] if source else '',
        sample_type=data.get('sample_type',''),matrix=data.get('matrix',''),preservation=data.get('preservation',''))


def _price(user,item):
    data=item['data']
    article=_get(Article,data['article_code'])
    require(user,Capability.EDIT_COST,category=article.category)
    values={'unit':_get(Unit,data['unit_code']),'amount':_decimal(data['price']),'currency':data['currency'].strip().upper(),
        'observed_on':_date(data['observed_on']),'source':data['source'],
        'supplier':_get(Party,data.get('supplier_code',''),optional=True)}
    existing=PriceObservation.objects.filter(article=article,**values).first()
    return existing or record_price(user,article,values)


def _temperature(user,item):
    from .cold_storage import record_temperature,_temperature_permission
    data=item['data']
    location=_get(Location,data['location_code'])
    _temperature_permission(user,location)
    values={'location':location,'measured_at':_moment(data['measured_at']),'value':_decimal(data['value'],signed=True)}
    existing=TemperatureReading.objects.filter(**values).first()
    return existing or record_temperature(user,**values,comment=data.get('comment',''),source='IMPORT')


def _plan_line(user,batch,item):
    from .procurement import add_plan_article,decide_plan_line
    data=item['data']
    plan=ProcurementPlan.objects.get(pk=batch.plan_id)
    article=_get(Article,data['article_code'])
    line=plan.lines.filter(article=article).first()
    if line is None:
        line=add_plan_article(user,plan.pk,expected=plan.version,article=article,lot_name=data['lot_name'],_record_revision=False)
    values={'retained_quantity':_decimal(data['retained_quantity']),'included':True,'lot_name':data['lot_name'],
        'decision_reason':data['decision_reason']}
    for field in ('estimated_price','tax_rate'):
        if data.get(field):
            values[field]=_decimal(data[field])
    if data.get('currency'):
        values['currency']=data['currency']
    if data.get('source'):
        values['price_source']=data['source']
    if data.get('supplier_code'):
        values['supplier']=_get(Party,data['supplier_code'])
    return decide_plan_line(user,line.pk,expected=plan.version,values=values,_record_revision=False)


def _execute(user,batch,item):
    if item.get('preparation_error'):
        raise ValidationError(item['preparation_error'])
    if batch.kind=='CATALOG':
        return _catalog(user,item)
    if batch.kind=='LOCATIONS':
        return _location(user,item)
    if batch.kind in ('INITIAL','RECEIPTS'):
        return _receipt(user,batch,item)
    if batch.kind=='SAMPLES':
        return _sample(user,batch,item)
    if batch.kind=='PRICES':
        return _price(user,item)
    if batch.kind=='TEMPERATURE':
        return _temperature(user,item)
    if batch.kind=='PLAN':
        return _plan_line(user,batch,item)
    raise ValidationError(_('Domaine d’import inconnu.'))


def _locks(user,batch):
    batch._created_article_codes=set()
    if batch.plan_id:
        from .procurement import _plan
        batch.plan=_plan(user,batch.plan_id,edit=True)
    if batch.kind=='SAMPLES':
        ids={item['source']['request_id'] for item in batch.payload if item.get('source')}
        list(Request.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by('pk'))
    lock_tree('locations')
    lock_tree('references')
    for baseline in sorted(batch.baselines,key=lambda item:(item['model'],item['id'])):
        model=BASELINE_MODELS[baseline['model']]
        obj=model.objects.select_for_update(no_key=True).get(pk=baseline['id'])
        if obj.version!=baseline['version'] or _hash(snapshot(obj))!=baseline['hash']:
            raise Conflict(_('Un référentiel ou le plan a changé depuis l’aperçu. Analysez à nouveau le fichier.'))


def _permissions(user,batch,item):
    data=item['data']
    if batch.kind=='PLAN':
        require_work(user,batch.plan.work,costs=any(data.get(name) for name in ('estimated_price','tax_rate','currency','source','supplier_code')))
        return
    if batch.kind=='LOCATIONS':
        code=data.get('code','').upper()
        location=Location.objects.filter(code=code).first()
        waiting={row['data'].get('code','').upper():row['data'].get('parent_code','').upper() for row in batch.payload}
        seen=set()
        while location is None and code:
            if code in seen:
                raise PermissionDenied
            seen.add(code)
            code=waiting.get(code,'')
            location=Location.objects.filter(code=code).first() if code else None
        require(user,Capability.EDIT_STORAGE,location=location)
        return
    location=_get(Location,data.get('location_code',''),optional=True)
    article=Article.objects.filter(code=data.get('article_code',data.get('code','')).upper()).first()
    category=article.category if article else _get(Category,data.get('category_code',data.get('new_category_code','')),optional=True)
    if batch.kind=='TEMPERATURE':
        from .cold_storage import _temperature_permission
        _temperature_permission(user,location)
    else:
        require(user,CAPABILITIES[batch.kind],category=category,location=location)
    if batch.kind in ('INITIAL','RECEIPTS') and data.get('unit_price_base'):
        require(user,Capability.EDIT_COST,category=category)
    if batch.kind=='SAMPLES' and item.get('source'):
        from .links import require_request
        require_request(user,Request.objects.get(pk=item['source']['request_id']),write=False)


def require_batch(user,batch):
    if not is_team(user) or not is_manager(user) and batch.actor_id!=user.pk:
        raise PermissionDenied
    if not is_manager(user):
        valid_rows={row['row'] for row in batch.report.get('preview',[]) if row['valid']}
        for item in batch.payload:
            if item['row'] not in valid_rows:
                continue
            try:
                _permissions(user,batch,item)
            except (ValidationError,ObjectDoesNotExist):
                raise PermissionDenied


@transaction.atomic
def preview_import(user,*,key,kind,filename,data,reason,plan=None):
    require_kind(user,kind,plan)
    if not reason.strip() or len(reason)>500:
        raise ValidationError(_('Justifiez l’origine et le but de cet import.'))
    if plan is not None and kind!='PLAN':
        raise ValidationError(_('Un plan ne doit être associé qu’à un import de ses articles.'))
    key=_key(key)
    rows=parse_table(kind,filename,data)
    digest=hashlib.sha256(data).hexdigest()
    creation_hash=_hash({'kind':kind,'file':digest,'plan':str(plan.pk) if plan else None,'reason':reason})
    lock_tree('import-creation')
    existing=ImportBatch.objects.filter(creation_key=key).first()
    if existing:
        if existing.actor_id!=user.pk or existing.creation_hash!=creation_hash:
            raise Conflict(_('Cette clé d’aperçu a déjà été utilisée pour un autre import.'))
        return existing
    prepared,baselines=_prepare(user,kind,rows,plan)
    positions=sum((_integer(row['data'].get('grid_rows') or 0)*_integer(row['data'].get('grid_columns') or 0)
        for row in prepared),0) if kind=='LOCATIONS' else 0
    if positions>20000:
        raise ValidationError(_('Un import est limité à 20 000 positions de stockage. Répartissez les boîtes entre plusieurs fichiers.'))
    batch=ImportBatch(creation_key=key,creation_hash=creation_hash,kind=kind,actor=user,plan=plan,
        filename=PurePath(filename.replace(chr(92),'/')).name[:180],sha256=digest,payload=prepared,baselines=baselines,
        reason=reason.strip(),expires_at=timezone.now()+timedelta(hours=24))
    checked=[]
    with transaction.atomic():
        _locks(user,batch)
        for item in prepared:
            try:
                with transaction.atomic():
                    obj=_execute(user,batch,item)
                checked.append({'row':item['row'],'valid':True,'message':str(_('Ligne vérifiée.')),
                    'entity_type':obj._meta.label_lower})
            except (ValidationError,IntegrityError,PermissionDenied,ObjectDoesNotExist) as exc:
                message=' ; '.join(exc.messages) if isinstance(exc,ValidationError) else str(_('Référence, doublon, relation ou permission à vérifier.'))
                checked.append({'row':item['row'],'valid':False,'message':message[:1500]})
        transaction.set_rollback(True)
    batch.report={'preview':checked,'valid':all(row['valid'] for row in checked),'row_count':len(prepared)}
    batch.full_clean()
    batch.save()
    audit(user,batch,'import_previewed',reason=reason)
    return batch


@transaction.atomic
def apply_import(user,pk,*,expected,confirmed):
    batch=ImportBatch.objects.select_for_update().get(pk=pk)
    require_batch(user,batch)
    if confirmed is not True:
        raise ValidationError(_('Confirmez explicitement les lignes vérifiées avant de les appliquer.'))
    if batch.status=='APPLIED':
        return batch
    require_kind(user,batch.kind,batch.plan)
    check_version(batch,expected)
    if batch.status!='PREVIEW' or not batch.report.get('valid') or batch.expires_at<=timezone.now():
        raise ValidationError(_('L’aperçu n’est plus applicable. Corrigez les erreurs ou analysez à nouveau le fichier.'))
    _locks(user,batch)
    results=[]
    for item in batch.payload:
        obj=_execute(user,batch,item)
        results.append({'row':item['row'],'entity_type':obj._meta.label_lower,'id':str(obj.pk)})
    if batch.kind=='PLAN':
        from .procurement import _revision
        _revision(user,ProcurementPlan.objects.get(pk=batch.plan_id),batch.reason)
    batch.status='APPLIED'
    batch.applied_by,batch.applied_at=user,timezone.now()
    batch.report={**batch.report,'applied':results}
    batch.version+=1
    batch.save()
    audit(user,batch,'import_applied',reason=batch.reason)
    return batch


@transaction.atomic
def cancel_import(user,pk,*,expected,reason):
    batch=ImportBatch.objects.select_for_update().get(pk=pk)
    require_batch(user,batch)
    check_version(batch,expected)
    if batch.status!='PREVIEW' or not reason.strip():
        raise ValidationError(_('Seul un aperçu peut être abandonné avec une justification.'))
    before=snapshot(batch)
    batch.status='CANCELLED'
    batch.version+=1
    batch.save()
    audit(user,batch,'import_cancelled',before,reason[:500])
    return batch
