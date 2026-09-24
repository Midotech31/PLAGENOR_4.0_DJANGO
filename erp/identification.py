import io
import re
from urllib.parse import urlencode
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist,PermissionDenied,ValidationError
from django.db.models import Q
from django.http import Http404,HttpResponse
from django.shortcuts import redirect,render
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import qrcode

from .models import Article,BiologicalSample,Capability,Location,LocationClosure,StockContainer,StockLot
from .permissions import catalog_scope,grants,has_access,is_manager,operational_scope,storage_scope
from .services.biobank import biobank_scope


MODELS={'article':Article,'lot':StockLot,'container':StockContainer,'location':Location,'sample':BiologicalSample}
TITLES={'article':_('Article'),'lot':_('Lot'),'container':_('Contenant'),'location':_('Emplacement'),'sample':_('Échantillon / aliquot')}
TOKEN=re.compile(r'^PLAGENOR\|([a-z]+)\|([0-9a-fA-F-]{36})$')


def identity_scope(user,kind):
    if kind not in MODELS:
        raise Http404
    stock=operational_scope(StockContainer.objects.all(),user)
    if kind=='container':
        return stock.select_related('lot__article','location')
    if kind=='lot':
        return StockLot.objects.filter(pk__in=stock.values('lot_id')).select_related('article')
    if kind=='article':
        return Article.objects.filter(Q(pk__in=catalog_scope(Article.objects.all(),user).values('pk'))|
            Q(pk__in=stock.values('lot__article_id')))
    if kind=='sample':
        return biobank_scope(user)
    stored=stock.values('location_id')
    location_ids=LocationClosure.objects.filter(descendant_id__in=stored).values('ancestor_id')
    return Location.objects.filter(Q(pk__in=storage_scope(Location.objects.all(),user).values('pk'))|
        Q(pk__in=storage_scope(Location.objects.all(),user,Capability.VIEW_BIOBANK).values('pk'))|Q(pk__in=location_ids))


def identity(user,kind,pk):
    try:
        return identity_scope(user,kind).get(pk=pk)
    except (ObjectDoesNotExist,ValidationError,ValueError):
        raise Http404


def target_url(user,kind,obj):
    if kind=='container':
        return reverse('erp:stock-detail',args=[obj.pk])
    if kind=='sample':
        return reverse('erp:sample-detail',args=[obj.pk])
    if kind=='lot':
        return reverse('erp:stock-list')+'?'+urlencode({'q':obj.code})
    if kind=='article':
        if catalog_scope(Article.objects.filter(pk=obj.pk),user).exists():
            return reverse('erp:article',args=[obj.pk])
        return reverse('erp:stock-list')+'?'+urlencode({'q':obj.code})
    if storage_scope(Location.objects.filter(pk=obj.pk),user,Capability.VIEW_STORAGE).exists():
        return reverse('erp:location',args=[obj.pk])
    if storage_scope(Location.objects.filter(pk=obj.pk),user,Capability.VIEW_BIOBANK).exists():
        return reverse('erp:storage-grid',args=[obj.pk]) if obj.grid_rows else reverse('erp:storage-maps')+'?'+urlencode({'parent':obj.pk})
    return reverse('erp:stock-list')+'?'+urlencode({'location':obj.pk})


@login_required
@require_GET
def identify(request):
    if not has_access(request.user):
        raise PermissionDenied
    query=request.GET.get('q','').strip()[:255]
    match=TOKEN.fullmatch(query)
    if match:
        kind,pk=match.groups()
        obj=identity(request.user,kind,pk)
        return redirect(target_url(request.user,kind,obj))
    results=[]
    if query:
        for kind in MODELS:
            qs=identity_scope(request.user,kind)
            filters=Q(code__iexact=query)
            if kind=='lot':
                filters|=Q(manufacturer_lot__iexact=query)|Q(barcode__exact=query)
            if kind=='article':
                filters|=Q(manufacturer_reference__iexact=query)|Q(cas__exact=query)
            for obj in qs.filter(filters).order_by('code')[:100]:
                results.append({'kind':TITLES[kind],'code':obj.code,'label':obj.code if kind=='sample' else str(obj),
                    'url':target_url(request.user,kind,obj),'label_url':reverse('erp:label',args=[kind,obj.pk])})
    return render(request,'erp/identify.html',{'q':query,'results':results})


@login_required
@require_GET
def identify_target(request,kind,pk):
    obj=identity(request.user,kind,pk)
    return redirect(target_url(request.user,kind,obj))


@login_required
@require_GET
def qr_image(request,kind,pk):
    obj=identity(request.user,kind,pk)
    token='PLAGENOR|'+kind+'|'+str(obj.pk)
    qr=qrcode.QRCode(version=None,error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=8,border=4)
    qr.add_data(token)
    qr.make(fit=True)
    buffer=io.BytesIO()
    qr.make_image(fill_color='black',back_color='white').save(buffer,format='PNG')
    response=HttpResponse(buffer.getvalue(),content_type='image/png')
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response


@login_required
@require_GET
def label(request,kind,pk):
    obj=identity(request.user,kind,pk)
    try:
        copies=int(request.GET.get('copies','1'))
    except ValueError:
        raise Http404
    if not 1<=copies<=100:
        raise Http404
    expiry=min((day for day in (getattr(obj,'expires_on',None),getattr(obj,'use_by',None),
        obj.lot.expires_on if kind=='container' else None) if day is not None),default=None)
    return render(request,'erp/labels.html',{'kind':kind,'pk':obj.pk,'code':obj.code,'type_label':TITLES[kind],
        'copies':range(copies),'expiry':expiry,'return_url':target_url(request.user,kind,obj)})
