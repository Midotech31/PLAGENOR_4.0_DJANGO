from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.db.models import Count,Max,Min,Q,Sum
from django.urls import reverse
from django.utils import timezone,translation
from django.utils.translation import gettext_lazy as _

from erp.models import (AlertAcknowledgement,AlertDigest,AlertPolicy,Article,BiologicalSample,Capability,
    Location,LocationClosure,StockContainer,StockEntry,StorageIncident,WorkItem)
from erp.permissions import TEAM_ROLES,grants,is_manager,is_team,operational_scope,permitted,require_manager,storage_scope
from notifications.models import Notification
from .common import Conflict,assign,audit,check_version,lock_tree,snapshot
from .stock import usable_filter
from .work import create_work,work_scope


ZERO=Decimal(0)
SEVERITY={'CRITICAL':0,'HIGH':1,'MEDIUM':2,'LOW':3}


def policy():
    return AlertPolicy.objects.filter(key='PLAGENOR').first() or AlertPolicy()


@transaction.atomic
def save_policy(user,values,*,expected):
    require_manager(user)
    lock_tree('alert-policy')
    obj=AlertPolicy.objects.filter(key='PLAGENOR').first()
    if obj:
        check_version(obj,expected)
    else:
        obj=AlertPolicy()
    before=snapshot(obj) if not obj._state.adding else {}
    allowed={'expiry_days','dormant_days','receipt_pending_days','occupancy_percent','overstock_multiplier','digest_enabled'}
    if set(values)-allowed:
        raise ValidationError(_('Paramètre d’alerte non autorisé.'))
    assign(obj,values)
    if not isinstance(obj.expiry_days,list) or not 1<=len(obj.expiry_days)<=20 or any(type(day) is not int or not 1<=day<=3660 for day in obj.expiry_days):
        raise ValidationError(_('Indiquez de 1 à 20 seuils entiers de péremption, entre 1 et 3 660 jours.'))
    obj.expiry_days=sorted(set(obj.expiry_days),reverse=True)
    if not 1<=obj.dormant_days<=3660 or not 0<=obj.receipt_pending_days<=365:
        raise ValidationError(_('Vérifiez les délais d’absence de consommation et de contrôle de réception.'))
    obj.version+=0 if obj._state.adding else 1
    obj.full_clean()
    obj.save()
    audit(user,obj,'alert_policy_saved',before)
    return obj


