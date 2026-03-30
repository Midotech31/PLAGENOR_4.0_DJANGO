from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

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
