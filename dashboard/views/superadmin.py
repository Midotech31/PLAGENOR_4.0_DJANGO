import logging
from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back, paginate_queryset
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.utils.translation import gettext as _
from django.conf import settings
from dashboard.decorators import superadmin_required

logger = logging.getLogger('plagenor')

from accounts.models import User, MemberProfile, Technique
from core.models import Service, Request, PlatformContent, Invoice, PaymentMethod, ServiceFormField, PaymentSettings
from core.financial import get_budget_dashboard
from core.productivity import get_all_productivity_stats
from core.registry import get_service_def


@superadmin_required
def index(request):
    from django.core.paginator import Paginator

    # Consolidate count queries into single aggregated queries
    from django.db.models import Sum, Case, When, IntegerField
    
    user_stats = User.objects.aggregate(
        total_users=Count('id'),
        total_members=Count(
            Case(When(member_profile__isnull=False, then=1), output_field=IntegerField())
        )
    )
    total_users = user_stats['total_users']
    total_members = user_stats['total_members']
    
    request_stats = Request.objects.aggregate(
        total_requests=Count('id', filter=Q(archived=False)),
        completed_requests=Count('id', filter=Q(status='COMPLETED')),
        ibtikar_count=Count('id', filter=Q(channel='IBTIKAR', archived=False)),
        genoclab_count=Count('id', filter=Q(channel='GENOCLAB', archived=False))
    )
    total_requests = request_stats['total_requests']
    completed_requests = request_stats['completed_requests']
    ibtikar_count = request_stats['ibtikar_count']
    genoclab_count = request_stats['genoclab_count']
    
    total_services = Service.objects.filter(active=True).count()
    total_techniques = Technique.objects.filter(active=True).count()

    # Users tab: search + pagination
    user_search = request.GET.get('user_q', '')
    user_role_filter = request.GET.get('user_role', '')
    users_qs = User.objects.order_by('-date_joined')
    if user_search:
        users_qs = users_qs.filter(
            Q(first_name__icontains=user_search) |
            Q(last_name__icontains=user_search) |
            Q(username__icontains=user_search) |
            Q(email__icontains=user_search)
        )
    if user_role_filter:
        users_qs = users_qs.filter(role=user_role_filter)
    users_paginator = Paginator(users_qs, 25)
    users_page = users_paginator.get_page(request.GET.get('users_page', 1))

    # Members tab: pagination
    members_qs = MemberProfile.objects.select_related('user').order_by('-user__date_joined')
    members_paginator = Paginator(members_qs, 25)
    members_page = members_paginator.get_page(request.GET.get('members_page', 1))

    services = Service.objects.order_by('code')
    techniques = Technique.objects.order_by('name')
    platform_content = PlatformContent.objects.all()

    recent_requests = Request.objects.filter(archived=False).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')[:5]
    recent_users = User.objects.order_by('-date_joined')[:5]

    status_dist = (
        Request.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Business logic from engines
    budget_dashboard = get_budget_dashboard()
    productivity_stats = get_all_productivity_stats()

    # Requests tab with filters + pagination
    sa_channel = request.GET.get('sa_channel', '')
    sa_status = request.GET.get('sa_status', '')
    sa_search = request.GET.get('sa_q', '')
    all_requests_qs = Request.objects.select_related('service', 'requester', 'assigned_to__user')
    if sa_channel:
        all_requests_qs = all_requests_qs.filter(channel=sa_channel)
    if sa_status:
        all_requests_qs = all_requests_qs.filter(status=sa_status)
    if sa_search:
        all_requests_qs = all_requests_qs.filter(Q(display_id__icontains=sa_search) | Q(title__icontains=sa_search))
    all_requests_qs = all_requests_qs.order_by('-created_at')
    requests_paginator = Paginator(all_requests_qs, 25)
    requests_page = requests_paginator.get_page(request.GET.get('requests_page', 1))

    # Payments tab: pagination
    all_invoices_qs = Invoice.objects.select_related('request', 'client').order_by('-created_at')
    invoices_paginator = Paginator(all_invoices_qs, 25)
    invoices_page = invoices_paginator.get_page(request.GET.get('invoices_page', 1))
    payment_methods = PaymentMethod.objects.all()

    # Documents tab - paginated
    reports_qs = Request.objects.exclude(report_file='').exclude(report_file__isnull=True).select_related('service', 'requester', 'assigned_to__user').order_by('-updated_at')
    reports_paginator, requests_with_reports, _reports = paginate_queryset(reports_qs, request, per_page=25, page_param='reports_page')

    # Forms tab
    all_form_fields = ServiceFormField.objects.select_related('service').order_by('service__code', 'sort_order')
    try:
        from core.registry import load_service_registry
        yaml_registry = load_service_registry()
    except Exception as e:
        logger.warning(f"Failed to load service registry: {e}")
        yaml_registry = {}

    # KPI - average rating
    avg_rating = Request.objects.filter(service_rating__isnull=False).aggregate(avg=Avg('service_rating'))['avg'] or 0

    # Request CSV export
    if request.GET.get('export') == 'requests_csv':
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="plagenor_requests.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Titre', 'Canal', 'Statut', 'Service', 'Demandeur', 'Assigné à', 'Date'])
        for r in all_requests_qs[:2000]:
            writer.writerow([
                r.display_id, r.title, r.channel, r.status,
                r.service.name if r.service else '',
                r.requester.get_full_name() if r.requester else r.guest_name or '',
                r.assigned_to.user.get_full_name() if r.assigned_to else '',
                r.created_at.strftime('%d/%m/%Y'),
            ])
        return response

    context = {
        'total_users': total_users,
        'total_members': total_members,
        'total_requests': total_requests,
        'completed_requests': completed_requests,
        'ibtikar_count': ibtikar_count,
        'genoclab_count': genoclab_count,
        'total_services': total_services,
        'total_techniques': total_techniques,
        # Users tab
        'users': users_page,
        'users_page': users_page,
        'user_search': user_search,
        'user_role_filter': user_role_filter,
        # Members tab
        'members': members_page,
        'members_page': members_page,
        # Services/Techniques
        'services': services,
        'techniques': techniques,
        'platform_content': platform_content,
        'status_dist': status_dist,
        'recent_requests': recent_requests,
        'recent_users': recent_users,
        'budget_dashboard': budget_dashboard,
        'productivity_stats': productivity_stats,
        'now': timezone.now(),
        # Requests tab
        'all_requests': requests_page,
        'requests_page': requests_page,
        'sa_channel': sa_channel,
        'sa_status': sa_status,
        'sa_search': sa_search,
        'status_choices': Request.STATUS_CHOICES,
        'role_choices': User.ROLE_CHOICES,
        # Payments tab
        'all_invoices': invoices_page,
        'invoices_page': invoices_page,
        'payment_methods': payment_methods,
        # Documents tab
        'requests_with_reports': requests_with_reports,
        'template_types': [
            ('ibtikar_form_template', _('Formulaire IBTIKAR')),
            ('platform_note_template', _('Note de plateforme')),
            ('reception_form_template', _('Fiche de réception')),
            ('quote_template', _('Devis')),
        ],
        # Forms tab
        'all_form_fields': all_form_fields,
        'yaml_registry': yaml_registry,
        # KPI
        'avg_rating': avg_rating,
        # Profile stats
        'profile_stats': {
            'total_users': total_users,
            'total_requests': total_requests,
            'total_services': total_services,
            'total_techniques': total_techniques,
        },
    }
    return render(request, 'dashboard/superadmin/index.html', context)


@superadmin_required
def user_toggle_active(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    user = get_object_or_404(User, pk=pk)
    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])
    status = 'activé' if user.is_active else 'désactivé'
    messages.success(request, f"Utilisateur {user.get_full_name()} {status}.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def member_toggle_available(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    profile = get_object_or_404(MemberProfile, pk=pk)
    profile.available = not profile.available
    profile.save(update_fields=['available'])
    status = 'disponible' if profile.available else 'indisponible'
    messages.success(request, f"Analyste {profile.user.get_full_name()} marqué {status}.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def member_assign_techniques(request, pk):
    """Assign techniques to a member profile."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    profile = get_object_or_404(MemberProfile, pk=pk)
    technique_ids = request.POST.getlist('techniques')
    profile.techniques.set(Technique.objects.filter(pk__in=technique_ids, active=True))
    messages.success(request, f"Techniques mises à jour pour {profile.user.get_full_name()}.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def service_create(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    Service.objects.create(
        code=request.POST.get('code', ''),
        name=request.POST.get('name', ''),
        description=request.POST.get('description', ''),
        channel_availability=request.POST.get('channel_availability', 'BOTH'),
        ibtikar_price=request.POST.get('ibtikar_price', 0),
        genoclab_price=request.POST.get('genoclab_price', 0),
        turnaround_days=request.POST.get('turnaround_days', 7),
        image=request.FILES.get('image'),
    )
    messages.success(request, "Service créé avec succès.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def service_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service = get_object_or_404(Service, pk=pk)
    
    # Check for active requests using this service
    active_requests_count = Request.objects.filter(service=service, archived=False).exclude(
        status__in=['COMPLETED', 'CLOSED', 'REJECTED', 'ARCHIVED']
    ).count()
    
    if active_requests_count > 0:
        messages.error(
            request, 
            f"Impossible de désactiver le service « {service.name} » — {active_requests_count} demande(s) active(s) y sont associées."
        )
        return redirect_back(request, 'dashboard:superadmin')
    
    service.active = False
    service.save(update_fields=['active'])
    messages.success(request, f"Service {service.name} désactivé.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def technique_create(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    Technique.objects.create(
        name=request.POST.get('name', ''),
        category=request.POST.get('category', ''),
    )
    messages.success(request, "Technique ajoutée.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def technique_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    technique = get_object_or_404(Technique, pk=pk)
    technique.active = False
    technique.save(update_fields=['active'])
    messages.success(request, f"Technique {technique.name} désactivée.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def technique_edit(request, pk):
    """Edit technique name and category."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    technique = get_object_or_404(Technique, pk=pk)
    name = request.POST.get('name', '').strip()
    category = request.POST.get('category', '').strip()
    if name:
        technique.name = name
        technique.category = category
        technique.save(update_fields=['name', 'category'])
        messages.success(request, f"Technique '{name}' mise à jour.")
    else:
        messages.error(request, "Le nom est requis.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def technique_reactivate(request, pk):
    """Reactivate a soft-deleted technique."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    technique = get_object_or_404(Technique, pk=pk)
    technique.active = True
    technique.save(update_fields=['active'])
    messages.success(request, f"Technique {technique.name} réactivée.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def service_reactivate(request, pk):
    """Reactivate a deactivated service."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    service = get_object_or_404(Service, pk=pk)
    service.active = True
    service.save(update_fields=['active'])
    messages.success(request, f"Service {service.name} réactivé.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def content_delete(request, pk):
    """Delete a platform content entry."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    content = get_object_or_404(PlatformContent, pk=pk)
    key = content.key
    content.delete()
    messages.success(request, f"Contenu '{key}' supprimé.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def content_update(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    key = request.POST.get('key', '')
    value = request.POST.get('value', '')
    PlatformContent.objects.update_or_create(
        key=key,
        defaults={'value': value, 'updated_by': request.user},
    )
    messages.success(request, f"Contenu '{key}' mis à jour.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def audit_log(request):
    """Paginated audit log viewer for SUPER_ADMIN."""
    from core.models import RequestHistory
    from django.core.paginator import Paginator

    qs = RequestHistory.objects.select_related('request', 'actor').order_by('-created_at')

    # Filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')

    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if action_filter:
        qs = qs.filter(to_status__icontains=action_filter)
    if user_filter:
        qs = qs.filter(
            Q(actor__first_name__icontains=user_filter) |
            Q(actor__last_name__icontains=user_filter) |
            Q(actor__username__icontains=user_filter)
        )

    paginator = Paginator(qs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'date_from': date_from,
        'date_to': date_to,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/superadmin/audit_log.html', context)


@superadmin_required
def service_edit(request, pk):
    """Edit a service and its custom form fields."""
    from core.models import ServiceFormField
    service = get_object_or_404(Service, pk=pk)
    form_fields = service.form_fields.all()

    if request.method == 'POST':
        service.name = request.POST.get('name', service.name)
        service.description = request.POST.get('description', service.description)
        service.channel_availability = request.POST.get('channel_availability', service.channel_availability)
        
        # Handle decimal fields with proper conversion
        ibtikar_price = request.POST.get('ibtikar_price', '').strip().replace('\xa0', '').replace(',', '.')
        if ibtikar_price:
            try:
                service.ibtikar_price = Decimal(ibtikar_price)
            except (ValueError, InvalidOperation):
                pass  # Keep existing value if invalid
        
        genoclab_price = request.POST.get('genoclab_price', '').strip().replace('\xa0', '').replace(',', '.')
        if genoclab_price:
            try:
                service.genoclab_price = Decimal(genoclab_price)
            except (ValueError, InvalidOperation):
                pass  # Keep existing value if invalid
        
        turnaround_days = request.POST.get('turnaround_days', '').strip()
        if turnaround_days:
            try:
                service.turnaround_days = int(turnaround_days)
            except ValueError:
                pass  # Keep existing value if invalid

        # Handle per-channel turnaround times (Part M)
        turnaround_ibtikar = request.POST.get('turnaround_ibtikar', '').strip()
        if turnaround_ibtikar:
            try:
                service.turnaround_ibtikar = int(turnaround_ibtikar)
            except ValueError:
                pass

        turnaround_genoclab = request.POST.get('turnaround_genoclab', '').strip()
        if turnaround_genoclab:
            try:
                service.turnaround_genoclab = int(turnaround_genoclab)
            except ValueError:
                pass

        service.turnaround_unit = request.POST.get('turnaround_unit', service.turnaround_unit)

        # Handle citation clause fields (Part K3)
        service.citation_clause_fr = request.POST.get('citation_clause_fr', service.citation_clause_fr)
        service.citation_clause_en = request.POST.get('citation_clause_en', service.citation_clause_en)

        if 'image' in request.FILES:
            service.image = request.FILES['image']
        service.save()

        messages.success(request, f"Service {service.name} mis à jour.")
        return redirect_back(request, 'dashboard:superadmin')

    return render(request, 'dashboard/superadmin/service_edit.html', {
        'service': service,
        'form_fields': form_fields,
    })


@superadmin_required
def service_fields_reset(request, pk):
    """Reset/restore form fields for a service to default values."""
    from core.models import ServiceFormField
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        # Delete existing form fields
        service.form_fields.all().delete()
        
        # Restore based on service code
        field_defs = get_default_service_fields(service.code)
        
        for field_data in field_defs:
            ServiceFormField.objects.create(
                service=service,
                field_category=field_data.get('field_category', 'sample_table'),
                name=field_data['name'],
                label=field_data.get('label', field_data['name']),
                label_fr=field_data.get('label_fr', field_data.get('label', field_data['name'])),
                label_en=field_data.get('label_en', field_data.get('label', field_data['name'])),
                field_type=field_data.get('field_type', 'text'),
                options=field_data.get('options', []),
                choices_json=field_data.get('options', []),
                order=field_data.get('order', 0),
                sort_order=field_data.get('order', 0),
                required=field_data.get('required', False),
                help_text=field_data.get('help_text', ''),
                help_text_fr=field_data.get('help_text_fr', ''),
                help_text_en=field_data.get('help_text_en', ''),
            )
        
        messages.success(request, f"Champs du service {service.name} restaurés.")
        return redirect('dashboard:superadmin_service_edit', pk=pk)
    
    return render(request, 'dashboard/superadmin/service_fields_reset.html', {
        'service': service,
    })


def get_default_service_fields(service_code):
    """Return default form field definitions for each service."""
    fields_map = {
        'EGTP-IMT': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'organism', 'label': 'Type microorganisme', 'label_fr': 'Type de microorganisme (Bactérie, levure, moisissure)', 'label_en': 'Microorganism Type', 'order': 2},
                {'name': 'isolation', 'label': 'Source isolement', 'label_fr': "Source d'isolement (environnementale, alimentaire, clinique, etc.)", 'label_en': 'Isolation Source', 'order': 3},
                {'name': 'isolation_date', 'label': 'Date isolement', 'label_fr': "Date d'isolement", 'label_en': 'Isolation Date', 'order': 4},
                {'name': 'culture_medium', 'label': 'Milieu culture', 'label_fr': 'Milieu de culture approprié', 'label_en': 'Culture Medium', 'order': 5},
                {'name': 'culture_conditions', 'label': 'Conditions culture', 'label_fr': 'Conditions de culture (Température, type respiratoire, durée incubation)', 'label_en': 'Culture Conditions', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {'name': 'fresh_cultures', 'label': 'Cultures fraîches', 'label_fr': 'Fourniture de cultures fraîches', 'label_en': 'Fresh Cultures Supplied', 'field_type': 'dropdown', 'options': ['Oui', 'Non'], 'order': 0},
                {'name': 'maldi_target', 'label': 'Cible MALDI', 'label_fr': 'Type de cible MALDI-TOF', 'label_en': 'MALDI-TOF Target Type', 'field_type': 'dropdown', 'options': ['Usage unique obligatoire pour pathogènes'], 'order': 1},
                {'name': 'analysis_mode', 'label': 'Mode analyse', 'label_fr': "Mode d'analyse", 'label_en': 'Analysis Mode', 'field_type': 'dropdown', 'options': ['Simple', 'Duplicata', 'Triplicata'], 'order': 2},
            ],
        },
        'EGTP-CAN': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'origin', 'label': 'Origine', 'label_fr': 'Origine des acides nucleiques', 'label_en': 'Nucleic Acid Origin', 'order': 2},
                {'name': 'nucleic_type', 'label': 'Type', 'label_fr': "Type d'acides nucleiques (plasmidique, chromosomique)", 'label_en': 'Nucleic Acid Type', 'order': 3},
                {'name': 'extraction', 'label': 'Méthode extraction', 'label_fr': "Méthode d'extraction utilisée", 'label_en': 'Extraction Method Used', 'order': 4},
                {'name': 'extraction_date', 'label': 'Date extraction', 'label_fr': "Date de l'extraction", 'label_en': 'Extraction Date', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {'name': 'qc_techniques', 'label': 'Techniques QC', 'label_fr': 'Techniques de contrôle qualité souhaitées', 'label_en': 'Requested QC Techniques', 'field_type': 'dropdown', 'options': [], 'order': 0},
                {'name': 'gel_percentage', 'label': '% agarose', 'label_fr': "Pourcentage de gel d'agarose souhaité (si demandé)", 'label_en': 'Desired Agarose Gel Percentage', 'field_type': 'text', 'order': 1},
                {'name': 'size_marker', 'label': 'Marqueur', 'label_fr': "Marqueur de taille pour l'électrophorèse", 'label_en': 'Size Marker for Electrophoresis', 'field_type': 'dropdown', 'options': [], 'order': 2},
            ],
        },
        'EGTP-Seq02': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': "Type d'échantillon", 'label_fr': "Type d'échantillon (Sang, bactérie, tissu animal…)", 'label_en': 'Sample Type (Blood, bacteria, animal tissue...)', 'order': 2},
                {'name': 'date', 'label': 'Date de prélèvement', 'label_fr': 'Date de prélèvement', 'label_en': 'Sampling Date', 'order': 3},
                {'name': 'volume', 'label': 'Volume/Quantité', 'label_fr': 'Volume (µl) / Quantité (g)', 'label_en': 'Volume (µl) / Quantity (g)', 'order': 4},
                {'name': 'storage', 'label': 'Conditions de stockage', 'label_fr': 'Condition de stockage', 'label_en': 'Storage Conditions', 'order': 5},
                {'name': 'state', 'label': "État de l'échantillon", 'label_fr': "État de l'échantillon", 'label_en': 'Sample State', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {'name': 'extraction_method', 'label': 'Méthode extraction', 'label_fr': "Méthode d'extraction souhaitée", 'label_en': 'Requested Extraction Method', 'field_type': 'dropdown', 'options': ['Méthode classique', 'Kit commercial'], 'order': 0},
                {'name': 'pcr_kit', 'label': 'Kit PCR', 'label_fr': 'Type de kit de PCR', 'label_en': 'PCR Kit Type', 'field_type': 'dropdown', 'options': [], 'order': 1},
                {'name': 'qc_techniques', 'label': 'Techniques QC', 'label_fr': 'Techniques de contrôle qualité souhaitées', 'label_en': 'Requested QC Techniques', 'field_type': 'dropdown', 'options': [], 'order': 2},
                {'name': 'size_marker', 'label': 'Marqueur taille', 'label_fr': 'Marqueur de taille pour électrophorèse', 'label_en': 'Size Marker for Electrophoresis', 'field_type': 'dropdown', 'options': [], 'order': 3},
                {'name': 'reading_direction', 'label': 'Sens lecture', 'label_fr': 'Sens de lecture souhaité', 'label_en': 'Requested Reading Direction', 'field_type': 'checkbox', 'options': ['Forward', 'Reverse', 'Les deux sens'], 'order': 4},
            ],
        },
        'EGTP-SeqS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'gene', 'label': 'Nom du gène', 'label_fr': 'Nom du gène', 'label_en': 'Gene Name', 'order': 2},
                {'name': 'gene_size', 'label': 'Taille gène (pb)', 'label_fr': 'Taille du gène (pb)', 'label_en': 'Gene Size (bp)', 'order': 3},
                {'name': 'origin', 'label': 'Source', 'label_fr': "Source/origine de l'échantillon", 'label_en': 'Sample Origin', 'order': 4},
                {'name': 'primers', 'label': 'Séquences amorces', 'label_fr': "Séquences des amorces utilisées (5'→3')", 'label_en': "Primer Sequences (5'→3')", 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {'name': 'sample_type', 'label': 'Type échantillon', 'label_fr': "Type d'échantillon soumis", 'label_en': 'Submitted Sample Type', 'field_type': 'checkbox', 'options': ["Produit de réaction BigDye", "Produit de PCR purifié", "Produit de PCR non purifié", 'Autre'], 'order': 0},
                {'name': 'supplies', 'label': 'Consommables', 'label_fr': 'Consommables fournis par le demandeur', 'label_en': 'Supplies Provided by Requester', 'field_type': 'text', 'order': 1},
                {'name': 'reading_direction', 'label': 'Sens lecture', 'label_fr': 'Sens de lecture souhaité', 'label_en': 'Requested Reading Direction', 'field_type': 'checkbox', 'options': ['Forward', 'Reverse', 'Les deux sens'], 'order': 2},
                {'name': 'amplification_kit', 'label': 'Kit amplification', 'label_fr': "Kit d'amplification utilisé", 'label_en': 'Amplification Kit Used', 'field_type': 'text', 'order': 3},
                {'name': 'qc_results', 'label': 'Résultats QC', 'label_fr': 'Résultats du contrôle de qualité des PCR', 'label_en': 'PCR QC Results', 'field_type': 'textarea', 'order': 4},
            ],
        },
        'EGTP-GDE': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': 'Type échantillon', 'label_fr': "Type d'échantillon (Sang, bactérie, tissu animal…)", 'label_en': 'Sample Type', 'order': 2},
                {'name': 'date', 'label': 'Date de prélèvement', 'label_fr': 'Date de prélèvement', 'label_en': 'Sampling Date', 'order': 3},
                {'name': 'volume', 'label': 'Volume/Quantité', 'label_fr': 'Volume (µl) / Quantité (g)', 'label_en': 'Volume/Quantity', 'order': 4},
                {'name': 'storage', 'label': 'Conditions stockage', 'label_fr': 'Condition de stockage', 'label_en': 'Storage Conditions', 'order': 5},
                {'name': 'state', 'label': "État échantillon", 'label_fr': "État de l'échantillon", 'label_en': 'Sample State', 'order': 6},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 7},
            ],
            'additional_info': [
                {'name': 'extraction_method', 'label': 'Méthode extraction', 'label_fr': "Méthode d'extraction souhaitée", 'label_en': 'Requested Extraction Method', 'field_type': 'dropdown', 'options': ['Méthode classique', 'Kit commercial'], 'order': 0},
                {'name': 'qc_techniques', 'label': 'Techniques QC', 'label_fr': 'Techniques de contrôle qualité souhaitées', 'label_en': 'Requested QC Techniques', 'field_type': 'dropdown', 'options': [], 'order': 1},
                {'name': 'desired_volume', 'label': 'Volume souhaité', 'label_fr': "Volume d'ADN souhaité récupérer après extraction", 'label_en': 'Desired DNA Volume After Extraction', 'field_type': 'text', 'order': 2},
            ],
        },
        'EGTP-PCR': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'dna_origin', 'label': 'Origine ADN', 'label_fr': "Origine de l'ADN", 'label_en': 'DNA Origin', 'order': 2},
                {'name': 'dna_type', 'label': 'Type ADN', 'label_fr': "Type de l'ADN (plasmidique, chromosomique…)", 'label_en': 'DNA Type', 'order': 3},
                {'name': 'extraction', 'label': 'Méthode extraction', 'label_fr': "Méthode de l'extraction d'ADN", 'label_en': 'DNA Extraction Method', 'order': 4},
                {'name': 'target_gene', 'label': 'Gène cible', 'label_fr': 'Gène cible', 'label_en': 'Target Gene', 'order': 5},
                {'name': 'amplicon_size', 'label': 'Taille amplicon', 'label_fr': "Taille de l'amplicon", 'label_en': 'Amplicon Size', 'order': 6},
                {'name': 'primers', 'label': 'Séquences amorces', 'label_fr': "Séquences des amorces utilisées (5'→3')", 'label_en': 'Primer Sequences', 'order': 7},
                {'name': 'tm', 'label': 'Tm (°C)', 'label_fr': 'Tm (°C)', 'label_en': 'Tm (°C)', 'order': 8},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 9},
            ],
            'additional_info': [
                {'name': 'pcr_kit', 'label': 'Kit PCR', 'label_fr': 'Type de kit PCR', 'label_en': 'PCR Kit Type', 'field_type': 'dropdown', 'options': [], 'order': 0},
                {'name': 'qc_techniques', 'label': 'Techniques QC', 'label_fr': 'Techniques de contrôle qualité souhaitées', 'label_en': 'Requested QC Techniques', 'field_type': 'dropdown', 'options': [], 'order': 1},
                {'name': 'size_marker', 'label': 'Marqueur', 'label_fr': "Marqueur de taille pour l'électrophorèse", 'label_en': 'Size Marker for Electrophoresis', 'field_type': 'dropdown', 'options': [], 'order': 2},
                {'name': 'pcr_volume', 'label': 'Volume PCR', 'label_fr': 'Volume du produit de PCR à récupérer après amplification', 'label_en': 'PCR Product Volume to Recover', 'field_type': 'text', 'order': 3},
            ],
        },
        'EGTP-PS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'fr', 'label': 'F/R', 'label_fr': 'F/R', 'label_en': 'F/R', 'order': 1},
                {'name': 'name', 'label': 'Nom amorce', 'label_fr': "Nom de l'amorce", 'label_en': 'Primer Name', 'order': 2},
                {'name': 'size', 'label': 'Taille (pb)', 'label_fr': 'Taille (pb)', 'label_en': 'Size (bp)', 'order': 3},
                {'name': 'sequence', 'label': 'Séquence', 'label_fr': "Séquence nucléotidique (5'→3')", 'label_en': "Nucleotide Sequence (5'→3')", 'order': 4},
                {'name': 'gene', 'label': 'Gène cible', 'label_fr': 'Nom du Gène ciblé', 'label_en': 'Target Gene Name', 'order': 5},
                {'name': 'accession', 'label': 'N° accession', 'label_fr': "N° d'accession du Gène", 'label_en': 'Gene Accession No.', 'order': 6},
                {'name': 'gc', 'label': '% GC', 'label_fr': '% GC', 'label_en': '% GC', 'order': 7},
                {'name': 'tm', 'label': 'Tm (°C)', 'label_fr': 'Tm (°C)', 'label_en': 'Tm (°C)', 'order': 8},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 9},
            ],
            'additional_info': [
                {'name': 'physical_state', 'label': 'État physique', 'label_fr': 'État physique souhaité pour recevoir les amorces', 'label_en': 'Desired Physical State for Primers', 'field_type': 'dropdown', 'options': ["Lyophilisé", "Dissous dans l'eau", "Dissous dans TE"], 'order': 0},
                {'name': 'final_volume', 'label': 'Volume final', 'label_fr': 'Volume final à récupérer pour chaque amorce (µL)', 'label_en': 'Final Volume per Primer (µL)', 'field_type': 'text', 'order': 1},
                {'name': 'concentration', 'label': 'Concentration', 'label_fr': 'concentration souhaitée', 'label_en': 'Desired Concentration', 'field_type': 'text', 'order': 2},
            ],
        },
        'EGTP-Illumina-Microbial-WGS': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'organism', 'label': 'Type microorganisme', 'label_fr': 'Type de microorganisme (Bactérie, levure, moisissure)', 'label_en': 'Microorganism Type', 'order': 2},
                {'name': 'isolation', 'label': 'Source isolement', 'label_fr': "Source d'isolement (environnementale, alimentaire, clinique, etc.)", 'label_en': 'Isolation Source', 'order': 3},
                {'name': 'culture_medium', 'label': 'Milieu culture', 'label_fr': 'Milieu de culture approprié', 'label_en': 'Appropriate Culture Medium', 'order': 4},
                {'name': 'culture_conditions', 'label': 'Conditions culture', 'label_fr': 'Conditions de culture (Température, type respiratoire, durée incubation)', 'label_en': 'Culture Conditions', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [
                {'name': 'file_format', 'label': 'Format fichiers', 'label_fr': 'Format fichiers livrés', 'label_en': 'Delivered File Format', 'field_type': 'text', 'options': ['FASTQ'], 'order': 0},
                {'name': 'delivery_method', 'label': 'Livraison', 'label_fr': 'Support de livraison', 'label_en': 'Delivery Method', 'field_type': 'text', 'options': ['Téléchargement via plateforme sécurisée'], 'order': 1},
            ],
        },
        'EGTP-Lyoph': {
            'sample_table': [
                {'name': 'id', 'label': 'N°', 'label_fr': 'N°', 'label_en': 'No.', 'order': 0},
                {'name': 'code', 'label': 'Code', 'label_fr': 'Code', 'label_en': 'Code', 'order': 1},
                {'name': 'type', 'label': 'Type échantillon', 'label_fr': "Type de l'échantillon (Bactérie, plantes…)", 'label_en': 'Sample Type', 'order': 2},
                {'name': 'volume', 'label': 'Volume/Poids', 'label_fr': 'Volume/poids initial (ml/g)', 'label_en': 'Initial Volume/Weight', 'order': 3},
                {'name': 'dessiccation', 'label': 'Niveau dessiccation', 'label_fr': 'Niveau de dessiccation (primaire/secondaire)', 'label_en': 'Dessiccation Level', 'order': 4},
                {'name': 'storage', 'label': 'Stockage initial', 'label_fr': 'Conditions de stockage initiales', 'label_en': 'Initial Storage Conditions', 'order': 5},
                {'name': 'notes', 'label': 'Remarques', 'label_fr': 'Remarques particulières', 'label_en': 'Special Notes', 'order': 6},
            ],
            'additional_info': [],
        },
    }
    
    result = []
    service_fields = fields_map.get(service_code, {})
    for cat, fields in service_fields.items():
        for f in fields:
            f_copy = f.copy()
            f_copy['field_category'] = cat
            result.append(f_copy)
    return result

    return render(request, 'dashboard/superadmin/service_edit.html', {
        'service': service,
        'form_fields': form_fields,
    })


@superadmin_required
def backup_now(request):
    """Create a database backup and return as download."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    import shutil
    from datetime import datetime as dt
    from django.http import FileResponse
    from django.conf import settings as s

    db_path = s.BASE_DIR / 'data' / 'plagenor.db'
    backup_dir = s.BASE_DIR / 'data' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = dt.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f'plagenor_{timestamp}.db'
    shutil.copy2(str(db_path), str(backup_path))

    # Keep last 30 backups
    backups = sorted(backup_dir.glob('plagenor_*.db'), reverse=True)
    for old_backup in backups[30:]:
        old_backup.unlink()

    return FileResponse(
        open(str(backup_path), 'rb'),
        as_attachment=True,
        filename=f'plagenor_{timestamp}.db',
    )


@superadmin_required
def revenue_archives(request):
    """Display monthly revenue archives."""
    from core.models import RevenueArchive

    archives = RevenueArchive.objects.order_by('-year', '-month')

    context = {
        'archives': archives,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/superadmin/revenue_archives.html', context)


# --- Task 1: Create User ---
@superadmin_required
def create_user(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from django.contrib.auth.hashers import make_password
    user = User.objects.create(
        username=request.POST.get('username', ''),
        first_name=request.POST.get('first_name', ''),
        last_name=request.POST.get('last_name', ''),
        email=request.POST.get('email', ''),
        role=request.POST.get('role', 'REQUESTER'),
        organization=request.POST.get('organization', ''),
        phone=request.POST.get('phone', ''),
        password=make_password(request.POST.get('password', '')),
    )
    if user.role == 'MEMBER':
        MemberProfile.objects.get_or_create(user=user)
    messages.success(request, f"Utilisateur {user.get_full_name()} créé avec succès.")
    return redirect_back(request, 'dashboard:superadmin')


# --- Task 2: Edit User ---
@superadmin_required
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        # Check if username is being changed and if it's already taken
        new_username = request.POST.get('username', user_obj.username).strip()
        if new_username != user_obj.username:
            if User.objects.filter(username=new_username).exclude(pk=user_obj.pk).exists():
                messages.error(request, f"Le nom d'utilisateur '{new_username}' est déjà utilisé.")
                return render(request, 'dashboard/superadmin/user_edit.html', {
                    'user_obj': user_obj,
                    'role_choices': User.ROLE_CHOICES,
                    'student_level_choices': User.STUDENT_LEVEL_CHOICES,
                })
            user_obj.username = new_username
        user_obj.first_name = request.POST.get('first_name', user_obj.first_name)
        user_obj.last_name = request.POST.get('last_name', user_obj.last_name)
        user_obj.email = request.POST.get('email', user_obj.email)
        old_role = user_obj.role
        user_obj.role = request.POST.get('role', user_obj.role)
        user_obj.organization = request.POST.get('organization', user_obj.organization or '')
        user_obj.phone = request.POST.get('phone', user_obj.phone or '')
        user_obj.laboratory = request.POST.get('laboratory', user_obj.laboratory or '')
        user_obj.supervisor = request.POST.get('supervisor', user_obj.supervisor or '')
        user_obj.student_level = request.POST.get('student_level', user_obj.student_level or '')
        user_obj.student_level_other = request.POST.get('student_level_other', user_obj.student_level_other or '')
        new_pass = request.POST.get('new_password', '').strip()
        if new_pass:
            user_obj.set_password(new_pass)
            # Clear the must_change_password flag when admin sets a new password
            user_obj.must_change_password = False
        user_obj.save()
        if user_obj.role == 'MEMBER' and old_role != 'MEMBER':
            MemberProfile.objects.get_or_create(user=user_obj)
        messages.success(request, f"Utilisateur {user_obj.get_full_name()} mis à jour.")
        return redirect_back(request, 'dashboard:superadmin')
    return render(request, 'dashboard/superadmin/user_edit.html', {
        'user_obj': user_obj,
        'role_choices': User.ROLE_CHOICES,
        'student_level_choices': User.STUDENT_LEVEL_CHOICES,
    })


# --- Task 4: Force Transition ---
@superadmin_required
def force_transition_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.workflow import transition
    req = get_object_or_404(Request, pk=pk)
    to_status = request.POST.get('to_status', '')
    justification = request.POST.get('justification', '')
    if not justification or len(justification.strip()) < 10:
        messages.error(request, "La justification doit comporter au moins 10 caractères.")
        return redirect_back(request, 'dashboard:superadmin')
    try:
        transition(req, to_status, request.user, notes=f"[FORCÉ] {justification}", force=True)
        messages.success(request, f"Demande {req.display_id} forcée vers {to_status}.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:superadmin')


# --- Task 5: Budget Override ---
@superadmin_required
def budget_override_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.financial import approve_with_budget_override
    req = get_object_or_404(Request, pk=pk)
    justification = request.POST.get('justification', '')
    try:
        approve_with_budget_override(req, request.user, float(req.budget_amount), justification)
        messages.success(request, f"Override budgétaire approuvé pour {req.display_id}.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect_back(request, 'dashboard:superadmin')


# --- Task 6: Add Payment Method ---
@superadmin_required
def add_payment_method(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    name = request.POST.get('name', '').strip()
    if name:
        PaymentMethod.objects.create(name=name)
        messages.success(request, "Méthode de paiement ajoutée.")
    else:
        messages.error(request, "Le nom est requis.")
    return redirect_back(request, 'dashboard:superadmin')


# --- Task 11: DOCX Template Upload ---
@superadmin_required
def upload_template(request):
    if request.method != 'POST' or 'template_file' not in request.FILES:
        return HttpResponseForbidden()
    import shutil
    template_type = request.POST.get('template_type', '')
    allowed = ['ibtikar_form_template', 'platform_note_template', 'reception_form_template', 'quote_template']
    if template_type not in allowed:
        messages.error(request, "Type de template invalide.")
        return redirect_back(request, 'dashboard:superadmin')
    upload = request.FILES['template_file']
    if not upload.name.endswith('.docx'):
        messages.error(request, "Seuls les fichiers .docx sont acceptés.")
        return redirect_back(request, 'dashboard:superadmin')
    dest = settings.BASE_DIR / 'documents' / 'docx_templates' / f'{template_type}.docx'
    if dest.exists():
        shutil.copy2(str(dest), str(dest.with_suffix('.backup.docx')))
    with open(str(dest), 'wb') as f:
        for chunk in upload.chunks():
            f.write(chunk)
    messages.success(request, f"Template '{template_type}' mis à jour.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def download_template(request, template_type):
    """Download the current DOCX template file."""
    allowed = ['ibtikar_form_template', 'platform_note_template', 'reception_form_template', 'quote_template']
    if template_type not in allowed:
        messages.error(request, "Type de template invalide.")
        return redirect_back(request, 'dashboard:superadmin')
    from django.http import FileResponse
    dest = settings.BASE_DIR / 'documents' / 'docx_templates' / f'{template_type}.docx'
    if not dest.exists():
        messages.error(request, "Template introuvable.")
        return redirect_back(request, 'dashboard:superadmin')
    return FileResponse(
        open(str(dest), 'rb'),
        as_attachment=True,
        filename=f'{template_type}.docx',
    )


# --- Task 12: Revenue Counter Reset ---
@superadmin_required
def reset_revenue(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.financial import archive_monthly_revenue
    archive_monthly_revenue()
    PlatformContent.objects.update_or_create(
        key='revenue_reset_date',
        defaults={'value': timezone.now().isoformat(), 'updated_by': request.user}
    )
    messages.success(request, "Compteurs de revenus réinitialisés. Les données ont été archivées.")
    return redirect_back(request, 'dashboard:superadmin')


# --- Email Export for Newsletter ---
@superadmin_required
def export_emails(request):
    """Export all unique emails as CSV for newsletter."""
    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="plagenor_contacts.csv"'

    writer = csv.writer(response)
    writer.writerow(['Nom', 'Email', 'Rôle', 'Source'])

    # Registered users with emails
    for u in User.objects.filter(is_active=True).exclude(email='').exclude(email__isnull=True):
        writer.writerow([u.get_full_name(), u.email, u.get_role_display(), 'Compte enregistré'])

    # Guest emails (deduplicated)
    seen_emails = set(User.objects.values_list('email', flat=True))
    guest_emails = Request.objects.filter(
        submitted_as_guest=True
    ).exclude(guest_email='').exclude(guest_email__isnull=True).values_list('guest_name', 'guest_email').distinct()
    for name, email in guest_emails:
        if email not in seen_emails:
            writer.writerow([name, email, 'Invité', 'Soumission invité'])
            seen_emails.add(email)

    return response


# --- Task 14: Restore from Backup ---
@superadmin_required
def restore_db(request):
    if request.method != 'POST' or 'db_file' not in request.FILES:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect_back(request, 'dashboard:superadmin')
    import shutil
    import sqlite3
    upload = request.FILES['db_file']
    temp_path = settings.BASE_DIR / 'data' / 'restore_temp.db'
    with open(str(temp_path), 'wb') as f:
        for chunk in upload.chunks():
            f.write(chunk)
    try:
        conn = sqlite3.connect(str(temp_path))
        conn.execute("SELECT count(*) FROM sqlite_master")
        conn.close()
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        messages.error(request, "Fichier invalide — ce n'est pas une base de données SQLite valide.")
        logger.error(f"Invalid SQLite file uploaded: {e}")
        return redirect_back(request, 'dashboard:superadmin')
    db_path = settings.BASE_DIR / 'data' / 'plagenor.db'
    if db_path.exists():
        shutil.copy2(str(db_path), str(db_path.with_suffix('.pre_restore.db')))
    shutil.move(str(temp_path), str(db_path))
    messages.success(request, "Base de données restaurée. Veuillez redémarrer le serveur.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def reset_account(request, pk):
    """Reset a user's password and force them to change it on next login."""
    import secrets
    import string
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from core.audit import log_action

    target_user = get_object_or_404(User, pk=pk)

    # Block self-reset
    if target_user == request.user:
        messages.error(request, _("Vous ne pouvez pas réinitialiser votre propre compte."))
        return redirect_back(request, 'dashboard:superadmin')

    if request.method == 'POST':
        # Generate secure temporary password (16 chars: upper, lower, digit, symbol)
        alphabet = string.ascii_letters + string.digits + '!@#$%^&*()'
        temp_password = ''.join(secrets.choice(alphabet) for _ in range(16))

        # Set password and flag
        target_user.set_password(temp_password)
        target_user.must_change_password = True
        target_user.save(update_fields=['password', 'must_change_password'])

        # Audit log
        log_action(
            action='ACCOUNT_RESET',
            entity_type='USER',
            entity_id=str(target_user.pk),
            actor=request.user,
            details={
                'target_username': target_user.username,
                'target_role': target_user.role,
                'reset_by': request.user.username,
            },
        )

        # Send email to the user
        if target_user.email:
            try:
                subject = _("Réinitialisation de votre compte PLAGENOR 4.0")
                email_ctx = {
                    'user': target_user,
                    'temp_password': temp_password,
                    'admin_name': request.user.get_full_name() or request.user.username,
                    'platform_name': 'PLAGENOR 4.0',
                    'login_url': request.build_absolute_uri('/accounts/login/'),
                }
                html_body = render_to_string('accounts/email/account_reset.html', email_ctx, request=request)
                send_mail(
                    subject=subject,
                    message='',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[target_user.email],
                    html_message=html_body,
                    fail_silently=True,
                )
            except Exception as e:
                logger.warning(f"Failed to send password reset email to {target_user.email}: {e}")

        messages.success(
            request,
            _("Le compte de %(username)s a été réinitialisé avec succès. Un email contenant les instructions a été envoyé.") % {'username': target_user.username}
        )
        return redirect_back(request, 'dashboard:superadmin')

    # GET: confirmation page
    return render(request, 'dashboard/superadmin/reset_account_confirm.html', {
        'target_user': target_user,
    })


# --- Superadmin Request Detail View ---
@superadmin_required
def request_detail(request, pk):
    """Full request detail view for SUPER_ADMIN with all information."""
    from core.models import Message
    from accounts.models import MemberProfile
    from documents.pdf_generators import check_template_status

    req = get_object_or_404(Request, pk=pk)
    history = req.history.select_related('actor').order_by('created_at')
    comments = req.comments.select_related('author').order_by('created_at')
    messages_list = Message.objects.filter(request=req).select_related('from_user', 'to_user').order_by('created_at')
    
    # Load YAML service definition for parameter labels
    yaml_def = None
    if req.service:
        yaml_def = get_service_def(req.service.code)

    # Available members for assignment
    available_members = MemberProfile.objects.filter(available=True).select_related('user').order_by('user__first_name', 'user__last_name')

    # Check IBTIKAR form status
    ibtikar_form_status = check_template_status(req) if req.channel == 'IBTIKAR' else None

    context = {
        'req': req,
        'history': history,
        'comments': comments,
        'messages_list': messages_list,
        'yaml_def': yaml_def,
        'available_members': available_members,
        'status_choices': Request.STATUS_CHOICES,
        'now': timezone.now(),
        'ibtikar_form_status': ibtikar_form_status,
    }
    return render(request, 'dashboard/superadmin/request_detail.html', context)


# --- Superadmin Direct Assignment ---
@superadmin_required
def assign_request_direct(request, pk):
    """Directly assign a request to an analyst from superadmin dashboard."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    req = get_object_or_404(Request, pk=pk)
    member_id = request.POST.get('member_id')
    
    if not member_id:
        messages.error(request, _("Veuillez sélectionner un analyste."))
        return redirect('dashboard:superadmin_request_detail', pk=pk)
    
    member = get_object_or_404(MemberProfile, pk=member_id)
    
    # Check if request is in a state that allows assignment
    assignable_states = ['IBTIKAR_CODE_SUBMITTED', 'PAYMENT_CONFIRMED', 'ORDER_UPLOADED', 'ASSIGNED', 'PENDING_ACCEPTANCE']
    if req.status not in assignable_states and req.assigned_to is None:
        messages.warning(
            request,
            _("La demande %(id)s n'est pas dans un état permettant l'assignation directe (statut: %(status)s). L'assignation sera quand même effectuée.") % {
                'id': req.display_id,
                'status': req.get_status_display()
            }
        )
    
    req.assigned_to = member
    req.save(update_fields=['assigned_to'])
    
    # Log the assignment
    log_action(
        action='DIRECT_ASSIGNMENT',
        entity_type='REQUEST',
        entity_id=str(req.pk),
        actor=request.user,
        details={
            'assigned_to': member.user.get_full_name(),
            'previous_status': req.status,
        }
    )
    
    messages.success(
        request,
        _("Demande %(id)s assignée à %(member)s.") % {
            'id': req.display_id,
            'member': member.user.get_full_name()
        }
    )
    return redirect('dashboard:superadmin_request_detail', pk=pk)


# =============================================================================
# PAYMENT SETTINGS (Finance/Invoice Configuration)
# =============================================================================

@superadmin_required
def payment_settings(request):
    """
    Configure payment settings for GENOCLAB invoices.
    These settings are used to auto-fill invoices and payment instructions.
    """
    settings_obj = PaymentSettings.get_settings()
    
    if request.method == 'POST':
        bank_account = request.POST.get('bank_account', '').strip()
        beneficiary_name = request.POST.get('beneficiary_name', '').strip()
        bank_name = request.POST.get('bank_name', '').strip()
        payment_instructions = request.POST.get('payment_instructions', '').strip()
        
        settings_obj.bank_account = bank_account
        settings_obj.beneficiary_name = beneficiary_name
        settings_obj.bank_name = bank_name
        settings_obj.payment_instructions = payment_instructions
        settings_obj.updated_by = request.user
        settings_obj.save()
        
        messages.success(request, _("Paramètres de paiement mis à jour avec succès."))
        return redirect('dashboard:superadmin')
    
    context = {
        'settings': settings_obj,
    }
    return render(request, 'dashboard/superadmin/payment_settings.html', context)
