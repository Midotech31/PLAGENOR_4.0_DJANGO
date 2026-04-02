# documents/pdf_generator_reception.py — PLAGENOR 4.0 Sample Reception Form PDF Generator
# Generates the official sample reception form as PDF

from io import BytesIO
from datetime import datetime
import logging

from django.conf import settings
from django.core.files import File
from django.db import models
from django.utils.translation import gettext_lazy as _

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from .pdf_styles import (
    MARGIN, PAGE_WIDTH, PAGE_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_BORDER, COLOR_HEADER_BG,
    COLOR_TEXT, COLOR_GRAY, COLOR_LIGHT_GRAY,
    FONT_HELVETICA, FONT_HELVETICA_BOLD, FONT_TIMES, FONT_TIMES_BOLD,
    get_styles, get_base_table_style, style_label_value_table,
    get_essbo_logo, get_plagenor_logo,
    format_date, format_datetime, format_currency,
    HorizontalLine, SectionDivider,
    make_page_template
)
from .pdf_labels import get_labels, get_label

logger = logging.getLogger('plagenor.documents')


# =============================================================================
# CONSTANTS
# =============================================================================

MIN_RECEPTION_ROWS = 15


# =============================================================================
# HELPER FLOWABLES
# =============================================================================

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

def generate_reception_form_pdf(request_obj, lang=None, force_regenerate=False):
    """
    Generate a Sample Reception Form PDF for a request.
    
    This form is generated when appointment is confirmed or samples are
    physically received at the platform.
    
    Args:
        request_obj: Request model instance
        lang: Language code ('fr' or 'en'), defaults to request.language or 'fr'
        force_regenerate: If True, regenerate even if form already exists
        
    Returns:
        Tuple of (file_path, error_message) - file_path is None on error
    """
    # Determine language
    lang = lang or getattr(request_obj, 'language', None) or 'fr'
    labels = get_labels(lang)
    
    # Check if form already exists (unless force_regenerate)
    if not force_regenerate and request_obj.generated_reception_form:
        existing_path = request_obj.generated_reception_form.path
        if existing_path and hasattr(existing_path, 'exists') and existing_path.exists():
            logger.info(f"Reception form already exists for {request_obj.display_id}")
            return str(existing_path), None
    
    # Get service
    service = request_obj.service
    
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
            title=labels['sample_reception_title'],
            author='PLAGENOR 4.0',
            subject=f"Sample Reception Form - {request_obj.display_id}",
        )
        
        # Build content
        story = []
        styles = get_styles()
        page_width = PAGE_WIDTH - 2 * MARGIN
        
        # -------------------------------------------------------------------------
        # INSTITUTIONAL HEADER
        # -------------------------------------------------------------------------
        story.extend(build_institutional_header(labels, page_width, styles))

        # -------------------------------------------------------------------------
        # QR CODE (Tracking)
        # -------------------------------------------------------------------------
        try:
            from core.qrcode_utils import generate_request_tracking_qr
            from django.contrib.sites.models import Site
            from reportlab.lib.utils import ImageReader
            import base64
            current_site = Site.objects.get_current()
            base_url = f"https://{current_site.domain}" if current_site else None
            qr_data_url = generate_request_tracking_qr(request_obj, base_url=base_url)
            if qr_data_url:
                qr_data = qr_data_url.split(',')[1]
                qr_bytes = base64.b64decode(qr_data)
                qr_buffer = BytesIO(qr_bytes)
                qr_img = ImageReader(qr_buffer)
                # Add QR code aligned right
                qr_table = Table([[Paragraph(f"<small>{request_obj.display_id}</small>", styles['SmallCenter']), Image(qr_img, width=2*cm, height=2*cm)]],
                                 colWidths=[page_width - 3*cm, 2*cm])
                qr_table.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ]))
                story.append(qr_table)
                story.append(Spacer(1, 4))
        except Exception as e:
            logger.debug(f"Could not generate QR code for Reception form: {e}")

        # -------------------------------------------------------------------------
        # TITLE
        # -------------------------------------------------------------------------
        story.append(Spacer(1, 12))
        story.append(Paragraph(labels['sample_reception_title'], styles['DocumentTitle']))
        story.append(Spacer(1, 8))
        story.append(HorizontalLine(page_width, thickness=1, color=COLOR_PRIMARY))
        
        # -------------------------------------------------------------------------
        # SECTION 1: SUBMITTER INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_submitter_section(request_obj, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 2: PROJECT INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_project_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 3: SAMPLE INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_sample_section(request_obj, labels, page_width, styles, lang))
        
        # -------------------------------------------------------------------------
        # SECTION 4: TRANSPORT AND TRACKING
        # -------------------------------------------------------------------------
        story.extend(build_transport_section(request_obj, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 5: CONSENT AND COMPLIANCE
        # -------------------------------------------------------------------------
        story.extend(build_consent_section(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 6: DECLARATION
        # -------------------------------------------------------------------------
        story.extend(build_declaration_section(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 7: ETHICAL DECLARATION
        # -------------------------------------------------------------------------
        story.extend(build_ethical_section(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 8: SIGNATURE BLOCK
        # -------------------------------------------------------------------------
        story.extend(build_signature_section(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # BUILD PDF
        # -------------------------------------------------------------------------
        doc.build(story, onFirstPage=lambda c, d: make_page_template(c, d, with_page_numbers=True),
                  onLaterPages=lambda c, d: make_page_template(c, d, with_page_numbers=True))
        
        # Save to model
        buffer.seek(0)
        filename = f"PLAGENOR_SampleReception_{request_obj.display_id}.pdf"
        
        from django.core.files.base import ContentFile
        pdf_content = ContentFile(buffer.read())
        
        request_obj.generated_reception_form.save(filename, pdf_content, save=True)
        
        logger.info(f"Generated Reception Form PDF for {request_obj.display_id}: {filename}")
        return str(request_obj.generated_reception_form.path), None
        
    except Exception as e:
        logger.error(
            f"Failed to generate Reception Form PDF for {request_obj.display_id}: {str(e)}",
            exc_info=True
        )
        return None, f"ERROR: {str(e)}"


# =============================================================================
# SECTION BUILDERS
# =============================================================================

def build_institutional_header(labels, page_width, styles):
    """Build the institutional header with Algerian Republic headers."""
    story = []
    
    # Algerian Republic header
    story.append(Paragraph(labels['republic_algeria'], styles['Center']))
    story.append(Paragraph(labels['ministry_higher_education'], styles['Center']))
    story.append(Spacer(1, 4))
    story.append(Paragraph(labels['essbo_full'], styles['Center']))
    story.append(Paragraph(labels['platform_tech'], styles['Center']))
    story.append(Spacer(1, 6))
    
    # Logo row
    essbo_logo = get_essbo_logo(width=2.5*cm)
    plagenor_logo = get_plagenor_logo(width=2.5*cm)
    
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
    
    return story


def build_submitter_section(request_obj, labels, page_width, styles):
    """Build Section 1: Submitter Information."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section1'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get submitter info
    requester = request_obj.requester
    if requester:
        full_name = requester.get_full_name() or requester.username or labels.get('not_specified', 'N/A')
        email = getattr(requester, 'email', '') or ''
        phone = getattr(requester, 'phone', '') or ''
        institution = getattr(requester, 'organization', '') or ''
        laboratory = getattr(requester, 'laboratory', '') or ''
        department = getattr(requester, 'department', '') or ''
        position = getattr(requester, 'position', '') or ''
        if position:
            position = get_label(f'position_{position}', 'fr', position)
    else:
        full_name = request_obj.guest_name or labels.get('not_specified', 'N/A')
        email = request_obj.guest_email or ''
        phone = request_obj.guest_phone or ''
        institution = ''
        laboratory = ''
        department = ''
        position = ''
    
    data = [
        [Paragraph(labels['applicant_full_name'], styles['Label']), 
         Paragraph(str(full_name), styles['Value'])],
        [Paragraph(labels['institution'], styles['Label']), 
         Paragraph(str(institution), styles['Value'])],
        [Paragraph(labels['laboratory'], styles['Label']), 
         Paragraph(str(laboratory), styles['Value'])],
        [Paragraph(labels.get('department', 'Department'), styles['Label']), 
         Paragraph(str(department) if department else labels.get('not_applicable', 'N/A'), styles['Value'])],
        [Paragraph(labels['position'], styles['Label']), 
         Paragraph(str(position), styles['Value'])],
        [Paragraph(labels['email'], styles['Label']), 
         Paragraph(str(email), styles['Value'])],
        [Paragraph(labels['phone'], styles['Label']), 
         Paragraph(str(phone), styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    return story


def build_project_section(request_obj, service, labels, page_width, styles):
    """Build Section 2: Project Information."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section2'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get PI info
    pi_name = getattr(request_obj, 'pi_name', '') or ''
    pi_email = getattr(request_obj, 'pi_email', '') or ''
    pi_phone = getattr(request_obj, 'pi_phone', '') or ''
    project_desc = getattr(request_obj, 'description', '') or ''
    
    data = [
        [Paragraph(labels['project_title'], styles['Label']), 
         Paragraph(str(request_obj.title or ''), styles['Value'])],
        [Paragraph(labels['pi_name'], styles['Label']), 
         Paragraph(str(pi_name), styles['Value'])],
        [Paragraph(labels.get('pi_email', 'PI Email'), styles['Label']), 
         Paragraph(str(pi_email), styles['Value'])],
        [Paragraph(labels.get('pi_phone', 'PI Phone'), styles['Label']), 
         Paragraph(str(pi_phone), styles['Value'])],
    ]
    
    if project_desc:
        data.append([
            Paragraph(labels.get('project_description', 'Description'), styles['Label']),
            Paragraph(str(project_desc), styles['Value'])
        ])
    
    if service:
        data.append([
            Paragraph(labels.get('service_requested', 'Service'), styles['Label']),
            Paragraph(str(service.name), styles['Value'])
        ])
    
    # Appointment date (set when requester confirms appointment)
    appointment_date = getattr(request_obj, 'appointment_date', None)
    if appointment_date:
        data.append([
            Paragraph(labels.get('appointment_date', 'Appointment Date'), styles['Label']),
            Paragraph(format_date(appointment_date), styles['Value'])
        ])
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    return story


def build_sample_section(request_obj, labels, page_width, styles, lang='fr'):
    """Build Section 3: Sample Information table with DB-driven columns filtered by channel."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section3'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get sample table columns from DB, filtered by channel (GENOCLAB or BOTH)
    # This ensures GENOCLAB reception form only shows relevant fields
    channel_filter = request_obj.channel if request_obj.channel in ['GENOCLAB', 'IBTIKAR'] else 'BOTH'
    db_columns = []
    if request_obj.service and hasattr(request_obj.service, 'form_fields'):
        from core.models import ServiceFormField
        db_columns = list(request_obj.service.form_fields.filter(
            field_category='sample_table'
        ).filter(
            models.Q(channel='BOTH') | models.Q(channel=channel_filter)
        ).order_by('order', 'sort_order', 'pk'))
    
    # Build dynamic columns list
    if db_columns:
        # Use DB-driven columns
        columns = [('id', labels['sample_id'])]
        for field in db_columns:
            col_label = field.label_fr if lang == 'fr' else (field.label_en or field.label_fr)
            columns.append((field.name, col_label))
    else:
        # Fallback to default columns
        columns = [
            ('id', labels['sample_id']),
            ('code', labels['sample_code']),
            ('origin', labels['sample_origin']),
            ('date', labels['sampling_date']),
            ('storage', labels['storage_conditions']),
            ('notes', labels.get('additional_notes', 'Notes')),
        ]
    
    # Build header
    header_row = [Paragraph(col[1], styles['TableHeader']) for col in columns]
    
    # Get samples
    samples = request_obj.sample_table if request_obj.sample_table else []
    if not isinstance(samples, list):
        samples = []
    
    # Build data rows
    data_rows = [header_row]
    
    for i, sample in enumerate(samples, 1):
        row = [Paragraph(str(i), styles['TableCellCenter'])]
        if isinstance(sample, dict):
            for col_key, _ in columns[1:]:  # Skip 'id'
                value = sample.get(col_key, '') or sample.get(f'param_{col_key}', '') or ''
                row.append(Paragraph(str(value), styles['TableCell']))
        else:
            for _ in columns[1:]:
                row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)
    
    # Pad to minimum rows
    while len(data_rows) < MIN_RECEPTION_ROWS + 1:
        row = [Paragraph(str(len(data_rows)), styles['TableCellCenter'])]
        for _ in columns[1:]:
            row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)
    
    # Create table
    num_cols = len(columns)
    col_width = page_width / num_cols
    
    table = Table(data_rows, colWidths=[col_width] * num_cols)
    table.setStyle(get_base_table_style(header_count=1))
    story.append(table)
    
    # Minimum rows note
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"{labels.get('minimum_rows_note', 'Minimum')} {MIN_RECEPTION_ROWS} rows" if labels.get('platform_note_title', '') == 'PLATFORM NOTE' else labels.get('minimum_rows_note', f'Minimum {MIN_RECEPTION_ROWS} rows required'),
        styles['SmallItalic']
    ))
    
    return story


def build_transport_section(request_obj, labels, page_width, styles):
    """Build Section 4: Transport and Tracking."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section4'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    shipping_date = getattr(request_obj, 'shipping_date', None)
    tracking_number = getattr(request_obj, 'tracking_number', '') or ''
    
    data = [
        [Paragraph(labels['shipping_date'], styles['Label']), 
         Paragraph(format_date(shipping_date) if shipping_date else labels.get('not_specified', 'Not specified'), styles['Value'])],
        [Paragraph(labels['tracking_number'], styles['Label']), 
         Paragraph(str(tracking_number) if tracking_number else labels.get('not_specified', 'Not specified'), styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    return story


def build_consent_section(labels, page_width, styles):
    """Build Section 5: Consent and Compliance."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section5'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    data = [
        [Paragraph(labels['consent_form_attached'], styles['Label']), 
         Paragraph(f"☐ {labels.get('yes', 'Yes')}    ☐ {labels.get('no', 'No')}", styles['Value'])],
        [Paragraph(labels['ethical_compliance'], styles['Label']), 
         Paragraph(f"☐ {labels.get('yes', 'Yes')}    ☐ {labels.get('no', 'No')}", styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    
    return story


def build_declaration_section(labels, page_width, styles):
    """Build Section 6: Declaration."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section6'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        labels.get('declaration_text', ''),
        styles['BodySerif']
    ))
    
    return story


def build_ethical_section(labels, page_width, styles):
    """Build Section 7: Ethical Responsibility Declaration."""
    story = []
    
    story.append(Spacer(1, 12))
    story.append(Paragraph(labels['reception_section7'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        labels.get('full_ethical_declaration', ''),
        styles['BodySerif']
    ))
    
    return story


def build_signature_section(labels, page_width, styles):
    """Build Section 8: Signature Block."""
    story = []
    
    story.append(Spacer(1, 16))
    story.append(Paragraph(labels['reception_section8'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph(labels.get('submitter_signature', 'Submitter Signature'), styles['Label']))
    story.append(Spacer(1, 4))
    story.append(SignatureLine(width=page_width, date_label=f"{labels.get('signature_date', 'Date')}:"))
    
    return story


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def check_reception_form_status(request_obj) -> dict:
    """
    Check the status of Reception Form for a request.
    
    Returns:
        Dictionary with status information
    """
    result = {
        'has_generated_form': False,
        'generated_form_url': None,
        'can_generate': False,
        'error': None,
    }
    
    result['can_generate'] = True
    
    if request_obj.generated_reception_form:
        result['has_generated_form'] = True
        result['generated_form_url'] = request_obj.generated_reception_form.url
    
    return result


def delete_reception_form(request_obj) -> bool:
    """
    Delete the generated Reception Form for a request.
    
    Returns:
        True if deleted successfully
    """
    try:
        if request_obj.generated_reception_form:
            request_obj.generated_reception_form.delete(save=True)
            logger.info(f"Deleted Reception Form for {request_obj.display_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to delete Reception Form for {request_obj.display_id}: {e}")
    
    return False
