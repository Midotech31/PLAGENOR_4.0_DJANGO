# documents/pdf_generator_ibtikar.py — PLAGENOR 4.0 IBTIKAR Form PDF Generator
# Generates the official IBTIKAR analysis request form as PDF
# Based on official PLAGENOR Word templates

from io import BytesIO
from datetime import datetime
import logging

from django.conf import settings
from django.core.files.base import ContentFile

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus.flowables import Flowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY

from .pdf_styles import (
    MARGIN, PAGE_WIDTH, PAGE_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_BORDER, COLOR_HEADER_BG,
    COLOR_TEXT, COLOR_GRAY, COLOR_LIGHT_GRAY, COLOR_WARNING,
    FONT_HELVETICA, FONT_HELVETICA_BOLD, FONT_TIMES, FONT_TIMES_BOLD,
    get_styles, get_base_table_style, style_label_value_table,
    get_essbo_logo, get_plagenor_logo, get_ibtikar_logo,
    format_date, format_datetime, format_currency,
    HorizontalLine, make_page_template
)
from .pdf_ibtikar_templates import (
    TRANSLATIONS, SERVICE_TITLES, SERVICE_SAMPLE_COLUMNS,
    SERVICE_INSTRUCTIONS, SERVICE_ADDITIONAL_FIELDS, SERVICE_CHECKLIST,
    get_translations, get_service_title, get_sample_columns,
    get_service_instructions, get_additional_fields, get_checklist
)
from .pdf_dynamic_fields import get_pdf_fields, render_pdf_fields

logger = logging.getLogger('plagenor.documents')

MIN_SAMPLE_ROWS = 5


class Checkbox(Flowable):
    """A checkbox flowable for checklist items."""
    
    def __init__(self, size=10, checked=False):
        Flowable.__init__(self)
        self.box_size = size
        self.checked = checked
        self.width = size + 4
        self.height = size + 2
    
    def wrap(self, aW, aH):
        return self.width, self.height
    
    def draw(self):
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(1)
        self.canv.rect(0, 1, self.box_size, self.box_size, fill=0, stroke=1)
        if self.checked:
            self.canv.setFillColor(COLOR_PRIMARY)
            self.canv.setFont(FONT_HELVETICA_BOLD, self.box_size - 1)
            self.canv.drawString(1, 2, 'X')


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
    
    def wrap(self, aW, aH):
        self.width = min(self.line_width, aW)
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
        self.height = 60
    
    def wrap(self, aW, aH):
        self.width = min(self.box_width, aW)
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
        self.canv.setFillColor(self.bg_color)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=1, stroke=0)
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(2)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=0, stroke=1)
        self.canv.setFillColor(self.title_color)
        self.canv.setFont(FONT_HELVETICA_BOLD, 11)
        self.canv.drawString(10, self.height - 18, '! ' + self.title)
        self.canv.setFillColor(COLOR_TEXT)
        self.canv.setFont(FONT_HELVETICA, 9)
        chars_per_line = int((self.width - 20) / 5.5)
        y = self.height - 32
        max_lines = 20
        for raw_line in self.content.split('\n'):
            if y < 10 or max_lines <= 0:
                break
            max_lines -= 1
            line = raw_line.strip()
            if not line:
                y -= 8
                continue
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


