from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from . import consumption_forms as forms
from .models import AnalysisRun, ConsumptionProfile, ConsumptionRule, RunAllocation
from .permissions import is_manager, is_team, require_manager
from .services.consumption import (cancel_run, confirm_run, create_run, reservation_proposal,
    reserve_run, run_scope, save_profile, save_rule)
from .services.links import request_scope, require_request
from .views import add_validation


def _form(request, form, title, cancel_url, subtitle=''):
    return render(request, 'erp/operation_form.html', {'form': form, 'title': title,
        'cancel_url': cancel_url, 'subtitle': subtitle}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def run_list(request):
    if not is_team(request.user):
        raise PermissionDenied
    qs = run_scope(request.user).order_by('-planned_on', 'code')
    query = request.GET.get('q', '').strip()[:200]
    if query:
        qs = qs.filter(Q(code__icontains=query) | Q(request__display_id__icontains=query))
    return render(request, 'erp/run_list.html', {'page': Paginator(qs, 30).get_page(request.GET.get('page')),
        'q': query, 'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def run_create(request, request_id):
    req = get_object_or_404(request_scope(request.user, write=True), pk=request_id)
    require_request(request.user, req)
    form = forms.RunCreateForm(request.POST or None, user=request.user, request=req)
    if request.method == 'POST' and form.is_valid():
        try:
            run = create_run(request.user, request=req, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:run-detail', pk=run.pk)
    return _form(request, form, _('Planifier une série analytique'), reverse('erp:run-list'), req.display_id)


@login_required
@require_GET
def run_detail(request, pk):
    run = get_object_or_404(run_scope(request.user), pk=pk)
    writable = request_scope(request.user, write=True).filter(pk=run.request_id).exists() and run.request.status not in ('REJECTED', 'ARCHIVED') and not run.request.archived
    proposal = reservation_proposal(request.user, run) if writable and run.status in ('PLANNED', 'RESERVED') else None
    requirements = run.requirements.select_related('article', 'unit')
    actual = {row['requirement_id']: row['total'] for row in run.consumptions.values('requirement_id').annotate(total=Sum('quantity'))}
    return render(request, 'erp/run_detail.html', {'run': run, 'proposal': proposal, 'editable': writable and run.status in ('PLANNED', 'RESERVED'),
        'manager': is_manager(request.user),
        'requirements': [{'row': row, 'actual': actual.get(row.pk)} for row in requirements],
        'allocations': RunAllocation.objects.filter(requirement__run=run).select_related('reservation__container', 'requirement__unit'),
        'inputs': run.inputs.select_related('sample'), 'consumptions': run.consumptions.select_related('container', 'movement__actor', 'requirement__unit')})


@login_required
@require_http_methods(['GET','POST'])
def run_procurement(request,pk):
    require_manager(request.user);run=get_object_or_404(run_scope(request.user),pk=pk)
    form=forms.RunProcurementForm(request.POST or None,user=request.user,run=run)
    if request.method=='POST' and form.is_valid():
        from .services.procurement import link_run_shortages
        try:plan,count=link_run_shortages(request.user,run.pk,form.cleaned_data['plan'].pk,expected_run=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except (ValidationError,IntegrityError) as error:add_validation(form,error)
        else:messages.success(request,_('%(count)s besoin(s) de stock ont été rattachés au plan d’approvisionnement.')%{'count':count});return redirect('erp:procurement-detail',pk=plan.pk)
    return _form(request,form,_('Transférer les manques vers l’approvisionnement'),reverse('erp:run-detail',args=[pk]),run.code)


@login_required
@require_http_methods(['GET', 'POST'])
def run_operation(request, pk, operation):
    run = get_object_or_404(run_scope(request.user), pk=pk)
    require_request(request.user, run.request)
    initial = {'expected_version': run.version}
    if operation == 'reserve':
        for name in ('requirement', 'container', 'amount'):
            if request.GET.get(name):
                initial[name] = request.GET[name]
        form = forms.RunReserveForm(request.POST or None, user=request.user, run=run, initial=initial)
        title = _('Affecter et réserver un lot à la série')
    elif operation == 'confirm':
        form = forms.RunConfirmForm(request.POST or None, run=run, initial=initial)
        title = _('Confirmer les consommations réelles')
    elif operation == 'cancel':
        form = forms.RunCancelForm(request.POST or None, initial=initial)
        title = _('Annuler la série et libérer les réservations')
    else:
        raise Http404
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected, key = values.pop('expected_version'), values.pop('key')
        try:
            if operation == 'reserve':
                allocation = {'requirement': str(values.pop('requirement').pk),
                    'container': str(values.pop('container').pk), 'quantity': str(values.pop('amount'))}
                reserve_run(request.user, pk, expected=expected, key=key, allocations=[allocation], **values)
            elif operation == 'confirm':
                actuals = {identity: str(values.pop(name)) for identity, name in form.actual_fields.items()}
                biology = {identity: str(values.pop(name)) for identity, name in form.biological_fields.items()}
                confirm_run(request.user, pk, expected=expected, key=key, actuals=actuals, biological_quantities=biology, **values)
            else:
                cancel_run(request.user, pk, expected=expected, key=key, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:run-detail', pk=pk)
    return _form(request, form, title, reverse('erp:run-detail', args=[pk]), run.code)


@login_required
@require_GET
def profile_list(request):
    if not is_team(request.user):
        raise PermissionDenied
    return render(request, 'erp/profile_list.html', {'profiles': ConsumptionProfile.objects.select_related('service').order_by('code'),
        'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def profile_edit(request, pk=None):
    require_manager(request.user)
    profile = get_object_or_404(ConsumptionProfile, pk=pk) if pk else ConsumptionProfile()
    form = forms.ProfileForm(request.POST or None, instance=profile, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        try:
            profile = save_profile(request.user, values, pk=pk, expected=expected)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:profile-detail', pk=profile.pk)
    return _form(request, form, _('Nomenclature de consommation d’un service'), reverse('erp:profile-list'))


@login_required
@require_GET
def profile_detail(request, pk):
    if not is_team(request.user):
        raise PermissionDenied
    profile = get_object_or_404(ConsumptionProfile.objects.select_related('service'), pk=pk)
    return render(request, 'erp/profile_detail.html', {'profile': profile,
        'rules': profile.rules.select_related('article', 'unit'), 'manager': is_manager(request.user)})


@login_required
@require_http_methods(['GET', 'POST'])
def rule_edit(request, profile_id, pk=None):
    require_manager(request.user)
    profile = get_object_or_404(ConsumptionProfile, pk=profile_id)
    rule = get_object_or_404(ConsumptionRule, pk=pk, profile=profile) if pk else ConsumptionRule(profile=profile)
    form = forms.RuleForm(request.POST or None, instance=rule, user=request.user,
        initial={'expected_version': profile.version})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        try:
            save_rule(request.user, profile.pk, values, expected=expected, pk=pk)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:profile-detail', pk=profile.pk)
    return _form(request, form, _('Règle de consommation'), reverse('erp:profile-detail', args=[profile.pk]), profile.name)
