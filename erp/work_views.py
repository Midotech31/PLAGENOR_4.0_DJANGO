from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from .models import WorkItem
from .permissions import has_access, is_manager, require_manager
from .services.work import (EDITABLE, comment_work, create_work, delegate_work,
                           transition_work, work_allowed, work_scope)
from .views import add_validation
from .work_forms import DelegationForm, WorkCommentForm, WorkForm, WorkTransitionForm


@login_required
@require_GET
def work_list(request):
    qs = work_scope(request.user)
    if not has_access(request.user):
        require_manager(request.user)
    search = request.GET.get('q', '').strip()[:200]
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(instructions__icontains=search))
    kind, state = request.GET.get('kind', ''), request.GET.get('state', '')
    if kind in WorkItem.Kind.values:
        qs = qs.filter(kind=kind)
    if state in WorkItem.Status.values:
        qs = qs.filter(status=state)
    if request.GET.get('mine') == '1':
        qs = qs.filter(assignee=request.user)
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    return render(request, 'erp/work_list.html', {'page': page, 'manager': is_manager(request.user),
        'q': search, 'kind': kind, 'state': state, 'kinds': WorkItem.Kind.choices, 'states': WorkItem.Status.choices})


@login_required
@require_http_methods(['GET', 'POST'])
def work_create(request):
    require_manager(request.user)
    form = WorkForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        values.pop('expected_version')
        try:
            work = create_work(request.user, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:work-detail', pk=work.pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Affecter une tâche'),
        'cancel_url': reverse('erp:work-list')}, status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def work_detail(request, pk):
    work = get_object_or_404(work_scope(request.user), pk=pk)
    form = WorkTransitionForm(initial={'expected_version': work.version})
    comment = WorkCommentForm()
    status = 200
    available_states = []
    if work_allowed(request.user, work, edit=True):
        available_states.append('IN_PROGRESS')
        if work.kind not in ('CDC', 'INVENTORY', 'PLAN'):
            available_states.append('SUBMITTED')
    if is_manager(request.user):
        if work.status == 'SUBMITTED':
            available_states.append('CHANGES_REQUESTED')
            if work.kind not in ('CDC', 'INVENTORY', 'PLAN'):
                available_states.append('APPROVED')
        if work.status not in ('APPROVED', 'CANCELLED'):
            available_states.append('CANCELLED')
    choices = [(code, label) for code, label in WorkItem.Status.choices if code in available_states]
    form.fields['state'].choices = choices
    if request.method == 'POST':
        if request.POST.get('action') == 'comment':
            comment = WorkCommentForm(request.POST)
            if comment.is_valid():
                try:
                    comment_work(request.user, work.pk, comment.cleaned_data['body'])
                except ValidationError as error:
                    add_validation(comment, error)
                else:
                    return redirect('erp:work-detail', pk=pk)
        else:
            form = WorkTransitionForm(request.POST)
            form.fields['state'].choices = choices
            if form.is_valid():
                try:
                    values = dict(form.cleaned_data)
                    transition_work(request.user, pk, expected=values.pop('expected_version'), **values)
                except ValidationError as error:
                    add_validation(form, error)
                else:
                    return redirect('erp:work-detail', pk=pk)
        status = 400
    return render(request, 'erp/work_detail.html', {'work': work, 'form': form, 'comment_form': comment,
        'manager': is_manager(request.user), 'editable': work_allowed(request.user, work, edit=True),
        'comments': work.comments.select_related('actor'), 'can_delegate': is_manager(request.user)
        and work.status not in (WorkItem.Status.APPROVED, WorkItem.Status.CANCELLED)}, status=status)


@login_required
@require_http_methods(['GET', 'POST'])
def work_delegate(request, pk):
    require_manager(request.user)
    work = get_object_or_404(work_scope(request.user), pk=pk)
    form = DelegationForm(request.POST or None, instance=work, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            delegate_work(request.user, pk, expected=values.pop('expected_version'), **values)
        except ValidationError as error:
            add_validation(form, error)
        else:
            messages.success(request, _('La délégation et les droits du dossier ont été mis à jour.'))
            return redirect('erp:work-detail', pk=pk)
    return render(request, 'erp/operation_form.html', {'form': form, 'title': _('Déléguer / réaffecter la tâche'),
        'cancel_url': reverse('erp:work-detail', args=[pk])}, status=400 if request.method == 'POST' else 200)
