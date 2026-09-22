import io
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET,require_http_methods

from .import_forms import ImportApplyForm,ImportCancelForm,ImportUploadForm
from .models import ImportBatch
from .permissions import has_access,is_manager
from .services.bulk_imports import apply_import,cancel_import,preview_import,require_batch
from .services.procurement import plan_scope
from .services.table_intake import LABELS,MAX_FILE,import_template
from .views import add_validation


def batches(user):
    if not has_access(user):
        raise PermissionDenied
    qs=ImportBatch.objects.select_related('actor','applied_by','plan__work')
    return qs if is_manager(user) else qs.filter(actor=user)


@login_required
@require_http_methods(['GET','POST'])
def import_home(request):
    qs=batches(request.user)
    form=ImportUploadForm(request.POST or None,request.FILES or None,user=request.user)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        uploaded=values.pop('file')
        data=uploaded.read(MAX_FILE+1)
        try:
            batch=preview_import(request.user,filename=uploaded.name,data=data,**values)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:import-detail',pk=batch.pk)
    return render(request,'erp/import_home.html',{'form':form,'page':Paginator(qs,25).get_page(request.GET.get('page')),
        'kinds':ImportBatch.Kind.choices},status=400 if request.method=='POST' else 200)


@login_required
@require_GET
def template_download(request,kind):
    if not has_access(request.user):
        raise PermissionDenied
    if kind not in ImportBatch.Kind.values:
        raise Http404
    return FileResponse(io.BytesIO(import_template(kind)),as_attachment=True,filename='PLAGENOR-'+kind+'.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@login_required
@require_http_methods(['GET','POST'])
def import_detail(request,pk):
    batch=get_object_or_404(batches(request.user),pk=pk)
    require_batch(request.user,batch)
    form=ImportApplyForm(request.POST or None,initial={'expected_version':batch.version})
    if request.method=='POST' and form.is_valid():
        try:
            apply_import(request.user,pk,expected=form.cleaned_data['expected_version'],confirmed=form.cleaned_data['confirmed'])
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:import-detail',pk=pk)
    headers=list(batch.payload[0]['data']) if batch.payload else []
    assessments={row['row']:row for row in batch.report.get('preview',[])}
    page=Paginator(batch.payload,40).get_page(request.GET.get('page'))
    rows=[{'number':row['row'],'values':[row['data'].get(name,'') for name in headers],
        'check':assessments.get(row['row'])} for row in page]
    return render(request,'erp/import_detail.html',{'batch':batch,'form':form,'page':page,'rows':rows,
        'headers':[LABELS.get(name,name) for name in headers]},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def import_cancel(request,pk):
    batch=get_object_or_404(batches(request.user),pk=pk)
    require_batch(request.user,batch)
    form=ImportCancelForm(request.POST or None,initial={'expected_version':batch.version})
    if request.method=='POST' and form.is_valid():
        try:
            cancel_import(request.user,pk,expected=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:import-detail',pk=pk)
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Abandonner cet aperçu d’import'),
        'cancel_url':reverse('erp:import-detail',args=[pk])},status=400 if request.method=='POST' else 200)


@login_required
@require_GET
def import_report(request,pk):
    batch=get_object_or_404(batches(request.user),pk=pk)
    require_batch(request.user,batch)
    from .services.report_exports import literal,workbook_table
    applied={row['row']:row for row in batch.report.get('applied',[])}
    rows=[]
    for row in batch.report.get('preview',[]):
        result=applied.get(row['row'],{})
        rows.append([row['row'],str(_('Valide')) if row['valid'] else str(_('À corriger')),row['message'],result.get('entity_type',''),result.get('id','')])
    book=workbook_table(str(_('PLAGENOR 4.0 — Rapport d’import')),batch.filename+' — '+str(batch.get_status_display()),
        [str(_('Ligne du fichier')),str(_('Contrôle')),str(_('Résultat de la vérification')),str(_('Type d’enregistrement')),str(_('Identifiant créé ou reconnu'))],
        rows,[18,18,85,30,42],numeric=(1,))
    sheet=book.create_sheet('Traçabilité')
    for index,(key,value) in enumerate([('Import',str(batch.pk)),('SHA-256',batch.sha256),
        ('Origine',batch.reason),('Auteur',str(batch.actor)),('Application',str(batch.applied_at or ''))],1):
        sheet.cell(index,1,key)
        sheet.cell(index,2,literal(value))
    sheet.column_dimensions['A'].width=20
    sheet.column_dimensions['B'].width=85
    output=io.BytesIO()
    book.save(output)
    response=FileResponse(io.BytesIO(output.getvalue()),as_attachment=True,filename='Import-'+str(batch.pk)+'.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control']='private, no-store'
    return response
