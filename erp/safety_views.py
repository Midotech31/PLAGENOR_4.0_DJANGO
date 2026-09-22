import io
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist,PermissionDenied,ValidationError
from django.db import IntegrityError
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET,require_http_methods

from . import safety_forms as forms
from .models import Article,ChemicalProfile,HazardTag,ResourceDocument,StorageSafetyRule
from .permissions import Capability,catalog_scope,is_manager,require_manager
from .services.safety import (MAX_DOCUMENT,attach_document,document_target,require_target,
    save_chemical_profile,save_hazard_tag,save_storage_rule,target_cost_access)
from .views import add_validation


def _target(user,kind,pk,write=False):
    try:
        return require_target(user,kind,pk,write=write)
    except (ObjectDoesNotExist,ValidationError):
        raise Http404


@login_required
@require_GET
def document_list(request,target_kind,target_id):
    target=_target(request.user,target_kind,target_id)
    qs=ResourceDocument.objects.filter(**{target_kind:target}).defer('content','replacement__content').select_related('actor','replacement')
    if not target_cost_access(request.user,target_kind,target):
        qs=qs.filter(financial=False)
    try:
        _target(request.user,target_kind,target_id,write=True)
        can_write=True
    except PermissionDenied:
        can_write=False
    return render(request,'erp/resource_documents.html',{'documents':qs,'target':target,
        'target_kind':target_kind,'target_id':target_id,'can_write':can_write})


@login_required
@require_http_methods(['GET','POST'])
def document_upload(request,target_kind,target_id):
    target=_target(request.user,target_kind,target_id,write=True)
    form=forms.DocumentForm(request.POST or None,request.FILES or None,user=request.user,target_kind=target_kind,target=target)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        file=values.pop('file')
        try:
            attach_document(request.user,target_kind,target_id,filename=file.name,data=file.read(MAX_DOCUMENT+1),**values)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:resource-documents',target_kind=target_kind,target_id=target_id)
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Joindre un document au dossier'),
        'cancel_url':reverse('erp:resource-documents',args=[target_kind,target_id])},status=400 if request.method=='POST' else 200)


@login_required
@require_GET
def document_download(request,pk):
    doc=get_object_or_404(ResourceDocument,pk=pk)
    kind,target_id=document_target(doc)
    target=_target(request.user,kind,target_id)
    if doc.financial and not target_cost_access(request.user,kind,target):
        raise PermissionDenied
    response=FileResponse(io.BytesIO(bytes(doc.content)),as_attachment=True,filename=doc.original_name,
        content_type='application/pdf' if doc.extension=='.pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response


@login_required
@require_GET
def safety_home(request):
    require_manager(request.user)
    return render(request,'erp/safety_rules.html',{'tags':HazardTag.objects.all().order_by('code'),
        'rules':StorageSafetyRule.objects.select_related('location','first_tag','second_tag').order_by('location__code','id')})


@login_required
@require_http_methods(['GET','POST'])
def hazard_edit(request,pk=None):
    require_manager(request.user)
    tag=get_object_or_404(HazardTag,pk=pk) if pk else HazardTag()
    form=forms.HazardForm(request.POST or None,user=request.user,instance=tag)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_hazard_tag(request.user,values,pk=pk,expected=values.pop('expected_version'))
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:safety')
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Définir un groupe de danger documenté'),
        'cancel_url':reverse('erp:safety')},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def rule_edit(request,pk=None):
    require_manager(request.user)
    rule=get_object_or_404(StorageSafetyRule,pk=pk) if pk else StorageSafetyRule()
    form=forms.StorageRuleForm(request.POST or None,user=request.user,instance=rule)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_storage_rule(request.user,values,pk=pk,expected=values.pop('expected_version'))
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:safety')
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Configurer une restriction de stockage'),
        'cancel_url':reverse('erp:safety')},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def chemical_edit(request,pk):
    article=get_object_or_404(catalog_scope(Article.objects.all(),request.user,Capability.EDIT_CATALOG),pk=pk)
    profile=ChemicalProfile.objects.filter(article=article).first() or ChemicalProfile(article=article,reviewed_by=request.user)
    form=forms.ChemicalForm(request.POST or None,user=request.user,article=article,instance=profile)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        expected,tags=values.pop('expected_version'),values.pop('tags')
        try:
            save_chemical_profile(request.user,pk,expected=expected,values=values,tags=tags)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:article',pk=pk)
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Renseigner les dangers à partir de la FDS'),
        'subtitle':article.name,'cancel_url':reverse('erp:article',args=[pk])},status=400 if request.method=='POST' else 200)
