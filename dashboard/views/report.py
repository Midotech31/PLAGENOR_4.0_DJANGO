from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Request
from dashboard.utils import safe_int


def report_viewer(request, token):
    """Public report viewing page — accessed via the report_token UUID link.

    Strict read-only. Marking the report as delivered is handled by the
    POST beacon ``mark_report_delivered`` so that link prefetchers /
    crawlers cannot flip ``report_delivered`` just by fetching the URL.
    """
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")
    return render(request, 'dashboard/report_viewer.html', {'req': req})


@require_POST
@csrf_exempt  # secret is the report_token UUID in the URL; cookies are absent
def mark_report_delivered(request, token):
    """POST beacon fired by the report viewer page on first display.

    Idempotent: the row is locked, the boolean is flipped only when it
    was False, and only the two delivery fields are written. Admin edits
    to price/status that landed between page render and beacon fire are
    therefore never clobbered.
    """
    with transaction.atomic():
        req = (
            Request.objects.select_for_update()
            .filter(report_token=token)
            .first()
        )
        if req is None:
            return HttpResponse(status=404)
        if not req.report_delivered:
            req.report_delivered = True
            req.report_delivered_at = timezone.now()
            req.save(update_fields=['report_delivered', 'report_delivered_at'])
            _notify_report_consulted(req)
    return HttpResponse(status=204)


def _notify_report_consulted(req):
    """Notify admins + assigned analyst that the report was opened."""
    try:
        from notifications.models import Notification
        from accounts.models import User
        msg = f"Rapport {req.display_id} consulté"
        admins = User.objects.filter(role__in=['SUPER_ADMIN', 'PLATFORM_ADMIN'])
        for admin in admins:
            Notification.objects.create(
                user=admin, message=msg, request=req,
                notification_type='REPORT',
            )
        if req.assigned_to and req.assigned_to.user_id:
            Notification.objects.create(
                user=req.assigned_to.user, message=msg, request=req,
                notification_type='REPORT',
            )
    except Exception:
        pass


def rate_report(request, token):
    """Handle star rating submission from the public report viewer."""
    if request.method != 'POST':
        return redirect('report_view', token=token)
    rating = safe_int(request.POST.get('rating'))
    if not (1 <= rating <= 5):
        return redirect('report_view', token=token)
    comment = request.POST.get('comment', '') or ''
    with transaction.atomic():
        req = (
            Request.objects.select_for_update()
            .filter(report_token=token)
            .first()
        )
        if req is None:
            raise Http404("Report not found")
        req.service_rating = rating
        req.rating_comment = comment
        req.rated_at = timezone.now()
        req.save(update_fields=['service_rating', 'rating_comment', 'rated_at'])
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


def download_report(request, token):
    """Serve the actual report file — server-side gated on the citation
    clause for IBTIKAR (academic) requests only. GENOCLAB (commercial)
    clients are paying customers, not researchers required to cite the
    platform in publications; they download directly. Bypasses (devtools
    tampering, direct /media/ URLs, scripted GETs without going through
    the modal) all land here and are blocked for IBTIKAR until
    ``citation_acknowledged`` is True.
    """
    try:
        req = Request.objects.get(report_token=token)
    except Request.DoesNotExist:
        raise Http404("Report not found")

    if not req.report_file:
        raise Http404("No report file")

    # The gate — only IBTIKAR. GENOCLAB requests skip straight to the
    # FileResponse below. The viewer page renders the modal for IBTIKAR
    # only; this is the defense-in-depth so nothing else can bypass it.
    if req.channel == 'IBTIKAR' and not req.citation_acknowledged:
        return redirect('report_view', token=token)

    # First successful download = mark delivered (idempotent).
    if not req.report_delivered:
        with transaction.atomic():
            locked = (
                Request.objects.select_for_update()
                .filter(pk=req.pk, report_delivered=False)
                .first()
            )
            if locked is not None:
                locked.report_delivered = True
                locked.report_delivered_at = timezone.now()
                locked.save(update_fields=['report_delivered', 'report_delivered_at'])

    # FileResponse streams the file; as_attachment triggers the download
    # dialog instead of inline preview.
    return FileResponse(req.report_file.open('rb'), as_attachment=True,
                        filename=f"{req.display_id}_rapport.pdf")
