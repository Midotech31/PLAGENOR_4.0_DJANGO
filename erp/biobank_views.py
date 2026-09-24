from decimal import Decimal, InvalidOperation
import uuid

from django import forms as django_forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_http_methods

from . import biobank_forms as forms
from .models import (BiologicalSample, Capability, Location, LocationClosure, PositionReservation,
    SampleEvent, StorageIncident, StoragePosition, StorageTransfer, TemperatureReading, Unit, WorkItem)
from .permissions import grants, is_manager, permitted, require_manager, storage_scope
from .services.biobank import (aliquot_sample, biobank_scope, build_positions, receive_sample,
    require_sample, reserve_position, sample_action, source_samples, transfer_sample)
from .services.cold_storage import (apply_transfer_plan, create_incident, record_temperature,
    resolve_incident, transfer_plan)
from .services.links import request_scope
from .services.work import work_scope
from .stock_forms import location_choices
from .views import add_validation


def require_biobank(user, *, write=False):
    capability = Capability.MANAGE_BIOBANK if write else Capability.VIEW_BIOBANK
    if not is_manager(user) and not grants(user, capability).exists():
        raise PermissionDenied


def _form(request, form, title, cancel_url, subtitle=''):
    return render(request, 'erp/operation_form.html', {'form': form, 'title': title,
        'subtitle': subtitle, 'cancel_url': cancel_url}, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def sample_list(request):
    require_biobank(request.user)
    qs = biobank_scope(request.user)
    search = request.GET.get('q', '').strip()[:200]
    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(origin_request__display_id__icontains=search) |
            Q(root_sample__origin_request__display_id__icontains=search) | Q(location__code__icontains=search))
    state = request.GET.get('state', '')
    if state in BiologicalSample.Status.values:
        qs = qs.filter(status=state)
    return render(request, 'erp/sample_list.html', {'page': Paginator(qs.order_by('code'), 30).get_page(request.GET.get('page')),
        'q': search, 'state': state, 'states': BiologicalSample.Status.choices,
        'can_write': is_manager(request.user) or grants(request.user, Capability.MANAGE_BIOBANK).exists()})


@login_required
@require_GET
def source_list(request, request_id):
    require_biobank(request.user, write=True)
    req = get_object_or_404(request_scope(request.user, write=True), pk=request_id)
    try:
        rows = source_samples(request.user, req)
        error = ''
    except ValidationError as exc:
        rows, error = [], '; '.join(exc.messages)
    return render(request, 'erp/sample_sources.html', {'req': req, 'sources': rows, 'source_error': error})


def source_initial(source):
    initial = {'sample_type': source['sample_type'], 'matrix': source['matrix'],
        'preservation': source['preservation'][:500], 'collected_on': source['collected_on']}
    label = str(source['declared_unit'] or '').casefold().replace('μ', 'µ')
    quantities = {'ml': ('VOLUME', Decimal('0.001')), 'µl': ('VOLUME', Decimal('0.000001')),
        'ul': ('VOLUME', Decimal('0.000001')), 'l': ('VOLUME', Decimal(1)),
        'g': ('MASS', Decimal('0.001')), 'mg': ('MASS', Decimal('0.000001')), 'kg': ('MASS', Decimal(1))}
    definition = quantities.get(label)
    if definition:
        units = list(Unit.objects.filter(active=True, dimension=definition[0], factor=definition[1])[:2])
        if len(units) == 1:
            try:
                amount = Decimal(str(source['declared_quantity']))
            except InvalidOperation:
                amount = None
            if amount is not None and amount.is_finite() and amount > 0:
                initial.update(amount=amount, unit=units[0].pk)
    return initial


