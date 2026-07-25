"""Stats dashboard views.

One read endpoint serves every role — ``stats_for_user`` in ``core.stats``
returns the bundle appropriate to who's asking. Admin + super-admin get
the full breakdown (wilaya / établissement / cadre / sexe) with filters;
other roles get a personal scope.

An export endpoint streams the same bundle as a branded DOCX so the
admin can produce the official statistics document (PDF on hosts that
have LibreOffice).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponseForbidden, Http404
from django.shortcuts import render

from core.stats import stats_for_user
from accounts.models import User


def _common_filters(request):
    """Pull the supported filter kwargs from the GET querystring."""
    g = request.GET
    out = {}
    for key in ('channel', 'service_code', 'status', 'wilaya', 'organization',
                'gender', 'analysis_frame'):
        v = g.get(key, '').strip()
        if v:
            out[key] = v
    df, dt = g.get('date_from'), g.get('date_to')
    if df:
        out['date_from'] = df
    if dt:
        out['date_to'] = dt
    return out


@login_required
def stats_view(request):
    """Role-aware stats dashboard."""
    from core.bilan import available_sections, DEFAULT_SECTIONS
    filters = _common_filters(request)
    bundle = stats_for_user(request.user, **filters)
    context = {
        'bundle': bundle,
        'filters': filters,
        'wilaya_choices': User.WILAYA_CHOICES,
        'gender_choices': User.GENDER_CHOICES,
        'channels': [('IBTIKAR', 'IBTIKAR'), ('GENOCLAB', 'GENOCLAB')],
        'is_admin': request.user.role in ('SUPER_ADMIN', 'PLATFORM_ADMIN'),
        'bilan_sections': available_sections(),
        'bilan_default_sections': DEFAULT_SECTIONS,
    }
    return render(request, 'dashboard/stats.html', context)


@login_required
def stats_export(request):
    """Download the configured activity report (bilan).

    Restricted to admin roles. Excel (.xlsx) is the default, fully
    configurable format — the admin picks the dimensions, the period
    granularity and the filters. DOCX/PDF remains available as a fallback
    summary via ``format=docx``.
    """
    if request.user.role not in ('SUPER_ADMIN', 'PLATFORM_ADMIN'):
        return HttpResponseForbidden()

    filters = _common_filters(request)
    fmt = (request.GET.get('format') or 'xlsx').lower()

    if fmt in ('xlsx', 'excel'):
        from core.bilan import build_bilan, DEFAULT_SECTIONS
        from documents.stats_excel import generate_bilan_excel
        sections = request.GET.getlist('sections') or list(DEFAULT_SECTIONS)
        granularity = (request.GET.get('granularity') or 'month').lower()
        if granularity not in ('month', 'quarter', 'year'):
            granularity = 'month'
        bilan = build_bilan(filters, sections=sections, granularity=granularity)
        xlsx_path = Path(generate_bilan_excel(bilan, filters, request.user))
        download_name = f"PLAGENOR_Bilan_{datetime.now().strftime('%Y%m%d')}.xlsx"
        response = FileResponse(
            open(xlsx_path, 'rb'),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response

    # --- DOCX / PDF fallback (summary document) ---
    from documents.generators import generate_stats_report
    from documents.pdf_converter import convert_docx_to_pdf

    bundle = stats_for_user(request.user, **filters)
    docx_path = Path(generate_stats_report(bundle, filters, request.user))
    suffix = '.docx'
    served = docx_path
    if getattr(settings, 'DOCUMENT_PDF_ENABLED', True):
        rendered = convert_docx_to_pdf(docx_path, output_dir=docx_path.parent)
        if rendered.suffix == '.pdf':
            served = rendered
            suffix = '.pdf'
    download_name = f"PLAGENOR_Statistiques_{datetime.now().strftime('%Y%m%d')}{suffix}"
    content_type = ('application/pdf' if suffix == '.pdf'
                    else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response = FileResponse(open(served, 'rb'), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{download_name}"'
    return response
