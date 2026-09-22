import io

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import FileResponse,Http404
from django.shortcuts import get_object_or_404,redirect,render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET,require_http_methods,require_POST

from . import procurement_forms as forms
from .cdc.docengine import DocumentError
from .models import ForecastObservation,ProcurementLine,ProcurementPlan,PurchaseOrderLine
from .permissions import Capability,grants,has_access,is_manager,require_manager
from .services.procurement import (add_plan_article,approve_plan,create_plan,decide_plan_line,plan_scope,
    plan_to_cdc,plan_totals,refresh_forecast,submit_plan)
from .services.purchases import (cancel_order,confirm_order,create_order,order_scope,receive_order_line,
    received_quantity,revise_delivery_date,save_order_line)
from .services.work import require_work,work_allowed
from .views import add_validation


METHOD_LABELS={'MEAN_12':_('Moyenne des douze derniers mois disponibles'),
    'RECENT_6':_('Moyenne des six derniers mois'),'TREND_12':_('Tendance linéaire sur douze mois'),
    'SEASONAL_NAIVE':_('Même mois de l’année précédente')}
CONFIDENCE_LABELS={'LOW':_('Faible'),'MEDIUM':_('Moyenne'),'HIGH':_('Élevée')}
WARNING_LABELS={'SHORT_HISTORY':_('Historique inférieur à douze mois : la proposition nécessite une revue renforcée.'),
    'OVERDUE_DELIVERIES_EXCLUDED':_('Les livraisons en retard sont exclues jusqu’à confirmation d’une nouvelle date.'),
    'FUTURE_RECEIPTS_REQUIRE_ACCEPTANCE_AND_EXPIRY_REVIEW':_('Les arrivages prévus restent soumis au contrôle de réception et à la vérification des péremptions.'),
    'LEAD_TIME_UNKNOWN':_('Le délai fournisseur n’est pas renseigné.'),
    'SHORTAGE_BEFORE_NORMAL_DELIVERY':_('Une rupture est prévue avant la livraison possible au délai habituel.')}


def _error(form,error):
    add_validation(form,ValidationError(str(error)) if isinstance(error,DocumentError) else error)


def _form(request,form,title,cancel_url,subtitle=''):
    return render(request,'erp/operation_form.html',{'form':form,'title':title,'cancel_url':cancel_url,'subtitle':subtitle},
        status=400 if request.method=='POST' else 200)


@login_required
@require_GET
def plan_list(request):
    if not has_access(request.user):
        raise PermissionDenied
    qs=plan_scope(request.user)
    q=request.GET.get('q','').strip()[:200]
    if q:
        qs=qs.filter(Q(reference__icontains=q)|Q(work__title__icontains=q))
    return render(request,'erp/procurement_list.html',{'page':Paginator(qs,30).get_page(request.GET.get('page')),
        'manager':is_manager(request.user),'q':q})


