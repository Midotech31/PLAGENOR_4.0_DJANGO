# documents/pdf_generator_platform_note.py — PLAGENOR 4.0 Platform Note PDF Generator
# Generates the official platform note document as PDF

from io import BytesIO
from datetime import datetime
import logging
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.utils.translation import gettext_lazy as _

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, Flowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from .pdf_styles import (
    MARGIN, PAGE_WIDTH, PAGE_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_BORDER, COLOR_HEADER_BG,
    COLOR_TEXT, COLOR_GRAY, COLOR_LIGHT_GRAY, COLOR_SUCCESS,
    FONT_HELVETICA, FONT_HELVETICA_BOLD, FONT_TIMES, FONT_TIMES_BOLD,
    get_styles, get_base_table_style, style_label_value_table,
    get_essbo_logo, get_plagenor_logo,
    format_date, format_datetime, format_currency,
    HorizontalLine, SectionDivider, SignatureBlock,
    make_page_template
)
from .pdf_labels import get_labels, get_label
from .pdf_dynamic_fields import get_pdf_fields, render_pdf_fields

logger = logging.getLogger('plagenor.documents')


# =============================================================================
# HELPER FLOWABLES
# =============================================================================

class Checkbox(Flowable):
    """A checkbox flowable."""
    
    def __init__(self, size=10, checked=False):
        Flowable.__init__(self)
        self.box_size = size
        self.checked = checked
        self.width = size + 4
        self.height = size + 2
    
    def wrap(self, availableWidth, availableHeight):
        return self.width, self.height
    
    def draw(self):
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(1)
        self.canv.rect(0, 1, self.box_size, self.box_size, fill=0, stroke=1)
        
        if self.checked:
            self.canv.setFillColor(COLOR_PRIMARY)
            self.canv.setFont(FONT_HELVETICA_BOLD, self.box_size - 1)
            self.canv.drawString(1, 2, '✓')


class SignatureLine(Flowable):
    """A signature line with optional date."""
    
    def __init__(self, width, label='', date_label='Date:', date_width=80, line_length=None):
        Flowable.__init__(self)
        self.line_width = width
        self.label = label
        self.date_label = date_label
        self.date_width = date_width
        self.signature_line_length = line_length or (width - date_width - 10)
        self.height = 50
    
    def wrap(self, availableWidth, availableHeight):
        self.width = min(self.line_width, availableWidth)
        return self.width, self.height
    
    def draw(self):
        if self.label:
            self.canv.setFont(FONT_HELVETICA, 9)
            self.canv.setFillColor(COLOR_GRAY)
            self.canv.drawString(0, 35, self.label)
        
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(0.5)
        line_start = 0
        self.canv.line(line_start, 20, line_start + self.signature_line_length, 20)
        
        date_start = line_start + self.signature_line_length + 8
        self.canv.setFont(FONT_HELVETICA, 8)
        self.canv.setFillColor(COLOR_GRAY)
        self.canv.drawString(date_start, 25, self.date_label)
        self.canv.line(date_start, 12, date_start + self.date_width, 12)


# =============================================================================
# MAIN GENERATOR FUNCTION
# =============================================================================

