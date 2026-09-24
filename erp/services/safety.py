from pathlib import PurePath
import hashlib

from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.upload_validation import validate_document
from erp.models import (Article,BiologicalSample,Capability,ChemicalProfile,HazardTag,Location,LocationClosure,
    PurchaseOrder,ResourceDocument,StockContainer,StockReceipt,StorageSafetyRule,WorkItem)
from erp.permissions import permitted,require,require_manager
from .common import Conflict,assign,audit,check_version,lock_tree,snapshot
from .work import require_work,work_allowed


TARGETS={'article':Article,'receipt':StockReceipt,'work':WorkItem,'sample':BiologicalSample,'order':PurchaseOrder}
MAX_DOCUMENT=10*1024*1024


def require_target(user,kind,pk,*,write=False):
    if kind not in TARGETS:
        raise ValidationError(_('Type de dossier documentaire inconnu.'))
    obj=TARGETS[kind].objects.get(pk=pk)
    if kind=='article':
        require(user,Capability.EDIT_CATALOG if write else Capability.VIEW_CATALOG,category=obj.category)
    elif kind=='receipt':
        require(user,Capability.RECEIVE_STOCK if write else Capability.VIEW_STOCK,
            category=obj.container.lot.article.category,location=obj.container.location)
    elif kind=='work':
        require_work(user,obj,edit=write)
    elif kind=='sample':
        from .biobank import require_sample
        require_sample(user,obj,write=write)
    else:
        require_work(user,obj.plan.work)
        if write:
            require_manager(user)
    return obj


def target_cost_access(user,kind,obj):
    if kind in ('work','order'):
        return work_allowed(user,obj if kind=='work' else obj.plan.work,costs=True)
    if kind=='article':
        return permitted(user,Capability.VIEW_COST,category=obj.category)
    if kind=='receipt':
        return permitted(user,Capability.VIEW_COST,category=obj.container.lot.article.category,location=obj.container.location)
    return False


def document_target(document):
    for kind in TARGETS:
        if getattr(document,kind+'_id') is not None:
            return kind,getattr(document,kind+'_id')
    raise ValidationError(_('Document sans dossier associé.'))


@transaction.atomic
def attach_document(user,target_kind,target_id,*,title,kind,filename,data,source,documented_on=None,supersedes=None,financial=False):
    target=require_target(user,target_kind,target_id,write=True)
    financial=bool(financial or target_kind=='order')
    if financial and not target_cost_access(user,target_kind,target):
        raise PermissionDenied
    extension=PurePath(filename).suffix.lower()
    if extension not in ('.pdf','.docx') or not isinstance(data,bytes) or not data or len(data)>MAX_DOCUMENT:
        raise ValidationError(_('Déposez un document PDF ou DOCX valide de 10 Mo au maximum.'))
    if not title.strip() or not source.strip():
        raise ValidationError(_('Un intitulé et une origine documentaire sont obligatoires.'))
    if documented_on is not None and documented_on>timezone.localdate():
        raise ValidationError(_('La date du document ne peut pas être future.'))
    validate_document(data,extension)
    digest=hashlib.sha256(data).hexdigest()
    lock_tree('resource-documents')
    existing=ResourceDocument.objects.filter(**{target_kind:target},sha256=digest,kind=kind,financial=financial).first()
    if existing:
        return existing
    if supersedes is not None:
        supersedes=ResourceDocument.objects.get(pk=supersedes.pk)
        if document_target(supersedes)!=(target_kind,target.pk) or supersedes.kind!=kind:
            raise ValidationError(_('La nouvelle version doit remplacer un document du même dossier et du même type.'))
        if supersedes.financial:
            financial=True
            if not target_cost_access(user,target_kind,target):
                raise PermissionDenied
        if hasattr(supersedes,'replacement'):
            raise Conflict(_('Ce document possède déjà une version ultérieure.'))
    document=ResourceDocument(**{target_kind:target},kind=kind,title=title.strip(),
        original_name=PurePath(filename.replace(chr(92),'/')).name[:180],extension=extension,
        content=data,sha256=digest,size=len(data),documented_on=documented_on,source=source.strip(),financial=financial,
        actor=user,supersedes=supersedes)
    document.full_clean()
    document.save()
    audit(user,document,'document_attached',reason=source[:500])
    return document


@transaction.atomic
def save_hazard_tag(user,values,*,pk=None,expected=None):
    require_manager(user)
    lock_tree('locations')
    obj=HazardTag.objects.get(pk=pk) if pk else HazardTag()
    if pk:
        check_version(obj,expected)
    before=snapshot(obj) if pk else {}
    allowed={'code','name','name_en','name_ar','ghs_code','description','active'}
    if set(values)-allowed:
        raise ValidationError(_('Champ de danger non autorisé.'))
    assign(obj,values)
    obj.full_clean()
    obj.version+=1 if pk else 0
    obj.save()
    audit(user,obj,'hazard_tag_saved',before)
    return obj


