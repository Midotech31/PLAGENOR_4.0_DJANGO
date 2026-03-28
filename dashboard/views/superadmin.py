from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.conf import settings

from accounts.models import User, MemberProfile, Technique
from core.models import Service, Request, PlatformContent, Invoice, PaymentMethod, ServiceFormField
from core.financial import get_budget_dashboard
from core.productivity import get_all_productivity_stats


def superadmin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'SUPER_ADMIN':
            return HttpResponseForbidden()
        return view_func(request, *args, **kwargs)
    wrapper.__wrapped__ = view_func
    return login_required(wrapper)


@superadmin_required
def index(request):
    total_users = User.objects.count()
    total_members = MemberProfile.objects.count()
    total_requests = Request.objects.filter(archived=False).count()
    completed_requests = Request.objects.filter(status='COMPLETED').count()
    ibtikar_count = Request.objects.filter(channel='IBTIKAR', archived=False).count()
    genoclab_count = Request.objects.filter(channel='GENOCLAB', archived=False).count()
    total_services = Service.objects.filter(active=True).count()
    total_techniques = Technique.objects.filter(active=True).count()

    users = User.objects.order_by('-date_joined')[:50]
    members = MemberProfile.objects.select_related('user').order_by('-user__date_joined')[:50]
    services = Service.objects.order_by('code')
    techniques = Technique.objects.order_by('name')
    platform_content = PlatformContent.objects.all()

    recent_requests = Request.objects.filter(archived=False).order_by('-created_at')[:5]
    recent_users = User.objects.order_by('-date_joined')[:5]

    status_dist = (
        Request.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Business logic from engines
    budget_dashboard = get_budget_dashboard()
    productivity_stats = get_all_productivity_stats()

    # Task 3: Requests tab with filters
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
    all_requests_qs = all_requests_qs.order_by('-created_at')[:100]

    # Task 6: Payments tab
    all_invoices = Invoice.objects.select_related('request', 'client').order_by('-created_at')[:50]
    payment_methods = PaymentMethod.objects.all()

    # Task 8: Documents tab
    requests_with_reports = Request.objects.exclude(report_file='').exclude(report_file__isnull=True).order_by('-updated_at')[:20]

    # Task 9: Forms tab
    all_form_fields = ServiceFormField.objects.select_related('service').order_by('service__code', 'sort_order')
    try:
        from core.registry import load_service_registry
        yaml_registry = load_service_registry()
    except Exception:
        yaml_registry = {}

    # Task 10: KPI - average rating
    avg_rating = Request.objects.filter(service_rating__isnull=False).aggregate(avg=Avg('service_rating'))['avg'] or 0

    context = {
        'total_users': total_users,
        'total_members': total_members,
        'total_requests': total_requests,
        'completed_requests': completed_requests,
        'ibtikar_count': ibtikar_count,
        'genoclab_count': genoclab_count,
        'total_services': total_services,
        'total_techniques': total_techniques,
        'users': users,
        'members': members,
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
        'all_requests': all_requests_qs,
        'sa_channel': sa_channel,
        'sa_status': sa_status,
        'sa_search': sa_search,
        'status_choices': Request.STATUS_CHOICES,
        'role_choices': User.ROLE_CHOICES,
        # Payments tab
        'all_invoices': all_invoices,
        'payment_methods': payment_methods,
        # Documents tab
        'requests_with_reports': requests_with_reports,
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
    return redirect('dashboard:superadmin')


@superadmin_required
def member_toggle_available(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    profile = get_object_or_404(MemberProfile, pk=pk)
    profile.available = not profile.available
    profile.save(update_fields=['available'])
    status = 'disponible' if profile.available else 'indisponible'
    messages.success(request, f"Analyste {profile.user.get_full_name()} marqué {status}.")
    return redirect('dashboard:superadmin')


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
    return redirect('dashboard:superadmin')


@superadmin_required
def service_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    service = get_object_or_404(Service, pk=pk)
    service.active = False
    service.save(update_fields=['active'])
    messages.success(request, f"Service {service.name} désactivé.")
    return redirect('dashboard:superadmin')


@superadmin_required
def technique_create(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    Technique.objects.create(
        name=request.POST.get('name', ''),
        category=request.POST.get('category', ''),
    )
    messages.success(request, "Technique ajoutée.")
    return redirect('dashboard:superadmin')


@superadmin_required
def technique_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    technique = get_object_or_404(Technique, pk=pk)
    technique.active = False
    technique.save(update_fields=['active'])
    messages.success(request, f"Technique {technique.name} désactivée.")
    return redirect('dashboard:superadmin')


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
    return redirect('dashboard:superadmin')


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
        service.ibtikar_price = request.POST.get('ibtikar_price', service.ibtikar_price)
        service.genoclab_price = request.POST.get('genoclab_price', service.genoclab_price)
        service.turnaround_days = request.POST.get('turnaround_days', service.turnaround_days)
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
        return redirect('dashboard:superadmin')

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
    return redirect('dashboard:superadmin')


# --- Task 2: Edit User ---
@superadmin_required
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
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
        return redirect('dashboard:superadmin')
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
        return redirect('dashboard:superadmin')
    try:
        force_transition(req, to_status, request.user, notes=f"[FORCÉ] {justification}")
        messages.success(request, f"Demande {req.display_id} forcée vers {to_status}.")
    except Exception as e:
        messages.error(request, str(e))
    return redirect('dashboard:superadmin')


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
    return redirect('dashboard:superadmin')


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
    return redirect('dashboard:superadmin')


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
        return redirect('dashboard:superadmin')
    upload = request.FILES['template_file']
    if not upload.name.endswith('.docx'):
        messages.error(request, "Seuls les fichiers .docx sont acceptés.")
        return redirect('dashboard:superadmin')
    dest = settings.BASE_DIR / 'documents' / 'docx_templates' / f'{template_type}.docx'
    if dest.exists():
        shutil.copy2(str(dest), str(dest.with_suffix('.backup.docx')))
    with open(str(dest), 'wb') as f:
        for chunk in upload.chunks():
            f.write(chunk)
    messages.success(request, f"Template '{template_type}' mis à jour.")
    return redirect('dashboard:superadmin')


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
    return redirect('dashboard:superadmin')


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
        return redirect('dashboard:superadmin')
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
    except Exception:
        temp_path.unlink(missing_ok=True)
        messages.error(request, "Fichier invalide — ce n'est pas une base de données SQLite valide.")
        return redirect('dashboard:superadmin')
    db_path = settings.BASE_DIR / 'data' / 'plagenor.db'
    if db_path.exists():
        shutil.copy2(str(db_path), str(db_path.with_suffix('.pre_restore.db')))
    shutil.move(str(temp_path), str(db_path))
    messages.success(request, "Base de données restaurée. Veuillez redémarrer le serveur.")
    return redirect('dashboard:superadmin')
