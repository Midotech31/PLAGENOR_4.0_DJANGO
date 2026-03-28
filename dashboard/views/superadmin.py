from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User, MemberProfile, Technique
from core.models import Service, Request, PlatformContent
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
def revenue_archives(request):
    """Display monthly revenue archives."""
    from core.models import RevenueArchive

    archives = RevenueArchive.objects.order_by('-year', '-month')

    context = {
        'archives': archives,
        'now': timezone.now(),
    }
    return render(request, 'dashboard/superadmin/revenue_archives.html', context)
