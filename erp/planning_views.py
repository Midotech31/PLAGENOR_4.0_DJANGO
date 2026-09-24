from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from . import planning_forms as forms
from .models import ActivitySchedule, AnalysisRun, AvailabilityBlock, PlanningResource, WorkItem
from .permissions import TEAM_ROLES, has_access, is_manager
from .services.links import request_scope
from .services.planning import (cancel_unavailability, confirm_resources, create_activity_series, readiness,
    save_resource, save_schedule, save_unavailability, schedule_scope, set_dependencies)
from .services.work import require_work, work_allowed, work_scope
from .views import add_validation


def _access(user, manager=False):
    if not (is_manager(user) if manager else has_access(user)):
        raise PermissionDenied


def _period(request):
    try:
        selected = date.fromisoformat(request.GET.get('date', timezone.localdate().isoformat()))
    except (ValueError, TypeError):
        raise Http404
    view = request.GET.get('view', 'week')
    if view not in ('day', 'week', 'month', 'list') or not 2000 <= selected.year <= 2099:
        raise Http404
    first = selected if view == 'day' else selected.replace(day=1) if view == 'month' else selected-timedelta(days=selected.weekday())
    last = (first.replace(day=28)+timedelta(days=4)).replace(day=1) if view == 'month' else first+timedelta(days=1 if view=='day' else 7)
    tz = timezone.get_current_timezone()
    return first, last, timezone.make_aware(datetime.combine(first, time.min), tz), timezone.make_aware(datetime.combine(last, time.min), tz), view


def _work_filter(request, qs):
    kind, member = request.GET.get('kind', ''), request.GET.get('member', '')
    if kind:
        if kind not in WorkItem.Kind.values:
            raise Http404
        qs = qs.filter(kind=kind)
    if member:
        try:
            member = int(member)
        except ValueError:
            raise Http404
        qs = qs.filter(assignee_id=member)
    text = request.GET.get('q', '').strip()[:200]
    if text:
        qs = qs.filter(title__icontains=text)
    return qs


@login_required
@require_GET
def planning_home(request):
    _access(request.user)
    first, last, start, end, mode = _period(request)
    base = work_scope(request.user)
    works = _work_filter(request, base)
    all_slots = schedule_scope(request.user).filter(work__in=works, starts_at__lt=end, ends_at__gt=start).exclude(work__status='CANCELLED')
    slot_count = all_slots.count()
    slots = list(all_slots.order_by('starts_at', 'id')[:500])
    days, load = [], {}
    for offset in range((last-first).days):
        day = first+timedelta(days=offset)
        day_start = timezone.make_aware(datetime.combine(day, time.min))
        day_end = timezone.make_aware(datetime.combine(day+timedelta(days=1), time.min))
        days.append({'date': day, 'today': day==timezone.localdate(),
            'slots': [slot for slot in slots if slot.starts_at < day_end and slot.ends_at > day_start]})
    for slot in all_slots.prefetch_related(None).iterator(chunk_size=200):
        if slot.work.assignee_id and slot.work.status not in ('SUBMITTED', 'APPROVED'):
            person = slot.work.assignee
            row = load.setdefault(person.pk, {'member': person, 'hours': 0, 'activities': 0})
            row['hours'] += (min(slot.ends_at,end)-max(slot.starts_at,start)).total_seconds()/3600
            row['activities'] += 1
    today = timezone.localdate()
    current = works.exclude(status__in=['APPROVED','CANCELLED'])
    inbox = Paginator(current.filter(schedule__isnull=True).order_by('due_on','title'), 15).get_page(request.GET.get('page'))
    requests = request_scope(request.user).filter(archived=False).exclude(status__in=['COMPLETED','CLOSED','REJECTED','ARCHIVED'])
    source_requests = requests.filter(planned_activities__isnull=True).select_related('assigned_to__user','service')
    sources = []
    for req in source_requests.order_by('created_at')[:12]:
        route = 'dashboard:admin_request_detail' if is_manager(request.user) else 'dashboard:analyst_request_detail'
        sources.append({'request': req, 'url': reverse(route,args=[req.pk])})
    query = request.GET.copy()
    query.pop('page', None)
    query['date']=(first-timedelta(days=1) if mode=='month' else first-timedelta(days=(last-first).days)).isoformat()
    previous='?'+query.urlencode()
    query['date']=last.isoformat()
    following='?'+query.urlencode()
    return render(request, 'erp/planning.html', {'days':days,'slots':slots,'mode':mode,'first':first,'last':last-timedelta(days=1),
        'selected_date':first.isoformat(),'previous':previous,'following':following,
        'members': get_user_model().objects.filter(is_active=True,role__in=TEAM_ROLES).order_by('last_name','username') if is_manager(request.user) else [],
        'kinds':WorkItem.Kind.choices,'filter_kind':request.GET.get('kind',''),'filter_member':request.GET.get('member',''),
        'q':request.GET.get('q','')[:200],'manager':is_manager(request.user),
        'counts':{'unscheduled':current.filter(schedule__isnull=True).count(),'overdue':current.filter(due_on__lt=today).count(),
            'review':works.filter(status='SUBMITTED').count(),'in_progress':works.filter(status='IN_PROGRESS').count()},
        'inbox':inbox,'reviews':works.filter(status='SUBMITTED').order_by('submitted_at')[:12],
        'overdue':current.filter(due_on__lt=today).order_by('due_on')[:12],
        'workload':sorted(load.values(),key=lambda row:row['hours'],reverse=True),
        'sources':sources,'source_count':source_requests.count(),'truncated':slot_count>len(slots),'slot_count':slot_count,
        'timezone_name':str(timezone.get_current_timezone())})


