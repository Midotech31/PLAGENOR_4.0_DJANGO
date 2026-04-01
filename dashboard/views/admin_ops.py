import logging
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.db.models import Count, Sum, Q, Avg, Case, When, IntegerField, Value
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.translation import gettext_lazy as _, gettext
from django.conf import settings
from dashboard.decorators import admin_required

logger = logging.getLogger('plagenor')

from accounts.models import MemberProfile, Cheer, PointsHistory
from core.models import Request, RequestHistory, RequestComment, Invoice, PaymentSettings
from core.workflow import get_allowed_transitions, transition
from core.assignment import get_recommended_members
from core.registry import get_service_def
from core.pricing import calculate_price
from core.exceptions import InvalidTransitionError, AuthorizationError
from core.audit import log_action
from notifications.models import Notification
from dashboard.utils import redirect_back, paginate_queryset

from datetime import timedelta
import csv
import io


# =============================================================================
# ACTIVITY LOG VIEW (Task 1)
# =============================================================================

@admin_required
def activity_log(request):
    """Paginated audit log view for PLATFORM_ADMIN showing request-related actions."""
    from django.db.models import Q
    
    # Filter for request-related actions only
    action_types = [
        'TRANSITION', 'ASSIGNMENT', 'COST_ADJUSTMENT', 'REPORT_VALIDATION',
        'STATUS_CHANGE', 'MEMBER_ASSIGNED'
    ]
    
    # Build query for RequestHistory entries (status transitions)
    history_qs = RequestHistory.objects.select_related(
        'request', 'actor'
    ).filter(
        Q(to_status__isnull=False)
    ).order_by('-created_at')
    
    # Apply filters
    action_filter = request.GET.get('action', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_q = request.GET.get('q', '')
    
    if action_filter:
        history_qs = history_qs.filter(to_status=action_filter)
    
    if date_from:
        history_qs = history_qs.filter(created_at__date__gte=date_from)
    
    if date_to:
        history_qs = history_qs.filter(created_at__date__lte=date_to)
    
    if search_q:
        history_qs = history_qs.filter(
            Q(request__display_id__icontains=search_q) |
            Q(request__title__icontains=search_q) |
            Q(actor__first_name__icontains=search_q) |
            Q(actor__last_name__icontains=search_q)
        )
    
    paginator, activity_logs, _ = paginate_queryset(history_qs, request, per_page=50, page_param='log_page')
    
    context = {
        'activity_logs': activity_logs,
        'paginator': paginator,
        'status_choices': Request.STATUS_CHOICES,
        'action_filter': action_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_q': search_q,
    }
    return render(request, 'dashboard/admin_ops/activity_log.html', context)


# =============================================================================
# NOTIFICATION BELL API (Task 2)
# =============================================================================

@admin_required
def notifications_api(request):
    """API endpoint for notification bell - returns JSON for AJAX dropdown."""
    if request.method == 'GET':
        # Get unread count
        unread_count = Notification.objects.filter(user=request.user, read=False).count()
        
        # Get recent notifications (last 20)
        recent = Notification.objects.filter(user=request.user).select_related(
            'request'
        ).order_by('-created_at')[:20]
        
        notifications_data = []
        for notif in recent:
            notifications_data.append({
                'id': notif.id,
                'message': notif.message,
                'notification_type': notif.notification_type,
                'read': notif.read,
                'created_at': notif.created_at.strftime('%d/%m/%Y %H:%M'),
                'link_url': notif.get_absolute_url(),
                'request_display_id': notif.request.display_id if notif.request else None,
            })
        
        return JsonResponse({
            'unread_count': unread_count,
            'notifications': notifications_data,
        })
    
    elif request.method == 'POST':
        action = request.POST.get('action', '')
        
        if action == 'mark_all_read':
            Notification.objects.filter(user=request.user, read=False).update(
                read=True, read_at=timezone.now()
            )
            return JsonResponse({'success': True, 'message': 'All notifications marked as read'})
        
        elif action == 'mark_read':
            notif_id = request.POST.get('notification_id')
            if notif_id:
                Notification.objects.filter(id=notif_id, user=request.user).update(
                    read=True, read_at=timezone.now()
                )
                return JsonResponse({'success': True})
        
        return JsonResponse({'success': False, 'error': 'Invalid action'})


# =============================================================================
# USER OVERSIGHT TAB (Task 3)
# =============================================================================

@admin_required
def users_list(request):
    """List all registered students and clients with filtering and search."""
    from accounts.models import User
    
    # Base queryset - exclude admin roles
    users_qs = User.objects.exclude(
        role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE']
    ).order_by('-date_joined')
    
    # Filters
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_q = request.GET.get('q', '')
    
    if role_filter:
        users_qs = users_qs.filter(role=role_filter)
    
    if status_filter:
        if status_filter == 'active':
            users_qs = users_qs.filter(is_active=True)
        elif status_filter == 'inactive':
            users_qs = users_qs.filter(is_active=False)
    
    if date_from:
        users_qs = users_qs.filter(date_joined__date__gte=date_from)
    
    if date_to:
        users_qs = users_qs.filter(date_joined__date__lte=date_to)
    
    if search_q:
        users_qs = users_qs.filter(
            Q(first_name__icontains=search_q) |
            Q(last_name__icontains=search_q) |
            Q(email__icontains=search_q) |
            Q(username__icontains=search_q)
        )
    
    # Annotate with request counts
    users_qs = users_qs.annotate(
        total_requests=Count('request'),
    ).annotate(
        last_submission=Count(
            'request',
            filter=Q(request__created_at__isnull=False),
            output_field=Case(
                When(Q(request__created_at__isnull=False), then='request__created_at'),
                default=Value(None),
                output_field=timezone.datetime,
            )
        )
    )
    
    paginator, users, _ = paginate_queryset(users_qs, request, per_page=25, page_param='users_page')
    
    context = {
        'users': users,
        'paginator': paginator,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_q': search_q,
    }
    return render(request, 'dashboard/admin_ops/users_list.html', context)


@admin_required
def user_detail(request, pk):
    """Detail view showing a user's complete request history."""
    from accounts.models import User
    
    user = get_object_or_404(User, pk=pk)
    
    # Get all requests by this user
    requests_qs = Request.objects.filter(
        Q(requester=user) | Q(guest_email=user.email)
    ).select_related('service', 'assigned_to__user').order_by('-created_at')
    
    paginator, requests, _ = paginate_queryset(requests_qs, request, per_page=25, page_param='req_page')
    
    # Request statistics
    stats = requests_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE', 'REPORT_UPLOADED', 'ADMIN_REVIEW'])),
        completed=Count('id', filter=Q(status='COMPLETED')),
    )
    
    context = {
        'viewed_user': user,
        'requests': requests,
        'paginator': paginator,
        'stats': stats,
    }
    return render(request, 'dashboard/admin_ops/user_detail.html', context)


