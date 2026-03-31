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

logger = logging.getLogger('plagenor')

from accounts.models import User, MemberProfile, Technique
from core.models import Service, Request, PlatformContent, Invoice, PaymentMethod, ServiceFormField
from core.financial import get_budget_dashboard
from core.productivity import get_all_productivity_stats
from core.registry import get_service_def


def superadmin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'SUPER_ADMIN':
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


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
    custom_fields = service.custom_fields.all()

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
        
        if 'image' in request.FILES:
            service.image = request.FILES['image']
        service.save()

        # Handle custom fields: delete existing and recreate from POST
        service.custom_fields.all().delete()
        field_names = request.POST.getlist('field_name')
        field_labels = request.POST.getlist('field_label')
        field_types = request.POST.getlist('field_type')
        field_required = request.POST.getlist('field_required')
        field_options = request.POST.getlist('field_options')
        for i, name in enumerate(field_names):
            if not name.strip():
                continue
            import json
            opts = []
            if i < len(field_options) and field_options[i].strip():
                try:
                    opts = json.loads(field_options[i])
                except (json.JSONDecodeError, ValueError):
                    opts = [o.strip() for o in field_options[i].split(',') if o.strip()]
            ServiceFormField.objects.create(
                service=service,
                name=name.strip(),
                label=field_labels[i].strip() if i < len(field_labels) else name.strip(),
                field_type=field_types[i] if i < len(field_types) else 'string',
                required=str(i) in field_required,
                options=opts,
                sort_order=i,
            )

        messages.success(request, f"Service {service.name} mis à jour.")
        return redirect_back(request, 'dashboard:superadmin')

    return render(request, 'dashboard/superadmin/service_edit.html', {
        'service': service,
        'custom_fields': custom_fields,
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
        new_pass = request.POST.get('new_password', '').strip()
        if new_pass:
            user_obj.set_password(new_pass)
        user_obj.save()
        if user_obj.role == 'MEMBER' and old_role != 'MEMBER':
            MemberProfile.objects.get_or_create(user=user_obj)
        messages.success(request, f"Utilisateur {user_obj.get_full_name()} mis à jour.")
        return redirect_back(request, 'dashboard:superadmin')
    return render(request, 'dashboard/superadmin/user_edit.html', {
        'user_obj': user_obj,
        'role_choices': User.ROLE_CHOICES,
    })


# --- Task 4: Force Transition ---
@superadmin_required
def force_transition_view(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.workflow import force_transition
    req = get_object_or_404(Request, pk=pk)
    to_status = request.POST.get('to_status', '')
    justification = request.POST.get('justification', '')
    if not justification or len(justification.strip()) < 10:
        messages.error(request, "La justification doit comporter au moins 10 caractères.")
        return redirect_back(request, 'dashboard:superadmin')
    try:
        force_transition(req, to_status, request.user, notes=f"[FORCÉ] {justification}")
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

    context = {
        'req': req,
        'history': history,
        'comments': comments,
        'messages_list': messages_list,
        'yaml_def': yaml_def,
        'available_members': available_members,
        'status_choices': Request.STATUS_CHOICES,
        'now': timezone.now(),
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