def generate_platform_note_pdf(request_obj, lang=None, force_regenerate=False):
    """
    Generate a Platform Note PDF for an IBTIKAR request.
    
    This document is generated when Admin Ops validates an IBTIKAR request
    and serves as an official "devis" documenting the analysis and cost.
    
    Args:
        request_obj: Request model instance
        lang: Language code ('fr' or 'en'), defaults to request.language or 'fr'
        force_regenerate: If True, regenerate even if note already exists
        
    Returns:
        Tuple of (file_path, error_message) - file_path is None on error
    """
    # Determine language
    lang = lang or getattr(request_obj, 'language', None) or 'fr'
    labels = get_labels(lang)
    
    # Check if note already exists (unless force_regenerate)
    if not force_regenerate and request_obj.generated_platform_note:
        existing_path = request_obj.generated_platform_note.path
        if existing_path and Path(existing_path).exists():
            logger.info(f"Platform note already exists for {request_obj.display_id}")
            return str(existing_path), None
    
    # Get service
    service = request_obj.service
    if not service:
        logger.warning(f"Request {request_obj.pk}: no service linked, skipping Platform Note PDF generation.")
        return None, "NO_SERVICE"
    
    try:
        # Create PDF buffer
        buffer = BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + 1*cm,
            title=labels['platform_note_title'],
            author='PLAGENOR 4.0',
            subject=f"Platform Note - {request_obj.display_id}",
        )
        
        # Build content
        story = []
        styles = get_styles()
        page_width = PAGE_WIDTH - 2 * MARGIN
        
        # -------------------------------------------------------------------------
        # HEADER
        # -------------------------------------------------------------------------
        story.extend(build_platform_note_header(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 1: IDENTIFICATION
        # -------------------------------------------------------------------------
        story.extend(build_identification_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 2: ANALYSIS INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_analysis_info_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 3: SERVICE DESCRIPTION
        # -------------------------------------------------------------------------
        story.extend(build_service_description_section(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 4: PROCESSING NOTES
        # -------------------------------------------------------------------------
        story.extend(build_processing_notes_section(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 5: PRICING
        # -------------------------------------------------------------------------
        story.extend(build_pricing_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 6: DELIVERABLES
        # -------------------------------------------------------------------------
        story.extend(build_deliverables_section(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 7: LAB CONTACT
        # -------------------------------------------------------------------------
        story.extend(build_lab_contact_section(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 8: ESTIMATED TURNAROUND
        # -------------------------------------------------------------------------
        story.extend(build_turnaround_section(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 8: COMPLIANCE STATEMENT
        # -------------------------------------------------------------------------
        story.extend(build_compliance_statement(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # DYNAMIC PDF FIELDS (SUPERADMIN)
        # -------------------------------------------------------------------------
        dynamic_fields = get_pdf_fields('platform_note', service=service)
        if dynamic_fields:
            render_pdf_fields(story, dynamic_fields, styles, page_width, request_obj.additional_data or {})

        # -------------------------------------------------------------------------
        # SIGNATURE BLOCK
        # -------------------------------------------------------------------------
        story.extend(build_signature_block(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # BUILD PDF
        # -------------------------------------------------------------------------
        doc.build(story, onFirstPage=lambda c, d: make_page_template(c, d, with_page_numbers=True),
                  onLaterPages=lambda c, d: make_page_template(c, d, with_page_numbers=True))
        
        # Save to model
        buffer.seek(0)
        filename = f"PLAGENOR_Note_{service.code}_{request_obj.display_id}.pdf"
        
        from django.core.files.base import ContentFile
        pdf_content = ContentFile(buffer.read())
        
        request_obj.generated_platform_note.save(filename, pdf_content, save=True)
        
        logger.info(f"Generated Platform Note PDF for {request_obj.display_id}: {filename}")
        return str(request_obj.generated_platform_note.path), None
        
    except Exception as e:
        logger.error(
            f"Failed to generate Platform Note PDF for {request_obj.display_id}: {str(e)}",
            exc_info=True
        )
        return None, f"ERROR: {str(e)}"


# =============================================================================
# SECTION BUILDERS
# =============================================================================

def build_platform_note_header(request_obj, service, labels, page_width, styles):
    """Build the document header."""
    story = []
    
    # Generate QR code for tracking
    qr_img = None
    try:
        from core.qrcode_utils import generate_request_tracking_qr
        from django.contrib.sites.models import Site
        current_site = Site.objects.get_current()
        base_url = f"https://{current_site.domain}" if current_site else None
        qr_data_url = generate_request_tracking_qr(request_obj, base_url=base_url)
        if qr_data_url:
            import base64
            from io import BytesIO
            from reportlab.lib.utils import ImageReader
            qr_parts = qr_data_url.split(',')
            if len(qr_parts) >= 2:
                qr_data = qr_parts[1]
                qr_bytes = base64.b64decode(qr_data)
                qr_img = ImageReader(BytesIO(qr_bytes))
    except Exception as e:
        logger.debug(f"Could not generate QR code for Platform Note: {e}")
    
    # Date (left-aligned)
    today = format_date(datetime.now())
    date_text = f"<b>{labels.get('date_format', 'Date:').format(date=today)}</b>"
    
    # Logo row with QR code
    essbo_logo = get_essbo_logo(width=2.5*cm)
    plagenor_logo = get_plagenor_logo(width=2.5*cm)
    
    if qr_img:
        # Table with logos, date, and QR code
        header_content = [[essbo_logo, Paragraph(date_text, styles['Reference']), Image(qr_img, width=2*cm, height=2*cm)]]
        col_widths = [2.5*cm, page_width - 4.5*cm - 2*cm, 2*cm]
    else:
        header_content = [[essbo_logo, Paragraph(date_text, styles['Reference']), plagenor_logo]]
        col_widths = [2.5*cm, page_width - 5*cm, 2.5*cm]
    
    header_table = Table(header_content, colWidths=col_widths)
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 8))
    
    # Title
    story.append(Paragraph(labels['platform_note_title'], styles['DocumentTitle']))
    story.append(Paragraph(labels['platform_note_subtitle'], styles['DocumentSubtitle']))
    
    story.append(Spacer(1, 8))
    story.append(HorizontalLine(page_width, thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 12))
    
    return story


def build_identification_section(request_obj, service, labels, page_width, styles):
    """Build Section 1: Identification."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section1'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Build identification table
    service_code = getattr(service, 'service_code', None) or service.code or 'N/A'
    
    data = [
        [Paragraph(labels['service_code'], styles['Label']), 
         Paragraph(str(service_code), styles['Value'])],
        [Paragraph(labels['request_id'], styles['Label']), 
         Paragraph(str(request_obj.display_id), styles['Value'])],
        [Paragraph(labels['date_issued'], styles['Label']), 
         Paragraph(format_date(datetime.now()), styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 12))
    
    return story


def build_analysis_info_section(request_obj, service, labels, page_width, styles):
    """Build Section 2: Analysis Information."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section2'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get sample count
    samples = request_obj.sample_table if request_obj.sample_table else []
    if not isinstance(samples, list):
        samples = []
    sample_count = len(samples)
    
    # Build analysis info table
    data = [
        [Paragraph(labels['analysis_type'], styles['Label']), 
         Paragraph(str(service.name), styles['Value'])],
        [Paragraph(labels['number_of_samples'], styles['Label']), 
         Paragraph(str(sample_count), styles['Value'])],
        [Paragraph(labels['project_title'], styles['Label']), 
         Paragraph(str(request_obj.title or ''), styles['Value'])],
    ]
    
    # Add requester info
    requester = request_obj.requester
    if requester:
        requester_name = requester.get_full_name() or requester.username or ''
        data.append([
            Paragraph(labels['full_name'], styles['Label']),
            Paragraph(str(requester_name), styles['Value'])
        ])
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    # Sample details summary
    if samples:
        story.append(Spacer(1, 8))
        story.append(Paragraph(labels['sample_details'], styles['Label']))
        story.append(Spacer(1, 4))
        
        # Create summary list
        sample_types = []
        for sample in samples[:10]:  # Show first 10
            if isinstance(sample, dict):
                sample_type = sample.get('type', sample.get('param_type', '')) or ''
                sample_origin = sample.get('origin', sample.get('param_origin', '')) or ''
                if sample_type:
                    summary = sample_type
                    if sample_origin:
                        summary += f" ({sample_origin})"
                    sample_types.append(summary)
        
        if sample_types:
            summary_text = ', '.join(sample_types)
            if len(samples) > 10:
                summary_text += f" ... (+{len(samples) - 10} more)"
            story.append(Paragraph(summary_text, styles['BodySmall']))
    
    story.append(Spacer(1, 12))
    return story


def build_service_description_section(service, labels, page_width, styles):
    """Build Section 3: Service Description."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section3'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get service description
    description = getattr(service, 'description', '') or ''
    
    if description:
        story.append(Paragraph(description, styles['BodySerif']))
    else:
        story.append(Paragraph(
            labels.get('not_specified', 'Service description not available'),
            styles['BodySmall']
        ))
    
    story.append(Spacer(1, 12))
    return story


def build_processing_notes_section(service, labels, page_width, styles):
    """Build Section 4: Processing Notes."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section4'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get processing steps from service
    processing_steps = getattr(service, 'processing_steps', '') or ''
    analysis_workflow = getattr(service, 'analysis_workflow', '') or ''
    
    notes = processing_steps or analysis_workflow
    
    if notes:
        story.append(Paragraph(notes, styles['BodySerif']))
    else:
        story.append(Paragraph(
            labels.get('not_specified', 'Processing notes not available'),
            styles['BodySmall']
        ))
    
    story.append(Spacer(1, 12))
    return story


def build_pricing_section(request_obj, service, labels, page_width, styles):
    """
    Build Section 5: Pricing — structured devis with sample table,
    itemised breakdown, supplements, and highlighted total.
    """
    from decimal import Decimal

    story = []

    # ── Section title ────────────────────────────────────────────────────────
    story.append(Paragraph(labels['platform_note_section5'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 8))

    # ── Server-side recalculation ────────────────────────────────────────────
    cost_result     = {}
    modifier_result = {}
    server_price    = None
    pricing_error   = None

    try:
        from core.pricing import validate_and_calculate_price
        price_validation = validate_and_calculate_price(
            service=service,
            channel=getattr(request_obj, 'channel', 'IBTIKAR') or 'IBTIKAR',
            sample_table=request_obj.sample_table or [],
            service_params=request_obj.service_params or {},
            urgency=getattr(request_obj, 'urgency', 'Normal') or 'Normal',
        )
        server_price    = price_validation.get('server_price')
        cost_result     = price_validation.get('cost_result') or {}
        modifier_result = price_validation.get('modifier_result') or {}
    except Exception as exc:
        pricing_error = str(exc)
        logger.warning(f"Platform Note pricing error for {request_obj.display_id}: {exc}")

    # ── Effective totals ─────────────────────────────────────────────────────
    # admin_validated_price wins over recalculated price (admin may have adjusted).
    admin_price   = getattr(request_obj, 'admin_validated_price', None)
    final_cost    = getattr(request_obj, 'final_cost', None)
    budget_amount = getattr(request_obj, 'budget_amount', None)
    discount_pct  = getattr(request_obj, 'discount_percentage', 0) or 0
    discount_amt  = getattr(request_obj, 'discount_amount', 0) or 0

    # Display price = admin override > server recalc > final_cost stored
    display_total = admin_price if admin_price is not None else (
        server_price if server_price is not None else final_cost
    )

    # ── SUB-SECTION A: Tableau des échantillons ──────────────────────────────
    sample_table_data = request_obj.sample_table if request_obj.sample_table else []
    if not isinstance(sample_table_data, list):
        sample_table_data = []

    if sample_table_data:
        story.append(Paragraph(
            labels.get('sample_table_title', 'Tableau des échantillons'),
            styles['Label']
        ))
        story.append(Spacer(1, 4))

        # Detect columns present in samples
        has_origin = any(s.get('origin') or s.get('param_origin') for s in sample_table_data if isinstance(s, dict))
        has_type   = any(s.get('type')   or s.get('param_type')   for s in sample_table_data if isinstance(s, dict))
        has_notes  = any(s.get('notes')  or s.get('remarques')    for s in sample_table_data if isinstance(s, dict))

        # Header row
        headers = [Paragraph('<b>N°</b>', styles['TableHeader'])]
        if has_type:
            headers.append(Paragraph(f'<b>{labels.get("sample_type", "Type")}</b>', styles['TableHeader']))
        if has_origin:
            headers.append(Paragraph(f'<b>{labels.get("sample_origin", "Origine")}</b>', styles['TableHeader']))
        if has_notes:
            headers.append(Paragraph(f'<b>{labels.get("sample_notes", "Remarques")}</b>', styles['TableHeader']))

        sample_rows = [headers]
        for idx, sample in enumerate(sample_table_data, 1):
            if not isinstance(sample, dict):
                continue
            row = [Paragraph(str(idx), styles['TableCell'])]
            if has_type:
                row.append(Paragraph(
                    str(sample.get('type') or sample.get('param_type') or '—'),
                    styles['TableCell']
                ))
            if has_origin:
                row.append(Paragraph(
                    str(sample.get('origin') or sample.get('param_origin') or '—'),
                    styles['TableCell']
                ))
            if has_notes:
                row.append(Paragraph(
                    str(sample.get('notes') or sample.get('remarques') or '—'),
                    styles['TableCell']
                ))
            sample_rows.append(row)

        n_cols = len(headers)
        num_col_w   = 0.8 * cm
        remaining   = page_width - num_col_w
        other_col_w = remaining / max(n_cols - 1, 1)
        col_widths  = [num_col_w] + [other_col_w] * (n_cols - 1)

        tbl = Table(sample_rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0),  COLOR_HEADER_BG),
            ('TEXTCOLOR',    (0, 0), (-1, 0),  white),
            ('FONTNAME',     (0, 0), (-1, 0),  FONT_HELVETICA_BOLD),
            ('FONTSIZE',     (0, 0), (-1, -1), 8),
            ('ALIGN',        (0, 0), (0, -1),  'CENTER'),
            ('ALIGN',        (1, 0), (-1, -1), 'LEFT'),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID',         (0, 0), (-1, -1), 0.4, COLOR_BORDER),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F9F9F9')]),
            ('TOPPADDING',   (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 14))

    # ── SUB-SECTION B: Détail du devis (lignes tarifaires) ───────────────────
    breakdown_items = cost_result.get('breakdown') or []

    # Fallback: quote_detail for older requests
    if not breakdown_items:
        quote_detail = getattr(request_obj, 'quote_detail', {}) or {}
        if isinstance(quote_detail, dict):
            for item_label, item_amount in quote_detail.items():
                if isinstance(item_amount, (int, float)):
                    breakdown_items.append({
                        'name': item_label,
                        'type': 'ITEM',
                        'amount': item_amount,
                        'quantity': 1,
                        'subtotal': item_amount,
                    })

    if breakdown_items:
        story.append(Paragraph(
            labels.get('cost_breakdown', 'Détail du devis'),
            styles['Label']
        ))
        story.append(Spacer(1, 4))

        # Header
        tbl_header = [
            Paragraph(f'<b>{labels.get("designation", "Désignation")}</b>', styles['TableHeader']),
            Paragraph(f'<b>{labels.get("quantity_short", "Qté")}</b>',     styles['TableHeader']),
            Paragraph(f'<b>{labels.get("unit_price", "P.U. (DZD)")}</b>',  styles['TableHeader']),
            Paragraph(f'<b>{labels.get("subtotal", "Sous-total")}</b>',    styles['TableHeader']),
        ]
        devis_rows = [tbl_header]

        supplement_detail_lines = []  # collect per-sample supplement details

        for entry in breakdown_items:
            name    = str(entry.get('name') or entry.get('type') or 'Désignation')
            amount  = entry.get('amount', 0)
            qty     = entry.get('quantity', 1)
            subtotal = entry.get('subtotal', 0)

            # Format quantity: if 1, show '—' for cleanliness
            qty_text = str(qty) if qty and qty != 1 else '1'

            devis_rows.append([
                Paragraph(name, styles['TableCell']),
                Paragraph(qty_text, styles['TableCellRight']),
                Paragraph(format_currency(amount), styles['TableCellRight']),
                Paragraph(format_currency(subtotal), styles['TableCellRight']),
            ])

            # Collect supplement details for footnote
            for det in (entry.get('details') or []):
                det_label  = det.get('label') or det.get('field') or 'Supplément'
                det_amount = det.get('amount')
                if isinstance(det_amount, (int, float)):
                    supplement_detail_lines.append(
                        f"• {det_label} : {format_currency(det_amount)} / échantillon"
                    )

        col_w = [page_width * 0.46, page_width * 0.12, page_width * 0.20, page_width * 0.22]
        d_tbl = Table(devis_rows, colWidths=col_w, repeatRows=1)
        d_tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0),  COLOR_HEADER_BG),
            ('TEXTCOLOR',     (0, 0), (-1, 0),  white),
            ('FONTNAME',      (0, 0), (-1, 0),  FONT_HELVETICA_BOLD),
            ('FONTSIZE',      (0, 0), (-1, -1), 9),
            ('ALIGN',         (1, 1), (-1, -1), 'RIGHT'),
            ('ALIGN',         (0, 0), (0, -1),  'LEFT'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID',          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F9F9F9')]),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(d_tbl)

        if supplement_detail_lines:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                labels.get('supplement_reason', 'Détail des suppléments par échantillon :'),
                styles['BodySmall']
            ))
            for line in supplement_detail_lines:
                story.append(Paragraph(line, styles['BodySmall']))

        story.append(Spacer(1, 10))

    # ── SUB-SECTION C: Modificateurs (mode analyse, urgence, etc.) ───────────
    modifiers_applied = (modifier_result.get('modifiers_applied') or []) if isinstance(modifier_result, dict) else []
    if modifiers_applied:
        story.append(Paragraph(
            labels.get('modifiers_applied', 'Suppléments / modificateurs appliqués'),
            styles['Label']
        ))
        story.append(Spacer(1, 4))

        mod_rows = []
        for mod in modifiers_applied:
            mod_label = mod.get('label') or mod.get('field') or 'Modificateur'
            mod_type  = mod.get('type') or mod.get('operation') or ''
            mod_val   = mod.get('value') or ''
            mod_option = mod.get('option') or ''

            if mod_type in ('option_multiply', 'multiply'):
                detail = f"× {mod_val}"
                if mod_option:
                    detail = f"{mod_option} → × {mod_val}"
            elif mod_type == 'add':
                detail = f"+ {format_currency(mod_val)}"
            elif mod_type == 'set':
                detail = f"= {format_currency(mod_val)}"
            else:
                detail = str(mod_val)

            mod_rows.append([
                Paragraph(str(mod_label), styles['TableCell']),
                Paragraph(detail, styles['TableCellRight']),
            ])

        if mod_rows:
            m_tbl = Table(mod_rows, colWidths=[page_width * 0.65, page_width * 0.35])
            m_tbl.setStyle(TableStyle([
                ('FONTSIZE',      (0, 0), (-1, -1), 9),
                ('ALIGN',         (1, 0), (1, -1),  'RIGHT'),
                ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID',          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
                ('ROWBACKGROUNDS',(0, 0), (-1, -1), [HexColor('#FFF8E7'), white]),
                ('TOPPADDING',    (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(m_tbl)
            story.append(Spacer(1, 10))

    # ── SUB-SECTION D: Récapitulatif financier ───────────────────────────────
    story.append(Paragraph(
        labels.get('financial_summary', 'Récapitulatif financier'),
        styles['Label']
    ))
    story.append(Spacer(1, 4))

    recap_rows = []

    sample_count = len([s for s in sample_table_data if s]) if sample_table_data else 0

    base_per_sample   = cost_result.get('base_per_sample', 0)
    per_sample_suppl  = cost_result.get('per_sample_supplements', 0)
    per_sample_total  = cost_result.get('per_sample_total', 0)
    calc_formula      = cost_result.get('calculation_formula', '')

    if base_per_sample:
        recap_rows.append([
            Paragraph(labels.get('base_price_per_sample', 'Prix de base / échantillon'), styles['TableCell']),
            Paragraph(format_currency(base_per_sample), styles['TableCellRight']),
        ])
    if per_sample_suppl and per_sample_suppl > 0:
        recap_rows.append([
            Paragraph(labels.get('per_sample_supplements', 'Suppléments / échantillon'), styles['TableCell']),
            Paragraph(format_currency(per_sample_suppl), styles['TableCellRight']),
        ])
    if sample_count:
        recap_rows.append([
            Paragraph(labels.get('number_of_samples', "Nombre d'échantillons"), styles['TableCell']),
            Paragraph(str(sample_count), styles['TableCellRight']),
        ])

    # urgency
    urgency_val = getattr(request_obj, 'urgency', '') or ''
    if urgency_val and urgency_val != 'Normal':
        recap_rows.append([
            Paragraph(labels.get('urgency_label', 'Urgence'), styles['TableCell']),
            Paragraph(str(urgency_val), styles['TableCellRight']),
        ])

    # budget declared
    if budget_amount:
        recap_rows.append([
            Paragraph(labels.get('budget_amount', 'Budget déclaré (demandeur)'), styles['TableCell']),
            Paragraph(format_currency(budget_amount), styles['TableCellRight']),
        ])

    # discount
    if discount_pct or discount_amt:
        discount_text = f"−{discount_pct}%" if discount_pct else f"−{format_currency(discount_amt)}"
        recap_rows.append([
            Paragraph(labels['discount_applied'], styles['TableCell']),
            Paragraph(discount_text, styles['TableCellRight']),
        ])

    if recap_rows:
        r_tbl = Table(recap_rows, colWidths=[page_width * 0.65, page_width * 0.35])
        r_tbl.setStyle(TableStyle([
            ('FONTSIZE',      (0, 0), (-1, -1), 9),
            ('ALIGN',         (1, 0), (1, -1),  'RIGHT'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID',          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [white, HexColor('#F9F9F9')]),
            ('TOPPADDING',    (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(r_tbl)
        story.append(Spacer(1, 6))

    # ── TOTAL highlighted row ────────────────────────────────────────────────
    if display_total is not None:
        total_label_text = labels.get('final_cost', 'MONTANT TOTAL')
        total_value_text = format_currency(display_total)

        total_row = Table(
            [[
                Paragraph(f'<b>{total_label_text}</b>', styles['TotalLabel']),
                Paragraph(f'<b>{total_value_text}</b>', styles['TotalValue']),
            ]],
            colWidths=[page_width * 0.65, page_width * 0.35]
        )
        total_row.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, -1), COLOR_PRIMARY),
            ('TEXTCOLOR',     (0, 0), (-1, -1), white),
            ('ALIGN',         (0, 0), (0, 0),   'LEFT'),
            ('ALIGN',         (1, 0), (1, 0),   'RIGHT'),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',    (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('FONTNAME',      (0, 0), (-1, -1), FONT_HELVETICA_BOLD),
            ('FONTSIZE',      (0, 0), (-1, -1), 11),
        ]))
        story.append(total_row)

        # Formula note below total (informational)
        if calc_formula:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                f"<i>{labels.get('formula_label', 'Formule')} : {calc_formula}</i>",
                styles['BodySmall']
            ))
    else:
        # No price yet
        story.append(Paragraph(
            f"<font color='#999999'>{labels.get('pending_validation', 'En attente de validation financière')}</font>",
            styles['Value']
        ))

    if pricing_error:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"<font color='#CC0000'>Erreur calcul : {pricing_error}</font>",
            styles['BodySmall']
        ))

    story.append(Spacer(1, 14))
    return story


def build_deliverables_section(service, labels, page_width, styles):
    """Build Section 6: Deliverables."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section6'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get deliverables from service
    deliverables = getattr(service, 'deliverables', '') or ''
    
    if deliverables:
        story.append(Paragraph(deliverables, styles['BodySerif']))
    else:
        # Default deliverables based on service type
        story.append(Paragraph(
            "• Rapport d'analyse au format PDF<br/>• Données brutes (si applicable)<br/>• Fichier de résultats annoté",
            styles['BodySerif']
        ))
    
    story.append(Spacer(1, 12))
    return story


def build_lab_contact_section(labels, page_width, styles):
    """Build Lab Contact section using PlatformContent model."""
    from core.models import PlatformContent
    
    story = []
    
    # Get lab contact info from PlatformContent
    contact_keys = ['lab_phone', 'lab_email', 'lab_address', 'lab_name']
    contact_data = {}
    
    try:
        platform_contents = PlatformContent.objects.filter(key__in=contact_keys)
        for pc in platform_contents:
            contact_data[pc.key] = pc.value
    except Exception as e:
        logger.debug(f"Could not fetch PlatformContent for lab contact: {e}")
    
    # Only add section if we have contact data
    if not contact_data:
        return story
    
    # Section title
    story.append(Paragraph(labels.get('lab_contact_section', 'Contact Laboratory'), styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Build contact info table
    contact_rows = []
    
    if contact_data.get('lab_name'):
        contact_rows.append([
            Paragraph(labels.get('lab_name', 'Laboratory'), styles['Label']),
            Paragraph(str(contact_data['lab_name']), styles['Value'])
        ])
    
    if contact_data.get('lab_address'):
        contact_rows.append([
            Paragraph(labels.get('lab_address', 'Address'), styles['Label']),
            Paragraph(str(contact_data['lab_address']), styles['Value'])
        ])
    
    if contact_data.get('lab_phone'):
        contact_rows.append([
            Paragraph(labels.get('lab_phone', 'Phone'), styles['Label']),
            Paragraph(str(contact_data['lab_phone']), styles['Value'])
        ])
    
    if contact_data.get('lab_email'):
        contact_rows.append([
            Paragraph(labels.get('lab_email', 'Email'), styles['Label']),
            Paragraph(str(contact_data['lab_email']), styles['Value'])
        ])
    
    if contact_rows:
        contact_table = Table(contact_rows, colWidths=[page_width * 0.35, page_width * 0.65])
        style_label_value_table(contact_table)
        story.append(contact_table)
    
    story.append(Spacer(1, 12))
    return story


def build_turnaround_section(service, labels, page_width, styles):
    """Build Section 7: Estimated Turnaround."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section7'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get turnaround time aligned with channel-specific service settings
    turnaround_days = getattr(service, 'turnaround_ibtikar', None) or getattr(service, 'turnaround_days', None)
    turnaround_unit = getattr(service, 'turnaround_unit', 'business_days')

    if turnaround_days:
        if turnaround_unit == 'calendar_days':
            unit_label = labels.get('calendar_days', 'jours calendaires')
        elif turnaround_unit == 'weeks':
            unit_label = labels.get('weeks', 'semaines')
        else:
            unit_label = labels.get('business_days', 'jours ouvrables')
        turnaround_text = f"{turnaround_days} {unit_label}"
        story.append(Paragraph(turnaround_text, styles['BodySerif']))
    else:
        story.append(Paragraph(
            labels.get('not_specified', 'Turnaround time not specified'),
            styles['BodySmall']
        ))
    
    story.append(Spacer(1, 12))
    return story


def build_compliance_statement(labels, page_width, styles):
    """Build the compliance statement section."""
    story = []
    
    # Section title
    story.append(Paragraph(labels.get('compliance_statement_title', 'Compliance Statement'), styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        labels.get('compliance_statement_text', ''),
        styles['BodySerif']
    ))
    story.append(Spacer(1, 16))
    
    return story


def build_signature_block(labels, page_width, styles):
    """Build the signature block."""
    story = []
    
    # Issuer signature
    story.append(Paragraph(labels.get('operator', 'Émetteur'), styles['Label']))
    story.append(Spacer(1, 4))
    story.append(SignatureLine(width=page_width * 0.6, date_label=f"{labels.get('signature_date', 'Date')}:"))
    story.append(Spacer(1, 20))
    
    return story


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def check_platform_note_status(request_obj) -> dict:
    """
    Check the status of Platform Note for a request.
    
    Returns:
        Dictionary with status information
    """
    result = {
        'has_generated_note': False,
        'generated_note_url': None,
        'can_generate': False,
        'error': None,
    }
    
    if not request_obj.service:
        result['error'] = "No service linked to request"
        return result
    
    result['can_generate'] = True
    
    if request_obj.generated_platform_note:
        result['has_generated_note'] = True
        result['generated_note_url'] = request_obj.generated_platform_note.url
    
    return result


def delete_platform_note(request_obj) -> bool:
    """
    Delete the generated Platform Note for a request.
    
    Returns:
        True if deleted successfully
    """
    try:
        if request_obj.generated_platform_note:
            request_obj.generated_platform_note.delete(save=True)
            logger.info(f"Deleted Platform Note for {request_obj.display_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to delete Platform Note for {request_obj.display_id}: {e}")
    
    return False
