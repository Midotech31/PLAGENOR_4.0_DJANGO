from functools import partial
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from . import forms
from .models import (AccessGrant, Article, ArticleConversion, AuditEvent, Capability,
                     Category, InventorySourceRecord, Location, LocationClosure, LocationType,
                     Party, Unit)
from .permissions import (catalog_scope, grants, has_access, is_manager, permitted,
                          require, require_manager, storage_scope)
from .services.access import save_grant
from .services.catalog import record_price, save_article, save_conversion, save_reference
from .services.inventory_bootstrap import apply_inventory, summarize as summarize_inventory
from .services.storage import save_location


SECTIONS = {
    'articles': (Article, forms.ArticleForm, _('Référentiel des articles'), save_article),
    'categories': (Category, forms.CategoryForm, _('Catégories'), partial(save_reference, model=Category)),
    'units': (Unit, forms.UnitForm, _('Unités'), partial(save_reference, model=Unit)),
    'parties': (Party, forms.PartyForm, _('Fournisseurs et fabricants'), partial(save_reference, model=Party)),
    'location-types': (LocationType, forms.LocationTypeForm, _('Types d’emplacements'), partial(save_reference, model=LocationType)),
    'locations': (Location, forms.LocationForm, _('Emplacements'), save_location),
    'delegations': (AccessGrant, forms.GrantForm, _('Délégations ERP'), save_grant),
}


def section_config(section):
    if section not in SECTIONS:
        raise Http404
    return SECTIONS[section]


def queryset_for(section, user):
    model, _, _, _ = section_config(section)
    if not has_access(user):
        raise PermissionDenied
    qs = model.objects.all()
    if section == 'delegations':
        require_manager(user)
        return qs.select_related('user', 'category', 'location').order_by('user_id', 'capability', 'id')
    if section == 'articles':
        return catalog_scope(qs, user).select_related('category', 'base_unit')
    if section == 'categories':
        return catalog_scope(qs, user, field='pk').select_related('parent')
    if section == 'locations':
        return storage_scope(qs, user).select_related('parent', 'kind')
    capability = Capability.VIEW_STORAGE if section == 'location-types' else Capability.VIEW_CATALOG
    if not is_manager(user) and not grants(user, capability).exists():
        raise PermissionDenied
    return qs


def can_edit(section, user, obj=None):
    if section == 'delegations':
        return is_manager(user)
    if section in ('locations', 'location-types'):
        return permitted(user, Capability.EDIT_STORAGE, location=obj if section == 'locations' else None)
    return permitted(user, Capability.EDIT_CATALOG, category=obj.category if section == 'articles' and obj else None)


def add_validation(form, error):
    if isinstance(error, IntegrityError):
        form.add_error(None, _('Un enregistrement avec cette identité existe déjà.'))
    else:
        for message in error.messages:
            form.add_error(None, message)


@login_required
@require_GET
def index(request):
    if not has_access(request.user):
        raise PermissionDenied
    cards = []
    for section, config in SECTIONS.items():
        title = config[2]
        if not is_manager(request.user) and section in ('articles', 'categories') and not grants(request.user, Capability.VIEW_CATALOG).exists():
            continue
        if not is_manager(request.user) and section == 'locations' and not grants(request.user, Capability.VIEW_STORAGE).exists():
            continue
        try:
            qs = queryset_for(section, request.user)
        except PermissionDenied:
            continue
        cards.append({'section': section, 'title': title, 'count': qs.count()})
    from .services.work import work_scope
    from .services.cdc import dossier_scope
    from .services.consumption import run_scope
    from .models import InventoryCampaign, StockContainer
    from .permissions import operational_scope
    from .services.procurement import plan_scope
    modules = [
        {'route':'erp:procurement-list','title':_('Prévisions et approvisionnement'),'count':plan_scope(request.user).count(),'detail':_('Besoins, plans annuels, CDC et réceptions')},
        {'route': 'erp:planning', 'title': _('Planning & activités'), 'count': work_scope(request.user).exclude(status__in=['APPROVED', 'CANCELLED']).count(), 'detail': _('Planifier, affecter, vérifier et valider')},
        {'route': 'erp:run-list', 'title': _('Séries analytiques'), 'count': run_scope(request.user).exclude(status__in=['COMPLETED', 'CANCELLED']).count(), 'detail': _('Besoins, lots réservés et consommations réelles')},
        {'route': 'erp:work-list', 'title': _('Tâches et délégations'), 'count': work_scope(request.user).exclude(status__in=['APPROVED', 'CANCELLED']).count(), 'detail': _('Responsabilités, échéances et comptes rendus')},
        {'route': 'erp:cdc-list', 'title': _('Cahiers des charges'), 'count': dossier_scope(request.user).count(), 'detail': _('Dossiers institutionnels et préparation déléguée')},
        {'route': 'erp:inventory-list', 'title': _('Inventaires physiques'), 'count': InventoryCampaign.objects.filter(work__in=work_scope(request.user)).count(), 'detail': _('Comptages, recomptages et ajustements validés')},
    ]
    if is_manager(request.user) or grants(request.user, Capability.VIEW_BIOBANK).exists():
        from .services.biobank import biobank_scope
        modules.insert(0, {'route': 'erp:sample-list', 'title': _('Échantillons et stockage froid'), 'count': biobank_scope(request.user).count(), 'detail': _('Aliquots, positions et chaîne de possession')})
    if is_manager(request.user) or grants(request.user, Capability.VIEW_STOCK).exists():
        modules.insert(0, {'route': 'erp:stock-list', 'title': _('Stocks et réceptions'), 'count': operational_scope(StockContainer.objects.all(), request.user).count(), 'detail': _('Lots, contenants, disponibilités et mouvements')})
    if is_manager(request.user):
        modules.insert(0, {
            'route': 'erp:inventory-source',
            'title': _('Inventaire PLAGENOR 2026'),
            'count': InventorySourceRecord.objects.count(),
            'detail': _('Source réelle, rapprochements et lignes à vérifier'),
        })
    return render(request, 'erp/index.html', {'cards': cards, 'modules': modules, 'manager': is_manager(request.user)})


