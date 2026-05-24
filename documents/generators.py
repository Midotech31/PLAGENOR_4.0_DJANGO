"""PLAGENOR document generators.

Each ``generate_*`` function returns a filesystem path to a finalised DOCX.
The path is then optionally rendered to PDF by ``documents.views`` via the
``pdf_converter`` module.

Phase 3.7 refactor highlights:
* Single :func:`build_field_map` is the source of truth for every placeholder
  the system supports — all four generators draw from the same dict, so an
  IBTIKAR form and a Platform Note never disagree on what ``{{FULL_NAME}}``
  resolves to.
* Placeholder substitution goes through :func:`docx_helpers.replace_placeholders`,
  which is run-preserving (the old ``paragraph.text = ...`` collapsed every
  run into one) and which only touches ``{{KEY}}``-wrapped tokens. The
  previous bare-key replacement caused the
  ``{{APPOINTMENT_24/05/2026}}`` corruption seen in reception forms.
* Programmatic-fallback generation applies the house style (A4, 1" margins,
  11 pt body) and injects the institutional logo banner into the header so
  that fallback documents look as branded as the IBTIKAR templates.
* Admin-editable :class:`documents.models.DocumentBlock` rows are injected
  at semantic positions (``TOP``, ``AFTER_REQUESTER``, ``AFTER_SAMPLES``,
  ``BEFORE_FOOTER``, ``BOTTOM``) so SuperAdmins can add notices/disclaimers
  globally or per-service without re-uploading the DOCX.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from django.conf import settings
from docx import Document
from docx.document import Document as DocumentType
from docx.shared import Pt

from documents.docx_helpers import (
    apply_house_style,
    ensure_institutional_header,
    replace_placeholders,
    strip_unresolved_placeholders,
)

_PLACEHOLDER_BARE_RE = re.compile(r'\{\{[A-Z0-9_]+\}\}')


IBTIKAR_TEMPLATE_MAP = {
    'EGTP-CAN': 'egtp_can.docx',
    'EGTP-IMT': 'egtp_imt.docx',
    'EGTP-PCR': 'egtp_pcr.docx',
    'EGTP-Lyoph': 'egtp_lyoph.docx',
    'EGTP-PS': 'egtp_ps.docx',
    'EGTP-Seq02': 'egtp_seq02.docx',
    'EGTP-SeqS': 'egtp_seqs.docx',
    'EGTP-GDE': 'egtp_gde.docx',
    'EGTP-Illumina-Microbial-WGS': 'egtp_illumina_wgs.docx',
}


def _money(value, currency='DZD', placeholder='N/A'):
    if value is None:
        return placeholder
    try:
        return f"{value:,.0f} {currency}"
    except (TypeError, ValueError):
        return placeholder


def _money_2dp(value, currency='DZD', placeholder='N/A'):
    if value is None:
        return placeholder
    try:
        return f"{value:,.2f} {currency}"
    except (TypeError, ValueError):
        return placeholder


def _safe_attr(obj, attr, default=''):
    try:
        return getattr(obj, attr, default) or default
    except Exception:
        return default


def _assigned_name(request_obj, placeholder='Non assigné'):
    try:
        if request_obj.assigned_to and request_obj.assigned_to.user:
            user = request_obj.assigned_to.user
            return user.get_full_name() or user.username or placeholder
    except Exception:
        pass
    return placeholder


def _assigned_email(request_obj, placeholder=''):
    try:
        if request_obj.assigned_to and request_obj.assigned_to.user:
            return _safe_attr(request_obj.assigned_to.user, 'email', placeholder)
    except Exception:
        pass
    return placeholder


def _format_date(value, placeholder='Non défini'):
    if not value:
        return placeholder
    try:
        return value.strftime('%d/%m/%Y')
    except Exception:
        return placeholder


def _format_sample_table_text(sample_table):
    """Render the sample_table JSON as a readable multi-line string."""
    if not sample_table or not isinstance(sample_table, list):
        return ''
    lines = []
    for i, sample in enumerate(sample_table, 1):
        if not isinstance(sample, dict):
            continue
        non_empty = [(k, v) for k, v in sample.items() if v not in (None, '', [])]
        if not non_empty:
            continue
        lines.append(f"#{i} " + " | ".join(f"{k}: {v}" for k, v in non_empty))
    return '\n'.join(lines)


def _format_service_params(service_params):
    """Render the service_params JSON as a readable key: value block."""
    if not service_params or not isinstance(service_params, dict):
        return ''
    out = []
    for key, value in service_params.items():
        if value in (None, '', [], {}):
            continue
        clean = key.replace('param_', '').replace('_', ' ').strip().capitalize()
        out.append(f"{clean}: {value}")
    return '\n'.join(out)


def build_field_map(request_obj) -> dict[str, str]:
    """Single source of truth for placeholder values.

    Every key listed here is documented in the SuperAdmin "Modèles de
    documents" help screen; the four generators draw from the same dict
    so callers never see drift between IBTIKAR and Platform Note for the
    same request.

    Naming conventions:
    * REQUESTER_*  — fields off ``request.requester`` (User row). For a
      guest submission these fall back to ``request.guest_*``.
    * SERVICE_*    — fields off ``request.service`` (Service row).
    * REQUEST_*    — fields directly on the Request row.
    * QUOTE_*      — derived financial figures for GENOCLAB.
    * ASSIGNED_*   — about the analyst the request is assigned to.
    * DATE / DATETIME / *_DATE — formatted dates.

    Legacy short-names (FULL_NAME, EMAIL, PHONE, etc.) are also emitted so
    pre-existing templates keep working — both forms are valid.
    """
    req = request_obj
    requester = req.requester

    if requester is not None:
        full_name = requester.get_full_name() or requester.username
        email = _safe_attr(requester, 'email')
        phone = _safe_attr(requester, 'phone')
        organization = _safe_attr(requester, 'organization')
        laboratory = _safe_attr(requester, 'laboratory')
        supervisor = _safe_attr(requester, 'supervisor')
        student_level = _safe_attr(requester, 'student_level')
        username = _safe_attr(requester, 'username')
    else:
        full_name = req.guest_name or 'N/A'
        email = req.guest_email or ''
        phone = req.guest_phone or ''
        organization = ''
        laboratory = ''
        supervisor = ''
        student_level = ''
        username = ''

    service = req.service
    if service is not None:
        svc_code = service.code
        svc_name = service.name
        svc_description = service.description or ''
        svc_turnaround = str(service.turnaround_days) if service.turnaround_days else 'N/A'
        svc_type = _safe_attr(service, 'service_type', 'Analysis')
    else:
        svc_code = 'N/A'
        svc_name = 'N/A'
        svc_description = ''
        svc_turnaround = 'N/A'
        svc_type = ''

    quote_amount = float(req.quote_amount or 0)
    vat_rate = float(getattr(settings, 'VAT_RATE', 0.19) or 0)
    vat_amount = round(quote_amount * vat_rate, 2)
    total_ttc = round(quote_amount + vat_amount, 2)

    field_map = {
        # ----- Dates --------------------------------------------------------
        'DATE': datetime.now().strftime('%d/%m/%Y'),
        'DATETIME': datetime.now().strftime('%d/%m/%Y à %H:%M'),
        'SUBMISSION_DATE': _format_date(req.created_at, placeholder=datetime.now().strftime('%d/%m/%Y')),
        'APPOINTMENT_DATE': _format_date(req.appointment_date),
        'CURRENT_YEAR': str(datetime.now().year),

        # ----- Request IDs -------------------------------------------------
        'DISPLAY_ID': req.display_id or '',
        'REQUEST_ID': str(req.pk),
        'TRACKING_CODE': str(req.guest_token or req.display_id or req.pk),
        'IBTIKAR_EXTERNAL_CODE': _safe_attr(req, 'ibtikar_external_code'),

        # ----- Requester / Client ------------------------------------------
        'FULL_NAME': full_name,
        'REQUESTER_NAME': full_name,
        'CLIENT_NAME': full_name,
        'USERNAME': username,
        'EMAIL': email,
        'REQUESTER_EMAIL': email,
        'CLIENT_EMAIL': email,
        'PHONE': phone,
        'REQUESTER_PHONE': phone,
        'ETABLISSEMENT': organization,
        'ORGANIZATION': organization,
        'LABORATORY': laboratory,
        'SUPERVISOR': supervisor,
        'STUDENT_LEVEL': student_level,
        'GUEST_NAME': req.guest_name or '',
        'GUEST_EMAIL': req.guest_email or '',
        'GUEST_PHONE': req.guest_phone or '',

        # ----- Service ------------------------------------------------------
        'SERVICE_CODE': svc_code,
        'SERVICE_NAME': svc_name,
        'SERVICE_DESCRIPTION': svc_description,
        'SERVICE_TURNAROUND': svc_turnaround,
        'TURNAROUND': svc_turnaround,
        'SERVICE_TYPE': svc_type,

        # ----- Request details ---------------------------------------------
        'TITLE': req.title or '',
        'PROJECT_TITLE': req.title or '',
        'DESCRIPTION': req.description or '',
        'CHANNEL': req.channel or '',
        'URGENCY': req.urgency or '',
        'STATUS': req.status or '',

        # ----- Financial ----------------------------------------------------
        'BUDGET_AMOUNT': _money(req.budget_amount),
        'IBTIKAR_BUDGET': _money(req.budget_amount),
        'IBTIKAR_BALANCE': _money(req.declared_ibtikar_balance),
        'FINAL_COST': _money(req.admin_validated_price, placeholder='En attente'),
        'QUOTE_AMOUNT': _money_2dp(quote_amount),
        'SUBTOTAL_HT': _money_2dp(quote_amount),
        'VAT_RATE': f"{vat_rate * 100:.0f}%",
        'VAT_AMOUNT': _money_2dp(vat_amount),
        'TVA': _money_2dp(vat_amount),  # legacy alias
        'TOTAL_TTC': _money_2dp(total_ttc),

        # ----- Assignment ---------------------------------------------------
        'ASSIGNED_ANALYST': _assigned_name(req),
        'ANALYST_NAME': _assigned_name(req),
        'ANALYST_EMAIL': _assigned_email(req),

        # ----- Free-text dumps ---------------------------------------------
        'SAMPLE_TABLE': _format_sample_table_text(req.sample_table),
        'SERVICE_PARAMS': _format_service_params(req.service_params),
    }
    return field_map


# DocumentBlock injection ---------------------------------------------------

def _resolve_block_language(request_obj) -> str:
    """Pick the language for DocumentBlock matching.

    Order of preference: requester's preferred_language → request channel
    default → settings.LANGUAGE_CODE. Validated against the supported
    language set so an unknown code can never reach the DB filter.
    """
    supported = {c for c, _ in getattr(settings, 'LANGUAGES', [])} or {'fr'}
    requester = getattr(request_obj, 'requester', None)
    if requester is not None:
        pref = getattr(requester, 'preferred_language', '') or ''
        if pref in supported:
            return pref
    default = getattr(settings, 'LANGUAGE_CODE', 'fr')
    return default if default in supported else 'fr'


def _resolve_block_text(text: str, field_map: dict) -> str:
    """Resolve ``{{KEY}}`` placeholders inside admin-authored block text.

    Mirrors the run-aware DOCX substitution behaviour for plain strings:
    only ``{{KEY}}``-wrapped tokens are touched (never bare keys), and
    unresolved tokens are stripped at the end so a stray placeholder
    never reaches the reader.
    """
    if not text:
        return ''
    for key, value in field_map.items():
        token = f'{{{{{key}}}}}'
        if token in text:
            text = text.replace(token, '' if value is None else str(value))
    return _PLACEHOLDER_BARE_RE.sub('', text)


def _inject_document_blocks(doc: DocumentType, template_type: str, request_obj) -> None:
    """Append admin-editable DocumentBlocks to the document.

    Blocks are appended at the end of the body in (position, priority, pk)
    order. The block's title (if any) is bolded; the body is split on
    blank lines into separate paragraphs. Placeholders inside the block
    text (``{{FULL_NAME}}``, ``{{DISPLAY_ID}}``, ``{{DATE}}``, …) are
    resolved against the same field_map the template substitution uses,
    so admins can author dynamic notices without escaping anything.
    """
    from documents.models import DocumentBlock

    language = _resolve_block_language(request_obj)
    blocks = list(DocumentBlock.applicable_blocks(
        template_type=template_type,
        service=request_obj.service,
        language=language,
    ))
    if not blocks and language != settings.LANGUAGE_CODE:
        # Fall back to the default-language blocks if the active language
        # has nothing to say — same fallback policy the cms template tag uses.
        blocks = list(DocumentBlock.applicable_blocks(
            template_type=template_type,
            service=request_obj.service,
            language=settings.LANGUAGE_CODE,
        ))
    if not blocks:
        return

    field_map = build_field_map(request_obj)

    for block in blocks:
        title_text = _resolve_block_text(block.title or '', field_map)
        body_text = _resolve_block_text(block.body or '', field_map)
        if title_text:
            heading = doc.add_paragraph()
            run = heading.add_run(title_text)
            run.bold = True
            run.font.size = Pt(12)
        # Split body on blank lines into paragraphs so newlines render.
        for chunk in body_text.split('\n\n'):
            chunk = chunk.strip()
            if not chunk:
                continue
            doc.add_paragraph(chunk)


def _get_uploaded_template(service, template_type) -> Optional[Path]:
    from documents.models import ServiceTemplate
    try:
        template = ServiceTemplate.objects.filter(
            service=service,
            template_type=template_type,
            is_active=True,
        ).first()
        if template and template.file:
            file_path = Path(settings.MEDIA_ROOT) / template.file.name
            if file_path.exists():
                return file_path
    except Exception:
        pass
    return None


def _save_document(doc: DocumentType, prefix: str, request_obj) -> str:
    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_id = (request_obj.display_id or str(request_obj.pk)).replace('/', '_')
    filename = f"{prefix}_{safe_id}_{datetime.now().strftime('%Y%m%d')}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)


# Generators ----------------------------------------------------------------

def generate_ibtikar_form(request_obj) -> str:
    """IBTIKAR form. Priority: uploaded template → service-specific
    branded template (egtp_*.docx with the institutional banner already
    in the header) → generic generic template → programmatic fallback.
    """
    field_map = build_field_map(request_obj)
    doc: Optional[DocumentType] = None

    if request_obj.service:
        uploaded = _get_uploaded_template(request_obj.service, 'IBTIKAR_FORM')
        if uploaded:
            doc = Document(str(uploaded))

    if doc is None and request_obj.service:
        template_name = IBTIKAR_TEMPLATE_MAP.get(request_obj.service.code, '')
        if template_name:
            path = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'ibtikar' / template_name
            if path.exists():
                doc = Document(str(path))

    if doc is None:
        generic = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'ibtikar_form_template.docx'
        if generic.exists():
            doc = Document(str(generic))

    if doc is None:
        doc = _build_ibtikar_form_programmatic(request_obj, field_map)

    replace_placeholders(doc, field_map)
    strip_unresolved_placeholders(doc)
    ensure_institutional_header(doc)
    _inject_document_blocks(doc, 'IBTIKAR_FORM', request_obj)
    return _save_document(doc, 'IBTIKAR', request_obj)


def _build_ibtikar_form_programmatic(request_obj, field_map) -> DocumentType:
    doc = Document()
    apply_house_style(doc)
    doc.add_heading('Formulaire IBTIKAR — PLAGENOR', level=1)
    doc.add_heading("ESSBO — École Supérieure en Sciences Biologiques d'Oran", level=2)
    doc.add_paragraph(f"Référence : {field_map['DISPLAY_ID']}")
    doc.add_paragraph(f"Date : {field_map['DATE']}")
    doc.add_paragraph('')

    doc.add_heading('Informations du demandeur', level=2)
    table = doc.add_table(rows=8, cols=2)
    table.style = 'Light Grid Accent 1'
    fields = [
        ('Nom complet', field_map['FULL_NAME']),
        ('Email', field_map['EMAIL']),
        ('Téléphone', field_map['PHONE']),
        ('Établissement', field_map['ETABLISSEMENT']),
        ('Laboratoire', field_map['LABORATORY']),
        ('Directeur de recherche', field_map['SUPERVISOR']),
        ('Niveau', field_map['STUDENT_LEVEL']),
        ('Code IBTIKAR-DGRSDT', field_map['IBTIKAR_EXTERNAL_CODE']),
    ]
    for i, (label, value) in enumerate(fields):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = str(value or '')

    doc.add_heading('Service demandé', level=2)
    svc_table = doc.add_table(rows=4, cols=2)
    svc_table.style = 'Light Grid Accent 1'
    svc_fields = [
        ('Code', field_map['SERVICE_CODE']),
        ('Intitulé', field_map['SERVICE_NAME']),
        ('Description', field_map['SERVICE_DESCRIPTION']),
        ('Délai', f"{field_map['SERVICE_TURNAROUND']} jours"),
    ]
    for i, (label, value) in enumerate(svc_fields):
        svc_table.rows[i].cells[0].text = label
        svc_table.rows[i].cells[1].text = str(value or '')

    doc.add_heading('Détails de la demande', level=2)
    doc.add_paragraph(f"Titre du projet : {field_map['TITLE']}")
    if field_map['DESCRIPTION']:
        doc.add_paragraph(f"Description : {field_map['DESCRIPTION']}")
    doc.add_paragraph(f"Urgence : {field_map['URGENCY']}")
    doc.add_paragraph(f"Budget estimé : {field_map['BUDGET_AMOUNT']}")
    doc.add_paragraph(f"Solde IBTIKAR déclaré : {field_map['IBTIKAR_BALANCE']}")

    _render_sample_table(doc, request_obj.sample_table)
    _render_service_params(doc, request_obj.service_params)
    _render_footer(doc)
    return doc


def generate_platform_note(request_obj) -> str:
    """Platform Note. Priority: uploaded template → static generic template
    → programmatic fallback. Substitution is run-preserving so existing
    bold/italic/colour from the template survives.
    """
    field_map = build_field_map(request_obj)
    doc: Optional[DocumentType] = None

    if request_obj.service:
        uploaded = _get_uploaded_template(request_obj.service, 'PLATFORM_NOTE')
        if uploaded:
            doc = Document(str(uploaded))

    if doc is None:
        generic = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'platform_note_template.docx'
        if generic.exists():
            doc = Document(str(generic))

    if doc is None:
        doc = _build_platform_note_programmatic(request_obj, field_map)

    replace_placeholders(doc, field_map)
    strip_unresolved_placeholders(doc)
    ensure_institutional_header(doc)
    _inject_document_blocks(doc, 'PLATFORM_NOTE', request_obj)
    return _save_document(doc, 'NOTE_PLT', request_obj)


def _build_platform_note_programmatic(request_obj, field_map) -> DocumentType:
    doc = Document()
    apply_house_style(doc)

    doc.add_heading('NOTE DE PLATEFORME — PLAGENOR', level=1)
    doc.add_paragraph("ESSBO — École Supérieure en Sciences Biologiques d'Oran")
    doc.add_paragraph(f"Référence : {field_map['DISPLAY_ID']}")
    doc.add_paragraph(f"Date d'émission : {field_map['DATETIME']}")
    doc.add_paragraph('')

    doc.add_heading('Demandeur', level=2)
    table = doc.add_table(rows=7, cols=2)
    table.style = 'Light Grid Accent 1'
    fields = [
        ('Nom complet', field_map['FULL_NAME']),
        ('Établissement', field_map['ETABLISSEMENT']),
        ('Laboratoire', field_map['LABORATORY']),
        ('Niveau / fonction', field_map['STUDENT_LEVEL']),
        ('Directeur de recherche', field_map['SUPERVISOR']),
        ('Email', field_map['EMAIL']),
        ('Téléphone', field_map['PHONE']),
    ]
    for i, (label, value) in enumerate(fields):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = str(value or '')

    doc.add_heading('Service demandé', level=2)
    doc.add_paragraph(f"Code : {field_map['SERVICE_CODE']}")
    doc.add_paragraph(f"Intitulé : {field_map['SERVICE_NAME']}")
    if field_map['SERVICE_DESCRIPTION']:
        doc.add_paragraph(f"Description : {field_map['SERVICE_DESCRIPTION']}")
    doc.add_paragraph(f"Délai estimé : {field_map['SERVICE_TURNAROUND']} jours ouvrables")

    doc.add_heading('Détails de la demande', level=2)
    doc.add_paragraph(f"Titre : {field_map['TITLE']}")
    if field_map['DESCRIPTION']:
        doc.add_paragraph(f"Description : {field_map['DESCRIPTION']}")
    doc.add_paragraph(f"Canal : {field_map['CHANNEL']}")
    doc.add_paragraph(f"Urgence : {field_map['URGENCY']}")

    _render_service_params(doc, request_obj.service_params)
    _render_sample_table(doc, request_obj.sample_table)

    doc.add_heading('Décompte budgétaire IBTIKAR', level=2)
    doc.add_paragraph('Budget annuel par étudiant : 200 000 DZD')
    doc.add_paragraph(f"Montant de cette prestation : {field_map['BUDGET_AMOUNT']}")
    if request_obj.declared_ibtikar_balance:
        doc.add_paragraph(f"Solde IBTIKAR déclaré : {field_map['IBTIKAR_BALANCE']}")

    if request_obj.assigned_to:
        doc.add_heading('Assignation', level=2)
        doc.add_paragraph(f"Analyste : {field_map['ASSIGNED_ANALYST']}")
        if field_map['ANALYST_EMAIL']:
            doc.add_paragraph(f"Email analyste : {field_map['ANALYST_EMAIL']}")
        if field_map['APPOINTMENT_DATE'] != 'Non défini':
            doc.add_paragraph(f"Rendez-vous : {field_map['APPOINTMENT_DATE']}")

    _render_footer(doc)
    return doc


def generate_quote(request_obj) -> str:
    """GENOCLAB quote. Priority: uploaded template → static generic
    template → programmatic fallback.
    """
    field_map = build_field_map(request_obj)

    # Quote number — sequential, atomic.
    from core.sequences import next_value
    year = datetime.now().year
    seq = next_value(f'GENOCLAB-QUOTE-{year}')
    quote_number = f"GENOCLAB-DEV-{year}-{seq:04d}"
    field_map['QUOTE_NUMBER'] = quote_number
    field_map['INVOICE_NUMBER'] = quote_number  # legacy alias

    doc: Optional[DocumentType] = None

    if request_obj.service:
        uploaded = _get_uploaded_template(request_obj.service, 'QUOTE')
        if uploaded:
            doc = Document(str(uploaded))

    if doc is None:
        generic = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'quote_template.docx'
        if generic.exists():
            doc = Document(str(generic))

    if doc is None:
        doc = _build_quote_programmatic(request_obj, field_map)

    replace_placeholders(doc, field_map)
    strip_unresolved_placeholders(doc)
    ensure_institutional_header(doc)
    _inject_document_blocks(doc, 'QUOTE', request_obj)
    return _save_document(doc, 'DEVIS', request_obj)


def _build_quote_programmatic(request_obj, field_map) -> DocumentType:
    doc = Document()
    apply_house_style(doc)

    doc.add_heading('DEVIS — GENOCLAB', level=1)
    doc.add_paragraph("ESSBO — École Supérieure en Sciences Biologiques d'Oran")
    doc.add_paragraph(f"N° Devis : {field_map['QUOTE_NUMBER']}")
    doc.add_paragraph(f"Référence demande : {field_map['DISPLAY_ID']}")
    doc.add_paragraph(f"Date : {field_map['DATE']}")
    doc.add_paragraph('')

    doc.add_heading('Client', level=2)
    client_table = doc.add_table(rows=5, cols=2)
    client_table.style = 'Light Grid Accent 1'
    fields = [
        ('Nom', field_map['CLIENT_NAME']),
        ('Organisation', field_map['ORGANIZATION']),
        ('Email', field_map['CLIENT_EMAIL']),
        ('Téléphone', field_map['PHONE']),
        ('Laboratoire', field_map['LABORATORY']),
    ]
    for i, (label, value) in enumerate(fields):
        client_table.rows[i].cells[0].text = label
        client_table.rows[i].cells[1].text = str(value or '')

    doc.add_heading('Prestations', level=2)
    table = doc.add_table(rows=2, cols=4)
    table.style = 'Light Grid Accent 1'
    headers = ['Description', 'Quantité', 'Prix unitaire', 'Total']
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    table.rows[1].cells[0].text = field_map['SERVICE_NAME']
    table.rows[1].cells[1].text = '1'
    table.rows[1].cells[2].text = field_map['SUBTOTAL_HT']
    table.rows[1].cells[3].text = field_map['SUBTOTAL_HT']

    doc.add_paragraph('')
    summary = doc.add_table(rows=3, cols=2)
    summary.style = 'Light Grid Accent 1'
    summary.rows[0].cells[0].text = 'Sous-total HT'
    summary.rows[0].cells[1].text = field_map['SUBTOTAL_HT']
    summary.rows[1].cells[0].text = f"TVA ({field_map['VAT_RATE']})"
    summary.rows[1].cells[1].text = field_map['VAT_AMOUNT']
    summary.rows[2].cells[0].text = 'Total TTC'
    summary.rows[2].cells[1].text = field_map['TOTAL_TTC']

    _render_footer(doc)
    return doc


def generate_reception_form(request_obj) -> str:
    field_map = build_field_map(request_obj)
    doc: Optional[DocumentType] = None

    if request_obj.service:
        uploaded = _get_uploaded_template(request_obj.service, 'RECEPTION_FORM')
        if uploaded:
            doc = Document(str(uploaded))

    if doc is None:
        generic = Path(settings.BASE_DIR) / 'documents' / 'docx_templates' / 'reception_form_template.docx'
        if generic.exists():
            doc = Document(str(generic))

    if doc is None:
        doc = _build_reception_form_programmatic(request_obj, field_map)

    replace_placeholders(doc, field_map)
    strip_unresolved_placeholders(doc)
    ensure_institutional_header(doc)
    _inject_document_blocks(doc, 'RECEPTION_FORM', request_obj)
    return _save_document(doc, 'RECEPTION', request_obj)


def _build_reception_form_programmatic(request_obj, field_map) -> DocumentType:
    doc = Document()
    apply_house_style(doc)

    doc.add_heading("Fiche de Réception d'Échantillons", level=1)
    doc.add_paragraph('PLAGENOR — ESSBO')
    doc.add_paragraph(f"Référence : {field_map['DISPLAY_ID']}")
    doc.add_paragraph(f"Code de suivi : {field_map['TRACKING_CODE']}")
    doc.add_paragraph('')

    table = doc.add_table(rows=6, cols=2)
    table.style = 'Light Grid Accent 1'
    fields = [
        ('Service', field_map['SERVICE_NAME']),
        ('Canal', field_map['CHANNEL']),
        ('Urgence', field_map['URGENCY']),
        ('Date de RDV', field_map['APPOINTMENT_DATE']),
        ('Analyste assigné', field_map['ASSIGNED_ANALYST']),
        ('Date de soumission', field_map['SUBMISSION_DATE']),
    ]
    for i, (label, value) in enumerate(fields):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = str(value or '')

    doc.add_heading('Déposant', level=2)
    client_table = doc.add_table(rows=5, cols=2)
    client_table.style = 'Light Grid Accent 1'
    client_fields = [
        ('Nom', field_map['FULL_NAME']),
        ('Email', field_map['EMAIL']),
        ('Téléphone', field_map['PHONE']),
        ('Établissement', field_map['ETABLISSEMENT']),
        ('Laboratoire', field_map['LABORATORY']),
    ]
    for i, (label, value) in enumerate(client_fields):
        client_table.rows[i].cells[0].text = label
        client_table.rows[i].cells[1].text = str(value or '')

    _render_sample_table(doc, request_obj.sample_table)

    doc.add_heading('Réception', level=2)
    rec_table = doc.add_table(rows=4, cols=2)
    rec_table.style = 'Light Grid Accent 1'
    rec_fields = [
        ('Date de réception', '___ / ___ / ______'),
        ("Nombre d'échantillons reçus", '____________'),
        ('État des échantillons', '☐ Bon   ☐ Acceptable   ☐ Dégradé'),
        ('Observations', ''),
    ]
    for i, (label, value) in enumerate(rec_fields):
        rec_table.rows[i].cells[0].text = label
        rec_table.rows[i].cells[1].text = str(value or '')

    doc.add_paragraph('')
    doc.add_paragraph('Signature du réceptionniste : ________________________')
    doc.add_paragraph('Signature du déposant : ________________________')
    _render_footer(doc)
    return doc


# Section helpers (shared body builders) -----------------------------------

def _render_sample_table(doc: DocumentType, sample_table) -> None:
    if not sample_table or not isinstance(sample_table, list):
        return
    samples = [s for s in sample_table if isinstance(s, dict) and any(s.values())]
    if not samples:
        return
    doc.add_heading('Tableau des échantillons', level=3)
    headers = list(samples[0].keys())
    table = doc.add_table(rows=len(samples) + 1, cols=len(headers))
    table.style = 'Light Grid Accent 1'
    for j, h in enumerate(headers):
        table.rows[0].cells[j].text = h.replace('_', ' ').capitalize()
    for i, sample in enumerate(samples):
        for j, h in enumerate(headers):
            table.rows[i + 1].cells[j].text = str(sample.get(h, ''))


def _render_service_params(doc: DocumentType, service_params) -> None:
    if not service_params or not isinstance(service_params, dict):
        return
    non_empty = [(k, v) for k, v in service_params.items() if v not in (None, '', [], {})]
    if not non_empty:
        return
    doc.add_heading('Paramètres du service', level=3)
    table = doc.add_table(rows=len(non_empty), cols=2)
    table.style = 'Light Grid Accent 1'
    for i, (key, value) in enumerate(non_empty):
        table.rows[i].cells[0].text = key.replace('param_', '').replace('_', ' ').capitalize()
        table.rows[i].cells[1].text = str(value)


def _render_footer(doc: DocumentType) -> None:
    doc.add_paragraph('')
    doc.add_paragraph('—' * 40)
    p = doc.add_paragraph()
    run = p.add_run(
        f"Document généré automatiquement par PLAGENOR 4.0 · "
        f"{datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    )
    run.font.size = Pt(9)


def generate_invoice_document(invoice_obj) -> str:
    """Standalone invoice DOCX (programmatic only — no template at present)."""
    doc = Document()
    apply_house_style(doc)
    doc.add_heading(f'Facture {invoice_obj.invoice_number}', level=1)
    doc.add_paragraph('GENOCLAB — ESSBO')
    doc.add_paragraph(f"Date : {invoice_obj.created_at.strftime('%d/%m/%Y')}")
    if invoice_obj.client:
        doc.add_paragraph(f"Client : {invoice_obj.client.get_full_name()}")

    table = doc.add_table(rows=3, cols=2)
    table.style = 'Light Grid Accent 1'
    table.rows[0].cells[0].text = 'Sous-total HT'
    table.rows[0].cells[1].text = _money_2dp(invoice_obj.subtotal_ht)
    table.rows[1].cells[0].text = f"TVA ({float(invoice_obj.vat_rate) * 100:.0f}%)"
    table.rows[1].cells[1].text = _money_2dp(invoice_obj.vat_amount)
    table.rows[2].cells[0].text = 'Total TTC'
    table.rows[2].cells[1].text = _money_2dp(invoice_obj.total_ttc)

    ensure_institutional_header(doc)
    _render_footer(doc)

    out_dir = Path(settings.MEDIA_ROOT) / 'documents'
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"INVOICE_{invoice_obj.invoice_number}.docx"
    filepath = out_dir / filename
    doc.save(str(filepath))
    return str(filepath)