# =============================================================================
# MAIN DASHBOARD INDEX (Enhanced KPIs + Overdue Alerts)
# =============================================================================

@admin_required
def index(request):
    """Main admin operations dashboard with enhanced KPIs and overdue alerts."""
    
    # Consolidate count queries into single aggregated query
    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)
    
    request_stats = Request.objects.aggregate(
        total_requests=Count('id'),
        pending_count=Count(
            'id',
            filter=Q(status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED', 'ADMIN_REVIEW'])
        ),
        ibtikar_count=Count('id', filter=Q(channel='IBTIKAR')),
        genoclab_count=Count('id', filter=Q(channel='GENOCLAB')),
        completed_count=Count('id', filter=Q(status='COMPLETED')),
    )
    
    total_requests = request_stats['total_requests']
    pending_count = request_stats['pending_count']
    ibtikar_count = request_stats['ibtikar_count']
    genoclab_count = request_stats['genoclab_count']
    completed_count = request_stats['completed_count']
    
    # Channel-specific pending counts
    pending_by_channel = {
        'ibtikar': Request.objects.filter(
            channel='IBTIKAR',
            status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED', 'ADMIN_REVIEW']
        ).count(),
        'genoclab': Request.objects.filter(
            channel='GENOCLAB',
            status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'REPORT_UPLOADED', 'ADMIN_REVIEW']
        ).count(),
    }
    
    # Overdue requests (stuck in same status for > 7 days)
    overdue_requests = Request.objects.filter(
        status__in=['SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE', 
                    'PLATFORM_NOTE_GENERATED', 'REPORT_UPLOADED', 'ADMIN_REVIEW',
                    'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
                    'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED'],
        updated_at__lt=seven_days_ago
    ).exclude(
        status__in=['COMPLETED', 'CLOSED', 'ARCHIVED', 'REJECTED', 'CANCELLED']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('updated_at')[:20]
    
    # Pending requests needing action - paginated
    pending_qs = Request.objects.filter(
        status__in=[
            'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'PLATFORM_NOTE_GENERATED',
            'REPORT_UPLOADED', 'ADMIN_REVIEW', 'REPORT_VALIDATED',
            'COMPLETED',
            'REQUEST_CREATED', 'QUOTE_DRAFT', 'QUOTE_SENT',
            'QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED', 'PAYMENT_CONFIRMED',
            'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
        ]
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')
    pending_paginator, pending_requests, _ = paginate_queryset(pending_qs, request, per_page=25, page_param='pending_page')

    # Requests needing validation - paginated
    validation_qs = Request.objects.filter(
        status__in=[
            'SUBMITTED', 'VALIDATION_PEDAGOGIQUE', 'VALIDATION_FINANCE',
            'REQUEST_CREATED', 'QUOTE_DRAFT', 'QUOTE_SENT',
            'QUOTE_VALIDATED_BY_CLIENT', 'INVOICE_GENERATED',
        ]
    ).select_related('service', 'requester').order_by('-created_at')
    validation_paginator, validation_requests, _ = paginate_queryset(validation_qs, request, per_page=25, page_param='validation_page')

    # Requests ready for assignment - paginated
    assignable_qs = Request.objects.filter(
        status__in=['IBTIKAR_CODE_SUBMITTED', 'PAYMENT_CONFIRMED', 'ORDER_UPLOADED']
    ).select_related('service', 'requester').order_by('-created_at')
    assignable_paginator, assignable_requests, _ = paginate_queryset(assignable_qs, request, per_page=25, page_param='assignable_page')

    # Requests needing report review - paginated
    review_qs = Request.objects.filter(
        status__in=['REPORT_UPLOADED', 'ADMIN_REVIEW']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-created_at')
    review_paginator, review_requests, _ = paginate_queryset(review_qs, request, per_page=25, page_param='review_page')

    # In-progress requests - paginated
    in_progress_qs = Request.objects.filter(
        status__in=[
            'ASSIGNED', 'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED',
            'SAMPLE_RECEIVED', 'ANALYSIS_STARTED', 'ANALYSIS_FINISHED',
        ]
    ).select_related('service', 'requester', 'assigned_to__user').prefetch_related('messages__from_user').order_by('-updated_at')
    in_progress_paginator, in_progress_requests, _ = paginate_queryset(in_progress_qs, request, per_page=25, page_param='in_progress_page')

    # Requests needing completion/closure actions - paginated
    completion_qs = Request.objects.filter(
        status__in=['REPORT_VALIDATED', 'COMPLETED']
    ).select_related('service', 'requester', 'assigned_to__user').order_by('-updated_at')
    completion_paginator, completion_requests, _ = paginate_queryset(completion_qs, request, per_page=25, page_param='completion_page')

    # All requests with optional filters
    channel_filter = request.GET.get('channel', '')
    status_filter = request.GET.get('status', '')
    search_q = request.GET.get('q', '')

    all_requests = Request.objects.select_related('service', 'requester', 'assigned_to__user')
    if channel_filter:
        all_requests = all_requests.filter(channel=channel_filter)
    if status_filter:
        all_requests = all_requests.filter(status=status_filter)
    if search_q:
        all_requests = all_requests.filter(
            Q(display_id__icontains=search_q) | Q(title__icontains=search_q)
        )
    all_requests_qs = all_requests.order_by('-created_at')
    all_requests_paginator, all_requests_page, _ = paginate_queryset(all_requests_qs, request, per_page=25, page_param='all_page')

    # Available members for assignment
    recommended_members = get_recommended_members(limit=20)
    available_members = MemberProfile.objects.filter(
        available=True
    ).select_related('user').order_by('current_load')

    # All members sorted by performance
    all_members_ranked = MemberProfile.objects.select_related('user').order_by(
        '-productivity_score', '-total_points'
    )
    max_productivity = max((m.productivity_score for m in all_members_ranked), default=100) or 100
    max_points = max((m.total_points for m in all_members_ranked), default=1) or 1

    # Budget overview
    from core.financial import get_budget_dashboard
    budget_data = get_budget_dashboard()
    ibtikar_budget = budget_data['ibtikar']['total']
    genoclab_revenue = budget_data['genoclab']['total']

    # Ratings & Reviews
    rated_requests = Request.objects.filter(service_rating__isnull=False)
    avg_rating = rated_requests.aggregate(avg=Avg('service_rating'))['avg'] or 0
    total_ratings = rated_requests.count()
    recent_reviews_qs = rated_requests.select_related('requester', 'service').order_by('-rated_at')
    reviews_paginator, recent_reviews, _ = paginate_queryset(recent_reviews_qs, request, per_page=10, page_param='reviews_page')

    rating_stats = rated_requests.aggregate(
        one_star=Count(Case(When(service_rating=1, then=1))),
        two_star=Count(Case(When(service_rating=2, then=1))),
        three_star=Count(Case(When(service_rating=3, then=1))),
        four_star=Count(Case(When(service_rating=4, then=1))),
        five_star=Count(Case(When(service_rating=5, then=1)))
    )
    rating_distribution = {1: rating_stats['one_star'], 2: rating_stats['two_star'], 3: rating_stats['three_star'], 4: rating_stats['four_star'], 5: rating_stats['five_star']}
    rating_percentages = {star: round((rating_distribution[star] / total_ratings * 100), 1) if total_ratings > 0 else 0 for star in range(1, 6)}
    
    # Notification count for bell
    unread_notifications = Notification.objects.filter(user=request.user, read=False).count()
    
    context = {
        'total_requests': total_requests,
        'pending_count': pending_count,
        'ibtikar_count': ibtikar_count,
        'genoclab_count': genoclab_count,
        'completed_count': completed_count,
        'pending_by_channel': pending_by_channel,
        'overdue_requests': overdue_requests,
        'pending_requests': pending_requests,
        'pending_paginator': pending_paginator,
        'validation_requests': validation_requests,
        'validation_paginator': validation_paginator,
        'assignable_requests': assignable_requests,
        'assignable_paginator': assignable_paginator,
        'review_requests': review_requests,
        'review_paginator': review_paginator,
        'in_progress_requests': in_progress_requests,
        'in_progress_paginator': in_progress_paginator,
        'completion_requests': completion_requests,
        'completion_paginator': completion_paginator,
        'all_requests': all_requests_page,
        'all_requests_paginator': all_requests_paginator,
        'available_members': available_members,
        'recommended_members': recommended_members,
        'ibtikar_budget': ibtikar_budget,
        'genoclab_revenue': genoclab_revenue,
        'budget_data': budget_data,
        'channel_filter': channel_filter,
        'status_filter': status_filter,
        'search_q': search_q,
        'status_choices': Request.STATUS_CHOICES,
        'now': now,
        # Ratings
        'avg_rating': avg_rating,
        'total_ratings': total_ratings,
        'recent_reviews': recent_reviews,
        'reviews_paginator': reviews_paginator,
        'rating_distribution': rating_distribution,
        'rating_percentages': rating_percentages,
        # Performance ranking
        'all_members_ranked': all_members_ranked,
        'max_productivity': max_productivity,
        'max_points': max_points,
        # Notifications
        'unread_notifications': unread_notifications,
    }
    return render(request, 'dashboard/admin_ops/index.html', context)


# =============================================================================
# REQUEST DETAIL (Task 5 - User Request History)
# =============================================================================

@admin_required
def request_detail(request, pk):
    """Full request preview with user history section."""
    from core.models import Message

    req = get_object_or_404(Request, pk=pk)
    history = req.history.select_related('actor').order_by('created_at')
    comments = req.comments.select_related('author').order_by('created_at')
    messages_list = Message.objects.filter(request=req).select_related('from_user', 'to_user').order_by('created_at')
    allowed = get_allowed_transitions(req)

    # Get requester's previous submissions (user history)
    user_history = []
    if req.requester:
        user_history = Request.objects.filter(
            requester=req.requester
        ).exclude(
            pk=req.pk
        ).select_related('service').order_by('-created_at')[:10]

    # Load YAML service definition
    yaml_def = None
    if req.service:
        yaml_def = get_service_def(req.service.code)

    context = {
        'req': req,
        'history': history,
        'comments': comments,
        'messages_list': messages_list,
        'allowed_transitions': allowed,
        'yaml_def': yaml_def,
        'available_members': MemberProfile.objects.filter(available=True).select_related('user'),
        'status_choices': Request.STATUS_CHOICES,
        'now': timezone.now(),
        'user_history': user_history,
    }
    return render(request, 'dashboard/admin_ops/request_detail.html', context)


# =============================================================================
# TRANSITION REQUEST (Enhanced with AJAX)
# =============================================================================

@admin_required
def transition_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    to_status = request.POST.get('to_status', '')
    notes = request.POST.get('notes', '')
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        transition(req, to_status, request.user, notes=notes)
        
        # Log to audit
        log_action(
            action='STATUS_CHANGE',
            entity_type='REQUEST',
            entity_id=str(req.id),
            actor=request.user,
            details={'to_status': to_status, 'notes': notes}
        )
        
        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': gettext("Request %(display_id)s transitioned to %(status)s") % {'display_id': req.display_id, 'status': to_status},
                'new_status': req.get_status_display()
            })

        messages.success(request, gettext("Request %(display_id)s transitioned to %(status)s.") % {'display_id': req.display_id, 'status': to_status})
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, str(e))
    
    return redirect_back(request, 'dashboard:admin_ops')


