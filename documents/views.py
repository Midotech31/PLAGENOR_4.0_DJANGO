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
from documents.models import DocumentBlock, ServiceTemplate
from documents.pdf_converter import convert_docx_to_pdf

logger = logging.getLogger('plagenor.documents')


def _serve_file(filepath, filename):
    """Serve a document with the correct Content-Type for its extension."""
    path = Path(filepath)
    if not path.exists():
        raise Http404("Document non trouvé.")
    if path.suffix.lower() == '.pdf':
        content_type = 'application/pdf'
    else:
        content_type = (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    response = FileResponse(open(filepath, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _serve_docx(filepath, filename):
    """Backwards-compatible alias kept for any external imports."""
    return _serve_file(filepath, filename)


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


def _block_signature(req, template_type):
    """Hash of all admin DocumentBlocks that affect this generation.

    Used so that editing a block immediately invalidates every cached
    document that block is injected into. Without this, a freshly edited
    notice would only appear on documents generated after the next Request
    save — surprising and easy to miss.
    """
    from django.db.models import Count
    blocks = (
        DocumentBlock.objects
        .filter(template_type=template_type, is_active=True)
        .annotate(_n=Count('services'))
        .filter(Q(_n=0) | Q(services=req.service))
        .distinct()
    )
    sig_parts = list(
        blocks.order_by('pk').values_list('pk', 'updated_at')
    )
    if not sig_parts:
        return '0'
    return str(max(t.timestamp() if t else 0 for _, t in sig_parts))


def _service_fields_signature(req):
    """Hash of the service's ``custom_fields`` definition.

    SuperAdmin edits to ``ServiceFormField`` (adding a column, renaming a
    label, changing field_category…) don't bump ``Request.updated_at``, so
    without this signature the document cache would keep serving the stale
    pre-edit PDF until the request itself is modified. Querying only the
    columns we need keeps this cheap (one row per ``custom_fields`` of the
    request's service).
    """
    if not getattr(req, 'service_id', None):
        return '0'
    try:
        from core.models import ServiceFormField
        ids = list(
            ServiceFormField.objects
            .filter(service_id=req.service_id)
            .order_by('pk').values_list('pk', flat=True)
        )
        if not ids:
            return '0'
        # signature = service pk + last form-fields id + their count, no
        # timestamp on this model so we rely on (count, max id) which jumps
        # whenever the wipe-and-recreate save runs.
        return f"{req.service_id}-{len(ids)}-{ids[-1]}"
    except Exception:
        return '0'


def _cached_doc_path(req, template_type, suffix='.docx'):
    """Versioned on-disk cache path for a generated document.

    Cache key includes ``Request.updated_at`` so request edits invalidate,
    the DocumentBlock signature so admin notice edits invalidate, and the
    ServiceFormField signature so SuperAdmin edits to the service's custom
    fields also invalidate the cached document.
    """
    cache_dir = Path(settings.MEDIA_ROOT) / 'documents_cache'
    cache_dir.mkdir(parents=True, exist_ok=True)
    ts = int(req.updated_at.timestamp()) if req.updated_at else 0
    safe_id = (req.display_id or str(req.pk)).replace('/', '_')
    blocks_sig = _block_signature(req, template_type)
    fields_sig = _service_fields_signature(req)
    return cache_dir / f"{safe_id}__{template_type}__{ts}__{blocks_sig}__{fields_sig}{suffix}"


def _cached_serve_doc(req, template_type, generator_fn, download_basename):
    """Generate DOCX, render to PDF if enabled, serve via versioned cache.

    The cache key encodes both ``Request.updated_at`` and the
    DocumentBlock signature, so any edit on either side invalidates the
    cached file and the next GET regenerates.
    """
    pdf_enabled = getattr(settings, 'DOCUMENT_PDF_ENABLED', True)
    suffix = '.pdf' if pdf_enabled else '.docx'
    cache_path = _cached_doc_path(req, template_type, suffix=suffix)
    download_name = f"{download_basename}{suffix}"

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
        # Track every intermediate we create so the only surviving artifact
        # is the file in documents_cache/. Without this, each cache-miss
        # left an orphan DOCX (and PDF) in media/documents/ forever.
        intermediates = [src]
        if pdf_enabled:
            rendered = convert_docx_to_pdf(src, output_dir=src.parent)
            intermediates.append(rendered)
            # convert_docx_to_pdf returns the DOCX path on failure; cache it
            # with the right extension so we don't loop on conversion.
            if rendered.suffix.lower() != suffix:
                cache_path = cache_path.with_suffix(rendered.suffix)
                download_name = f"{download_basename}{rendered.suffix}"
            shutil.copy2(str(rendered), str(cache_path))
        else:
            shutil.copy2(str(src), str(cache_path))
        # Remove intermediates now that the cache holds the served copy.
        for tmp in intermediates:
            try:
                if Path(tmp).resolve() != cache_path.resolve():
                    Path(tmp).unlink(missing_ok=True)
            except OSError:
                pass
    return _serve_file(str(cache_path), download_name)


@login_required
def ibtikar_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'IBTIKAR_FORM', generate_ibtikar_form,
        f"IBTIKAR_FORM_{req.display_id}",
    )


def guest_ibtikar_form_view(request, token):
    """Serve a guest's IBTIKAR form using their tracking token.

    Guest users cannot pass ``login_required``.  The UUID tracking token is
    the same capability already required to view the public tracking page.
    """
    req = get_object_or_404(
        Request,
        guest_token=token,
        submitted_as_guest=True,
        channel='IBTIKAR',
    )
    return _cached_serve_doc(
        req, 'IBTIKAR_FORM', generate_ibtikar_form,
        f"IBTIKAR_FORM_{req.display_id}",
    )


@login_required
def platform_note_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req, admin_only=True):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'PLATFORM_NOTE', generate_platform_note,
        f"PLATFORM_NOTE_{req.display_id}",
    )


