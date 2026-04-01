# documents/pdf_generator_platform_note.py — PLAGENOR 4.0 Platform Note PDF Generator
# Generates the official platform note document as PDF

from io import BytesIO
from datetime import datetime
import logging

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
        if existing_path and hasattr(existing_path, 'exists') and existing_path.exists():
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
        # SECTION 7: ESTIMATED TURNAROUND
        # -------------------------------------------------------------------------
        story.extend(build_turnaround_section(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 8: COMPLIANCE STATEMENT
        # -------------------------------------------------------------------------
        story.extend(build_compliance_statement(labels, page_width, styles))
        
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
    
    # Date (right-aligned)
    today = format_date(datetime.now())
    story.append(Paragraph(
        f"<b>{labels.get('date_format', 'Date:').format(date=today)}</b>",
        styles['Reference']
    ))
    story.append(Spacer(1, 4))
    
    # Logo row
    essbo_logo = get_essbo_logo(width=3*cm)
    plagenor_logo = get_plagenor_logo(width=3*cm)
    
    if essbo_logo and plagenor_logo:
        logo_table = Table(
            [[essbo_logo, plagenor_logo]],
            colWidths=[page_width / 2, page_width / 2]
        )
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(logo_table)
    elif essbo_logo:
        story.append(essbo_logo)
    elif plagenor_logo:
        story.append(plagenor_logo)
    
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
    """Build Section 5: Pricing."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section5'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get pricing information
    validated_cost = getattr(request_obj, 'admin_validated_price', None)
    discount_percentage = getattr(request_obj, 'discount_percentage', 0) or 0
    discount_amount = getattr(request_obj, 'discount_amount', 0) or 0
    final_cost = getattr(request_obj, 'final_cost', None)
    
    # Build pricing table
    data = []
    
    if validated_cost is not None:
        data.append([
            Paragraph(labels['calculated_cost'], styles['Label']),
            Paragraph(format_currency(validated_cost), styles['Value'])
        ])
        
        if discount_percentage or discount_amount:
            discount_text = f"{discount_percentage}%" if discount_percentage else format_currency(discount_amount)
            data.append([
                Paragraph(labels['discount_applied'], styles['Label']),
                Paragraph(discount_text, styles['Value'])
            ])
        
        if final_cost is not None:
            data.append([
                Paragraph(labels['final_cost'], styles['Label']),
                Paragraph(format_currency(final_cost), styles['Value'])
            ])
        else:
            data.append([
                Paragraph(labels['final_cost'], styles['Label']),
                Paragraph(format_currency(validated_cost), styles['Value'])
            ])
    else:
        # No validated cost yet
        pending_color = '#999999'
        pending_text = labels.get('pending_validation', 'En attente de validation financiere')
        data.append([
            Paragraph(labels['final_cost'], styles['Label']),
            Paragraph(
                f"<font color='{pending_color}'>{pending_text}</font>",
                styles['Value']
            )
        ])
    
    # Add IBTIKAR budget info
    budget_amount = getattr(request_obj, 'budget_amount', None)
    if budget_amount:
        data.append([
            Paragraph(labels.get('budget_amount', 'Budget déclaré'), styles['Label']),
            Paragraph(format_currency(budget_amount), styles['Value'])
        ])
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    # Cost breakdown if available
    quote_detail = getattr(request_obj, 'quote_detail', {}) or {}
    if quote_detail and isinstance(quote_detail, dict):
        story.append(Spacer(1, 8))
        story.append(Paragraph(labels.get('cost_breakdown', 'Détail du coût'), styles['Label']))
        story.append(Spacer(1, 4))
        
        breakdown_data = []
        for item_name, item_amount in quote_detail.items():
            if isinstance(item_amount, (int, float)):
                breakdown_data.append([
                    Paragraph(str(item_name), styles['TableCell']),
                    Paragraph(format_currency(item_amount), styles['TableCell'])
                ])
        
        if breakdown_data:
            breakdown_table = Table(breakdown_data, colWidths=[page_width * 0.6, page_width * 0.4])
            breakdown_table.setStyle(TableStyle([
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(breakdown_table)
    
    story.append(Spacer(1, 12))
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


def build_turnaround_section(service, labels, page_width, styles):
    """Build Section 7: Estimated Turnaround."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['platform_note_section7'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get turnaround time
    turnaround_days = getattr(service, 'turnaround_days', None)
    
    if turnaround_days:
        turnaround_text = f"{turnaround_days} {labels.get('business_days', 'jours ouvrables')}"
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