def _row(kind,severity,obj,message,url,*,values=None,location=None,category=None):
    data={'kind':kind,'entity_type':obj._meta.label_lower,'entity_id':str(obj.pk),'values':values or {}}
    signature=hashlib.sha256(json.dumps(data,default=str,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {'signature':signature,'kind':kind,'severity':severity,'code':getattr(obj,'code',getattr(obj,'title','')),
        'label':str(obj.get_kind_display())+' — '+str(obj.location) if isinstance(obj,StorageIncident) else str(obj),'message':str(message),'url':url,'data':data,
        'location_id':str(location.pk) if location else None,'category_id':str(category.pk) if category else None}


def collect_alerts(user,*,limit=2000):
    if not is_team(user):
        raise PermissionDenied
    config=policy()
    now,today=timezone.now(),timezone.localdate()
    result=[]
    stock=operational_scope(StockContainer.objects.all(),user)
    aggregates={row['lot__article_id']:row for row in stock.values('lot__article_id').annotate(
        physical=Sum('quantity'),reserved_total=Sum('reserved'),usable=Sum('quantity',filter=usable_filter()),
        usable_reserved=Sum('reserved',filter=usable_filter()),first_recorded=Min('created_at'))}
    usage={row['container__lot__article_id']:row['last'] for row in operational_scope(
        StockEntry.objects.filter(quantity_delta__lt=0,movement__kind__in=['CONSUMPTION','PREPARATION'],movement__reversal__isnull=True),
        user,category_field='container__lot__article__category_id').values('container__lot__article_id').annotate(last=Max('created_at'))}
    complete=Article.objects.filter(active=True).select_related('category','base_unit')
    if not is_manager(user):
        complete_grants=grants(user,Capability.VIEW_STOCK).filter(location__isnull=True)
        if not complete_grants.filter(category__isnull=True).exists():
            complete=complete.filter(category_id__in=complete_grants.values('category_id'))
    for article in complete:
        values=aggregates.get(article.pk)
        url=reverse('erp:stock-list')+'?'+urlencode({'q':article.code})
        if values is None:
            if article.criticality=='CRITICAL':
                result.append(_row('UNINITIALIZED','MEDIUM',article,_('Le suivi physique de cette référence critique n’est pas encore initialisé.'),url,category=article.category))
            continue
        physical=values['physical'] or ZERO
        available=(values['usable'] or ZERO)-(values['usable_reserved'] or ZERO)
        if available<=0:
            message=_('Aucun stock utilisable n’est disponible pour de nouvelles activités.')
            severity='CRITICAL' if article.criticality=='CRITICAL' else 'HIGH'
            result.append(_row('UNAVAILABLE',severity,article,message,url,values={'available':str(available),'physical':str(physical)},category=article.category))
        elif (article.minimum_stock and available<article.minimum_stock) or (article.safety_stock and available<article.safety_stock):
            result.append(_row('LOW_STOCK','HIGH',article,_('Le stock disponible est inférieur au minimum ou au stock de sécurité configuré.'),url,
                values={'available':str(available),'minimum':str(article.minimum_stock),'safety':str(article.safety_stock)},category=article.category))
        elif article.reorder_point and available<=article.reorder_point:
            result.append(_row('REORDER','MEDIUM',article,_('Le seuil configuré de réapprovisionnement est atteint.'),url,
                values={'available':str(available),'threshold':str(article.reorder_point)},category=article.category))
        if article.target_stock and (values['usable'] or ZERO)>article.target_stock*config.overstock_multiplier:
            result.append(_row('OVERSTOCK','LOW',article,_('Le stock utilisable dépasse le multiple configuré du stock cible.'),url,
                values={'usable':str(values['usable']),'target':str(article.target_stock),'multiple':str(config.overstock_multiplier)},category=article.category))
        last=usage.get(article.pk,values['first_recorded'])
        if physical>0 and last and (now-last).days>=config.dormant_days:
            result.append(_row('DORMANT','LOW',article,_('Aucune consommation n’a été enregistrée pendant le délai configuré.'),url,
                values={'last':str(last),'threshold':config.dormant_days},category=article.category))
    cutoff=today+timedelta(days=max(config.expiry_days))
    candidates=stock.filter(quantity__gt=0).filter(Q(use_by__lte=cutoff)|Q(lot__expires_on__lte=cutoff)|
        ~Q(status='AVAILABLE')|~Q(lot__status='AVAILABLE')).select_related('lot__article__category','location')
    for container in candidates.iterator(chunk_size=500):
        expiry=min((value for value in (container.use_by,container.lot.expires_on) if value is not None),default=None)
        url=reverse('erp:stock-detail',args=[container.pk])
        common={'location':container.location,'category':container.lot.article.category}
        if container.status=='RECALLED' or container.lot.status=='RECALLED':
            result.append(_row('RECALL','CRITICAL',container,_('Ce contenant appartient à un stock rappelé et ne doit pas être utilisé.'),url,
                values={'status':container.status,'lot_status':container.lot.status},**common))
        elif expiry and expiry<today:
            result.append(_row('EXPIRED','HIGH',container,_('La date limite de ce contenant est dépassée ; il est exclu du stock utilisable.'),url,values={'expires_on':str(expiry)},**common))
        elif expiry:
            days=(expiry-today).days
            windows=[day for day in config.expiry_days if days<=day]
            if windows:
                window=min(windows)
                result.append(_row('EXPIRY_SOON','HIGH' if window<=30 else 'MEDIUM',container,
                    _('Péremption ou limite après ouverture dans %(days)s jours.') % {'days':days},url,
                    values={'expires_on':str(expiry),'window':window},**common))
        if container.status in ('PENDING','QUARANTINE') and (now-container.created_at).days>=config.receipt_pending_days:
            result.append(_row('RECEIPT_CONTROL','MEDIUM',container,_('Ce contenant attend un contrôle ou une levée de quarantaine.'),url,
                values={'status':container.status,'version':container.version},**common))
    bio_locations=storage_scope(Location.objects.all(),user,Capability.VIEW_BIOBANK)
    for incident in StorageIncident.objects.filter(location__in=bio_locations,resolved_at__isnull=True).select_related('location'):
        result.append(_row('STORAGE_INCIDENT','HIGH',incident,_('Un incident de stockage reste ouvert : %(location)s.') % {'location':incident.location.code},
            reverse('erp:cold-incidents'),values={'kind':incident.kind,'started_at':str(incident.started_at)},location=incident.location))
    occupancy=bio_locations.filter(grid_rows__isnull=False).annotate(total=Count('positions',distinct=True),
        occupied=Count('positions',filter=Q(positions__occupant__isnull=False),distinct=True),
        reserved=Count('positions',filter=Q(positions__reservations__active=True,positions__reservations__until__gt=now),distinct=True))
    for location in occupancy:
        used=location.occupied+location.reserved
        if location.total and Decimal(used)*100>=config.occupancy_percent*location.total:
            result.append(_row('OCCUPANCY','MEDIUM',location,_('L’occupation des positions atteint le seuil configuré.'),
                reverse('erp:storage-grid',args=[location.pk]),values={'used':used,'total':location.total,'threshold':str(config.occupancy_percent)},location=location))
    for work in work_scope(user).filter(due_on__lt=today).exclude(status__in=['APPROVED','CANCELLED']).select_related('location','category'):
        result.append(_row('TASK_OVERDUE','HIGH' if work.priority in ('HIGH','URGENT') else 'MEDIUM',work,
            _('Cette tâche a dépassé son échéance et reste à traiter.'),reverse('erp:work-detail',args=[work.pk]),
            values={'due_on':str(work.due_on),'status':work.status,'version':work.version},location=work.location,category=work.category))
    result.sort(key=lambda row:(SEVERITY[row['severity']],row['kind'],row['code'],row['signature']))
    counts={key:sum(row['severity']==key for row in result) for key in SEVERITY}
    counts['total']=len(result)
    visible=result[:limit] if limit is not None else result
    acknowledgements={row.signature:row for row in AlertAcknowledgement.objects.filter(user=user,signature__in=[row['signature'] for row in visible]).select_related('work')}
    for row in visible:
        row['acknowledgement']=acknowledgements.get(row['signature'])
    return {'alerts':visible,'counts':counts,'truncated':len(visible)<len(result),'policy':config,
        'computed_at':now,'platform_thresholds_available':is_manager(user) or grants(user,Capability.VIEW_STOCK).filter(location__isnull=True).exists()}


@transaction.atomic
def acknowledge(user,signature,*,reason,assignee=None):
    if not reason.strip() or len(reason)>500:
        raise ValidationError(_('Décrivez l’action engagée en 1 à 500 caractères.'))
    found=next((row for row in collect_alerts(user,limit=None)['alerts'] if row['signature']==signature),None)
    if found is None:
        raise Conflict(_('L’alerte a évolué ou n’est plus visible dans votre périmètre. Actualisez la liste.'))
    lock_tree('alert-actions')
    existing=AlertAcknowledgement.objects.filter(user=user,signature=signature).first()
    if existing:
        return existing
    work=None
    if assignee is not None:
        require_manager(user)
        location=Location.objects.get(pk=found['location_id']) if found['location_id'] else None
        from erp.models import Category
        category=Category.objects.get(pk=found['category_id']) if found['category_id'] else None
        work=create_work(user,kind='CONTROL',title=(str(_('Traiter une alerte'))+' — '+found['code'])[:255],
            assignee=assignee,location=location,category=category,instructions=found['message']+chr(10)+reason,
            priority='URGENT' if found['severity']=='CRITICAL' else 'HIGH',due_on=timezone.localdate())
    value=AlertAcknowledgement.objects.create(user=user,signature=signature,data=found['data'],reason=reason.strip(),work=work)
    audit(user,value,'alert_acknowledged',reason=reason)
    return value


@transaction.atomic
def send_digest(user,*,day=None):
    if not is_team(user):
        raise PermissionDenied
    day=day or timezone.localdate()
    config=policy()
    if not config.digest_enabled:
        return None
    lock_tree('alert-digest-'+str(user.pk))
    existing=AlertDigest.objects.filter(user=user,day=day).first()
    if existing:
        return existing
    with translation.override(getattr(user,'preferred_language','fr') or 'fr'):
        result=collect_alerts(user)
        counts=result['counts']
        if not counts['total']:
            return None
        notification=Notification.objects.create(user=user,notification_type='SYSTEM',
            message=str(_('Ressources PLAGENOR : %(total)s alertes, dont %(critical)s critiques. Consultez la synthèse avant les activités prévues.')) %
                {'total':counts['total'],'critical':counts['CRITICAL']},
            link_url=reverse('erp:alerts'),link_text=str(_('Examiner les alertes')))
    digest=AlertDigest.objects.create(user=user,day=day,notification=notification,counts=counts)
    return digest
