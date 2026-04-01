# documents/pdf_generator_ibtikar.py — PLAGENOR 4.0 IBTIKAR Form PDF Generator
# Generates the official IBTIKAR analysis request form as PDF

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
    Image, PageBreak, HRFlowable
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from .pdf_styles import (
    MARGIN, PAGE_WIDTH, PAGE_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_BORDER, COLOR_HEADER_BG,
    COLOR_TEXT, COLOR_GRAY, COLOR_LIGHT_GRAY, COLOR_WARNING,
    FONT_HELVETICA, FONT_HELVETICA_BOLD, FONT_TIMES, FONT_TIMES_BOLD,
    get_styles, get_base_table_style, style_label_value_table,
    get_essbo_logo, get_plagenor_logo,
    format_date, format_datetime, format_currency,
    HorizontalLine, SectionDivider, WarningBox, SignatureBlock,
    make_page_template
)
from .pdf_labels import get_labels, get_label, format_reference

logger = logging.getLogger('plagenor.documents')


# =============================================================================
# CONSTANTS
# =============================================================================

MIN_SAMPLE_ROWS = 10


# =============================================================================
# HELPER FLOWABLES
# =============================================================================

class Checkbox(Flowable):
    """A checkbox flowable for checklist items."""
    
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
        # Label
        if self.label:
            self.canv.setFont(FONT_HELVETICA, 9)
            self.canv.setFillColor(COLOR_GRAY)
            self.canv.drawString(0, 35, self.label)
        
        # Signature line
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(0.5)
        line_start = 0
        self.canv.line(line_start, 20, line_start + self.signature_line_length, 20)
        
        # Date label and line
        date_start = line_start + self.signature_line_length + 8
        self.canv.setFont(FONT_HELVETICA, 8)
        self.canv.setFillColor(COLOR_GRAY)
        self.canv.drawString(date_start, 25, self.date_label)
        self.canv.line(date_start, 12, date_start + self.date_width, 12)