def generate_ibtikar_form_pdf(request_obj, lang=None, force_regenerate=False):
    """
    Generate an IBTIKAR form PDF for a request.
    
    This function creates a complete IBTIKAR analysis request form with:
    - Header with 3 logos (ESSBO, IBTIKAR, PLAGENOR) and institutional text
    - Request number with format: IBK-2026-XXXX/2026/IBTIKAR/GTP-ESSBO
    - Service-specific title
    - Section 1: Requester information
    - Section 2: Analysis request information
    - Section 3: Sample table (service-specific columns)
    - Service-specific instructions
    - Section 4: Additional information (service-specific)
    - Ethical declaration
    - Requester signature
    - Section 5: PLAGENOR validation block
    
    Args:
        request_obj: Request model instance
        lang: Language code ('fr' or 'en'), defaults to form_data.language or 'fr'
        force_regenerate: If True, regenerate even if form already exists
        
    Returns:
        bytes: PDF file content
    """
    form_data = request_obj.additional_data or {}
    lang = lang or form_data.get('language', 'fr')
    t = get_translations(lang)
    
    if not force_regenerate and request_obj.generated_ibtikar_form:
        try:
            path = request_obj.generated_ibtikar_form.path
            if path and hasattr(path, 'exists') and path.exists():
                with open(path, 'rb') as f:
                    return f.read()
        except Exception:
            pass
    
    if not request_obj.service:
        raise ValueError(f"Request {request_obj.display_id}: no service linked")
    
    service = request_obj.service
    service_code = service.code
    samples = request_obj.sample_table or []
    
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=60,
            rightMargin=60,
            topMargin=70,
            bottomMargin=60,
            title="Formulaire IBTIKAR" if lang == 'fr' else "IBTIKAR Form",
            author='PLAGENOR 4.0',
            subject=f"IBTIKAR Form - {request_obj.display_id}",
        )
        
        story = []
        styles = get_styles()
        page_width = PAGE_WIDTH - 120
        
        # ================================================================
        # HEADER WITH 3 LOGOS AND INSTITUTIONAL TEXT
        # ================================================================
        story.extend(build_official_header(service_code, lang, t, page_width, styles))
        
        # ================================================================
        # REQUEST NUMBER AND SERVICE TITLE
        # ================================================================
        story.extend(build_request_header(request_obj, service, lang, t, page_width, styles))
        
        # ================================================================
        # SECTION 1: REQUESTER INFORMATION
        # ================================================================
        story.extend(build_requester_section(request_obj, lang, t, page_width, styles))
        
        # ================================================================
        # SECTION 2: ANALYSIS REQUEST INFORMATION
        # ================================================================
        story.extend(build_analysis_section(request_obj, lang, t, page_width, styles))
        
        # ================================================================
        # SECTION 3: SAMPLE INFORMATION TABLE
        # ================================================================
        story.extend(build_sample_section(request_obj, service, lang, t, page_width, styles, samples))
        
        # ================================================================
        # SERVICE-SPECIFIC INSTRUCTIONS
        # ================================================================
        story.extend(build_service_instructions(service_code, lang, t, page_width, styles))
        
        # ================================================================
        # SECTION 4: ADDITIONAL INFORMATION
        # ================================================================
        story.extend(build_additional_section(request_obj, service_code, lang, t, page_width, styles))
        
        # ================================================================
        # ETHICAL DECLARATION
        # ================================================================
        story.extend(build_ethical_section(lang, t, page_width, styles))
        
        # ================================================================
        # DYNAMIC PDF FIELDS (SUPERADMIN)
        # ================================================================
        dynamic_fields = get_pdf_fields('ibtikar_form', service=service)
        if dynamic_fields:
            render_pdf_fields(story, dynamic_fields, styles, page_width, request_obj.additional_data or {})

        # ================================================================
        # REQUESTER SIGNATURE
        # ================================================================
        story.extend(build_requester_signature(request_obj, lang, t, page_width, styles))
        
        # Page break
        story.append(PageBreak())
        
        # ================================================================
        # SECTION 5: VALIDATION BLOCK (PLAGENOR)
        # ================================================================
        story.extend(build_validation_section(lang, t, page_width, styles))
        
        # Build PDF
        doc.build(
            story,
            onFirstPage=lambda c, d: make_page_template(c, d, with_page_numbers=True),
            onLaterPages=lambda c, d: make_page_template(c, d, with_page_numbers=True)
        )
        
        buffer.seek(0)
        pdf_bytes = buffer.read()
        
        filename = f"PLAGENOR_IBTIKAR_{service_code}_{request_obj.display_id}.pdf"
        request_obj.generated_ibtikar_form.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info(f"Generated IBTIKAR form PDF for {request_obj.display_id}: {filename}")
        
        return pdf_bytes
        
    except Exception as e:
        import traceback
        logger.error(f"Failed to generate IBTIKAR form PDF for {request_obj.display_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise


def build_official_header(service_code, lang, t, page_width, styles):
    """Build the official header with 3 logos and institutional text."""
    story = []
    
    logo_width = 1.8 * cm
    logo_height = 1.4 * cm
    
    essbo_img = get_essbo_logo(logo_width)
    ibtikar_img = get_ibtikar_logo(logo_width)
    plagenor_img = get_plagenor_logo(logo_width)
    
    left_cell = essbo_img if essbo_img else Paragraph('', styles['Normal'])
    center_cell = ibtikar_img if ibtikar_img else Paragraph('', styles['Normal'])
    right_cell = plagenor_img if plagenor_img else Paragraph('', styles['Normal'])
    
    logo_table = Table(
        [[left_cell, center_cell, right_cell]],
        colWidths=[2.5 * cm, page_width - 5 * cm, 2.5 * cm]
    )
    logo_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(logo_table)
    
    story.append(Spacer(1, 6))
    
    def inst_line(text, font_size=9):
        return Paragraph(
            text,
            ParagraphStyle('InstLine', fontName=FONT_TIMES, fontSize=font_size,
                          textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=1)
        )
    
    story.append(inst_line(t['republic'], 9))
    story.append(inst_line(t['ministry'], 8))
    story.append(inst_line(t['school'], 9))
    story.append(inst_line(t['platform'], 8))
    
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width=page_width, thickness=1, color=COLOR_PRIMARY, spaceAfter=8))
    
    return story


