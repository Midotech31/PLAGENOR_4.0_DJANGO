import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Q

from core.models import Request, Service
from dashboard.views.admin_ops import admin_required
from documents.generators import (
    generate_ibtikar_form,
    generate_platform_note,
    generate_quote,
    generate_reception_form,
)
from documents.models import ServiceTemplate

logger = logging.getLogger('plagenor.documents')


def _serve_docx(filepath, filename):
    """Serve a DOCX file as a download response."""
    if not Path(filepath).exists():
        raise Http404("Document non trouvé.")
    response = FileResponse(
        open(filepath, 'rb'),
        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _can_download_request_doc(user, req, admin_only=False):
    """Authorization for per-request document downloads.

    Allows: any admin, the request's owning requester, AND the assigned
    analyst. ``admin_only=True`` restricts to admins (used for the platform
    note, which is an internal document).
    """
    if user.is_admin:
        return True
    if admin_only:
        return False
    if req.requester_id and req.requester_id == user.pk:
        return True
    if req.assigned_to_id and req.assigned_to.user_id == user.pk:
        return True
    return False


def _cached_doc_path(req, template_type):
    """Versioned on-disk cache path for a generated document.

    The filename embeds ``updated_at`` as a UNIX timestamp so any mutation
    of the Request auto-invalidates the cache (Django sets ``updated_at``
    via ``auto_now=True`` on every save).
    """
    cache_dir = Path(settings.MEDIA_ROOT) / 'documents_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    ts = int(req.updated_at.timestamp()) if req.updated_at else 0
    safe_id = (req.display_id or str(req.pk)).replace('/', '_')
    return cache_dir / f"{safe_id}__{template_type}__{ts}.docx"


def _cached_serve_doc(req, template_type, generator_fn, download_name):
    """Serve a generated DOCX via a versioned cache.

    Generates only when the cache file for this Request's current
    ``updated_at`` does not exist. Stale per-version files accumulate but
    are bounded by the number of edits per request and can be pruned by
    a periodic maintenance task.
    """
    cache_path = _cached_doc_path(req, template_type)
    if not cache_path.exists():
        try:
            src = Path(generator_fn(req))
        except Exception as exc:
            logger.exception(
                "Document generation failed for %s/%s: %s",
                req.display_id, template_type, exc,
            )
            raise Http404("Document non disponible.")
        if not src.exists():
            raise Http404("Document non disponible.")
        # Copy into the versioned cache so the next GET is a pure file read.
        shutil.copy2(str(src), str(cache_path))
    return _serve_docx(str(cache_path), download_name)


@login_required
def ibtikar_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'IBTIKAR_FORM', generate_ibtikar_form,
        f"IBTIKAR_FORM_{req.display_id}.docx",
    )


@login_required
def platform_note_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req, admin_only=True):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'PLATFORM_NOTE', generate_platform_note,
        f"PLATFORM_NOTE_{req.display_id}.docx",
    )


@login_required
def quote_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'QUOTE', generate_quote,
        f"QUOTE_{req.display_id}.docx",
    )


@login_required
def reception_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'RECEPTION_FORM', generate_reception_form,
        f"RECEPTION_FORM_{req.display_id}.docx",
    )


# ============================================================
# Template Management Views (Super Admin)
# ============================================================

@admin_required
def template_list(request):
    """List all document templates with filtering."""
    template_type = request.GET.get('type')
    service_id = request.GET.get('service')
    is_active = request.GET.get('active')
    
    templates = ServiceTemplate.objects.select_related('service', 'created_by')
    
    if template_type:
        templates = templates.filter(template_type=template_type)
    if service_id:
        templates = templates.filter(service_id=service_id)
    if is_active == '1':
        templates = templates.filter(is_active=True)
    elif is_active == '0':
        templates = templates.filter(is_active=False)
    
    services = Service.objects.filter(is_active=True).order_by('name')
    
    context = {
        'templates': templates,
        'services': services,
        'template_types': ServiceTemplate.TEMPLATE_TYPE_CHOICES,
        'current_type': template_type,
        'current_service': service_id,
        'current_active': is_active,
    }
    return render(request, 'documents/template_list.html', context)


@admin_required
def template_create(request):
    """Create a new document template."""
    services = Service.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        service_id = request.POST.get('service')
        template_type = request.POST.get('template_type')
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        file = request.FILES.get('file')
        
        if not all([service_id, template_type, name, file]):
            messages.error(request, 'Veuillez remplir tous les champs obligatoires.')
        else:
            # Deactivate existing templates of the same type for this service
            ServiceTemplate.objects.filter(
                service_id=service_id,
                template_type=template_type,
                is_active=True
            ).update(is_active=False)
            
            template = ServiceTemplate.objects.create(
                service_id=service_id,
                template_type=template_type,
                name=name,
                description=description,
                file=file,
                is_active=True,
                created_by=request.user,
            )
            messages.success(request, f'Modèle "{template.name}" créé avec succès.')
            return redirect('template_detail', pk=template.pk)
    
    context = {
        'services': services,
        'template_types': ServiceTemplate.TEMPLATE_TYPE_CHOICES,
    }
    return render(request, 'documents/template_form.html', context)


@admin_required
def template_detail(request, pk):
    """View template details."""
    template = get_object_or_404(
        ServiceTemplate.objects.select_related('service', 'created_by'),
        pk=pk
    )
    return render(request, 'documents/template_detail.html', {'template': template})


@admin_required
def template_edit(request, pk):
    """Edit an existing document template."""
    template = get_object_or_404(ServiceTemplate, pk=pk)
    services = Service.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        is_active = request.POST.get('is_active') == 'on'
        new_file = request.FILES.get('file')
        
        if not name:
            messages.error(request, 'Le nom est obligatoire.')
        else:
            template.name = name
            template.description = description
            template.is_active = is_active
            
            if new_file:
                # Deactivate existing active templates of the same type for this service
                ServiceTemplate.objects.filter(
                    service=template.service,
                    template_type=template.template_type,
                    is_active=True
                ).exclude(pk=template.pk).update(is_active=False)
                template.file = new_file
                # Make this one active
                template.is_active = True
            
            template.save()
            messages.success(request, f'Modèle "{template.name}" mis à jour.')
            return redirect('template_detail', pk=template.pk)
    
    context = {
        'template': template,
        'services': services,
        'template_types': ServiceTemplate.TEMPLATE_TYPE_CHOICES,
    }
    return render(request, 'documents/template_form.html', context)


@admin_required
def template_delete(request, pk):
    """Delete a document template."""
    template = get_object_or_404(ServiceTemplate, pk=pk)
    
    if request.method == 'POST':
        template_name = template.name
        template.delete()
        messages.success(request, f'Modèle "{template_name}" supprimé.')
        return redirect('template_list')
    
    return render(request, 'documents/template_confirm_delete.html', {'template': template})


@admin_required
def template_toggle_active(request, pk):
    """Toggle template active status."""
    template = get_object_or_404(ServiceTemplate, pk=pk)
    
    if request.method == 'POST':
        if template.is_active:
            # Deactivate
            template.is_active = False
            messages.info(request, f'Modèle "{template.name}" désactivé.')
        else:
            # Activate and deactivate others
            ServiceTemplate.objects.filter(
                service=template.service,
                template_type=template.template_type,
                is_active=True
            ).exclude(pk=template.pk).update(is_active=False)
            template.is_active = True
            messages.success(request, f'Modèle "{template.name}" activé.')
        
        template.save()
    
    return redirect('template_detail', pk=template.pk)