# =============================================================================
# BULK ACTIONS (Task 6)
# =============================================================================

@admin_required
@require_POST
def bulk_action(request):
    """Bulk assign or status transition for multiple requests."""
    action = request.POST.get('action', '')
    request_ids = request.POST.getlist('request_ids', [])
    
    if not request_ids:
        messages.error(request, gettext("No requests selected."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    success_count = 0
    errors = []
    
    if action == 'bulk_assign':
        member_id = request.POST.get('member_id')
        if not member_id:
            if is_ajax:
                return JsonResponse({'success': False, 'error': gettext('Member required for assignment')})
            messages.error(request, gettext("Please select a member for assignment."))
            return redirect_back(request, 'dashboard:admin_ops')

        member = get_object_or_404(MemberProfile, pk=member_id)

        for req_id in request_ids:
            try:
                req = Request.objects.get(pk=req_id)
                if req.status in ('IBTIKAR_CODE_SUBMITTED', 'PAYMENT_CONFIRMED', 'ORDER_UPLOADED'):
                    req.assigned_to = member
                    req.save(update_fields=['assigned_to'])
                    transition(req, 'ASSIGNED', request.user, notes=gettext("Bulk assign to %(member)s") % {'member': member.user.get_full_name()})
                    success_count += 1
            except Exception as e:
                errors.append(f"{req_id}: {str(e)}")

        msg = gettext("Assigned %(count)s requests to %(member)s") % {'count': success_count, 'member': member.user.get_full_name()}

    elif action == 'bulk_transition':
        to_status = request.POST.get('to_status', '')
        if not to_status:
            if is_ajax:
                return JsonResponse({'success': False, 'error': gettext('Status required for transition')})
            messages.error(request, gettext("Please select a target status."))
            return redirect_back(request, 'dashboard:admin_ops')

        for req_id in request_ids:
            try:
                req = Request.objects.get(pk=req_id)
                transition(req, to_status, request.user, notes=gettext('Bulk transition'))
                success_count += 1
            except Exception as e:
                errors.append(f"{req_id}: {str(e)}")

        msg = gettext("Transitioned %(count)s requests to %(status)s") % {'count': success_count, 'status': to_status}

    else:
        if is_ajax:
            return JsonResponse({'success': False, 'error': gettext('Invalid action')})
        messages.error(request, gettext("Invalid bulk action."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': msg,
            'success_count': success_count,
            'errors': errors
        })
    
    if errors:
        messages.warning(request, f"{msg}. {len(errors)} errors occurred.")
    else:
        messages.success(request, msg)
    
    return redirect_back(request, 'dashboard:admin_ops')


# =============================================================================
# CSV EXPORT (Task 6)
# =============================================================================

@admin_required
def export_requests_csv(request):
    """Export filtered request list to CSV."""
    channel_filter = request.GET.get('channel', '')
    status_filter = request.GET.get('status', '')
    search_q = request.GET.get('q', '')
    
    queryset = Request.objects.select_related('service', 'requester', 'assigned_to__user')
    
    if channel_filter:
        queryset = queryset.filter(channel=channel_filter)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if search_q:
        queryset = queryset.filter(
            Q(display_id__icontains=search_q) | Q(title__icontains=search_q)
        )
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="requests_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Display ID', 'Title', 'Channel', 'Status', 'Service',
        'Requester', 'Assigned To', 'Created At', 'Updated At',
        'Budget Amount', 'Quote Amount', 'Validated Price'
    ])
    
    for req in queryset.order_by('-created_at'):
        writer.writerow([
            req.display_id,
            req.title,
            req.get_channel_display(),
            req.get_status_display(),
            req.service.name if req.service else '',
            req.requester.get_full_name() if req.requester else '',
            req.assigned_to.user.get_full_name() if req.assigned_to else '',
            req.created_at.strftime('%Y-%m-%d %H:%M'),
            req.updated_at.strftime('%Y-%m-%d %H:%M'),
            req.budget_amount or '',
            req.quote_amount or '',
            req.admin_validated_price or '',
        ])
    
    return response


