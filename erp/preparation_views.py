from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404,redirect,render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET,require_http_methods

from .models import Capability,InternalPreparation,StockContainer
from .permissions import grants,is_manager,operational_scope
from .preparation_forms import IngredientFormSet,PreparationForm
from .services.preparations import prepare_stock
from .views import add_validation


@login_required
@require_http_methods(['GET','POST'])
def preparation_create(request):
    if not is_manager(request.user) and not grants(request.user,Capability.RECEIVE_STOCK).exists():
        raise PermissionDenied
    form=PreparationForm(request.POST or None,user=request.user)
    ingredients=IngredientFormSet(request.POST or None,form_kwargs={'user':request.user},prefix='sources')
    if request.method=='POST' and form.is_valid() and ingredients.is_valid():
        values=[dict(row.cleaned_data) for row in ingredients if row.cleaned_data]
        try:
            preparation=prepare_stock(request.user,ingredients=values,**form.cleaned_data)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:preparation-detail',pk=preparation.pk)
    return render(request,'erp/preparation_form.html',{'form':form,'ingredients':ingredients},status=400 if request.method=='POST' else 200)


@login_required
@require_GET
def preparation_detail(request,pk):
    preparation=get_object_or_404(InternalPreparation.objects.select_related('output_lot__article','movement__actor').distinct(),pk=pk,
        output_lot__containers__in=operational_scope(StockContainer.objects.all(),request.user))
    return render(request,'erp/preparation_detail.html',{'preparation':preparation,
        'outputs':operational_scope(preparation.output_lot.containers.all(),request.user).select_related('location')})
