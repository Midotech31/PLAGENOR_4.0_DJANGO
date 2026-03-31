from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse, FileResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from pathlib import Path

from core.models import Request


def report_viewer(request, token):
    """Public report viewing page — accessed via email link."""
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")

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
        except Exception:
            pass

    return render(request, 'dashboard/report_viewer.html', {'req': req})


def report_detail_viewer(request, token):
    """Public detailed report page with embedded report — accessed via QR code."""
    try:
        req = Request.objects.select_related('service', 'assigned_to', 'assigned_to__user').get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")

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
        except Exception:
            pass

    # Get request history for the timeline
    history = req.history.select_related('actor').order_by('created_at')[:10]

    return render(request, 'dashboard/report_detail_viewer.html', {
        'req': req,
        'history': history,
    })


def download_report(request, token):
    """Download the report file directly."""
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")

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
    """Handle star rating submission."""
    if request.method == 'POST':
        req = get_object_or_404(Request, report_token=token)
        rating = int(request.POST.get('rating', 0))
        if 1 <= rating <= 5:
            req.service_rating = rating
            req.rating_comment = request.POST.get('comment', '')
            req.rated_at = timezone.now()
            req.save()
    return redirect('report_view', token=token)


@require_POST
def acknowledge_citation(request, token):
    """Mark citation as acknowledged for this report (called via AJAX)."""
    try:
        req = Request.objects.get(report_token=token)
        if not req.citation_acknowledged:
            req.citation_acknowledged = True
            req.save(update_fields=['citation_acknowledged'])
        return JsonResponse({'ok': True})
    except Request.DoesNotExist:
        return JsonResponse({'ok': False}, status=404)