from django.http import HttpResponse


# =============================================================================
# ASSIGN REQUEST (Enhanced with AJAX)
# =============================================================================

@admin_required
def assign_request(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    member_id = request.POST.get('member_id')
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if not member_id:
        if is_ajax:
            return JsonResponse({'success': False, 'error': gettext('Please select an analyst')})
        messages.error(request, gettext("Please select an analyst."))
        return redirect_back(request, 'dashboard:admin_ops')

    member = get_object_or_404(MemberProfile, pk=member_id)

    if req.status not in ('IBTIKAR_CODE_SUBMITTED', 'PAYMENT_CONFIRMED', 'ORDER_UPLOADED'):
        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': gettext("Request %(display_id)s is not ready for assignment (current status: %(status)s)") % {'display_id': req.display_id, 'status': req.get_status_display()}
            })
        messages.error(
            request,
            gettext("Request %(display_id)s is not ready for assignment (current status: %(status)s).") % {'display_id': req.display_id, 'status': req.get_status_display()}
        )
        return redirect_back(request, 'dashboard:admin_ops')

    req.assigned_to = member
    req.save(update_fields=['assigned_to'])
    try:
        transition(req, 'PENDING_ACCEPTANCE', request.user, notes=gettext("Assigned to %(member)s") % {'member': member.user.get_full_name()})
        
        # Log to audit
        log_action(
            action='MEMBER_ASSIGNED',
            entity_type='REQUEST',
            entity_id=str(req.id),
            actor=request.user,
            details={'member': member.user.get_full_name()}
        )
        
        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': gettext("Request %(display_id)s assigned to %(member)s") % {'display_id': req.display_id, 'member': member.user.get_full_name()},
                'assigned_to': member.user.get_full_name()
            })
        messages.success(request, gettext("Request %(display_id)s assigned to %(member)s.") % {'display_id': req.display_id, 'member': member.user.get_full_name()})
    except (InvalidTransitionError, AuthorizationError, ValueError) as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, gettext("Assignment error: %(error)s") % {'error': str(e)})
    
    return redirect_back(request, 'dashboard:admin_ops')


