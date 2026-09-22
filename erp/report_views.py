import tempfile
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.paginator import Paginator
from django.http import FileResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .permissions import Capability,grants,has_access,is_manager
from .report_forms import ReportFilterForm
from .services.reports import export_report,render_value,report,stock_value_estimate


@login_required
@require_GET
def report_home(request):
    if not has_access(request.user):
        raise PermissionDenied
    values={'kind':'STOCK' if is_manager(request.user) or grants(request.user,Capability.VIEW_STOCK).exists() else 'TASKS','year':timezone.localdate().year,'days':30}
    values.update(request.GET.dict())
    form=ReportFilterForm(values,user=request.user)
    context={'form':form,'dataset':None,'page':None,'rows':[],'valuation':None}
    if form.is_valid():
        filters=form.cleaned_data
        try:
            dataset=report(request.user,filters['kind'],filters)
            if request.GET.get('export')=='xlsx':
                stream=tempfile.SpooledTemporaryFile(max_size=2*1024*1024,mode='w+b')
                try:
                    export_report(dataset,stream)
                    stream.seek(0)
                    response=FileResponse(stream,as_attachment=True,filename='PLAGENOR-'+filters['kind']+'-'+str(filters['year'])+'.xlsx',
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    response['Cache-Control']='private, no-store'
                    response['X-Content-Type-Options']='nosniff'
                    return response
                except Exception:
                    stream.close()
                    raise
            page=Paginator(dataset.queryset,50).get_page(request.GET.get('page'))
            context.update(dataset=dataset,page=page,rows=[[render_value(value) for value in dataset.serialize(obj)] for obj in page])
            if filters['kind']=='STOCK':
                context['valuation']=stock_value_estimate(request.user,filters)
        except ValidationError as exc:
            form.add_error(None,exc)
    query=request.GET.copy()
    query.pop('page',None)
    query['export']='xlsx'
    context['export_url']='?'+query.urlencode()
    return render(request,'erp/reports.html',context,status=400 if form.errors else 200)
