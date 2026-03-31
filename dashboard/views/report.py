from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse, FileResponse, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from pathlib import Path

from core.models import Request


def _can_access_report(user, report):
    """Check if user has permission to access the report.
    
    Returns True if user is:
    - The requester (owner of the report)
    - The assigned analyst/member
    - A staff member (SUPER_ADMIN, PLATFORM_ADMIN, or analyst role)
    """
    if not user.is_authenticated:
        return False
    
    # Staff and admins have access
    if user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']:
        return True
    
    # Requester/owner has access
    if report.requester == user:
        return True
    
    # Assigned analyst has access
    if report.assigned_to and report.assigned_to.user == user:
        return True
    
    # Analysts with PENDING_ACCEPTANCE or assigned requests
    if user.role == 'MEMBER' and report.assigned_to:
        if report.assigned_to.user == user:
            return True
    
    return False


def report_viewer(request, token):
    """Report viewing page — requires authentication and ownership/staff access."""
    # Require login
    if not request.user.is_authenticated:
        messages.warning(request, "Veuillez vous connecter pour accéder à cette page.")
        return redirect(f'/accounts/login/?next={request.path}')
    
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")
    
    # Check permission
    if not _can_access_report(request.user, req):
        messages.error(request, "Vous n'avez pas la permission d'accéder à ce rapport.")
        return HttpResponseForbidden("Accès interdit")
    
    # Mark as delivered on first view
    if not req.report_delivered:
        req.report_delivered = True
        req.report_delivered_at = timezone.now()
        req.save()

        # Notify admins and assigned member
        try:
            from notifications.models import Notification
            from accounts.models import User
            admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
            for admin in admins:
                Notification.objects.create(user=admin, message=f"Rapport {req.display_id} consulté", request=req)
            if req.assigned_to:
                Notification.objects.create(user=req.assigned_to.user, message=f"Rapport {req.display_id} consulté", request=req)
        except Exception as e:
            logger.warning(f"Failed to create notification for report {req.display_id}: {e}")

    return render(request, 'dashboard/report_viewer.html', {'req': req})


def report_detail_viewer(request, token):
    """Detailed report page with embedded report — requires authentication and ownership/staff access."""
    # Require login
    if not request.user.is_authenticated:
        messages.warning(request, "Veuillez vous connecter pour accéder à cette page.")
        return redirect(f'/accounts/login/?next={request.path}')
    
    try:
        req = Request.objects.select_related('service', 'assigned_to', 'assigned_to__user').get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")
    
    # Check permission
    if not _can_access_report(request.user, req):
        messages.error(request, "Vous n'avez pas la permission d'accéder à ce rapport.")
        return HttpResponseForbidden("Accès interdit")
    
    # Mark as delivered on first view
    if not req.report_delivered:
        req.report_delivered = True
        req.report_delivered_at = timezone.now()
        req.save()

        # Notify admins and assigned member
        try:
            from notifications.models import Notification
            from accounts.models import User
            admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
            for admin in admins:
                Notification.objects.create(user=admin, message=f"Rapport {req.display_id} consulté via QR", request=req)
            if req.assigned_to:
                Notification.objects.create(user=req.assigned_to.user, message=f"Rapport {req.display_id} consulté via QR", request=req)
        except Exception as e:
            logger.warning(f"Failed to create notification for QR report access {req.display_id}: {e}")

    # Get request history for the timeline
    history = req.history.select_related('actor').order_by('created_at')[:10]

    return render(request, 'dashboard/report_detail_viewer.html', {
        'req': req,
        'history': history,
    })


def download_report(request, token):
    """Download the report file directly — requires authentication and ownership/staff access."""
    # Require login
    if not request.user.is_authenticated:
        messages.warning(request, "Veuillez vous connecter pour télécharger ce rapport.")
        return redirect(f'/accounts/login/?next={request.path}')
    
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")
    
    # Check permission
    if not _can_access_report(request.user, req):
        messages.error(request, "Vous n'avez pas la permission de télécharger ce rapport.")
        return HttpResponseForbidden("Accès interdit")
    
    if not req.report_file:
        raise Http404("No report file available")

    file_path = req.report_file.path
    if not Path(file_path).exists():
        raise Http404("Report file not found")

    # Determine content type based on file extension
    ext = Path(file_path).suffix.lower()
    if ext == '.pdf':
        content_type = 'application/pdf'
    elif ext in ['.doc', '.docx']:
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    else:
        content_type = 'application/octet-stream'

    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{Path(file_path).name}"'
    return response


def rate_report(request, token):
    """Handle star rating submission — requires authentication and ownership."""
    # Require login
    if not request.user.is_authenticated:
        if request.method == 'POST':
            return JsonResponse({'error': 'Authentication required'}, status=401)
        messages.warning(request, "Veuillez vous connecter pour évaluer ce service.")
        return redirect(f'/accounts/login/?next={request.path}')
    
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")
    
    # Only the requester can rate their own report
    if req.requester != request.user and request.user.role not in ['SUPER_ADMIN', 'PLATFORM_ADMIN']:
        if request.method == 'POST':
            return JsonResponse({'error': 'Not authorized'}, status=403)
        messages.error(request, "Vous n'avez pas la permission d'évaluer ce rapport.")
        return HttpResponseForbidden("Accès interdit")
    
    if request.method == 'POST':
        rating = int(request.POST.get('rating', 0))
        if 1 <= rating <= 5:
            req.service_rating = rating
            req.rating_comment = request.POST.get('comment', '')
            req.rated_at = timezone.now()
            req.save()
            messages.success(request, "Merci pour votre évaluation!")
    
    return redirect('report_view', token=token)


@require_POST
def acknowledge_citation(request, token):
    """Mark citation as acknowledged for this report — requires authentication and ownership/staff access."""
    # Require login
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'Report not found'}, status=404)
    
    # Check permission - only requester or staff can acknowledge
    if not _can_access_report(request.user, req):
        return JsonResponse({'ok': False, 'error': 'Not authorized'}, status=403)
    
    try:
        if not req.citation_acknowledged:
            req.citation_acknowledged = True
            req.save(update_fields=['citation_acknowledged'])
        return JsonResponse({'ok': True})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=500)
