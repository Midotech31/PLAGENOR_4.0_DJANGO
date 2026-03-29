from pathlib import Path
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, FileResponse, Http404
from django.shortcuts import get_object_or_404

from core.models import Request
from documents.generators import (
    generate_ibtikar_form,
    generate_platform_note,
    generate_quote,
    generate_reception_form,
)


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
    return _serve_docx(filepath, os.path.basename(filepath))


@login_required
def platform_note_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin:
        return HttpResponseForbidden()
    filepath = generate_platform_note(req)
    return _serve_docx(filepath, os.path.basename(filepath))


@login_required
def quote_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin and request.user != req.requester:
        return HttpResponseForbidden()
    filepath = generate_quote(req)
    return _serve_docx(filepath, os.path.basename(filepath))


@login_required
def reception_form_view(request, request_id):
    req = get_object_or_404(Request, pk=request_id)
    if not request.user.is_admin and request.user != req.requester:
        return HttpResponseForbidden()
    filepath = generate_reception_form(req)
    return _serve_docx(filepath, os.path.basename(filepath))
