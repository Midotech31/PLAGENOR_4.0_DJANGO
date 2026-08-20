import logging

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Q
from django.http import (
    FileResponse, Http404, HttpResponse, HttpResponseForbidden, JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.models import Request
from dashboard.utils import safe_int

logger = logging.getLogger('plagenor.reports')


# Internal staff (analyst / admins / finance) are never subject to the
# citation clause nor the rating step — they consult and download reports
# from the history at any time. The gate only concerns the academic
# requester. Clients (GENOCLAB) are already exempt by channel.
_STAFF_ROLES = {'MEMBER', 'SUPER_ADMIN', 'PLATFORM_ADMIN', 'FINANCE'}


def _is_internal_staff(user) -> bool:
    return (getattr(user, 'is_authenticated', False)
            and getattr(user, 'role', '') in _STAFF_ROLES)


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
    return render(request, 'dashboard/report_viewer.html', {
        'req': req,
        'is_staff_viewer': _is_internal_staff(request.user),
    })


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
        logger.exception(
            "Failed to create report-consulted notifications for %s",
            req.display_id,
        )


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

    # The gate — only IBTIKAR, and only for the requester. Internal staff
    # (analyst / admins) download from the history without restriction.
    if (req.channel == 'IBTIKAR' and not req.citation_acknowledged
            and not _is_internal_staff(request.user)):
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
    # dialog instead of inline preview. Keep the report's real extension —
    # naming a .docx ".pdf" breaks the file for the recipient.
    import os as _os
    _ext = _os.path.splitext(req.report_file.name)[1].lower() or '.pdf'
    return FileResponse(req.report_file.open('rb'), as_attachment=True,
                        filename=f"{req.display_id}_rapport{_ext}")


def protected_report_media(request, path):
    """Gate direct ``/media/reports/<file>`` access behind the citation clause.

    Report files live under ``MEDIA_ROOT/reports/`` and would otherwise be
    served raw by the static media handler. Raw filenames are not access
    tokens: only internal staff or the authenticated request owner may use
    this route. External/guest delivery uses the unguessable report token.
    """
    rel = f"reports/{path}"
    req = Request.objects.filter(report_file=rel).first()
    # Raw storage names are not authorization capabilities.  Anonymous users
    # must use the unguessable report-token route; otherwise a predictable
    # GENOCLAB filename could expose a confidential commercial report.
    if req is None:
        raise Http404("Fichier introuvable")
    if _is_internal_staff(request.user):
        pass
    elif not (
        getattr(request.user, 'is_authenticated', False)
        and req.requester_id == request.user.pk
    ):
        raise Http404("Fichier introuvable")
    elif req.channel == 'IBTIKAR' and not req.citation_acknowledged:
        if req.report_token:
            return redirect('report_view', token=req.report_token)
        return HttpResponseForbidden(
            "Veuillez accepter la clause d'auteur et de citation avant de "
            "télécharger le rapport."
        )
    # Authorized staff/owner → stream from the configured storage backend.
    if not default_storage.exists(rel):
        raise Http404("Fichier introuvable")
    return FileResponse(default_storage.open(rel, 'rb'))


# Prefixes anyone may fetch: shown on public pages (login avatars, service
# cards). Everything else carries business data and is authorised below.
_PUBLIC_MEDIA_PREFIXES = ('avatars/', 'service_images/')
# Purchase orders / payment receipts: confidential commercial documents.
_OWNER_MEDIA_PREFIXES = ('orders/', 'payments/')


def _may_access_media(user, path) -> bool:
    """Authorisation policy for non-report media.

    - avatars/ + service_images/  → public (rendered on public pages).
    - orders/ + payments/         → internal staff OR the request's owner.
    - anything else (documents/, document_templates/, gifts/, …) → staff only.
      Generated devis/factures have predictable sequential filenames, so they
      must never be guessable by anonymous visitors; authenticated flows
      stream them through their own permission-checked views instead.
    """
    if path.startswith(_PUBLIC_MEDIA_PREFIXES):
        return True
    if path.startswith(_OWNER_MEDIA_PREFIXES):
        if _is_internal_staff(user):
            return True
        if not getattr(user, 'is_authenticated', False):
            return False
        return Request.objects.filter(
            Q(order_file=path) | Q(payment_receipt_file=path),
            requester=user,
        ).exists()
    return _is_internal_staff(user)


def serve_media(request, path):
    """Stream ordinary uploaded media through the configured storage backend.

    Report PDFs are NOT served here — they have their own gated route
    (``protected_report_media``), declared before this catch-all so it wins.
    The ``reports/`` guard below is defensive in case routing order ever
    changes. This view exists because media lives on Supabase Storage (or the
    local disk in dev) and must be streamed by Django: ``MEDIA_ROOT`` is not
    web-served in production, and the bucket is private.

    Access control lives in ``_may_access_media``; denials answer 404 (not
    403) so unauthorized probing cannot confirm that a file exists.
    """
    if path.startswith('reports/'):
        raise Http404("Fichier introuvable")
    if not _may_access_media(request.user, path):
        raise Http404("Fichier introuvable")
    if not default_storage.exists(path):
        raise Http404("Fichier introuvable")
    return FileResponse(default_storage.open(path, 'rb'))