class ImportantBox(Flowable):
    """An important/warning box with styled border."""
    
    def __init__(self, width, title, content, title_color=COLOR_PRIMARY, 
                 bg_color=HexColor('#fff8e1'), border_color=HexColor('#ffc107')):
        Flowable.__init__(self)
        self.box_width = width
        self.title = title
        self.content = content
        self.title_color = title_color
        self.bg_color = bg_color
        self.border_color = border_color
        self.height = 60  # Will be calculated in wrap
    
    def wrap(self, availableWidth, availableHeight):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        
        self.width = min(self.box_width, availableWidth)
        
        # Calculate height based on content - handle newlines
        content_lines = self.content.split('\n')
        chars_per_line = int((self.width - 20) / 5.5)
        total_lines = 0
        for line in content_lines:
            if line.strip():
                total_lines += max(1, (len(line) // chars_per_line) + 1)
            else:
                total_lines += 1
        
        self.height = total_lines * 12 + 30
        return self.width, self.height
    
    def draw(self):
        # Background
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        
        # Border
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(2)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=0, stroke=1)
        
        # Title with icon
        self.canv.setFillColor(self.title_color)
        self.canv.setFont(FONT_HELVETICA_BOLD, 11)
        self.canv.drawString(10, self.height - 18, '⚠ ' + self.title)
        
        # Content - handle newlines properly
        self.canv.setFillColor(COLOR_TEXT)
        self.canv.setFont(FONT_HELVETICA, 9)
        
        chars_per_line = int((self.width - 20) / 5.5)
        y = self.height - 32
        max_lines = 20  # Max lines to prevent overflow
        
        for raw_line in self.content.split('\n'):
            if y < 10 or max_lines <= 0:
                break
            max_lines -= 1
            
            line = raw_line.strip()
            if not line:
                y -= 8
                continue
            
            # Word wrap long lines
            words = line.split()
            current_line = ''
            
            for word in words:
                test_line = current_line + ' ' + word if current_line else word
                if len(test_line) <= chars_per_line:
                    current_line = test_line
                else:
                    if current_line:
                        self.canv.drawString(10, y, current_line)
                        y -= 12
                        max_lines -= 1
                        if y < 10 or max_lines <= 0:
                            break
                    current_line = word
            
            if current_line and y >= 10 and max_lines > 0:
                self.canv.drawString(10, y, current_line)
                y -= 12


# =============================================================================
# MAIN GENERATOR FUNCTION
# =============================================================================

def generate_ibtikar_form_pdf(request_obj, lang=None, force_regenerate=False):
    """
    Generate an IBTIKAR form PDF for a request.
    
    This function creates a complete IBTIKAR analysis request form with:
    - Header with reference, logos, service info
    - Section 1: Requester information
    - Section 2: Analysis information
    - Section 3: Sample table (dynamic columns from ServiceFormField)
    - "Très important" block (from service.ibtikar_instructions)
    - Section 4: Additional information (dynamic fields)
    - Ethical declaration
    - Section 5: Validation (PLAGENOR use)
    - Signature blocks
    
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
    if not force_regenerate and request_obj.generated_ibtikar_form:
        existing_path = request_obj.generated_ibtikar_form.path
        if existing_path and hasattr(existing_path, 'exists') and existing_path.exists():
            logger.info(f"IBTIKAR form already exists for {request_obj.display_id}")
            return str(existing_path), None
    
    # Get service
    service = request_obj.service
    if not service:
        logger.warning(f"Request {request_obj.pk}: no service linked, skipping IBTIKAR PDF generation.")
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
            title=labels['ibtikar_form_title'],
            author='PLAGENOR 4.0',
            subject=f"IBTIKAR Form - {request_obj.display_id}",
        )
        
        # Build content
        story = []
        styles = get_styles()
        page_width = PAGE_WIDTH - 2 * MARGIN
        
        # -------------------------------------------------------------------------
        # HEADER
        # -------------------------------------------------------------------------
        story.extend(build_header(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 1: REQUESTER INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_requester_section(request_obj, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 2: ANALYSIS INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_analysis_section(request_obj, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 3: SAMPLE TABLE
        # -------------------------------------------------------------------------
        story.extend(build_sample_table(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # "TRÈS IMPORTANT" BLOCK
        # -------------------------------------------------------------------------
        story.extend(build_important_block(service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SECTION 4: ADDITIONAL INFORMATION
        # -------------------------------------------------------------------------
        story.extend(build_additional_info_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # ETHICAL DECLARATION
        # -------------------------------------------------------------------------
        story.extend(build_ethical_declaration(labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # SUBMITTER SIGNATURE
        # -------------------------------------------------------------------------
        story.extend(build_submitter_signature(labels, page_width, styles))
        
        # Page break before validation
        story.append(PageBreak())
        
        # -------------------------------------------------------------------------
        # SECTION 5: VALIDATION (PLAGENOR USE)
        # -------------------------------------------------------------------------
        story.extend(build_validation_section(request_obj, service, labels, page_width, styles))
        
        # -------------------------------------------------------------------------
        # BUILD PDF
        # -------------------------------------------------------------------------
        doc.build(story, onFirstPage=lambda c, d: make_page_template(c, d, with_page_numbers=True),
                  onLaterPages=lambda c, d: make_page_template(c, d, with_page_numbers=True))
        
        # Save to model
        buffer.seek(0)
        filename = f"PLAGENOR_IBTIKAR_{service.code}_{request_obj.display_id}.pdf"
        
        from django.core.files.base import ContentFile
        pdf_content = ContentFile(buffer.read())
        
        request_obj.generated_ibtikar_form.save(filename, pdf_content, save=True)
        
        logger.info(f"Generated IBTIKAR form PDF for {request_obj.display_id}: {filename}")
        return str(request_obj.generated_ibtikar_form.path), None
        
    except Exception as e:
        logger.error(
            f"Failed to generate IBTIKAR form PDF for {request_obj.display_id}: {str(e)}",
            exc_info=True
        )
        return None, f"ERROR: {str(e)}"


# =============================================================================
# SECTION BUILDERS
# =============================================================================

def build_header(request_obj, service, labels, page_width, styles):
    """Build the document header with reference, logos, and service info."""
    story = []
    
    # Get service display name based on code (official form titles)
    service_display_names = {
        'EGTP-Seq02': 'DEMANDE D\'IDENTIFICATION MICROBIENNE VIA LE SÉQUENÇAGE',
        'EGTP-SeqS': 'DEMANDE DE SÉQUENÇAGE D\'ADN (SANGER)',
        'EGTP-SeqI': 'DEMANDE DE SÉQUENÇAGE ILLUMINA',
        'EGTP-PCR': 'DEMANDE D\'AMPLIFICATION PAR PCR',
        'EGTP-IMT': 'DEMANDE D\'IDENTIFICATION PAR MALDI-TOF',
        'EGTP-PFGE': 'DEMANDE D\'ÉLECTROPHORÈSE EN CHAMP PULSÉ (PFGE)',
        'EGTP-CGH': 'DEMANDE D\'HYBRIDATION GÉNOMIQUE COMPARATIVE (CGH)',
        'EGTP-WGS': 'DEMANDE DE SÉQUENÇAGE GÉNOMIQUE COMPLET (WGS)',
        'EGTP-SeqM': 'DEMANDE DE SÉQUENÇAGE MÉTAGÉNOMIQUE',
    }
    
    # Full service title (use mapping or fallback to name)
    full_service_title = service_display_names.get(service.code, service.name.upper() if service.name else service.code)
    
    # Logo row with reference line centered
    essbo_logo = get_essbo_logo(width=2.5*cm)
    plagenor_logo = get_plagenor_logo(width=2.5*cm)
    
    # Reference line text
    reference = format_reference(service.code, lang=labels.get('platform_note_title', 'fr')[:2] or 'fr')
    reference_text = f"<b>{labels.get('request_reference', 'N° de la demande')}</b><br/>{reference}"
    reference_para = Paragraph(reference_text, styles['Reference'])
    
    # Create header table with logos on sides and reference centered
    logo_cell_left = essbo_logo if essbo_logo else Paragraph('', styles['Normal'])
    logo_cell_right = plagenor_logo if plagenor_logo else Paragraph('', styles['Normal'])
    
    header_table = Table(
        [[logo_cell_left, reference_para, logo_cell_right]],
        colWidths=[2.5*cm, page_width - 5*cm, 2.5*cm]
    )
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(header_table)
    
    story.append(Spacer(1, 8))
    
    # Title - service specific bold centered
    story.append(Paragraph(f"<b>{full_service_title}</b>", styles['CenterBold']))
    story.append(Spacer(1, 6))
    
    # Service code and version info
    form_version = getattr(service, 'form_version', 'V 01')
    version_info = Table(
        [
            [Paragraph(f"<b>{service.code}</b>", styles['Center']),
             Paragraph(f"{labels.get('version', 'Version')} {form_version}", styles['SmallItalic']),
             Paragraph(format_date(datetime.now()), styles['SmallItalic'])],
        ],
        colWidths=[page_width * 0.3, page_width * 0.4, page_width * 0.3]
    )
    version_info.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(version_info)
    
    story.append(Spacer(1, 6))
    story.append(HorizontalLine(page_width, thickness=1, color=COLOR_PRIMARY))
    story.append(Spacer(1, 10))
    
    return story


def build_requester_section(request_obj, labels, page_width, styles):
    """Build Section 1: Requester information table."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['section_requester'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get requester info
    requester = request_obj.requester
    if requester:
        full_name = requester.get_full_name() or requester.username or labels.get('not_specified', 'N/A')
        email = getattr(requester, 'email', '') or ''
        phone = getattr(requester, 'phone', '') or ''
        institution = getattr(requester, 'organization', '') or ''
        laboratory = getattr(requester, 'laboratory', '') or ''
        position = getattr(requester, 'position', '') or ''
        if position:
            position = get_label(f'position_{position}', labels.get('platform_note_title', 'fr')[:2] or 'fr', position)
    else:
        full_name = request_obj.guest_name or labels.get('not_specified', 'N/A')
        email = request_obj.guest_email or ''
        phone = request_obj.guest_phone or ''
        institution = ''
        laboratory = ''
        position = ''
    
    # Build label/value table
    data = [
        [Paragraph(labels['full_name'], styles['Label']), Paragraph(str(full_name), styles['Value'])],
        [Paragraph(labels['institution'], styles['Label']), Paragraph(str(institution), styles['Value'])],
        [Paragraph(labels['laboratory'], styles['Label']), Paragraph(str(laboratory), styles['Value'])],
        [Paragraph(labels['position'], styles['Label']), Paragraph(str(position), styles['Value'])],
        [Paragraph(labels['email'], styles['Label']), Paragraph(str(email), styles['Value'])],
        [Paragraph(labels['phone'], styles['Label']), Paragraph(str(phone), styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 12))
    
    return story


def build_analysis_section(request_obj, labels, page_width, styles):
    """Build Section 2: Analysis request information."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['section_analysis'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get analysis framework display
    analysis_framework = getattr(request_obj, 'analysis_framework', '') or ''
    if analysis_framework:
        framework_display = get_label(f'{analysis_framework}', labels.get('platform_note_title', 'fr')[:2] or 'fr', analysis_framework)
    else:
        framework_display = ''
    
    # Get PI name - check model field first, then fall back to service_params
    pi_name = getattr(request_obj, 'pi_name', '') or ''
    if not pi_name:
        pi_name = request_obj.service_params.get('supervisor', '')
    
    # Build table
    data = [
        [Paragraph(labels['analysis_framework'], styles['Label']), 
         Paragraph(str(framework_display), styles['Value'])],
        [Paragraph(labels['project_title'], styles['Label']), 
         Paragraph(str(request_obj.title or ''), styles['Value'])],
        [Paragraph(labels['pi_name'], styles['Label']), 
         Paragraph(str(pi_name), styles['Value'])],
    ]
    
    table = Table(data, colWidths=[page_width * 0.35, page_width * 0.65])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 12))
    
    return story


def build_sample_table(request_obj, service, labels, page_width, styles):
    """Build Section 3: Sample table with dynamic columns."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['section_samples'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get sample table columns from ServiceFormField
    sample_fields = service.form_fields.filter(
        field_category='sample_table'
    ).order_by('sort_order', 'pk') if hasattr(service, 'form_fields') else []
    
    # Build header row
    header_row = [Paragraph(labels['sample_id'], styles['TableHeader'])]
    column_keys = ['id']  # Row number key
    
    for field in sample_fields:
        field_label = field.label if hasattr(field, 'label') else field.get('label', 'Field')
        header_row.append(Paragraph(str(field_label), styles['TableHeader']))
        column_keys.append(str(field.pk) if hasattr(field, 'pk') else field.get('name', 'field'))
    
    # Also add standard columns if no custom fields
    if not sample_fields:
        standard_columns = [
            ('code', labels['sample_code']),
            ('type', labels['sample_type']),
            ('date', labels['sampling_date']),
            ('volume', labels['volume_quantity']),
            ('storage', labels['storage_conditions']),
            ('state', labels['sample_state']),
            ('notes', labels['special_notes']),
        ]
        header_row = [Paragraph(labels['sample_id'], styles['TableHeader'])]
        column_keys = ['id']
        for key, label in standard_columns:
            header_row.append(Paragraph(label, styles['TableHeader']))
            column_keys.append(key)
    
    # Build data rows
    samples = request_obj.sample_table if request_obj.sample_table else []
    if not isinstance(samples, list):
        samples = []
    
    data_rows = [header_row]
    
    # Add sample rows
    for i, sample in enumerate(samples, 1):
        row = [Paragraph(str(i), styles['TableCellCenter'])]
        if isinstance(sample, dict):
            for key in column_keys[1:]:  # Skip 'id'
                value = sample.get(key, '') or sample.get(f'param_{key}', '') or ''
                row.append(Paragraph(str(value), styles['TableCell']))
        else:
            # Empty/non-dict sample
            for _ in column_keys[1:]:
                row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)
    
    # Pad to minimum rows
    while len(data_rows) < MIN_SAMPLE_ROWS + 1:
        row = [Paragraph(str(len(data_rows)), styles['TableCellCenter'])]
        for _ in column_keys[1:]:
            row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)
    
    # Create table
    num_cols = len(column_keys)
    col_width = page_width / num_cols
    
    table = Table(data_rows, colWidths=[col_width] * num_cols)
    table.setStyle(get_base_table_style(header_count=1))
    story.append(table)
    
    # Minimum rows note
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        labels.get('minimum_rows_note', 'Minimum 10 rows required'),
        styles['SmallItalic']
    ))
    story.append(Spacer(1, 12))
    
    return story