@login_required
@require_GET
def record_list(request, section):
    _, _, title, _ = section_config(section)
    qs = queryset_for(section, request.user)
    search = request.GET.get('q', '').strip()[:200]
    if search and section != 'delegations':
        condition = Q(code__icontains=search) | Q(name__icontains=search) | Q(name_en__icontains=search) | Q(name_ar__icontains=search)
        if section == 'articles':
            condition |= Q(manufacturer_reference__icontains=search) | Q(catalog_reference__icontains=search) | Q(cas__icontains=search)
        qs = qs.filter(condition)
    state = request.GET.get('state', 'active')
    if state in ('active', 'inactive'):
        qs = qs.filter(active=state == 'active')
    page = Paginator(qs, 30).get_page(request.GET.get('page'))
    rows = [{'obj': obj, 'editable': can_edit(section, request.user, obj)} for obj in page]
    creatable = can_edit(section, request.user)
    if not creatable and section in ('articles', 'locations'):
        capability = Capability.EDIT_CATALOG if section == 'articles' else Capability.EDIT_STORAGE
        creatable = grants(request.user, capability).exists()
    return render(request, 'erp/list.html', {'section': section, 'title': title, 'rows': rows,
                  'page': page, 'q': search, 'state': state, 'creatable': creatable})


@login_required
@require_http_methods(['GET', 'POST'])
def record_edit(request, section, pk=None):
    model, form_class, title, service = section_config(section)
    qs = queryset_for(section, request.user)
    obj = get_object_or_404(qs, pk=pk) if pk else model()
    allowed = can_edit(section, request.user, obj if pk else None)
    if not pk and section in ('articles', 'locations') and not allowed:
        capability = Capability.EDIT_CATALOG if section == 'articles' else Capability.EDIT_STORAGE
        allowed = grants(request.user, capability).exists()
    if not allowed:
        raise PermissionDenied
    initial = {}
    if section == 'locations' and not pk and request.GET.get('parent'):
        try:
            parent_id = uuid.UUID(request.GET['parent'])
        except ValueError:
            raise Http404
        parent = get_object_or_404(storage_scope(Location.objects.all(), request.user, Capability.EDIT_STORAGE), pk=parent_id)
        initial['parent'] = parent.pk
    form = form_class(request.POST or None, instance=obj, user=request.user, initial=initial)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        try:
            service(user=request.user, values=values, pk=pk, expected=expected)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            messages.success(request, _('Enregistrement sauvegardé.'))
            return redirect('erp:list', section=section)
    return render(request, 'erp/form.html', {'form': form, 'title': title, 'section': section},
                  status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def article_detail(request, pk):
    obj = get_object_or_404(queryset_for('articles', request.user), pk=pk)
    costs = permitted(request.user, Capability.VIEW_COST, category=obj.category)
    fields = [(field.verbose_name, getattr(obj, f'get_{field.name}_display')() if field.choices else getattr(obj, field.name)) for field in obj._meta.concrete_fields
              if field.editable and not field.primary_key and field.name not in ('name_en', 'name_ar')]
    return render(request, 'erp/article.html', {'article': obj, 'fields': fields,
        'conversions': obj.conversions.select_related('unit').order_by('unit__code'),
        'prices': obj.prices.select_related('supplier', 'unit')[:50] if costs else [], 'costs': costs,
        'editable': permitted(request.user, Capability.EDIT_CATALOG, category=obj.category),
        'price_editable': permitted(request.user, Capability.EDIT_COST, category=obj.category)})


@login_required
@require_http_methods(['GET', 'POST'])
def conversion_edit(request, article_id, pk=None):
    article = get_object_or_404(queryset_for('articles', request.user), pk=article_id)
    require(request.user, Capability.EDIT_CATALOG, category=article.category)
    obj = get_object_or_404(ArticleConversion, pk=pk, article=article) if pk else ArticleConversion(article=article)
    form = forms.ConversionForm(request.POST or None, instance=obj, user=request.user)
    if request.method == 'POST' and form.is_valid():
        values = dict(form.cleaned_data)
        expected = values.pop('expected_version')
        try:
            save_conversion(request.user, article, values, pk=pk, expected=expected)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:article', pk=article.pk)
    return render(request, 'erp/form.html', {'form': form, 'title': _('Conversion d’unité'), 'section': 'articles'},
                  status=400 if request.method == 'POST' else 200)


@login_required
@require_http_methods(['GET', 'POST'])
def price_create(request, pk):
    article = get_object_or_404(queryset_for('articles', request.user), pk=pk)
    require(request.user, Capability.EDIT_COST, category=article.category)
    form = forms.PriceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            record_price(request.user, article, form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            add_validation(form, error)
        else:
            return redirect('erp:article', pk=article.pk)
    return render(request, 'erp/form.html', {'form': form, 'title': _('Historique des prix'), 'section': 'articles'},
                  status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
def audit_trail(request):
    require_manager(request.user)
    events = AuditEvent.objects.select_related('actor').order_by('-id')
    page = Paginator(events, 30).get_page(request.GET.get('page'))
    return render(request, 'erp/audit.html', {'page': page})


@login_required
@require_GET
def inventory_source(request):
    require_manager(request.user)
    qs = InventorySourceRecord.objects.all()
    domain = request.GET.get('domain', '').strip()
    status = request.GET.get('status', '').strip()
    query = request.GET.get('q', '').strip()[:200]
    if domain in InventorySourceRecord.Domain.values:
        qs = qs.filter(domain=domain)
    else:
        domain = ''
    if status in InventorySourceRecord.Status.values:
        qs = qs.filter(status=status)
    else:
        status = ''
    if query:
        qs = qs.filter(
            Q(source_file__icontains=query) | Q(source_sheet__icontains=query)
            | Q(identity_key__icontains=query) | Q(notes__icontains=query)
            | Q(normalized_data__product__icontains=query)
            | Q(normalized_data__name__icontains=query)
            | Q(normalized_data__equipment_name__icontains=query)
            | Q(normalized_data__model__icontains=query)
            | Q(normalized_data__serial_number__icontains=query)
        )
    counts = {
        'total': InventorySourceRecord.objects.count(),
        'review': InventorySourceRecord.objects.filter(status=InventorySourceRecord.Status.NEEDS_REVIEW).count(),
        'equipment': InventorySourceRecord.objects.filter(domain=InventorySourceRecord.Domain.EQUIPMENT).count(),
        'stock': InventorySourceRecord.objects.exclude(domain=InventorySourceRecord.Domain.EQUIPMENT).count(),
    }
    preview = summarize_inventory()
    preview['workbook_total'] = sum(preview['raw_workbook_rows'].values())
    preview['source_total'] = preview['workbook_total'] + preview['room_list_rows']
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    return render(request, 'erp/inventory_source.html', {
        'page': page, 'counts': counts, 'domain': domain, 'status': status, 'q': query,
        'domains': InventorySourceRecord.Domain.choices, 'statuses': InventorySourceRecord.Status.choices,
        'preview': preview,
    })


@login_required
@require_POST
def inventory_source_apply(request):
    require_manager(request.user)
    if request.POST.get('confirm') != 'PLAGENOR-2026':
        messages.error(request, _('Confirmation de reprise invalide.'))
        return redirect('erp:inventory-source')
    snapshot_date = request.POST.get('snapshot_date', '').strip()
    if not snapshot_date:
        messages.error(request, _('La date du constat d’inventaire est obligatoire.'))
        return redirect('erp:inventory-source')
    try:
        stats = apply_inventory(request.user, snapshot_date)
    except (ValidationError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect('erp:inventory-source')
    imported = stats.get('stock_rows_imported', 0)
    equipment = stats.get('equipment_created', 0) + stats.get('equipment_existing', 0)
    review = stats.get('needs_review', 0) + stats.get('room_rows_review', 0)
    messages.success(
        request,
        _(
            'Reprise PLAGENOR 2026 appliquée de manière idempotente : '
            '%(equipment)s équipement(s), %(stock)s ligne(s) de stock initial, '
            '%(review)s ligne(s) conservée(s) pour vérification.'
        ) % {'equipment': equipment, 'stock': imported, 'review': review},
    )
    return redirect('erp:inventory-source')


@login_required
@require_GET
def location_detail(request, pk):
    obj = get_object_or_404(queryset_for('locations', request.user), pk=pk)
    ancestors = LocationClosure.objects.filter(descendant=obj, depth__gt=0).select_related('ancestor').order_by('-depth')
    children = storage_scope(Location.objects.filter(parent=obj), request.user).select_related('kind')
    editable = permitted(request.user, Capability.EDIT_STORAGE, location=obj)
    return render(request, 'erp/location.html', {'location': obj, 'ancestors': ancestors,
                                               'children': children, 'editable': editable})
