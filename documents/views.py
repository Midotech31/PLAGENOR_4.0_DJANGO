from pathlib import Path
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


@login_required
def ibtikar_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin and request.user != req.requester:
        return HttpResponseForbidden()
    filepath = generate_ibtikar_form(req)
    return _serve_docx(filepath, Path(filepath).name)


@login_required
def platform_note_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin:
        return HttpResponseForbidden()
    filepath = generate_platform_note(req)
    return _serve_docx(filepath, Path(filepath).name)


@login_required
def quote_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin and request.user != req.requester:
        return HttpResponseForbidden()
    filepath = generate_quote(req)
    return _serve_docx(filepath, Path(filepath).name)


@login_required
def reception_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin and request.user != req.requester:
        return HttpResponseForbidden()
    filepath = generate_reception_form(req)
    return _serve_docx(filepath, Path(filepath).name)


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
