from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect,render
from django.urls import reverse
from django.views.decorators.http import require_GET,require_http_methods
from django.utils.translation import gettext_lazy as _

from .alert_forms import AlertActionForm,AlertPolicyForm
from .permissions import has_access,is_manager,require_manager
from .services.alerts import acknowledge,collect_alerts,policy,save_policy
from .views import add_validation


@login_required
@require_GET
def alert_list(request):
    if not has_access(request.user):
        raise PermissionDenied
    result=collect_alerts(request.user)
    severity=request.GET.get('severity','')
    alerts=[row for row in result['alerts'] if not severity or row['severity']==severity]
    state=request.GET.get('state','')
    if state=='new':
        alerts=[row for row in alerts if not row['acknowledgement']]
    return render(request,'erp/alerts.html',{'assessment':result,'page':Paginator(alerts,40).get_page(request.GET.get('page')),
        'manager':is_manager(request.user),'severity':severity,'state':state})


@login_required
@require_http_methods(['GET','POST'])
def alert_policy(request):
    require_manager(request.user)
    obj=policy()
    initial={name:getattr(obj,name) for name in ('dormant_days','receipt_pending_days','occupancy_percent','overstock_multiplier','digest_enabled')}
    initial.update(expected_version=obj.version,expiry_days=', '.join(str(day) for day in obj.expiry_days))
    form=AlertPolicyForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_policy(request.user,values,expected=values.pop('expected_version'))
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:alerts')
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Configurer les alertes de ressources'),
        'cancel_url':reverse('erp:alerts')},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def alert_action(request,signature):
    if not has_access(request.user):
        raise PermissionDenied
    found=next((row for row in collect_alerts(request.user,limit=None)['alerts'] if row['signature']==signature),None)
    if found is None:
        from django.http import Http404
        raise Http404
    form=AlertActionForm(request.POST or None,user=request.user)
    if request.method=='POST' and form.is_valid():
        try:
            value=acknowledge(request.user,signature,**form.cleaned_data)
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:work-detail',pk=value.work_id) if value.work_id else redirect('erp:alerts')
    return render(request,'erp/operation_form.html',{'form':form,'title':_('Prendre en charge une alerte'),
        'subtitle':found['label']+' — '+found['message'],'cancel_url':reverse('erp:alerts')},status=400 if request.method=='POST' else 200)