def build_request_header(request_obj, service, lang, t, page_width, styles):
    """Build request number and service title."""
    story = []
    
    year = datetime.now().year
    request_num = request_obj.display_id or f"IBK-{year}-XXXX"
    service_code = service.code
    
    ref_line = f"<b>{t['request_number']}:</b> {request_num}/{year}/IBTIKAR/GTP-ESSBO"
    
    version_table = Table(
        [[
            Paragraph(ref_line, ParagraphStyle('Ref', fontName=FONT_TIMES, fontSize=9,
                                              textColor=COLOR_GRAY, alignment=TA_LEFT)),
            Paragraph(f"<b>{t['version']}</b> 02 / 02.11.2025",
                      ParagraphStyle('Ver', fontName=FONT_TIMES, fontSize=8,
                                    textColor=COLOR_GRAY, alignment=TA_RIGHT)),
        ]],
        colWidths=[page_width * 0.65, page_width * 0.35]
    )
    version_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(version_table)
    
    story.append(Spacer(1, 10))
    
    service_title = get_service_title(service_code, lang)
    title_lines = service_title.split('\n')
    
    story.append(Paragraph(
        f"<b>{title_lines[0]}</b>",
        ParagraphStyle('Title', fontName=FONT_TIMES_BOLD, fontSize=12,
                      textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=4)
    ))
    if len(title_lines) > 1:
        story.append(Paragraph(
            f"<b>{title_lines[1]}</b>",
            ParagraphStyle('Code', fontName=FONT_TIMES_BOLD, fontSize=11,
                          textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=6)
        ))
    
    story.append(Paragraph(
        t['form_intro'],
        ParagraphStyle('Intro', fontName=FONT_TIMES, fontSize=8,
                      textColor=COLOR_GRAY, alignment=TA_JUSTIFY, spaceAfter=8)
    ))
    
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=10))
    
    return story