# =============================================================================
# AWARD POINTS (Enhanced with AJAX - Task 6)
# =============================================================================

@admin_required
def award_points(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    member = get_object_or_404(MemberProfile, pk=member_pk)
    points = int(request.POST.get('points', 0))
    reason = request.POST.get('reason', '')
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if points <= 0:
        if is_ajax:
            return JsonResponse({'success': False, 'error': gettext('Points must be positive')})
        messages.error(request, gettext("Points must be positive."))
        return redirect_back(request, 'dashboard:admin_ops')

    PointsHistory.objects.create(
        member=member, points=points, reason=reason, awarded_by=request.user
    )
    member.total_points += points

    # Auto-unlock gift box at 100 points threshold
    if member.total_points >= 100 and not member.gift_unlocked:
        member.gift_unlocked = True
        Notification.objects.create(
            user=member.user,
            message=gettext("🎁 Congratulations! You unlocked a surprise gift box! Visit your Points space."),
            notification_type='reward'
        )
    
    # Calculate reward milestone
    reward_milestone = (member.total_points // 1000) * 1000
    next_milestone = reward_milestone + 1000
    
    member.save(update_fields=['total_points', 'gift_unlocked'])
    
    # Notify member
    Notification.objects.create(
        user=member.user,
        message=gettext("%(points)s points received! %(reason)s") % {'points': points, 'reason': reason} if reason else gettext("%(points)s points received!") % {'points': points},
        notification_type='reward'
    )
    
    # Log to audit
    log_action(
        action='POINTS_AWARDED',
        entity_type='MEMBER',
        entity_id=str(member.id),
        actor=request.user,
        details={'points': points, 'reason': reason, 'total': member.total_points}
    )
    
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': gettext("%(points)s points awarded to %(member)s") % {'points': points, 'member': member.user.get_full_name()},
            'new_total': member.total_points,
            'milestone': reward_milestone,
            'next_milestone': next_milestone,
            'gift_unlocked': member.gift_unlocked
        })

    messages.success(request, gettext("%(points)s points awarded to %(member)s.") % {'points': points, 'member': member.user.get_full_name()})
    return redirect_back(request, 'dashboard:admin_ops')


# =============================================================================
# PERFORMANCE & POINTS REWARD SYSTEM (Task 7)
# =============================================================================