@login_required
@require_http_methods(['GET','POST'])
def activity_create(request):
    _access(request.user, manager=True)
    initial = {}
    if request.GET.get('request'):
        req = get_object_or_404(request_scope(request.user,write=True),pk=request.GET['request'])
        initial['request']=req
    form = forms.ActivityCreateForm(request.POST or None,user=request.user,initial=initial)
    if request.method=='POST' and form.is_valid():
        try:
            schedule=create_activity_series(request.user,**form.cleaned_data)[0]
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:activity-detail',pk=schedule.work_id)
    return _form(request,form,_('Planifier une activité'),reverse('erp:planning'))


def _form(request,form,title,cancel):
    return render(request,'erp/operation_form.html',{'form':form,'title':title,'cancel_url':cancel},status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def activity_schedule(request,pk):
    _access(request.user,manager=True)
    work=get_object_or_404(work_scope(request.user),pk=pk)
    schedule=ActivitySchedule.objects.filter(work=work).first()
    initial={'expected_version':work.version}
    if schedule:
        initial.update(starts_at=timezone.localtime(schedule.starts_at),ends_at=timezone.localtime(schedule.ends_at),
            resources=schedule.resources.all(),request=schedule.request_id,run=schedule.run_id)
    form=forms.ScheduleForm(request.POST or None,user=request.user,initial=initial)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_schedule(request.user,pk,expected=values.pop('expected_version'),**values)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:activity-detail',pk=pk)
    return _form(request,form,_('Définir ou modifier le créneau'),reverse('erp:work-detail',args=[pk]))


@login_required
@require_http_methods(['GET','POST'])
def activity_detail(request,pk):
    work=get_object_or_404(work_scope(request.user),pk=pk)
    result=readiness(request.user,work)
    form=forms.ReadinessForm(request.POST or None,initial={'expected_version':work.version})
    if request.method=='POST' and form.is_valid():
        try:
            confirm_resources(request.user,pk,expected=form.cleaned_data['expected_version'],note=form.cleaned_data['note'])
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:activity-detail',pk=pk)
    prerequisites=work.prerequisites.select_related('prerequisite')
    visible_ids=set(work_scope(request.user).filter(pk__in=prerequisites.values('prerequisite_id')).values_list('pk',flat=True))
    steps=[{'title':edge.prerequisite.title if edge.prerequisite_id in visible_ids else str(_('Prérequis géré par une autre équipe')),
        'state':edge.prerequisite.get_status_display(),'url':reverse('erp:activity-detail',args=[edge.prerequisite_id]) if edge.prerequisite_id in visible_ids else ''} for edge in prerequisites]
    return render(request,'erp/activity_detail.html',{'work':work,'assessment':result,'schedule':result['schedule'],
        'form':form,'prerequisites':steps,'manager':is_manager(request.user),'editable':work_allowed(request.user,work,edit=True)},
        status=400 if request.method=='POST' else 200)


@login_required
@require_http_methods(['GET','POST'])
def dependencies_edit(request,pk):
    _access(request.user,manager=True)
    work=get_object_or_404(work_scope(request.user),pk=pk)
    form=forms.DependencyForm(request.POST or None,work=work,initial={'expected_version':work.version,
        'prerequisites':work.prerequisites.values_list('prerequisite_id',flat=True)})
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            set_dependencies(request.user,pk,expected=values.pop('expected_version'),**values)
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:activity-detail',pk=pk)
    return _form(request,form,_('Préparer les prérequis'),reverse('erp:activity-detail',args=[pk]))


@login_required
@require_GET
def resource_list(request):
    _access(request.user,manager=True)
    return render(request,'erp/planning_resources.html',{'resources':PlanningResource.objects.select_related('location').order_by('code'),
        'blocks':AvailabilityBlock.objects.select_related('member','resource').filter(active=True,ends_at__gt=timezone.now()).order_by('starts_at')[:100]})


@login_required
@require_http_methods(['GET','POST'])
def resource_edit(request,pk=None):
    _access(request.user,manager=True)
    obj=get_object_or_404(PlanningResource,pk=pk) if pk else PlanningResource()
    form=forms.ResourceForm(request.POST or None,instance=obj,user=request.user)
    if request.method=='POST' and form.is_valid():
        values=dict(form.cleaned_data)
        try:
            save_resource(request.user,values,pk=pk,expected=values.pop('expected_version'))
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:planning-resources')
    return _form(request,form,_('Équipement ou salle réservable'),reverse('erp:planning-resources'))


@login_required
@require_http_methods(['GET','POST'])
def unavailability_create(request):
    _access(request.user,manager=True)
    form=forms.UnavailabilityForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        try:
            save_unavailability(request.user,**form.cleaned_data)
        except (ValidationError,IntegrityError) as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:planning-resources')
    return _form(request,form,_('Indisponibilité ou maintenance'),reverse('erp:planning-resources'))


@login_required
@require_http_methods(['GET','POST'])
def unavailability_end(request,pk):
    _access(request.user,manager=True)
    block=get_object_or_404(AvailabilityBlock,pk=pk)
    form=forms.UnavailabilityEndForm(request.POST or None,initial={'expected_version':block.version})
    if request.method=='POST' and form.is_valid():
        try:
            cancel_unavailability(request.user,pk,expected=form.cleaned_data['expected_version'],reason=form.cleaned_data['reason'])
        except ValidationError as exc:
            add_validation(form,exc)
        else:
            return redirect('erp:planning-resources')
    return _form(request,form,_('Lever une indisponibilité'),reverse('erp:planning-resources'))
