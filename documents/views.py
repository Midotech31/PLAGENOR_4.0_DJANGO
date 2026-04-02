# documents/views.py — PLAGENOR 4.0 PDF Document Views
# Handles PDF download and regeneration for IBTIKAR forms

from pathlib import Path
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required

from core.models import Request

from documents.pdf_generators import generate_ibtikar_form_pdf
from documents.pdf_generator_platform_note import generate_platform_note_pdf
from documents.pdf_generator_reception import generate_reception_form_pdf


# =============================================================================
# PDF Generation + Download Views
# =============================================================================

import logging
from django.utils.translation import get_language

logger = logging.getLogger('plagenor.documents')


@login_required
def ibtikar_form_pdf(request, pk):
    """
    Generate (or retrieve cached) and serve an IBTIKAR form as PDF.
    Returns PDF bytes inline — no file is saved to disk for the response.
    The generated PDF is also stored in request.generated_ibtikar_form for future use.
    """
    req = get_object_or_404(Request, pk=pk)

    is_admin = getattr(request.user, 'is_admin', False) or request.user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    is_requester = request.user == req.requester

    if not is_admin and not is_requester:
        return HttpResponseForbidden(_("Vous n'avez pas la permission d'accéder à ce document."))

    lang = get_language() or 'fr'

    try:
        pdf_bytes = generate_ibtikar_form_pdf(req, lang=lang)
    except ValueError as e:
        logger.error(f"PDF generation failed for {req.display_id}: {e}")
        messages.error(request, _("Erreur lors de la génération du formulaire : service manquant."))
        return redirect('dashboard:requester_request_detail', pk=pk)
    except Exception as e:
        logger.error(f"PDF generation failed for {req.display_id}: {e}", exc_info=True)
        messages.error(request, _("Erreur lors de la génération du formulaire."))
        return redirect('dashboard:requester_request_detail', pk=pk)

    filename = f"PLAGENOR_IBTIKAR_{req.service.code}_{req.display_id}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    return response