@transaction.atomic
def save_chemical_profile(user,article_id,*,expected,values,tags):
    lock_tree('locations')
    article=Article.objects.select_for_update().get(pk=article_id)
    require(user,Capability.EDIT_CATALOG,category=article.category)
    check_version(article,expected)
    allowed={'classification','signal_word','handling','source_reference','source_document','reviewed_on'}
    if set(values)-allowed:
        raise ValidationError(_('Champ de fiche chimique non autorisé.'))
    profile=ChemicalProfile.objects.filter(article=article).first()
    before=snapshot(profile) if profile else {}
    if profile:
        before['tags']=list(profile.tags.values_list('code',flat=True))
    profile=profile or ChemicalProfile(article=article,reviewed_by=user)
    assign(profile,values)
    profile.reviewed_by=user
    if not profile.source_reference.strip() or not profile.classification.strip() or not profile.reviewed_on or profile.reviewed_on>timezone.localdate():
        raise ValidationError(_('Relevez la classification dans une source identifiée et indiquez sa date de vérification.'))
    if profile.source_document and (profile.source_document.article_id!=article.pk or profile.source_document.kind!='SDS'):
        raise ValidationError(_('La FDS jointe doit appartenir à cet article.'))
    ids=[tag.pk for tag in tags]
    if len(ids)!=len(set(ids)) or HazardTag.objects.filter(pk__in=ids,active=True).count()!=len(ids):
        raise ValidationError(_('Les groupes de danger sélectionnés doivent être actifs et distincts.'))
    profile.version+=0 if profile._state.adding else 1
    profile.full_clean()
    profile.save()
    profile.tags.set(tags)
    article.version+=1
    article.save(update_fields=['version','updated_at'])
    audit(user,profile,'chemical_profile_saved',before,profile.source_reference[:500],after={**snapshot(profile),'tags':list(profile.tags.values_list('code',flat=True))})
    return profile


@transaction.atomic
def save_storage_rule(user,values,*,pk=None,expected=None):
    require_manager(user)
    lock_tree('locations')
    rule=StorageSafetyRule.objects.get(pk=pk) if pk else StorageSafetyRule(created_by=user)
    if pk:
        check_version(rule,expected)
    before=snapshot(rule) if pk else {}
    if set(values)-{'location','mode','first_tag','second_tag','blocking','active','reference'}:
        raise ValidationError(_('Champ de règle de stockage non autorisé.'))
    assign(rule,values)
    if not rule.reference.strip() or not rule.location.active or not rule.first_tag.active:
        raise ValidationError(_('La règle exige une source et des références actives.'))
    if rule.second_tag and (not rule.second_tag.active or rule.second_tag_id==rule.first_tag_id):
        raise ValidationError(_('Les deux groupes incompatibles doivent être distincts et actifs.'))
    rule.full_clean()
    rule.version+=1 if pk else 0
    rule.save()
    audit(user,rule,'storage_rule_saved',before,rule.reference[:500])
    return rule


def storage_compatibility(article,location,*,exclude=None):
    tags=set(HazardTag.objects.filter(chemical_profiles__article=article).values_list('pk',flat=True))
    if not tags:
        return []
    rules=StorageSafetyRule.objects.filter(active=True,location_id__in=LocationClosure.objects.filter(descendant=location).values('ancestor_id')).select_related('first_tag','second_tag','location')
    issues=[]
    for rule in rules:
        conflict=False
        if rule.mode=='PROHIBITED':
            conflict=rule.first_tag_id in tags
        elif rule.first_tag_id in tags or rule.second_tag_id in tags:
            target=rule.second_tag_id if rule.first_tag_id in tags else rule.first_tag_id
            conflict=target in tags
            stored=StockContainer.objects.filter(quantity__gt=0,location_id__in=LocationClosure.objects.filter(ancestor=rule.location).values('descendant_id'),
                lot__article__chemical_profile__tags__pk=target)
            if exclude is not None:
                stored=stored.exclude(pk=exclude.pk)
            conflict=conflict or stored.exists()
        if conflict:
            issues.append({'rule':rule,'blocking':rule.blocking,'message':str(_('Incompatibilité de stockage configurée dans %(location)s : %(reference)s')) %
                {'location':rule.location.code,'reference':rule.reference}})
    return issues


def enforce_storage(article,location,*,exclude=None):
    blocked=[row['message'] for row in storage_compatibility(article,location,exclude=exclude) if row['blocking']]
    if blocked:
        raise ValidationError(blocked)