def build_important_block(service, labels, page_width, styles):
    """Build the 'Très important' warning block."""
    story = []
    
    # Get instructions from service
    instructions_field = 'ibtikar_instructions'
    if labels.get('platform_note_title', 'fr')[:2] == 'en':
        instructions_field = 'ibtikar_instructions_en'
    
    instructions = getattr(service, instructions_field, '') or ''
    
    if instructions:
        story.append(ImportantBox(
            width=page_width,
            title=labels.get('very_important', 'Très important'),
            content=instructions
        ))
        story.append(Spacer(1, 12))
    elif hasattr(service, 'ibtikar_instructions') and service.ibtikar_instructions:
        story.append(ImportantBox(
            width=page_width,
            title=labels.get('very_important', 'Très important'),
            content=service.ibtikar_instructions
        ))
        story.append(Spacer(1, 12))
    
    return story


def build_additional_info_section(request_obj, service, labels, page_width, styles):
    """Build Section 4: Additional information from dynamic ServiceFormField."""
    story = []
    
    # Get additional info fields
    additional_fields = service.form_fields.filter(
        field_category='additional_info'
    ).order_by('sort_order', 'pk') if hasattr(service, 'form_fields') else []
    
    if not additional_fields:
        return story
    
    # Section title
    story.append(Paragraph(labels['section_additional'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Get additional data from request
    additional_data = getattr(request_obj, 'additional_data', {}) or {}
    
    # Build rows for each additional field
    data = []
    for field in additional_fields:
        field_id = str(field.pk) if hasattr(field, 'pk') else field.get('name', 'field')
        field_label = field.label if hasattr(field, 'label') else field.get('label', 'Field')
        
        # Get value from request
        value = additional_data.get(field_id, '') or ''
        
        # If field type is dropdown/checkbox, get display value
        field_type = getattr(field, 'field_type', 'text') if hasattr(field, 'field_type') else field.get('field_type', 'text')
        if field_type == 'dropdown' and hasattr(field, 'options'):
            options = field.options or []
            if isinstance(options, list) and value in options:
                value = value  # Use value as-is
            elif isinstance(options, list) and len(options) > 0:
                # Try to find matching option
                for opt in options:
                    if isinstance(opt, dict) and opt.get('value') == value:
                        value = opt.get('label', value)
                        break
        
        # Handle checkbox (list of values)
        if field_type == 'checkbox' and isinstance(value, list):
            value = ', '.join(str(v) for v in value)
        
        data.append([
            Paragraph(str(field_label), styles['Label']),
            Paragraph(str(value) if value else labels.get('to_be_filled', 'À remplir'), styles['Value'])
        ])
    
    if data:
        table = Table(data, colWidths=[page_width * 0.4, page_width * 0.6])
        style_label_value_table(table)
        story.append(table)
    
    story.append(Spacer(1, 12))
    return story


def build_ethical_declaration(labels, page_width, styles):
    """Build the ethical responsibility declaration."""
    story = []
    
    story.append(Paragraph(labels['section_ethical'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    story.append(Paragraph(
        labels.get('ethical_declaration_text', ''),
        styles['BodySerif']
    ))
    story.append(Spacer(1, 12))
    
    return story


def build_submitter_signature(labels, page_width, styles):
    """Build submitter signature block."""
    story = []
    
    story.append(Paragraph(labels['section_signature'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 6))
    
    # Signature block with 4cm blank space
    signature_data = [
        [Paragraph(labels['submitter_signature'], styles['Label']), ''],
        [Paragraph('_' * 60, styles['Normal']), ''],  # ~4cm signature space
        [Paragraph('', styles['Normal']), Paragraph(f"{labels.get('signature_date', 'Date')}: ___________________", styles['SmallItalic'])],
    ]
    
    signature_table = Table(signature_data, colWidths=[page_width * 0.6, page_width * 0.4])
    signature_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(signature_table)
    
    story.append(Spacer(1, 16))
    story.append(Spacer(1, 20))
    
    return story


def build_validation_section(request_obj, service, labels, page_width, styles):
    """Build Section 5: PLAGENOR validation section."""
    story = []
    
    # Section title
    story.append(Paragraph(labels['section_validation'], styles['SectionTitle']))
    story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
    story.append(Spacer(1, 8))
    
    # Reserved for PLAGENOR label in bordered box
    reserved_box = Table(
        [[Paragraph(
            f"<b>{labels.get('reserved_plagenor', 'Cadre réservé à PLAGENOR')}</b>",
            styles['ImportantNote']
        )]],
        colWidths=[page_width]
    )
    reserved_box.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f5f5f5')),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(reserved_box)
    story.append(Spacer(1, 10))
    
    # Operator field
    story.append(Paragraph(labels['operator'], styles['Label']))
    story.append(Spacer(1, 2))
    story.append(SignatureLine(width=page_width * 0.6, date_label=f"{labels.get('reception_date', 'Date')}:"))
    story.append(Spacer(1, 12))
    
    # Checklist
    story.append(Paragraph(labels.get('checklist_title', 'Checklist'), styles['Label']))
    story.append(Spacer(1, 4))
    
    # Get checklist items from service
    checklist_items = getattr(service, 'checklist_items', []) or []
    
    if checklist_items:
        for item in checklist_items:
            # Create checkbox row
            checkbox_row = Table(
                [[Checkbox(size=10), Paragraph(str(item), styles['ChecklistItem'])]],
                colWidths=[16, page_width - 16]
            )
            checkbox_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 1),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
            ]))
            story.append(checkbox_row)
    else:
        # Default empty checklist rows
        for i in range(5):
            checkbox_row = Table(
                [[Checkbox(size=10), Paragraph(f"_______________________________________", styles['ChecklistItem'])]],
                colWidths=[16, page_width - 16]
            )
            checkbox_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            story.append(checkbox_row)
    
    story.append(Spacer(1, 12))
    
    # Optional comment
    story.append(Paragraph(labels.get('optional_comment', 'Commentaire optionnel'), styles['Label']))
    story.append(Spacer(1, 4))
    for _ in range(3):
        story.append(HorizontalLine(page_width, thickness=0.5, color=COLOR_BORDER))
        story.append(Spacer(1, 12))
    
    story.append(Spacer(1, 12))
    
    # Reception date and signature
    story.append(Paragraph(f"{labels.get('reception_date', 'Date de la réception')}: ________________________", styles['Label']))
    story.append(Spacer(1, 8))
    story.append(Paragraph(labels.get('signature', 'Signature'), styles['Label']))
    story.append(Spacer(1, 4))
    story.append(SignatureLine(width=page_width, date_label=f"{labels.get('signature_date', 'Date')}:"))
    story.append(Spacer(1, 20))
    
    # Visa blocks (side by side) with proper signature spaces
    visa_col_width = (page_width - 20) / 2
    
    # Left visa block
    left_visa = Table([
        [Paragraph(labels.get('visa_chef', 'Visa du Chef du Service Commun'), styles['CenterBold'])],
        [Paragraph('', styles['Normal'])],  # Blank space
        [Paragraph('', styles['Normal'])],  # Blank space  
        [Paragraph('', styles['Normal'])],  # Blank space
        [Paragraph('_' * 40, styles['Normal'])],  # Signature line
        [Paragraph(f"{labels.get('signature_date', 'Date')}: _______________", styles['SmallItalic'])],
    ], colWidths=[visa_col_width])
    left_visa.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    # Right visa block
    right_visa = Table([
        [Paragraph(labels.get('visa_directeur', 'Visa du Directeur de l\'ESSBO'), styles['CenterBold'])],
        [Paragraph('', styles['Normal'])],  # Blank space
        [Paragraph('', styles['Normal'])],  # Blank space
        [Paragraph('', styles['Normal'])],  # Blank space
        [Paragraph('_' * 40, styles['Normal'])],  # Signature line
        [Paragraph(f"{labels.get('signature_date', 'Date')}: _______________", styles['SmallItalic'])],
    ], colWidths=[visa_col_width])
    right_visa.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    # Combined visa table
    visa_table = Table([[left_visa, right_visa]], colWidths=[visa_col_width + 10, visa_col_width + 10])
    visa_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (0, 0), 0.5, COLOR_BORDER),
        ('BOX', (1, 0), (1, 0), 0.5, COLOR_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(visa_table)
    
    return story


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def check_ibtikar_form_status(request_obj) -> dict:
    """
    Check the status of IBTIKAR form for a request.
    
    Returns:
        Dictionary with status information
    """
    result = {
        'has_generated_form': False,
        'generated_form_url': None,
        'can_generate': False,
        'error': None,
    }
    
    if not request_obj.service:
        result['error'] = "No service linked to request"
        return result
    
    result['can_generate'] = True
    
    if request_obj.generated_ibtikar_form:
        result['has_generated_form'] = True
        result['generated_form_url'] = request_obj.generated_ibtikar_form.url
    
    return result


def delete_ibtikar_form(request_obj) -> bool:
    """
    Delete the generated IBTIKAR form for a request.
    
    Returns:
        True if deleted successfully
    """
    try:
        if request_obj.generated_ibtikar_form:
            request_obj.generated_ibtikar_form.delete(save=True)
            logger.info(f"Deleted IBTIKAR form for {request_obj.display_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to delete IBTIKAR form for {request_obj.display_id}: {e}")
    
    return False