@login_required
@require_http_methods(['GET', 'POST'])
def sample_receive(request, request_id=None, source_key=None):
    require_biobank(request.user, write=True)
    req, source = None, None
    initial = {}
    if request_id:
        req = get_object_or_404(request_scope(request.user, write=True), pk=request_id)
        source = next((value for value in source_samples(request.user, req) if value['key'] == source_key), None)
        if source is None:
            raise Http404
        initial.update(source_initial(source))
    for name in ('location', 'position'):
        if request.GET.get(name):
            initial[name] = request.GET[name]
    form = forms.SampleReceiveForm(request.POST or None, user=request.user, initial=initial)
    if source:
        form.fields['source_fingerprint'] = django_forms.CharField(max_length=64, widget=django_forms.HiddenInput,
            initial=source['fingerprint'])
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        if source:
            values.update(request=req, source_key=source_key)
        try:
            sample = receive_sample(request.user, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:sample-detail', pk=sample.pk)
    return _form(request, form, _('Réceptionner et ranger un échantillon'),
        reverse('erp:sample-sources', args=[req.pk]) if req else reverse('erp:sample-list'),
        str(_('Source PLAGENOR : %(request)s · %(sample)s')) % {'request': req.display_id, 'sample': source['code']} if req else '')


@login_required
@require_GET
def sample_detail(request, pk):
    require_biobank(request.user)
    sample = get_object_or_404(biobank_scope(request.user), pk=pk)
    metadata = sample.shared_metadata
    can_write = permitted(request.user, Capability.MANAGE_BIOBANK, location=sample.location)
    events = sample.events.select_related('actor', 'from_location', 'to_location', 'from_position', 'to_position').order_by('-created_at', '-id')
    if not is_manager(request.user):
        locations = storage_scope(Location.objects.all(), request.user, Capability.VIEW_BIOBANK)
        events = events.filter(Q(from_location__in=locations) | Q(to_location__in=locations))
    return render(request, 'erp/sample_detail.html', {'sample': sample, 'metadata': metadata,
        'can_write': can_write and sample.status not in ('DESTROYED', 'SHIPPED', 'EXHAUSTED'),
        'events': events[:100], 'aliquots': biobank_scope(request.user).filter(parent=sample),
        'cycle_warning': metadata.freeze_thaw_limit is not None and sample.freeze_thaw_cycles > metadata.freeze_thaw_limit})


@login_required
@require_http_methods(['GET', 'POST'])
def sample_operation(request, pk, operation):
    sample = get_object_or_404(biobank_scope(request.user), pk=pk)
    require_sample(request.user, sample)
    config = {'transfer': (forms.SampleTransferForm, _('Déplacer un échantillon')),
        'aliquot': (forms.AliquotForm, _('Créer un aliquot')),
        'action': (forms.SampleActionForm, _('Enregistrer un événement biologique'))}
    if operation not in config:
        raise Http404
    form_type, title = config[operation]
    kwargs = {'user': request.user, 'initial': {'expected_version': sample.version, 'unit': sample.unit_id}}
    if operation == 'action':
        kwargs['sample'] = sample
    form = form_type(request.POST or None, **kwargs)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        try:
            if operation == 'transfer':
                transfer_sample(request.user, pk, expected=expected, **values)
            elif operation == 'aliquot':
                values['location'] = values.pop('destination')
                child = aliquot_sample(request.user, pk, expected=expected, **values)
                return redirect('erp:sample-detail', pk=child.pk)
            else:
                sample_action(request.user, pk, expected=expected, **values)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:sample-detail', pk=pk)
    return _form(request, form, title, reverse('erp:sample-detail', args=[pk]), sample.code)


@login_required
@require_GET
def position_options(request):
    require_biobank(request.user, write=True)
    try:
        location = get_object_or_404(location_choices(request.user, Capability.MANAGE_BIOBANK), pk=request.GET.get('location'))
    except (ValidationError, ValueError):
        raise Http404
    positions = location.positions.filter(active=True).select_related('occupant').order_by('row', 'column')
    reserved = set(PositionReservation.objects.filter(position__location=location, active=True,
        until__gt=timezone.now()).exclude(assignee=request.user).values_list('position_id', flat=True))
    result = [{'id': str(position.pk), 'label': str(position.row) + ':' + str(position.column),
               'occupied': hasattr(position, 'occupant'), 'reserved': position.pk in reserved} for position in positions]
    return JsonResponse({'positions': result, 'grid_required': bool(location.grid_rows)})


@login_required
@require_GET
def storage_maps(request):
    require_biobank(request.user)
    locations = storage_scope(Location.objects.filter(active=True), request.user, Capability.VIEW_BIOBANK)
    parent = request.GET.get('parent')
    if parent:
        try:
            selected = get_object_or_404(locations, pk=parent)
        except (ValidationError, ValueError):
            raise Http404
        locations = locations.filter(parent=selected)
    else:
        selected = None
        locations = locations.filter(grid_rows__isnull=False)
    rows = []
    locations = locations.annotate(total_positions=Count('positions', distinct=True),
        occupied_positions=Count('positions', filter=Q(positions__occupant__isnull=False), distinct=True),
        reserved_positions=Count('positions', filter=Q(positions__reservations__active=True, positions__reservations__until__gt=timezone.now()), distinct=True))
    for location in locations.order_by('code')[:200]:
        occupied, total, reserved = location.occupied_positions, location.total_positions, location.reserved_positions
        rows.append({'location': location, 'occupied': occupied, 'total': total, 'reserved': reserved,
                     'free': max(0, total-occupied-reserved)})
    return render(request, 'erp/storage_maps.html', {'rows': rows, 'parent': selected})


@login_required
@require_GET
def storage_grid(request, pk):
    require_biobank(request.user)
    location = get_object_or_404(storage_scope(Location.objects.all(), request.user, Capability.VIEW_BIOBANK), pk=pk)
    positions = location.positions.select_related('occupant').order_by('row', 'column')
    reserved = {reservation.position_id: reservation for reservation in PositionReservation.objects.filter(
        position__location=location, active=True, until__gt=timezone.now()).select_related('assignee')}
    rows = {}
    for position in positions:
        rows.setdefault(position.row, []).append({'position': position, 'sample': getattr(position, 'occupant', None),
            'reservation': reserved.get(position.pk)})
    return render(request, 'erp/storage_grid.html', {'location': location, 'rows': rows.items(),
        'columns': range(1, (location.grid_columns or 0)+1),
        'can_write': permitted(request.user, Capability.MANAGE_BIOBANK, location=location)})


@login_required
@require_http_methods(['GET', 'POST'])
def position_reserve(request, pk):
    position = get_object_or_404(StoragePosition, pk=pk,
        location__in=storage_scope(Location.objects.all(), request.user, Capability.MANAGE_BIOBANK))
    form = forms.PositionReservationForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            reserve_position(request.user, pk, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:storage-grid', pk=position.location_id)
    return _form(request, form, _('Réserver une position'), reverse('erp:storage-grid', args=[position.location_id]),
        str(position.location) + ' — ' + str(position.row) + ':' + str(position.column))


@login_required
@require_http_methods(['GET', 'POST'])
def temperature_create(request):
    work = None
    if request.GET.get('task'):
        try:
            work = get_object_or_404(work_scope(request.user), pk=request.GET['task'], kind=WorkItem.Kind.TEMPERATURE)
        except (ValidationError, ValueError):
            raise Http404
    if work is None and not is_manager(request.user) and not grants(request.user, Capability.MANAGE_BIOBANK).exists() and not grants(request.user, Capability.EDIT_STORAGE).exists():
        raise PermissionDenied
    form = forms.TemperatureForm(request.POST or None, user=request.user, work=work)
    if request.method == 'POST' and form.is_valid():
        try:
            record_temperature(request.user, work=work, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:work-detail', pk=work.pk) if work else redirect('erp:cold-incidents')
    return _form(request, form, _('Enregistrer un relevé de température'),
        reverse('erp:work-detail', args=[work.pk]) if work else reverse('erp:cold-incidents'))


@login_required
@require_http_methods(['GET', 'POST'])
def cold_incidents(request):
    require_biobank(request.user)
    locations = storage_scope(Location.objects.all(), request.user, Capability.VIEW_BIOBANK)
    form = forms.IncidentForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            create_incident(request.user, **form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:cold-incidents')
    return render(request, 'erp/cold_incidents.html', {'form': form,
        'incidents': StorageIncident.objects.filter(location__in=locations).select_related('location', 'actor')[:100],
        'readings': TemperatureReading.objects.filter(location__in=locations).select_related('location', 'actor')[:100],
        'manager': is_manager(request.user), 'can_write': is_manager(request.user) or grants(request.user, Capability.MANAGE_BIOBANK).exists()},
        status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def incident_resolve(request, pk):
    require_manager(request.user)
    incident = get_object_or_404(StorageIncident, pk=pk)
    form = forms.IncidentResolutionForm(request.POST or None, initial={'expected_version': incident.version})
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        try:
            resolve_incident(request.user, pk, expected=values.pop('expected_version'), **values)
        except ValidationError as error:
            add_validation(form, error)
        else:
            return redirect('erp:cold-incidents')
    return _form(request, form, _('Clôturer un incident de stockage'), reverse('erp:cold-incidents'), str(incident.location))


@login_required
@require_http_methods(['GET', 'POST'])
def mass_transfer(request):
    require_biobank(request.user, write=True)
    form = forms.MassTransferForm(request.POST or None, user=request.user)
    preview = None
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        token = values.pop('preview_token')
        try:
            if request.POST.get('action') == 'apply':
                data = signing.loads(token, salt='erp.biobank.transfer', max_age=1800)
                if data['actor'] != request.user.pk or data['source'] != str(values['source'].pk) or data['destination'] != str(values['destination'].pk):
                    raise ValidationError(_('Cet aperçu ne correspond pas au membre et aux stockages sélectionnés.'))
                transfer = apply_transfer_plan(request.user, mapping=data['mapping'], **values)
                return redirect('erp:mass-transfer-detail', pk=transfer.pk)
            preview = transfer_plan(request.user, values['source'], values['destination'])
            token = signing.dumps({'actor': request.user.pk, 'source': str(values['source'].pk),
                'destination': str(values['destination'].pk), 'mapping': preview}, salt='erp.biobank.transfer', compress=True)
            data = request.POST.copy()
            data['preview_token'] = token
            form = forms.MassTransferForm(data, user=request.user)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        except signing.BadSignature:
            form.add_error(None, _('L’aperçu a expiré ou a été modifié. Recalculez le plan.'))
    return render(request, 'erp/mass_transfer.html', {'form': form, 'preview': preview},
        status=400 if request.method == 'POST' and not preview else 200)


@login_required
@require_GET
def mass_transfer_detail(request, pk):
    require_biobank(request.user)
    locations = storage_scope(Location.objects.all(), request.user, Capability.VIEW_BIOBANK)
    transfer = get_object_or_404(StorageTransfer.objects.select_related('source', 'destination', 'actor'),
        pk=pk, source__in=locations, destination__in=locations)
    return render(request, 'erp/mass_transfer_detail.html', {'transfer': transfer})