@login_required
def quote_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'QUOTE', generate_quote,
        f"QUOTE_{req.display_id}",
    )


@login_required
def reception_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not _can_download_request_doc(request.user, req):
        return HttpResponseForbidden()
    return _cached_serve_doc(
        req, 'RECEPTION_FORM', generate_reception_form,
        f"RECEPTION_FORM_{req.display_id}",
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
    
    services = Service.objects.filter(active=True).order_by('name')
    
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
    services = Service.objects.filter(active=True).order_by('name')
    
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
            return redirect('documents:template_detail', pk=template.pk)
    
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
    services = Service.objects.filter(active=True).order_by('name')
    
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
            return redirect('documents:template_detail', pk=template.pk)
    
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
        return redirect('documents:template_list')
    
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

    return redirect('documents:template_detail', pk=template.pk)


# ============================================================
# Document Block Management Views (Super Admin) — Phase 3.7
# ============================================================

@admin_required
def block_list(request):
    """List all admin-editable document blocks with filtering.

    The "service" filter is "any of" against the M2M: picking PCR shows
    blocks that target PCR (alone or with others) AND every global block
    (since globals apply to PCR too). "global" filters strictly to blocks
    with no services attached.
    """
    from django.db.models import Count
    template_type = request.GET.get('type', '').strip()
    service_id = request.GET.get('service', '').strip()
    language = request.GET.get('lang', '').strip()

    blocks = (
        DocumentBlock.objects
        .select_related('created_by', 'updated_by')
        .prefetch_related('services')
        .annotate(_n_services=Count('services'))
    )
    if template_type:
        blocks = blocks.filter(template_type=template_type)
    if service_id:
        if service_id == 'global':
            blocks = blocks.filter(_n_services=0)
        else:
            blocks = blocks.filter(Q(_n_services=0) | Q(services__pk=service_id))
    if language:
        blocks = blocks.filter(language=language)

    context = {
        'blocks': blocks.distinct(),
        'services': Service.objects.filter(active=True).order_by('code'),
        'template_types': DocumentBlock.TEMPLATE_TYPE_CHOICES,
        'languages': DocumentBlock.LANGUAGE_CHOICES,
        'current_type': template_type,
        'current_service': service_id,
        'current_lang': language,
    }
    return render(request, 'documents/block_list.html', context)


def _block_form_context(block=None):
    """Build the form context.

    ``selected_service_ids`` is a string-keyed set so the template can
    do an O(1) lookup without triggering a fresh queryset evaluation
    per row — and without relying on Django template's ``s in qs`` test
    which evaluates the manager weirdly inside a loop.
    """
    selected_ids: set[str] = set()
    if block and block.pk:
        selected_ids = {str(pk) for pk in block.services.values_list('pk', flat=True)}
    return {
        'block': block,
        'services': Service.objects.filter(active=True).order_by('code'),
        'selected_service_ids': selected_ids,
        'template_types': DocumentBlock.TEMPLATE_TYPE_CHOICES,
        'position_choices': DocumentBlock.POSITION_CHOICES,
        'language_choices': DocumentBlock.LANGUAGE_CHOICES,
    }


def _save_block(request, block):
    """Apply form fields onto a DocumentBlock instance; return validation msg or None.

    Returns a 2-tuple ``(error_msg, services_to_set)``. The caller is
    responsible for assigning the M2M after ``block.save()`` because
    ``services.set()`` only works once the row has a primary key.
    """
    template_type = request.POST.get('template_type', '').strip()
    service_ids = [v for v in request.POST.getlist('services') if v.strip()]
    position = request.POST.get('position', 'BOTTOM').strip()
    language = request.POST.get('language', 'fr').strip()
    title = request.POST.get('title', '').strip()
    body = request.POST.get('body', '').strip()
    priority = request.POST.get('priority', '0').strip() or '0'
    is_active = request.POST.get('is_active') == 'on'

    valid_types = {c for c, _ in DocumentBlock.TEMPLATE_TYPE_CHOICES}
    valid_positions = {c for c, _ in DocumentBlock.POSITION_CHOICES}
    valid_langs = {c for c, _ in DocumentBlock.LANGUAGE_CHOICES}

    if template_type not in valid_types:
        return 'Type de document invalide.', None
    if position not in valid_positions:
        return 'Position invalide.', None
    if language not in valid_langs:
        return 'Langue invalide.', None
    if not body:
        return 'Le contenu est obligatoire.', None

    try:
        priority_int = int(priority)
    except ValueError:
        priority_int = 0

    # Service uses a UUID primary key; an invalid string raises ValidationError
    # at the SQL boundary, not a clean "not found". Wrap the count probe.
    from django.core.exceptions import ValidationError as DjangoValidationError
    services_qs = Service.objects.none()
    if service_ids:
        try:
            services_qs = Service.objects.filter(pk__in=service_ids)
            found = services_qs.count()
        except (DjangoValidationError, ValueError):
            return 'Un ou plusieurs identifiants de service sont invalides.', None
        if found != len(set(service_ids)):
            return 'Un ou plusieurs services sélectionnés sont introuvables.', None

    block.template_type = template_type
    block.position = position
    block.language = language
    block.title = title
    block.body = body
    block.priority = priority_int
    block.is_active = is_active
    return None, services_qs


@admin_required
def block_create(request):
    if request.method == 'POST':
        block = DocumentBlock(created_by=request.user, updated_by=request.user)
        error, services_qs = _save_block(request, block)
        if error:
            messages.error(request, error)
        else:
            block.save()
            block.services.set(services_qs)
            messages.success(request, 'Bloc de contenu créé.')
            return redirect('documents:block_list')
    return render(request, 'documents/block_form.html', _block_form_context())


@admin_required
def block_edit(request, pk):
    block = get_object_or_404(DocumentBlock, pk=pk)
    if request.method == 'POST':
        error, services_qs = _save_block(request, block)
        if error:
            messages.error(request, error)
        else:
            block.updated_by = request.user
            block.save()
            block.services.set(services_qs)
            messages.success(request, 'Bloc de contenu mis à jour.')
            return redirect('documents:block_list')
    return render(request, 'documents/block_form.html', _block_form_context(block))


@admin_required
def block_delete(request, pk):
    block = get_object_or_404(DocumentBlock, pk=pk)
    if request.method == 'POST':
        block.delete()
        messages.success(request, 'Bloc de contenu supprimé.')
        return redirect('documents:block_list')
    return render(request, 'documents/block_confirm_delete.html', {'block': block})


@admin_required
def block_toggle_active(request, pk):
    block = get_object_or_404(DocumentBlock, pk=pk)
    if request.method == 'POST':
        block.is_active = not block.is_active
        block.updated_by = request.user
        block.save(update_fields=['is_active', 'updated_by', 'updated_at'])
        state = 'activé' if block.is_active else 'désactivé'
        messages.success(request, f'Bloc {state}.')
    return redirect('documents:block_list')
