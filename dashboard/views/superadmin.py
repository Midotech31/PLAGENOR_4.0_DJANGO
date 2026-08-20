from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from dashboard.utils import redirect_back
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.utils.translation import gettext as _
from django.conf import settings

from accounts.models import User, MemberProfile, Technique
from core.models import Service, Request, PlatformContent, Invoice, PaymentMethod, ServiceFormField, Announcement
from core.templatetags.cms import clear_cms_cache
from core.financial import get_budget_dashboard
from core.productivity import get_all_productivity_stats
from core.uploads import validate_upload
from django.core.exceptions import ValidationError


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

    total_users = User.objects.count()
    total_members = MemberProfile.objects.count()
    total_requests = Request.objects.filter(archived=False).count()
    completed_requests = Request.objects.filter(status='COMPLETED').count()
    ibtikar_count = Request.objects.filter(channel='IBTIKAR', archived=False).count()
    genoclab_count = Request.objects.filter(channel='GENOCLAB', archived=False).count()
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
    platform_content = PlatformContent.objects.order_by('key', 'lang')
    # Group content one row per key with all three languages side by side so
    # the Content Manager can edit FR/EN/AR together.
    _content_langs = [code for code, _ in PlatformContent.LANGUAGE_CHOICES]
    _grouped = {}
    for pc in platform_content:
        row = _grouped.setdefault(pc.key, {'key': pc.key, 'updated_at': pc.updated_at})
        row[pc.lang] = pc.value
        if pc.updated_at and (row['updated_at'] is None or pc.updated_at > row['updated_at']):
            row['updated_at'] = pc.updated_at
    for row in _grouped.values():
        row['missing'] = [lg for lg in _content_langs if not (row.get(lg) or '').strip()]
    content_rows = sorted(_grouped.values(), key=lambda r: r['key'])

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

    # Documents tab
    requests_with_reports = Request.objects.exclude(report_file='').exclude(report_file__isnull=True).order_by('-updated_at')[:20]

    # Forms tab
    all_form_fields = ServiceFormField.objects.select_related('service').order_by('service__code', 'sort_order')
    try:
        from core.registry import load_service_registry
        yaml_registry = load_service_registry()
    except Exception:
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
        'content_rows': content_rows,
        'platform_content_languages': PlatformContent.LANGUAGE_CHOICES,
        'announcements': Announcement.objects.all()[:50],
        'announcement_levels': Announcement.LEVEL_CHOICES,
        'announcement_audiences': Announcement.AUDIENCE_CHOICES,
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
    image = request.FILES.get('image')
    if image:
        try:
            image = validate_upload(image, 'image')
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect_back(request, 'dashboard:superadmin')
    Service.objects.create(
        code=request.POST.get('code', ''),
        name=request.POST.get('name', ''),
        description=request.POST.get('description', ''),
        channel_availability=request.POST.get('channel_availability', 'BOTH'),
        ibtikar_price=request.POST.get('ibtikar_price', 0),
        genoclab_price=request.POST.get('genoclab_price', 0),
        turnaround_days=request.POST.get('turnaround_days', 7),
        image=image,
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
    """Delete a single platform content row (one key + one language)."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    content = get_object_or_404(PlatformContent, pk=pk)
    key = content.key
    content.delete()
    clear_cms_cache()
    messages.success(request, f"Contenu '{key}' supprimé.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def content_update(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    key = request.POST.get('key', '').strip()
    value = request.POST.get('value', '')
    lang = request.POST.get('lang', '').strip() or settings.LANGUAGE_CODE
    allowed_langs = {code for code, _ in PlatformContent.LANGUAGE_CHOICES}
    if lang not in allowed_langs:
        lang = settings.LANGUAGE_CODE
    if not key:
        messages.error(request, "Clé manquante.")
        return redirect_back(request, 'dashboard:superadmin')
    PlatformContent.objects.update_or_create(
        key=key,
        lang=lang,
        defaults={'value': value, 'updated_by': request.user},
    )
    clear_cms_cache()
    messages.success(request, f"Contenu '{key}' [{lang}] mis à jour.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def announcement_create(request):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.models import Announcement
    title = (request.POST.get('title') or '').strip()
    message = (request.POST.get('message') or '').strip()
    level = request.POST.get('level', 'info')
    audience = request.POST.get('audience', 'ALL')
    valid_levels = {c for c, _ in Announcement.LEVEL_CHOICES}
    valid_aud = {c for c, _ in Announcement.AUDIENCE_CHOICES}
    if not title or not message:
        messages.error(request, "Titre et message obligatoires.")
        return redirect_back(request, 'dashboard:superadmin')
    Announcement.objects.create(
        title=title, message=message,
        level=level if level in valid_levels else 'info',
        audience=audience if audience in valid_aud else 'ALL',
        created_by=request.user)
    messages.success(request, "Annonce publiée.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def announcement_toggle(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.models import Announcement
    a = get_object_or_404(Announcement, pk=pk)
    a.active = not a.active
    a.save(update_fields=['active'])
    messages.success(request, "Annonce mise à jour.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def announcement_delete(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    from core.models import Announcement
    get_object_or_404(Announcement, pk=pk).delete()
    messages.success(request, "Annonce supprimée.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def reset_2fa(request, pk):
    """Disable a user's two-factor auth — recovery path when a device is lost
    (no self-service recovery codes by design)."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    target = get_object_or_404(User, pk=pk)
    reason = request.POST.get('reason', '').strip()
    if len(reason) < 10:
        messages.error(request, "Une raison d'au moins 10 caractères est obligatoire.")
        return redirect_back(request, 'dashboard:superadmin')
    target.totp_secret = ''
    target.totp_enabled = False
    target.save(update_fields=['totp_secret', 'totp_enabled'])
    from core.audit import log_action
    log_action('ADMIN_2FA_RESET', 'USER', str(target.pk), request.user,
               {'reason': reason})
    from notifications.models import Notification
    Notification.objects.create(
        user=target,
        message=("Votre double authentification a été réinitialisée par un "
                 "administrateur. Réinscrivez un appareil avant de continuer."),
        notification_type='SECURITY')
    messages.success(request, f"2FA réinitialisée pour {target.username}.")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def content_save(request):
    """Upsert all three languages of one content key in a single submit.

    POST: key, value_fr, value_en, value_ar. A blank language value clears
    that translation (the {% cms %} tag then falls back to the default
    language, then to the template default).
    """
    if request.method != 'POST':
        return HttpResponseForbidden()
    key = request.POST.get('key', '').strip()
    if not key:
        messages.error(request, "Clé manquante.")
        return redirect_back(request, 'dashboard:superadmin')
    for code, _label in PlatformContent.LANGUAGE_CHOICES:
        value = request.POST.get(f'value_{code}', '')
        PlatformContent.objects.update_or_create(
            key=key, lang=code,
            defaults={'value': value, 'updated_by': request.user},
        )
    clear_cms_cache()
    messages.success(request, f"Contenu '{key}' enregistré (toutes les langues).")
    return redirect_back(request, 'dashboard:superadmin')


@superadmin_required
def content_delete_key(request):
    """Delete every language row for a content key. POST: key."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    key = request.POST.get('key', '').strip()
    if not key:
        messages.error(request, "Clé manquante.")
        return redirect_back(request, 'dashboard:superadmin')
    deleted, _ = PlatformContent.objects.filter(key=key).delete()
    clear_cms_cache()
    messages.success(request, f"Contenu '{key}' supprimé ({deleted} entrée(s)).")
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
    """Edit a service, its custom form fields, and its detailed pricing tiers.

    Three datasets live on this page and submit as one form:
      * Service core fields (name, prices, channel, turnaround, image)
      * ServiceFormField rows (custom request-form questions)
      * ServicePricing rows (per-tier / per-condition pricing rules:
        BASE, PER_SAMPLE, PER_PARAMETER, URGENCY_SURCHARGE, DISCOUNT)

    Pricing rules are keyed by ``pricing_pk[]`` (empty for new rows). Existing
    rules whose pk is missing from the POST are deleted. The rest are
    update_or_create'd so a tier's PK survives an edit — important because
    other tables may reference it.
    """
    from core.models import ServiceFormField, ServicePricing
    from decimal import Decimal, InvalidOperation

    service = get_object_or_404(Service, pk=pk)
    custom_fields = service.custom_fields.all()
    pricing_tiers = service.pricing_configs.order_by('priority', 'pk')

    if request.method == 'POST':
        service.name = request.POST.get('name', service.name)
        service.description = request.POST.get('description', service.description)
        service.channel_availability = request.POST.get('channel_availability', service.channel_availability)
        service.ibtikar_price = request.POST.get('ibtikar_price', service.ibtikar_price)
        service.genoclab_price = request.POST.get('genoclab_price', service.genoclab_price)
        service.turnaround_days = request.POST.get('turnaround_days', service.turnaround_days)
        if 'image' in request.FILES:
            try:
                service.image = validate_upload(request.FILES['image'], 'image')
            except ValidationError as exc:
                messages.error(request, exc.messages[0])
                return redirect('dashboard:superadmin_service_edit', pk=service.pk)
        service.save()

        # ---- Custom form fields: wipe + recreate (simple, low-volume data)
        import json
        service.custom_fields.all().delete()
        field_names = request.POST.getlist('field_name')
        field_labels = request.POST.getlist('field_label')
        field_types = request.POST.getlist('field_type')
        field_categories = request.POST.getlist('field_category')
        field_required = request.POST.getlist('field_required')
        field_options = request.POST.getlist('field_options')
        # Variable-pricing + conditional-logic config (parallel lists, one per field)
        field_affects = request.POST.getlist('field_affects_pricing')
        field_mod_type = request.POST.getlist('field_price_modifier_type')
        field_mod_value = request.POST.getlist('field_price_modifier_value')
        field_note_fr = request.POST.getlist('field_condition_note_fr')
        field_note_en = request.POST.getlist('field_condition_note_en')
        field_option_pricing = request.POST.getlist('field_option_pricing')
        field_conditional = request.POST.getlist('field_conditional_logic')

        def _at(lst, idx, default=''):
            return lst[idx] if idx < len(lst) else default

        def _parse_json(raw, fallback):
            raw = (raw or '').strip()
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return fallback

        for i, name in enumerate(field_names):
            if not name.strip():
                continue
            opts = []
            if i < len(field_options) and field_options[i].strip():
                try:
                    opts = json.loads(field_options[i])
                except (json.JSONDecodeError, ValueError):
                    opts = [o.strip() for o in field_options[i].split(',') if o.strip()]

            mod_value = _at(field_mod_value, i).strip()
            try:
                mod_value = Decimal(mod_value) if mod_value else None
            except (InvalidOperation, ValueError):
                mod_value = None

            category = _at(field_categories, i, 'parameter').strip()
            if category not in ('parameter', 'sample_column'):
                category = 'parameter'

            ServiceFormField.objects.create(
                service=service,
                name=name.strip(),
                label=field_labels[i].strip() if i < len(field_labels) else name.strip(),
                field_type=field_types[i] if i < len(field_types) else 'string',
                field_category=category,
                required=str(i) in field_required,
                options=opts,
                sort_order=i,
                affects_pricing=str(i) in field_affects,
                price_modifier_type=_at(field_mod_type, i).strip(),
                price_modifier_value=mod_value,
                condition_note_fr=_at(field_note_fr, i).strip(),
                condition_note_en=_at(field_note_en, i).strip(),
                option_pricing=_parse_json(_at(field_option_pricing, i), {}),
                conditional_logic=_parse_json(_at(field_conditional, i), []),
            )

        # ---- Pricing tiers are managed by the modal UI via the JSON API
        #     (dashboard.views.pricing_api). They're saved instantly on each
        #     Add/Edit/Delete click — we deliberately do NOT touch them on
        #     the main form submit, so the Cancel button (or a half-filled
        #     form) never wipes the tiers an admin just configured.

        # ---- Unified base-price & multipliers (Service.pricing_data) ------
        # Same formula as before: base_price (pathogenic / non_pathogenic) ×
        # multiplier (chosen via multiplier_param) × N_samples. The admin
        # adjusts the numbers here when reagent/consumable costs vary.
        bp_non = _to_decimal_or_none(request.POST.get('pd_base_non_pathogenic'))
        bp_pat = _to_decimal_or_none(request.POST.get('pd_base_pathogenic'))
        mult_param = (request.POST.get('pd_multiplier_param') or '').strip()
        mult_keys = request.POST.getlist('pd_mult_key')
        mult_factors = request.POST.getlist('pd_mult_factor')
        multipliers = {}
        for k, f in zip(mult_keys, mult_factors):
            k = (k or '').strip()
            if not k:
                continue
            try:
                multipliers[k] = float(f)
            except (TypeError, ValueError):
                continue
        if bp_non is not None or bp_pat is not None or multipliers or mult_param:
            new_pdata = dict(service.pricing_data or {})
            new_pdata['base_price'] = {
                'non_pathogenic': float(bp_non) if bp_non is not None else (
                    (service.pricing_data or {}).get('base_price', {}).get('non_pathogenic')
                ),
                'pathogenic': float(bp_pat) if bp_pat is not None else (
                    (service.pricing_data or {}).get('base_price', {}).get('pathogenic')
                ),
            }
            new_pdata['base_price'] = {k: v for k, v in new_pdata['base_price'].items() if v is not None}
            if multipliers:
                new_pdata['multipliers'] = multipliers
            if mult_param:
                new_pdata['multiplier_param'] = mult_param
            service.pricing_data = new_pdata
            service.save(update_fields=['pricing_data'])

        messages.success(request, f"Service {service.name} mis à jour.")
        return redirect_back(request, 'dashboard:superadmin')

    # Build the pricing_data view context. If the admin hasn't authored any
    # DB pricing yet for one of the 9 legacy services, pre-fill the form from
    # the YAML registry so the visible numbers are the actual ones currently
    # applied — first save then writes them to the DB.
    pdata = service.pricing_data or {}
    try:
        from core.registry import get_service_def
        yaml_def = get_service_def(service.code) or {}
    except Exception:
        yaml_def = {}
    yaml_pricing = (yaml_def.get('pricing') or {})
    yaml_base = yaml_pricing.get('base_price') or {}
    yaml_mults = yaml_pricing.get('multipliers') or {}
    yaml_params = yaml_def.get('parameters', []) or []
    pricing_data_view = {
        'base_non_pathogenic': pdata.get('base_price', {}).get('non_pathogenic',
                                                              yaml_base.get('non_pathogenic') or ''),
        'base_pathogenic': pdata.get('base_price', {}).get('pathogenic',
                                                          yaml_base.get('pathogenic') or ''),
        'multipliers': pdata.get('multipliers') or yaml_mults or {},
        'multiplier_param': pdata.get('multiplier_param') or _guess_multiplier_param(yaml_params, yaml_mults),
        'param_options': [p.get('name') for p in yaml_params if p.get('options')],
        'has_db_override': bool(pdata.get('base_price') or pdata.get('multipliers')),
        'has_yaml_default': bool(yaml_base or yaml_mults),
    }

    return render(request, 'dashboard/superadmin/service_edit.html', {
        'service': service,
        'custom_fields': custom_fields,
        'pricing_tiers': pricing_tiers,
        'pricing_type_choices': ServicePricing.PRICING_TYPE_CHOICES,
        'pricing_channel_choices': ServicePricing.CHANNEL_CHOICES,
        'pricing_data_view': pricing_data_view,
    })


def _to_decimal_or_none(value):
    """Parse a form value to Decimal, or None if blank/invalid."""
    from decimal import Decimal, InvalidOperation
    if value is None:
        return None
    v = str(value).strip()
    if v == '':
        return None
    try:
        return Decimal(v.replace(',', '.'))
    except (InvalidOperation, ValueError):
        return None


def _guess_multiplier_param(yaml_params, yaml_mults):
    """Return the param name whose options match the multiplier keys."""
    if not yaml_mults:
        return ''
    keys = {str(k) for k in yaml_mults.keys()}
    for p in yaml_params:
        opts = {str(o) for o in (p.get('options') or [])}
        if opts and (opts & keys):
            return p.get('name', '')
    return ''


@superadmin_required
def backup_now(request):
    """Create a database backup and stream it back as a download.

    Engine-aware (SQLite or PostgreSQL) — see core.db_backup.
    """
    if request.method != 'POST':
        return HttpResponseForbidden()
    from django.http import FileResponse
    from core.db_backup import perform_backup
    try:
        backup_path = perform_backup()
    except Exception as exc:
        messages.error(request, f"Échec de la sauvegarde: {exc}")
        return redirect_back(request, 'dashboard:superadmin')
    return FileResponse(
        open(str(backup_path), 'rb'),
        as_attachment=True,
        filename=backup_path.name,
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
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as DjangoValidationError

    username = (request.POST.get('username') or '').strip()
    email = (request.POST.get('email') or '').strip()
    role = request.POST.get('role') or 'REQUESTER'
    password = request.POST.get('password') or ''
    valid_roles = {r for r, _ in User.ROLE_CHOICES}

    if not username:
        messages.error(request, "Le nom d'utilisateur est obligatoire.")
        return redirect_back(request, 'dashboard:superadmin')
    if role not in valid_roles:
        messages.error(request, "Rôle invalide.")
        return redirect_back(request, 'dashboard:superadmin')
    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, f"Le nom d'utilisateur « {username} » existe déjà.")
        return redirect_back(request, 'dashboard:superadmin')
    if email and User.objects.filter(email__iexact=email).exists():
        messages.error(request, f"L'email « {email} » est déjà utilisé.")
        return redirect_back(request, 'dashboard:superadmin')
    try:
        validate_password(password)
    except DjangoValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect_back(request, 'dashboard:superadmin')

    user = User(
        username=username,
        first_name=(request.POST.get('first_name') or '').strip(),
        last_name=(request.POST.get('last_name') or '').strip(),
        email=email,
        role=role,
        organization=(request.POST.get('organization') or '').strip(),
        phone=(request.POST.get('phone') or '').strip(),
    )
    user.set_password(password)
    user.save()
    # MemberProfile is auto-created by the accounts post_save signal for MEMBER.
    messages.success(request, f"Utilisateur {user.get_full_name() or user.username} créé avec succès.")
    return redirect_back(request, 'dashboard:superadmin')


# --- Task 2: Edit User ---
@superadmin_required
def user_edit(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        new_email = (request.POST.get('email') or user_obj.email).strip()
        new_role = request.POST.get('role') or user_obj.role
        valid_roles = {r for r, _ in User.ROLE_CHOICES}
        if new_role not in valid_roles:
            messages.error(request, "Rôle invalide.")
            return redirect_back(request, 'dashboard:superadmin')
        if new_email and new_email.lower() != (user_obj.email or '').lower():
            if User.objects.filter(email__iexact=new_email).exclude(pk=user_obj.pk).exists():
                messages.error(request, f"L'email « {new_email} » est déjà utilisé.")
                return redirect_back(request, 'dashboard:superadmin')

        new_pass = (request.POST.get('new_password') or '').strip()
        if new_pass:
            try:
                validate_password(new_pass, user=user_obj)
            except DjangoValidationError as e:
                messages.error(request, " ".join(e.messages))
                return redirect_back(request, 'dashboard:superadmin')

        user_obj.first_name = request.POST.get('first_name', user_obj.first_name)
        user_obj.last_name = request.POST.get('last_name', user_obj.last_name)
        user_obj.email = new_email
        user_obj.role = new_role
        user_obj.organization = request.POST.get('organization', user_obj.organization or '')
        user_obj.phone = request.POST.get('phone', user_obj.phone or '')
        user_obj.laboratory = request.POST.get('laboratory', user_obj.laboratory or '')
        user_obj.supervisor = request.POST.get('supervisor', user_obj.supervisor or '')
        user_obj.student_level = request.POST.get('student_level', user_obj.student_level or '')
        if new_pass:
            user_obj.set_password(new_pass)
        user_obj.save()
        # MemberProfile auto-created by signal when role becomes MEMBER.
        messages.success(request, f"Utilisateur {user_obj.get_full_name() or user_obj.username} mis à jour.")
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
    try:
        validate_upload(upload, 'docx_template')
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
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
        lang=settings.LANGUAGE_CODE,
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
    """Restore the live database from an uploaded backup.

    Engine-aware: SQLite expects a `.db` file; PostgreSQL expects a
    `pg_dump --format=custom` archive. The file is validated before any
    destructive operation runs.
    """
    if request.method != 'POST' or 'db_file' not in request.FILES:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect_back(request, 'dashboard:superadmin')
    from pathlib import Path
    from core.db_backup import perform_restore

    upload = request.FILES['db_file']
    temp_dir = settings.BASE_DIR / 'data'
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f'restore_upload_{upload.name}'
    with open(str(temp_path), 'wb') as f:
        for chunk in upload.chunks():
            f.write(chunk)

    try:
        perform_restore(temp_path)
    except ValueError as e:
        Path(temp_path).unlink(missing_ok=True)
        messages.error(request, f"Fichier de sauvegarde invalide : {e}")
        return redirect_back(request, 'dashboard:superadmin')
    except Exception as e:
        Path(temp_path).unlink(missing_ok=True)
        messages.error(request, f"Échec de la restauration : {e}")
        return redirect_back(request, 'dashboard:superadmin')

    # SQLite restore moves the temp into place; Postgres leaves it — clean up.
    Path(temp_path).unlink(missing_ok=True)
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
            except Exception:
                pass

        messages.success(
            request,
            _("Le compte de %(username)s a été réinitialisé avec succès. Un email contenant les instructions a été envoyé.") % {'username': target_user.username}
        )
        return redirect_back(request, 'dashboard:superadmin')

    # GET: confirmation page
    return render(request, 'dashboard/superadmin/reset_account_confirm.html', {
        'target_user': target_user,
    })