def build_requester_section(request_obj, lang, t, page_width, styles):
    """Build Section 1: Requester information."""
    story = []
    
    story.append(Paragraph(t['section1_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    requester = request_obj.requester
    form_data = request_obj.additional_data or {}
    requester_data = request_obj.requester_data or {}

    def _pick_first(*values):
        for v in values:
            if v is None:
                continue
            vv = str(v).strip()
            if vv and vv != '—':
                return vv
        return '—'

    if requester:
        full_name = _pick_first(
            requester.get_full_name(),
            getattr(requester, 'first_name', ''),
            requester_data.get('full_name'),
            form_data.get('full_name'),
            requester.username,
        )
        email = _pick_first(
            getattr(requester, 'email', ''),
            requester_data.get('email'),
            form_data.get('email'),
            request_obj.guest_email,
        )
        phone = _pick_first(
            getattr(requester, 'phone', ''),
            requester_data.get('phone'),
            form_data.get('phone'),
            request_obj.guest_phone,
        )
        organization = _pick_first(
            getattr(requester, 'organization', ''),
            getattr(requester, 'department', ''),
            getattr(requester, 'faculty', ''),
            requester_data.get('organization'),
            requester_data.get('university'),
            form_data.get('organization'),
            form_data.get('university'),
            form_data.get('etablissement'),
            getattr(requester, 'institution', ''),
        )
        laboratory = _pick_first(
            getattr(requester, 'laboratory', ''),
            getattr(requester, 'research_team', ''),
            requester_data.get('laboratory'),
            form_data.get('laboratory'),
            form_data.get('research_team'),
            form_data.get('team'),
        )
        position = _pick_first(
            getattr(requester, 'position', ''),
            getattr(requester, 'student_level', ''),
            requester_data.get('position'),
            form_data.get('position'),
            form_data.get('function'),
            form_data.get('role'),
        )
    else:
        full_name = _pick_first(request_obj.guest_name, requester_data.get('full_name'), form_data.get('full_name'))
        email = _pick_first(request_obj.guest_email, requester_data.get('email'), form_data.get('email'))
        phone = _pick_first(request_obj.guest_phone, requester_data.get('phone'), form_data.get('phone'))
        organization = _pick_first(
            requester_data.get('organization'), requester_data.get('university'),
            form_data.get('organization'), form_data.get('university'), form_data.get('etablissement')
        )
        laboratory = _pick_first(
            requester_data.get('laboratory'), form_data.get('laboratory'), form_data.get('research_team'), form_data.get('team')
        )
        position = _pick_first(
            requester_data.get('position'), form_data.get('position'), form_data.get('function'), form_data.get('role')
        )
    
    def lv(label_key, value):
        return [
            Paragraph(t.get(label_key, label_key), styles['Label']),
            Paragraph(str(value), styles['Value']),
        ]
    
    data = [
        lv('full_name', full_name),
        lv('university', organization),
        lv('laboratory', laboratory),
        lv('position', position),
        lv('email', email),
        lv('phone', phone),
    ]
    
    table = Table(data, colWidths=[page_width * 0.30, page_width * 0.70])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 12))
    
    return story


def build_analysis_section(request_obj, lang, t, page_width, styles):
    """Build Section 2: Analysis request information."""
    story = []
    
    story.append(Paragraph(t['section2_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    form_data = request_obj.additional_data or {}
    
    analysis_frame_map = {
        'memoire_fin_cycle': 'Mémoire de fin de cycle' if lang == 'fr' else 'End-of-cycle Thesis',
        'these_doctorat': 'Thèse de doctorat' if lang == 'fr' else 'Doctoral Thesis',
        'projet_recherche': 'Projet de recherche' if lang == 'fr' else 'Research Project',
        'habilitation': 'Habilitation universitaire' if lang == 'fr' else 'University Habilitation',
        'autre': 'Autre' if lang == 'fr' else 'Other',
    }
    
    analysis_frame = analysis_frame_map.get(request_obj.analysis_framework, request_obj.analysis_framework or '—')
    project_title = request_obj.title or '—'
    research_director = request_obj.pi_name or form_data.get('project_director', '—')
    
    def lv(label_key, value):
        return [
            Paragraph(t.get(label_key, label_key), styles['Label']),
            Paragraph(str(value), styles['Value']),
        ]
    
    data = [
        lv('analysis_frame', analysis_frame),
        lv('project_title', project_title),
        lv('research_director', research_director),
    ]
    
    table = Table(data, colWidths=[page_width * 0.30, page_width * 0.70])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 12))
    
    return story


def build_sample_section(request_obj, service, lang, t, page_width, styles, samples):
    """Build Section 3: Sample information table with service-specific columns."""
    story = []
    
    story.append(Paragraph(t['section3_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    service_code = service.code

    def _is_number_column(col_name):
        key_norm = str(col_name).strip().lower()
        return (
            key_norm in ('n°', 'nº', 'n', 'no', 'num', 'numero', 'number', '#')
            or ('n' in key_norm and ('°' in key_norm or 'º' in key_norm))
            or 'number' in key_norm
        )

    # Keep official IBTIKAR template columns (exact form layout)
    columns = get_sample_columns(service_code, lang)
    if not columns:
        columns = [
            t.get('sample_id', 'N°'),
            t.get('sample_code', 'Code'),
            t.get('special_notes', 'Remarques'),
        ]

    # Generic mapping for all current/future services:
    # derive candidate payload keys from first non-empty sample row
    payload_keys = []
    for sample in samples:
        if isinstance(sample, dict):
            for raw_key in sample.keys():
                key_norm = str(raw_key).strip().lower()
                if _is_number_column(raw_key):
                    continue
                if key_norm in ('id', 'sample_id'):
                    continue
                payload_keys.append(str(raw_key))
            if payload_keys:
                break

    def _norm(txt):
        return str(txt or '').strip().lower().replace('-', ' ').replace('_', ' ')

    def _match_key_for_column(column_label, available_keys):
        c = _norm(column_label)
        key_candidates = []

        if 'code' in c:
            key_candidates = ['code', 'sample_code']
        elif 'microorgan' in c or 'microorganisme' in c or 'organism' in c:
            key_candidates = ['organism', 'microorganism', 'microorganisme', 'type_microorganisme']
        elif 'source' in c and ('isolation' in c or 'isolement' in c):
            key_candidates = ['isolation', 'source', 'isolation_source']
        elif 'date' in c and ('isolation' in c or 'isolement' in c):
            key_candidates = ['isolation_date', 'date_isolement', 'date']
        elif 'medium' in c or 'milieu' in c:
            key_candidates = ['culture_medium', 'milieu', 'medium']
        elif 'condition' in c or 'respir' in c or 'incubation' in c:
            key_candidates = ['culture_conditions', 'conditions', 'condition']
        elif 'note' in c or 'remarque' in c:
            key_candidates = ['notes', 'note', 'remarques', 'remark']

        available_norm = {k: _norm(k) for k in available_keys}
        for cand in key_candidates:
            cand_norm = _norm(cand)
            for k, kn in available_norm.items():
                if kn == cand_norm or cand_norm in kn:
                    return k
        return None
    num_cols = len(columns)
    col_widths = []
    if num_cols > 0:
        num_col_width = 0.8 * cm
        remaining_width = page_width - num_col_width
        other_col_width = remaining_width / (num_cols - 1)
        col_widths = [num_col_width] + [other_col_width] * (num_cols - 1)

    header_row = [Paragraph(col, styles['TableHeader']) for col in columns]
    data_rows = [header_row]

    for i, sample in enumerate(samples, 1):
        if isinstance(sample, dict):
            row = [Paragraph(str(i), styles['TableCellCenter'])]

            normalized_sample = {str(k).strip().lower(): v for k, v in sample.items()}

            # Generic mapping: match each official column to the right payload key
            if payload_keys:
                used_keys = set()
                for j in range(1, num_cols):
                    val = ''
                    col_label = columns[j] if j < len(columns) else ''

                    matched_key = _match_key_for_column(col_label, payload_keys)
                    if matched_key and matched_key not in used_keys:
                        mk_norm = _norm(matched_key)
                        val = sample.get(matched_key, normalized_sample.get(mk_norm, ''))
                        used_keys.add(matched_key)

                    # Secondary fallback: remaining payload keys by order
                    if not val:
                        remaining = [k for k in payload_keys if k not in used_keys]
                        if remaining:
                            fallback_key = remaining[0]
                            fk_norm = _norm(fallback_key)
                            val = sample.get(fallback_key, normalized_sample.get(fk_norm, ''))
                            used_keys.add(fallback_key)

                    # Legacy fallback
                    if not val:
                        key = f'col_{j}'
                        val = sample.get(key, sample.get(f'param_{key}', '')) or ''

                    row.append(Paragraph(str(val or ''), styles['TableCell']))
            else:
                # Generic fallback for legacy payloads without discoverable keys
                sample_values = []
                for sample_key, sample_val in sample.items():
                    if _is_number_column(sample_key):
                        continue
                    key_norm = str(sample_key).strip().lower()
                    if key_norm in ('id', 'sample_id'):
                        continue
                    sample_values.append(sample_val)

                for j in range(1, num_cols):
                    key = f'col_{j}'
                    val = sample.get(key, sample.get(f'param_{key}', '')) or ''
                    if not val and (j - 1) < len(sample_values):
                        val = sample_values[j - 1] or ''
                    row.append(Paragraph(str(val), styles['TableCell']))

            data_rows.append(row)
        else:
            row = [Paragraph(str(i), styles['TableCellCenter'])]
            for _ in range(1, num_cols):
                row.append(Paragraph('', styles['TableCell']))
            data_rows.append(row)
    
    table = Table(data_rows, colWidths=col_widths if col_widths else None)
    table.setStyle(get_base_table_style(header_count=1, alternating=False))
    story.append(table)
    
    if not samples:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            t.get('to_be_filled', 'À remplir') if lang == 'fr' else 'To be filled',
            ParagraphStyle('Note', fontName=FONT_HELVETICA + '-Oblique', fontSize=8,
                          textColor=COLOR_LIGHT_GRAY, alignment=TA_LEFT)
        ))
    
    story.append(Spacer(1, 12))
    
    return story


def build_service_instructions(service_code, lang, t, page_width, styles):
    """Build service-specific instructions (Très important block)."""
    story = []
    
    instructions = get_service_instructions(service_code, lang)
    
    if instructions.get('important'):
        story.append(Paragraph(
            f"<b>{t['very_important']}</b>",
            ParagraphStyle('ImpTitle', fontName=FONT_HELVETICA_BOLD, fontSize=10,
                          textColor=COLOR_WARNING, alignment=TA_LEFT, spaceAfter=4)
        ))
        story.append(ImportantBox(
            width=page_width,
            title=t['very_important'],
            content=instructions['important'],
            title_color=COLOR_WARNING
        ))
        story.append(Spacer(1, 8))
    
    if instructions.get('transport'):
        story.append(Paragraph(
            instructions['transport'],
            ParagraphStyle('Transport', fontName=FONT_TIMES, fontSize=8,
                          textColor=COLOR_GRAY, alignment=TA_JUSTIFY, spaceAfter=12)
        ))
    
    return story


def build_additional_section(request_obj, service_code, lang, t, page_width, styles):
    """Build Section 4: Additional information with service-specific fields."""
    story = []
    
    additional_fields = get_additional_fields(service_code, lang)
    if not additional_fields:
        return story
    
    form_data = request_obj.additional_data or {}
    service_params = request_obj.service_params or {}
    
    story.append(Paragraph(t['section4_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    alias_keys = {
        'fresh_culture': ['fresh_culture', 'fresh_cultures', 'fresh_culture_available', 'cultures_fraiches'],
        'maldi_target_type': ['maldi_target_type', 'target_type', 'maldi_target'],
        'analysis_mode': ['analysis_mode', 'mode_analyse', 'analysis_type'],
    }

    def _value_from_sources(primary_key):
        candidates = alias_keys.get(primary_key, [primary_key])
        for k in candidates:
            if k in form_data and form_data.get(k) not in (None, '', []):
                return form_data.get(k)
            if k in service_params and service_params.get(k) not in (None, '', []):
                return service_params.get(k)
        return t.get('to_be_filled', '—')

    data = []
    for field in additional_fields:
        key = field['key']
        label = field['label']
        value = _value_from_sources(key)

        if isinstance(value, bool):
            value = t['yes'] if value else t['no']
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ('true', 'yes', 'oui', '1'):
                value = t['yes']
            elif lowered in ('false', 'no', 'non', '0'):
                value = t['no']
            elif key == 'maldi_target_type' and lowered == 'disposable':
                value = 'Disposable target'
            elif key == 'analysis_mode' and lowered == 'duplicate':
                value = 'Duplicata' if lang == 'fr' else 'Duplicate'
            elif key == 'analysis_mode' and lowered == 'triplicate':
                value = 'Triplicata' if lang == 'fr' else 'Triplicate'
        elif isinstance(value, list):
            value = ', '.join(str(v) for v in value if str(v).strip())

        if not value:
            value = t.get('to_be_filled', '—')
        
        data.append([
            Paragraph(label, styles['Label']),
            Paragraph(str(value), styles['Value']),
        ])
    
    if data:
        table = Table(data, colWidths=[page_width * 0.40, page_width * 0.60])
        style_label_value_table(table)
        story.append(table)
    
    story.append(Spacer(1, 12))
    
    return story


def build_ethical_section(lang, t, page_width, styles):
    """Build ethical declaration section."""
    story = []
    
    story.append(Paragraph(t['ethical_declaration_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    story.append(Paragraph(
        t['ethical_declaration_text'],
        ParagraphStyle('Ethical', fontName=FONT_TIMES, fontSize=9, leading=13,
                      textColor=COLOR_TEXT, alignment=TA_JUSTIFY, spaceAfter=12)
    ))
    
    return story


def build_requester_signature(request_obj, lang, t, page_width, styles):
    """Build requester and supervisor signature blocks on the same line."""
    story = []

    supervisor_label = 'Supervisor Signature' if lang == 'en' else 'Signature du superviseur'

    requester = request_obj.requester
    form_data = request_obj.additional_data or {}
    requester_data = request_obj.requester_data or {}

    supervisor_name = (
        request_obj.pi_name
        or form_data.get('project_director')
        or form_data.get('research_supervisor')
        or (getattr(requester, 'supervisor', '') if requester else '')
        or requester_data.get('supervisor')
        or '—'
    )

    sig_width = (page_width - 12) / 2

    header_style = ParagraphStyle(
        'SigL',
        fontName=FONT_TIMES_BOLD,
        fontSize=10,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
    )
    date_style = ParagraphStyle(
        'SigD',
        fontName=FONT_HELVETICA,
        fontSize=8,
        textColor=COLOR_GRAY,
        alignment=TA_LEFT,
    )

    requester_col = [
        Paragraph(t['requester_signature'], header_style),
        Spacer(1, 20),
        Paragraph('_' * 36, styles['Normal']),
        Paragraph(f"{t['date']}: _______________", date_style),
    ]

    supervisor_col = [
        Paragraph(supervisor_label, header_style),
        Paragraph(str(supervisor_name), ParagraphStyle('SigName', fontName=FONT_HELVETICA, fontSize=8, textColor=COLOR_GRAY, alignment=TA_CENTER)),
        Spacer(1, 14),
        Paragraph('_' * 36, styles['Normal']),
        Paragraph(f"{t['date']}: _______________", date_style),
    ]

    sig_table = Table([[requester_col, supervisor_col]], colWidths=[sig_width, sig_width])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    story.append(Spacer(1, 10))
    story.append(sig_table)
    story.append(Spacer(1, 15))

    return story


def build_validation_section(lang, t, page_width, styles):
    """Build Section 5: PLAGENOR validation block."""
    story = []
    
    story.append(Paragraph(t['section5_title'], styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))
    
    reserved_box = Table(
        [[Paragraph(
            f"<b>{'Cadre réservé à PLAGENOR' if lang == 'fr' else 'Reserved for PLAGENOR'}</b>",
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
    
    service_code = 'EGTP-IMT'
    checklist_items = get_checklist(service_code, lang)
    
    checklist_data = []
    for item in checklist_items:
        checklist_data.append([
            Checkbox(size=10),
            Paragraph(str(item), styles['ChecklistItem'])
        ])
    
    checklist_table = Table(checklist_data, colWidths=[16, page_width - 16])
    checklist_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    
    operator_data = [
        [Paragraph(t['operator'], styles['Label']), Paragraph('', styles['Value'])],
        [Paragraph(t['operator_name'] + ':', styles['Label']),
         Paragraph('_' * 40, styles['Value'])],
        [Paragraph(t['reception_date'] + ':', styles['Label']),
         Paragraph('_' * 25 + '  ' + t['date'] + ': ________', styles['Value'])],
        [Paragraph(t['signature'] + ':', styles['Label']),
         Paragraph('', styles['Value'])],
    ]
    
    operator_table = Table(operator_data, colWidths=[3 * cm, page_width - 3 * cm])
    operator_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    
    validation_left_table = Table(
        [[operator_table], [Spacer(1, 10)], [checklist_table]],
        colWidths=[page_width * 0.45]
    )
    validation_left_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    story.append(Paragraph(t['checklist_title'], styles['Label']))
    story.append(Spacer(1, 4))
    story.append(checklist_table)
    story.append(Spacer(1, 8))
    
    story.append(Paragraph(t.get('comment', 'Commentaire') + ':', styles['Label']))
    story.append(Spacer(1, 4))
    for _ in range(3):
        story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=12))
    
    story.append(Spacer(1, 12))
    
    visa_col_width = (page_width - 20) / 2
    
    left_visa = Table([
        [Paragraph(t['visa_chef_service'], ParagraphStyle('VisaTitle', fontName=FONT_TIMES_BOLD,
                                                           fontSize=10, textColor=COLOR_PRIMARY,
                                                           alignment=TA_CENTER))],
        [Spacer(1, 30)],
        [Paragraph('_' * 40, styles['Normal'])],
        [Paragraph(f"{t['date']}: _______________", ParagraphStyle('Date', fontName=FONT_HELVETICA,
                                                                   fontSize=8, textColor=COLOR_GRAY))],
    ], colWidths=[visa_col_width])
    left_visa.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    right_visa = Table([
        [Paragraph(t['visa_directeur'], ParagraphStyle('VisaTitle2', fontName=FONT_TIMES_BOLD,
                                                        fontSize=10, textColor=COLOR_PRIMARY,
                                                        alignment=TA_CENTER))],
        [Spacer(1, 30)],
        [Paragraph('_' * 40, styles['Normal'])],
        [Paragraph(f"{t['date']}: _______________", ParagraphStyle('Date2', fontName=FONT_HELVETICA,
                                                                   fontSize=8, textColor=COLOR_GRAY))],
    ], colWidths=[visa_col_width])
    right_visa.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    
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
    
    story.append(Paragraph(t.get('visa_responsables', 'Visa des responsables'), styles['Label']))
    story.append(Spacer(1, 6))
    story.append(visa_table)
    
    return story


def check_ibtikar_form_status(request_obj) -> dict:
    """Check the status of IBTIKAR form for a request."""
    result = {
        'has_generated_form': False,
        'generated_form_url': None,
        'can_generate': False,
        'error': None,
    }
    
    if not request_obj.service:
        result['error'] = "No service linked to request"
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
    
    result['can_generate'] = True
    
    if request_obj.generated_ibtikar_form:
        result['has_generated_form'] = True
        result['generated_form_url'] = request_obj.generated_ibtikar_form.url
    
    return result