@login_required
@require_http_methods(['GET','POST'])
def plan_create(request):
    require_manager(request.user)
    form=forms.PlanCreateForm(request.POST or None,user=request.user)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        values.pop('expected_version')
        try:
            plan=create_plan(request.user,**values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:procurement-detail',pk=plan.pk)
    return _form(request,form,_('Créer et déléguer un plan d’approvisionnement'),reverse('erp:procurement-list'))


@login_required
@require_http_methods(['GET','POST'])
def plan_detail(request,pk):
    plan=get_object_or_404(plan_scope(request.user),pk=pk)
    form=forms.PlanActionForm(request.POST or None,initial={'expected_version':plan.version})
    if request.method=='POST' and form.is_valid():
        action=request.POST.get('action')
        if action not in ('submit','approve'):
            raise Http404
        try:
            (submit_plan if action=='submit' else approve_plan)(request.user,pk,
                expected=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:procurement-detail',pk=pk)
    costs=work_allowed(request.user,plan.work,costs=True)
    return render(request,'erp/procurement_detail.html',{'plan':plan,'form':form,
        'lines':plan.lines.select_related('article','purchase_unit','forecast'),
        'totals':plan_totals(request.user,plan) if costs else None,'costs':costs,
        'manager':is_manager(request.user),'editable':work_allowed(request.user,plan.work,edit=True),
        'orders':plan.orders.select_related('supplier'),'revisions':plan.revisions.defer('data')[:50]},
        status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def plan_article(request,pk):
    plan=get_object_or_404(plan_scope(request.user),pk=pk)
    require_work(request.user,plan.work,edit=True)
    form=forms.PlanArticleForm(request.POST or None,plan=plan,initial={'expected_version':plan.version})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            add_plan_article(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:procurement-detail',pk=pk)
    return _form(request,form,_('Ajouter un article au plan'),reverse('erp:procurement-detail',args=[pk]))


@login_required
@require_http_methods(['GET','POST'])
def plan_line(request,pk):
    line=get_object_or_404(ProcurementLine.objects.select_related('plan__work'),pk=pk,plan__in=plan_scope(request.user))
    plan=line.plan
    require_work(request.user,plan.work,edit=True)
    form=forms.PlanDecisionForm(request.POST or None,user=request.user,plan=plan,instance=line)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            decide_plan_line(request.user,pk,expected=values.pop('expected_version'),values=values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:procurement-detail',pk=plan.pk)
    return _form(request,form,_('Décider la quantité et le budget'),reverse('erp:procurement-detail',args=[plan.pk]),
        line.article_snapshot['name']+' — '+line.article_snapshot['purchase_unit_name'])


@login_required
@require_http_methods(['GET','POST'])
def forecast_detail(request,pk):
    line=get_object_or_404(ProcurementLine.objects.select_related('plan__work','forecast'),pk=pk,plan__in=plan_scope(request.user))
    form=forms.PlanActionForm(request.POST or None,initial={'expected_version':line.plan.version,'reason':_('Recalculer la proposition')})
    del form.fields['reason']
    if request.method=='POST' and form.is_valid():
        try:
            refresh_forecast(request.user,pk,expected=form.cleaned_data['expected_version'])
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:forecast-detail',pk=pk)
    observation=line.forecast
    result=observation.result if observation else None
    return render(request,'erp/forecast_detail.html',{'line':line,'plan':line.plan,'observation':observation,
        'model':result['model'] if result else None,'projection':result['projection'] if result else None,
        'method':METHOD_LABELS.get(result['model']['method']) if result else None,
        'confidence':CONFIDENCE_LABELS.get(result['model']['confidence']) if result else None,
        'warnings':[WARNING_LABELS.get(code,code) for code in result['warnings']] if result else [],
        'form':form,'editable':work_allowed(request.user,line.plan.work,edit=True)},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def cdc_from_plan(request,pk):
    require_manager(request.user)
    plan=get_object_or_404(plan_scope(request.user),pk=pk)
    form=forms.CdcFromPlanForm(request.POST or None,initial={'expected_version':plan.version})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            dossier=plan_to_cdc(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError,DocumentError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:cdc-detail',pk=dossier.pk)
    return _form(request,form,_('Préparer le CDC à partir du plan approuvé'),reverse('erp:procurement-detail',args=[pk]))


@login_required
@require_http_methods(['GET','POST'])
def order_create(request,pk):
    require_manager(request.user)
    plan=get_object_or_404(plan_scope(request.user),pk=pk)
    form=forms.OrderCreateForm(request.POST or None,initial={'expected_version':plan.version})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            order=create_order(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:order-detail',pk=order.pk)
    return _form(request,form,_('Enregistrer une commande institutionnelle'),reverse('erp:procurement-detail',args=[pk]))


@login_required
@require_http_methods(['GET','POST'])
def order_detail(request,pk):
    order=get_object_or_404(order_scope(request.user),pk=pk)
    form=forms.PlanActionForm(request.POST or None,initial={'expected_version':order.version})
    if request.method=='POST' and form.is_valid():
        action=request.POST.get('action')
        if action not in ('confirm','cancel'):
            raise Http404
        try:
            (confirm_order if action=='confirm' else cancel_order)(request.user,pk,expected=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:order-detail',pk=pk)
    rows=[]
    for line in order.lines.select_related('unit','plan_line__article'):
        received=received_quantity(line)
        rows.append({'line':line,'received':received,'remaining':line.quantity-received,
            'deliveries':line.deliveries.select_related('receipt__container','receipt__movement')})
    return render(request,'erp/order_detail.html',{'order':order,'rows':rows,'form':form,
        'manager':is_manager(request.user),'costs':work_allowed(request.user,order.plan.work,costs=True)},
        status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def order_line(request,order_id,pk=None):
    require_manager(request.user)
    order=get_object_or_404(order_scope(request.user),pk=order_id)
    line=get_object_or_404(PurchaseOrderLine,pk=pk,order=order) if pk else None
    initial={'expected_version':order.version}
    if line:
        initial.update({name:getattr(line,name) for name in ('plan_line','quantity','unit_price','tax_rate','currency','variance_reason')})
    form=forms.OrderLineForm(request.POST or None,order=order,initial=initial)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_order_line(request.user,order.pk,expected=values.pop('expected_version'),pk=pk,**values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:order-detail',pk=order.pk)
    return _form(request,form,_('Article commandé et prix contractuel'),reverse('erp:order-detail',args=[order.pk]))


@login_required
@require_http_methods(['GET','POST'])
def order_receive(request,pk):
    if not is_manager(request.user) and not grants(request.user,Capability.RECEIVE_STOCK).exists():
        raise PermissionDenied
    line=get_object_or_404(PurchaseOrderLine.objects.select_related('order__plan__work','plan_line__article'),
        pk=pk,order__in=order_scope(request.user))
    form=forms.OrderReceiptForm(request.POST or None,user=request.user,line=line,initial={'expected_version':line.order.version})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            receive_order_line(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError) as exc:
            _error(form,exc)
        else:
            return redirect('erp:order-detail',pk=line.order_id)
    return _form(request,form,_('Réceptionner la ligne de commande'),reverse('erp:order-detail',args=[line.order_id]),
        line.article_snapshot['name']+' — '+line.article_snapshot['purchase_unit_name'])


@login_required
@require_http_methods(['GET','POST'])
def order_date(request,pk):
    require_manager(request.user)
    order=get_object_or_404(order_scope(request.user),pk=pk)
    form=forms.OrderDateForm(request.POST or None,initial={'expected_version':order.version,'expected_on':order.expected_on})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            revise_delivery_date(request.user,pk,expected=values.pop('expected_version'),**values)
        except ValidationError as exc:
            _error(form,exc)
        else:
            return redirect('erp:order-detail',pk=pk)
    return _form(request,form,_('Actualiser la livraison attendue'),reverse('erp:order-detail',args=[pk]))


@login_required
@require_GET
def plan_export(request,pk):
    plan=get_object_or_404(plan_scope(request.user),pk=pk)
    from .services.report_exports import export_plan
    data=export_plan(request.user,plan)
    response=FileResponse(io.BytesIO(data),as_attachment=True,filename='Plan-'+str(plan.pk)+'.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response