@admin_required
def performance_points(request):
    """Performance & Points reward system dashboard for admin."""
    from django.db.models import Func, F
    
    # Get all members with their performance data
    members_qs = MemberProfile.objects.select_related('user').order_by('-total_points')
    
    # Calculate efficiency rates and completed services for each member
    members_data = []
    for member in members_qs:
        # Get completed services count
        completed_services = Request.objects.filter(
            assigned_to=member,
            status='COMPLETED'
        ).count()
        
        # Get total assigned services
        total_services = Request.objects.filter(
            assigned_to=member,
            status__in=['ASSIGNED', 'COMPLETED', 'CLOSED']
        ).count()
        
        # Calculate efficiency (completed before deadline)
        early_completions = Request.objects.filter(
            assigned_to=member,
            status='COMPLETED',
            updated_at__lt=F('declared_deadline')
        ).count() if member.user else 0
        
        efficiency_rate = round((early_completions / completed_services * 100), 1) if completed_services > 0 else 0
        
        # Calculate milestone progress
        current_milestone = (member.total_points // 1000) * 1000
        next_milestone = current_milestone + 1000
        progress_to_next = member.total_points - current_milestone
        progress_percentage = (progress_to_next / 1000) * 100
        
        # Count reward boxes
        reward_boxes = member.total_points // 1000
        
        members_data.append({
            'member': member,
            'completed_services': completed_services,
            'total_services': total_services,
            'efficiency_rate': efficiency_rate,
            'current_milestone': current_milestone,
            'next_milestone': next_milestone,
            'progress_to_next': progress_to_next,
            'progress_percentage': progress_percentage,
            'reward_boxes': reward_boxes,
        })
    
    # Sorting options
    sort_by = request.GET.get('sort', 'total_points')
    if sort_by == 'efficiency':
        members_data.sort(key=lambda x: x['efficiency_rate'], reverse=True)
    elif sort_by == 'services':
        members_data.sort(key=lambda x: x['completed_services'], reverse=True)
    elif sort_by == 'recent':
        members_data.sort(key=lambda x: x['member'].user.date_joined, reverse=True)
    
    # Filters
    min_points = request.GET.get('min_points', '')
    max_points = request.GET.get('max_points', '')
    
    if min_points:
        members_data = [m for m in members_data if m['member'].total_points >= int(min_points)]
    if max_points:
        members_data = [m for m in members_data if m['member'].total_points <= int(max_points)]
    
    # Pagination
    paginator, members_page, _ = paginate_queryset(members_data, request, per_page=25, page_param='perf_page')
    
    context = {
        'members_data': members_page,
        'paginator': paginator,
        'sort_by': sort_by,
        'min_points': min_points,
        'max_points': max_points,
    }
    return render(request, 'dashboard/admin_ops/performance_points.html', context)


@admin_required
def member_points_detail(request, member_pk):
    """Detailed points history for a member with manual bonus award form."""
    member = get_object_or_404(MemberProfile, pk=member_pk)
    
    # Points history
    points_history = PointsHistory.objects.filter(
        member=member
    ).select_related('awarded_by').order_by('-created_at')
    
    # Calculate milestones reached
    reward_boxes = member.total_points // 1000
    
    # Get completed services
    completed_services = Request.objects.filter(
        assigned_to=member,
        status='COMPLETED'
    ).count()
    
    # Early completions for efficiency bonus
    early_completions = Request.objects.filter(
        assigned_to=member,
        status='COMPLETED'
    ).exclude(
        declared_deadline__isnull=True
    ).count()
    
    context = {
        'member': member,
        'points_history': points_history,
        'reward_boxes': reward_boxes,
        'completed_services': completed_services,
    }
    return render(request, 'dashboard/admin_ops/member_points_detail.html', context)


# =============================================================================
# REMAINING VIEWS (unchanged except for internationalization)
# =============================================================================

@admin_required
def upload_gift(request, member_pk):
    """Admin uploads a reward picture into the member's gift box."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    gift_image = request.FILES.get('gift_image')
    if gift_image:
        member.gift_image = gift_image
        member.gift_unlocked = True
        member.gift_collected = False
        member.save(update_fields=['gift_image', 'gift_unlocked', 'gift_collected'])
        Notification.objects.create(
            user=member.user,
            message=gettext("🎁 A reward awaits you! Open your surprise box in your Points space."),
            notification_type='reward'
        )
        messages.success(request, gettext("Reward added for %(member)s.") % {'member': member.user.get_full_name()})
    else:
        messages.error(request, gettext("Please select an image."))
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def send_cheer(request, member_pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    member = get_object_or_404(MemberProfile, pk=member_pk)
    message_text = request.POST.get('message', '')
    Cheer.objects.create(member=member, message=message_text, from_user=request.user)
    Notification.objects.create(
        user=member.user,
        message=gettext("Encouragement received: %(message)s") % {'message': message_text} if message_text else gettext("You received an encouragement!"),
        notification_type='reward'
    )
    messages.success(request, gettext("Encouragement sent to %(member)s.") % {'member': member.user.get_full_name()})
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def modify_appointment(request, pk):
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    if req.appointment_confirmed:
        messages.error(request, gettext("The appointment is already confirmed, cannot modify."))
        return redirect_back(request, 'dashboard:admin_ops')
    date_str = request.POST.get('appointment_date', '')
    if date_str:
        from datetime import datetime
        req.appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        req.save(update_fields=['appointment_date'])
        messages.success(request, gettext("Appointment date modified: %(date)s") % {'date': req.appointment_date})
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def report_review(request, pk):
    req = get_object_or_404(Request, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'validate':
            try:
                transition(req, 'REPORT_VALIDATED', request.user, notes=gettext('Report validated by admin'))

                # Log to audit
                log_action(
                    action='REPORT_VALIDATION',
                    entity_type='REQUEST',
                    entity_id=str(req.id),
                    actor=request.user,
                    details={'status': 'validated'}
                )

                messages.success(request, gettext("Report %(display_id)s validated.") % {'display_id': req.display_id})
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        elif action == 'send_back':
            revision_notes = request.POST.get('revision_notes', '')
            req.admin_revision_notes = revision_notes
            req.save(update_fields=['admin_revision_notes'])
            try:
                transition(
                    req, 'ANALYSIS_STARTED', request.user,
                    notes=gettext("Report sent back for revision. %(notes)s") % {'notes': revision_notes}.strip()
                )
                if req.assigned_to:
                    Notification.objects.create(
                        user=req.assigned_to.user,
                        message=gettext("%(display_id)s: Report sent back for revision. %(notes)s") % {'display_id': req.display_id, 'notes': revision_notes}.strip(),
                        request=req,
                        notification_type='WORKFLOW',
                    )
                messages.success(request, gettext("Report %(display_id)s sent back for revision.") % {'display_id': req.display_id})
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        return redirect_back(request, 'dashboard:admin_ops')
    allowed = get_allowed_transitions(req)
    return render(request, 'dashboard/admin_ops/report_review.html', {
        'req': req,
        'allowed_transitions': allowed,
    })


@admin_required
def adjust_cost(request, pk):
    """Admin adjusts the validated cost of a request with justification."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    req = get_object_or_404(Request, pk=pk)
    new_price = request.POST.get('admin_price', '')
    justification = request.POST.get('cost_justification', '')

    if not new_price:
        messages.error(request, gettext("Please enter an amount."))
        return redirect_back(request, 'dashboard:admin_ops')

    try:
        price = float(new_price)
    except ValueError:
        messages.error(request, gettext("Invalid amount."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    old_price = req.admin_validated_price or req.budget_amount or req.quote_amount
    req.admin_validated_price = price
    req.save(update_fields=['admin_validated_price'])

    # Log to audit
    log_action(
        action='COST_ADJUSTMENT',
        entity_type='REQUEST',
        entity_id=str(req.id),
        actor=request.user,
        details={
            'old_price': str(old_price),
            'new_price': str(price),
            'justification': justification,
        }
    )

    messages.success(request, gettext("Cost adjusted for %(display_id)s: %(price)s DA. %(justification)s") % {'display_id': req.display_id, 'price': f"{price:,.0f}", 'justification': gettext('Justification: %(justification)s') % {'justification': justification} if justification else ''})
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def prepare_quote(request, pk):
    """Admin prepares/edits a detailed quote for a GENOCLAB request."""
    req = get_object_or_404(Request, pk=pk)

    if request.method == 'POST':
        items = []
        idx = 0
        while f'item_label_{idx}' in request.POST:
            label = request.POST.get(f'item_label_{idx}', '')
            unit_price = float(request.POST.get(f'item_unit_price_{idx}', 0))
            quantity = int(request.POST.get(f'item_quantity_{idx}', 0))
            total = unit_price * quantity
            if label:
                items.append({
                    'label': label,
                    'unit_price': unit_price,
                    'quantity': quantity,
                    'total': total,
                })
            idx += 1

        admin_fees = float(request.POST.get('admin_fees', 0))
        report_fees = float(request.POST.get('report_fees', 0))
        vat_rate = float(request.POST.get('vat_rate', 19)) / 100
        notes = request.POST.get('quote_notes', '')

        subtotal_ht = sum(item['total'] for item in items)
        subtotal_before_tax = subtotal_ht + admin_fees + report_fees
        vat_amount = round(subtotal_before_tax * vat_rate, 2)
        total_ttc = round(subtotal_before_tax + vat_amount, 2)

        quote_detail = {
            'items': items,
            'subtotal_ht': subtotal_ht,
            'admin_fees': admin_fees,
            'report_fees': report_fees,
            'subtotal_before_tax': subtotal_before_tax,
            'vat_rate': vat_rate,
            'vat_amount': vat_amount,
            'total_ttc': total_ttc,
            'notes': notes,
        }

        req.quote_detail = quote_detail
        req.quote_amount = total_ttc
        req.save(update_fields=['quote_detail', 'quote_amount'])

        action = request.POST.get('action', 'save')
        if action == 'send':
            try:
                if req.status == 'REQUEST_CREATED':
                    transition(req, 'QUOTE_DRAFT', request.user, notes=gettext('Quote prepared'))
                if req.status == 'QUOTE_DRAFT':
                    transition(req, 'QUOTE_SENT', request.user, notes=gettext('Quote sent to client'))
                messages.success(request, gettext("Quote sent to client for %(display_id)s.") % {'display_id': req.display_id})
            except (InvalidTransitionError, AuthorizationError, ValueError) as e:
                messages.error(request, str(e))
        else:
            messages.success(request, gettext("Quote saved for %(display_id)s.") % {'display_id': req.display_id})
        
        return redirect_back(request, 'dashboard:admin_ops')

    # Load YAML service definition
    yaml_def = None
    if req.service:
        yaml_def = get_service_def(req.service.code)

    context = {
        'req': req,
        'yaml_def': yaml_def,
    }
    return render(request, 'dashboard/admin_ops/prepare_quote.html', context)


@admin_required
def generate_invoice(request, pk):
    """Generate invoice for a request."""
    from documents.generators import generate_invoice_pdf
    
    req = get_object_or_404(Request, pk=pk)
    if request.method == 'POST':
        try:
            # Create or get invoice
            invoice, created = Invoice.objects.get_or_create(
                request=req,
                defaults={
                    'invoice_number': f"INV-{req.display_id}-{timezone.now().strftime('%Y%m%d')}",
                    'client': req.requester,
                    'line_items': req.quote_detail.get('items', []) if req.quote_detail else [],
                    'subtotal_ht': req.quote_detail.get('subtotal_ht', 0) if req.quote_detail else req.quote_amount,
                }
            )
            
            # Generate PDF
            pdf_data = generate_invoice_pdf(invoice)

            response = HttpResponse(pdf_data, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="invoice-{invoice.invoice_number}.pdf"'
            return response

        except Exception as e:
            messages.error(request, gettext("Error generating invoice: %(error)s") % {'error': str(e)})
            return redirect_back(request, 'dashboard:admin_ops')
    
    return redirect_back(request, 'dashboard:admin_ops')


@admin_required
def confirm_payment(request, pk):
    """Confirm payment for a request."""
    if request.method != 'POST':
        return HttpResponseForbidden()
    
    req = get_object_or_404(Request, pk=pk)
    payment_receipt = request.FILES.get('payment_receipt')
    
    if payment_receipt:
        req.payment_receipt = payment_receipt
        req.payment_status = 'CONFIRMED'
        req.save(update_fields=['payment_receipt', 'payment_status'])

        try:
            transition(req, 'PAYMENT_CONFIRMED', request.user, notes=gettext('Payment confirmed by admin'))
            messages.success(request, gettext("Payment confirmed for %(display_id)s.") % {'display_id': req.display_id})
        except (InvalidTransitionError, AuthorizationError, ValueError) as e:
            messages.error(request, str(e))
    else:
        messages.error(request, gettext("Please upload a payment receipt."))

    return redirect_back(request, 'dashboard:admin_ops')


# =============================================================================
# GENOCLAB INVOICE WORKFLOW
# =============================================================================

@admin_required
def generate_genoclab_invoice(request, pk):
    """
    Generate an Excel invoice for a GENOCLAB request.
    The invoice is auto-generated with client info, service details, and payment info.
    Only Admin Ops can access this view.
    """
    from documents.generators import generate_invoice_excel
    from django.core.files.base import ContentFile
    
    req = get_object_or_404(Request, pk=pk)
    
    # Only for GENOCLAB channel
    if req.channel != 'GENOCLAB':
        messages.error(request, gettext("Invoice generation is only available for GENOCLAB requests."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    # Only allow after analysis is finished
    finished_statuses = ['ANALYSIS_FINISHED', 'REPORT_UPLOADED', 'REPORT_VALIDATED', 'PAYMENT_PENDING', 'PAYMENT_CONFIRMED']
    if req.status not in finished_statuses:
        messages.error(
            request,
            gettext("Invoice can only be generated after analysis is finished (status: %(status)s).") % {
                'status': req.get_status_display()
            }
        )
        return redirect_back(request, 'dashboard:admin_request_detail', pk=pk)
    
    try:
        # Generate Excel invoice
        excel_data = generate_invoice_excel(req)
        
        # Save to Request model
        invoice_filename = f"invoice-{req.display_id}-{timezone.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        req.generated_invoice.save(invoice_filename, ContentFile(excel_data))
        req.save(update_fields=['generated_invoice'])
        
        messages.success(
            request,
            gettext("Invoice generated successfully for %(display_id)s. Please download, sign, and upload the signed version.") % {
                'display_id': req.display_id
            }
        )
        
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except Exception as e:
        messages.error(request, gettext("Error generating invoice: %(error)s") % {'error': str(e)})
        return redirect('dashboard:admin_request_detail', pk=pk)


@admin_required
def upload_signed_invoice(request, pk):
    """
    Upload a signed invoice for a GENOCLAB request.
    Admin Ops downloads the generated invoice, signs it, and uploads it back.
    """
    req = get_object_or_404(Request, pk=pk)
    
    # Only for GENOCLAB channel
    if req.channel != 'GENOCLAB':
        messages.error(request, gettext("Signed invoice upload is only available for GENOCLAB requests."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    if request.method != 'POST':
        messages.error(request, gettext("Please use the form to upload the signed invoice."))
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    signed_file = request.FILES.get('signed_invoice')
    if not signed_file:
        messages.error(request, gettext("Please select a file to upload."))
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    # Validate file type
    allowed_extensions = ['.pdf', '.xlsx', '.docx']
    file_ext = signed_file.name.lower().split('.')[-1]
    if f'.{file_ext}' not in allowed_extensions:
        messages.error(
            request,
            gettext("Invalid file type. Allowed types: PDF, XLSX, DOCX")
        )
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    try:
        # Save signed invoice
        req.signed_invoice = signed_file
        req.save(update_fields=['signed_invoice'])
        
        messages.success(
            request,
            gettext("Signed invoice uploaded successfully for %(display_id)s. You can now send it to the client.") % {
                'display_id': req.display_id
            }
        )
        
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except Exception as e:
        messages.error(request, gettext("Error uploading signed invoice: %(error)s") % {'error': str(e)})
        return redirect('dashboard:admin_request_detail', pk=pk)


@admin_required
def send_invoice_to_client(request, pk):
    """
    Send the signed invoice to the client via email and in-app notification.
    Only available after a signed invoice has been uploaded.
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from accounts.models import User
    
    req = get_object_or_404(Request, pk=pk)
    
    # Only for GENOCLAB channel
    if req.channel != 'GENOCLAB':
        messages.error(request, gettext("Invoice sending is only available for GENOCLAB requests."))
        return redirect_back(request, 'dashboard:admin_ops')
    
    # Check if signed invoice exists
    if not req.signed_invoice:
        messages.error(
            request,
            gettext("Please upload a signed invoice before sending to the client.")
        )
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    # Get client
    client = req.requester
    if not client:
        messages.error(request, gettext("No client associated with this request."))
        return redirect('dashboard:admin_request_detail', pk=pk)
    
    try:
        # Update request with invoice sent timestamp
        req.invoice_sent_at = timezone.now()
        req.save(update_fields=['invoice_sent_at'])
        
        # Create in-app notification for client
        Notification.objects.create(
            user=client,
            message=gettext("Your invoice for request %(display_id)s is ready for download. Please proceed with payment.") % {
                'display_id': req.display_id
            },
            request=req,
            notification_type='INVOICE_READY'
        )
        
        # Send email notification
        payment_settings = PaymentSettings.get_settings()
        try:
            email_context = {
                'user': client,
                'request': req,
                'payment_settings': payment_settings,
                'platform_name': 'PLAGENOR 4.0',
                'invoice_url': request.build_absolute_uri(
                    f"/dashboard/client/invoice/{req.pk}/download/"
                ),
            }
            html_body = render_to_string('dashboard/emails/invoice_notification.html', email_context, request=request)
            
            send_mail(
                subject=gettext("Invoice Ready for %(display_id)s — PLAGENOR") % {'display_id': req.display_id},
                message='',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[client.email],
                html_message=html_body,
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to send invoice email to {client.email}: {e}")
        
        messages.success(
            request,
            gettext("Invoice sent to client %(client_name)s successfully!") % {
                'client_name': client.get_full_name()
            }
        )
        
        return redirect('dashboard:admin_request_detail', pk=pk)
        
    except Exception as e:
        messages.error(request, gettext("Error sending invoice: %(error)s") % {'error': str(e)})
        return redirect('dashboard:admin_request_detail', pk=pk)