@login_required
def download_ibtikar_form(request, pk):
    """
    Download the IBTIKAR Form PDF for a request (serves saved FileField).
    Available to the request owner and admins.
    """
    req = get_object_or_404(Request, pk=pk)
    
    # Check permissions
    is_admin = getattr(request.user, 'is_admin', False) or request.user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    is_requester = request.user == req.requester
    
    if not is_admin and not is_requester:
        return HttpResponseForbidden(_("Vous n'avez pas la permission d'accéder à ce document."))
    
    # Check if form exists
    if not req.generated_ibtikar_form or not req.generated_ibtikar_form.name:
        messages.warning(request, _("Formulaire IBTIKAR non encore généré."))
        return redirect('dashboard:request_detail', request_id=req.pk)
    
    try:
        file_path = Path(settings.MEDIA_ROOT) / req.generated_ibtikar_form.name
        if not file_path.exists():
            messages.error(request, _("Fichier non trouvé."))
            return redirect('dashboard:request_detail', request_id=req.pk)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf',
        )
        response['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
        return response
    except Exception as e:
        messages.error(request, _(f"Erreur: {str(e)}"))
        return redirect('dashboard:request_detail', request_id=req.pk)


@login_required
def download_platform_note(request, pk):
    """
    Download the Platform Note PDF for a request.
    Available to the request owner (after validation) and admins.
    Only for IBTIKAR requests.
    """
    req = get_object_or_404(Request, pk=pk)
    
    # Check permissions
    is_admin = getattr(request.user, 'is_admin', False) or request.user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    is_requester = request.user == req.requester
    
    if not is_admin and not is_requester:
        return HttpResponseForbidden(_("Vous n'avez pas la permission d'accéder à ce document."))
    
    # Only for IBTIKAR requests
    if req.channel != 'IBTIKAR':
        messages.error(request, _("La Note de Plateforme n'est disponible que pour les demandes IBTIKAR."))
        return redirect('dashboard:request_detail', request_id=req.pk)
    
    # Requester can only download after validation
    if not is_admin and is_requester:
        validated_states = ['PLATFORM_NOTE_GENERATED', 'ASSIGNED', 'PENDING_ACCEPTANCE',
                          'APPOINTMENT_PROPOSED', 'APPOINTMENT_CONFIRMED', 'SAMPLE_RECEIVED',
                          'ANALYSIS_STARTED', 'ANALYSIS_FINISHED', 'REPORT_UPLOADED',
                          'ADMIN_REVIEW', 'REPORT_VALIDATED', 'SENT_TO_REQUESTER', 'COMPLETED', 'CLOSED']
        if req.status not in validated_states and not req.generated_platform_note:
            return HttpResponseForbidden(_("Ce document n'est pas encore disponible."))
    
    # Check if note exists
    if not req.generated_platform_note or not req.generated_platform_note.name:
        messages.warning(request, _("Note de Plateforme non encore générée."))
        return redirect('dashboard:request_detail', request_id=req.pk)
    
    try:
        file_path = Path(settings.MEDIA_ROOT) / req.generated_platform_note.name
        if not file_path.exists():
            messages.error(request, _("Fichier non trouvé."))
            return redirect('dashboard:request_detail', request_id=req.pk)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf',
        )
        response['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
        return response
    except Exception as e:
        messages.error(request, _(f"Erreur: {str(e)}"))
        return redirect('dashboard:request_detail', request_id=req.pk)


@login_required
def download_reception_form(request, pk):
    """
    Download the Sample Reception Form PDF for a request.
    Available to the request owner and admins.
    """
    req = get_object_or_404(Request, pk=pk)
    
    # Check permissions
    is_admin = getattr(request.user, 'is_admin', False) or request.user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    is_requester = request.user == req.requester
    
    if not is_admin and not is_requester:
        return HttpResponseForbidden(_("Vous n'avez pas la permission d'accéder à ce document."))
    
    # Check if form exists
    if not req.generated_reception_form or not req.generated_reception_form.name:
        messages.warning(request, _("Formulaire de réception non encore généré."))
        return redirect('dashboard:request_detail', request_id=req.pk)
    
    try:
        file_path = Path(settings.MEDIA_ROOT) / req.generated_reception_form.name
        if not file_path.exists():
            messages.error(request, _("Fichier non trouvé."))
            return redirect('dashboard:request_detail', request_id=req.pk)
        
        response = FileResponse(
            open(file_path, 'rb'),
            content_type='application/pdf',
        )
        response['Content-Disposition'] = f'attachment; filename="{file_path.name}"'
        return response
    except Exception as e:
        messages.error(request, _(f"Erreur: {str(e)}"))
        return redirect('dashboard:request_detail', request_id=req.pk)


# =============================================================================
# PDF Regeneration Views (Admin Only)
# =============================================================================

@staff_member_required
def regenerate_pdf(request, pk, doc_type):
    """
    Regenerate a specific PDF document for a request.
    Staff/Admin only.
    
    Args:
        doc_type: One of 'ibtikar', 'platform_note', or 'reception'
    """
    req = get_object_or_404(Request, pk=pk)
    
    # Only for IBTIKAR requests when regenerating platform note
    if doc_type == 'platform_note' and req.channel != 'IBTIKAR':
        messages.error(request, _("La Note de Plateforme n'est disponible que pour les demandes IBTIKAR."))
        return redirect('dashboard:request_detail', request_id=req.pk)
    
    try:
        error = None
        success_msg = None
        error_msg = None
        if doc_type == 'ibtikar':
            try:
                generate_ibtikar_form_pdf(req, lang='fr', force_regenerate=True)
                success_msg = _("Formulaire IBTIKAR régénéré avec succès.")
            except ValueError as e:
                error_msg = str(e)
            except Exception as e:
                error_msg = str(e)

        elif doc_type == 'platform_note':
            filepath, error = generate_platform_note_pdf(req, force_regenerate=True)
            success_msg = _("Note de Plateforme régénérée avec succès.")
            error_msg = _("La régénération de la Note de Plateforme a échoué.")

        elif doc_type == 'reception':
            filepath, error = generate_reception_form_pdf(req, force_regenerate=True)
            success_msg = _("Formulaire de réception régénéré avec succès.")
            error_msg = _("La régénération du Formulaire de réception a échoué.")

        else:
            messages.error(request, _("Type de document invalide."))
            return redirect('dashboard:request_detail', request_id=req.pk)

        if error:
            messages.error(request, error_msg)
        elif success_msg:
            messages.success(request, success_msg)
            
    except Exception as e:
        messages.error(request, _(f"Erreur: {str(e)}"))
    
    return redirect('dashboard:request_detail', request_id=req.pk)


# =============================================================================
# Legacy/Deprecated Views (kept for backwards compatibility)
# =============================================================================

@login_required
def ibtikar_form_view(request, request_id):
    """Legacy view - redirects to new download view."""
    return download_ibtikar_form(request, request_id)


@login_required
def platform_note_view(request, request_id):
    """Legacy view - redirects to new download view."""
    return download_platform_note(request, request_id)


@login_required
def reception_form_view(request, request_id):
    """Legacy view - redirects to new download view."""
    return download_reception_form(request, request_id)


# =============================================================================
# Status Check API (for AJAX calls)
# =============================================================================

@login_required
def check_pdf_status(request, pk):
    """
    API endpoint to check PDF generation status for a request.
    Returns JSON with status information.
    """
    req = get_object_or_404(Request, pk=pk)
    
    is_admin = getattr(request.user, 'is_admin', False) or request.user.role in ['SUPER_ADMIN', 'PLATFORM_ADMIN']
    
    return JsonResponse({
        'ibtikar_form': {
            'exists': bool(req.generated_ibtikar_form and req.generated_ibtikar_form.name),
            'url': req.generated_ibtikar_form.url if req.generated_ibtikar_form else None,
        },
        'platform_note': {
            'exists': bool(req.generated_platform_note and req.generated_platform_note.name),
            'url': req.generated_platform_note.url if req.generated_platform_note else None,
            'is_ibtikar_only': req.channel == 'IBTIKAR',
        },
        'reception_form': {
            'exists': bool(req.generated_reception_form and req.generated_reception_form.name),
            'url': req.generated_reception_form.url if req.generated_reception_form else None,
        },
        'can_regenerate': is_admin,
    })
