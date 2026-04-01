# documents/pdf_generators.py — PLAGENOR 4.0 IBTIKAR Form PDF Generator
# Programmatic PDF generation via ReportLab — no template files needed.

from io import BytesIO
from datetime import datetime
import logging

from django.conf import settings

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable
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
    get_essbo_logo, get_plagenor_logo,
    format_date, make_page_template
)
from .pdf_labels import LABELS_FR, LABELS_EN

logger = logging.getLogger('plagenor.documents')

MIN_SAMPLE_ROWS = 15
GENERIC_COLUMNS = [
    ('code', 'Code échantillon'),
    ('remarques', 'Remarques'),
]


class Checkbox(Flowable):
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
            self.canv.drawString(1, 2, 'X')


class SignatureLine(Flowable):
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


class ImportantBox(Flowable):
    def __init__(self, width, title, content,
                 title_color=COLOR_PRIMARY,
                 bg_color=HexColor('#fff8e1'),
                 border_color=HexColor('#ffc107')):
        Flowable.__init__(self)
        self.box_width = width
        self.title = title
        self.content = content
        self.title_color = title_color
        self.bg_color = bg_color
        self.border_color = border_color
        self.height = 60

    def wrap(self, availableWidth, availableHeight):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        self.width = min(self.box_width, availableWidth)
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


class VisaBlock(Flowable):
    def __init__(self, width, title, date_label='Date:', line_length=None):
        Flowable.__init__(self)
        self.block_width = width
        self.title = title
        self.date_label = date_label
        self.signature_line_length = line_length or (width - 20)
        self.height = 80

    def wrap(self, availableWidth, availableHeight):
        self.width = min(self.block_width, availableWidth)
        return self.width, self.height

    def draw(self):
        self.canv.setFont(FONT_TIMES_BOLD, 10)
        self.canv.setFillColor(COLOR_PRIMARY)
        self.canv.drawCentredString(self.width / 2, self.height - 15, self.title)
        self.canv.setStrokeColor(COLOR_TEXT)
        self.canv.setLineWidth(0.5)
        sig_x = (self.width - self.signature_line_length) / 2
        self.canv.line(sig_x, self.height - 45, sig_x + self.signature_line_length, self.height - 45)
        self.canv.setFont(FONT_HELVETICA, 8)
        self.canv.setFillColor(COLOR_GRAY)
        self.canv.drawString(sig_x, self.height - 55, self.date_label)
        self.canv.line(sig_x + 35, self.height - 55, sig_x + 35 + 80, self.height - 55)


def generate_ibtikar_form_pdf(request_obj, lang='fr', force_regenerate=False):
    """
    Generate an IBTIKAR Analysis Request Form PDF for a request.

    Returns bytes (PDF content) on success.
    Raises ValueError if service is missing.
    Falls back to generic 3-column table if service has no form_fields.

    Args:
        request_obj: Request model instance
        lang: Language code ('fr' or 'en')
        force_regenerate: If True, regenerate even if already saved

    Returns:
        bytes: PDF file content
    """
    labels = LABELS_EN if lang == 'en' else LABELS_FR

    if not request_obj.service:
        raise ValueError(f"Request {getattr(request_obj, 'pk', '?')}: no service linked")

    service = request_obj.service

    if not force_regenerate and request_obj.generated_ibtikar_form:
        try:
            path = request_obj.generated_ibtikar_form.path
            if path and hasattr(path, 'exists') and path.exists():
                with open(path, 'rb') as f:
                    return f.read()
        except Exception:
            pass

    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=MARGIN + 1 * cm,
            title=labels.get('ibtikar_form_title', 'IBTIKAR Form'),
            author='PLAGENOR 4.0',
            subject=f"IBTIKAR Form - {getattr(request_obj, 'display_id', '?')}",
        )

        story = []
        styles = get_styles()
        page_width = PAGE_WIDTH - 2 * MARGIN

        # A) Institutional Header
        story.extend(_build_institutional_header(labels, page_width, styles))

        # B) Form Title
        story.extend(_build_form_title(request_obj, service, labels, page_width, styles))

        # C) Section 1 — Requester Information
        story.extend(_build_requester_section(request_obj, labels, page_width, styles))

        # D) Section 2 — Project Information
        story.extend(_build_project_section(request_obj, labels, page_width, styles))

        # E) Section 3 — Sample Table
        story.extend(_build_sample_table(request_obj, service, labels, page_width, styles, lang=lang))

        # F) Section 4 — Service-Specific Instructions
        story.extend(_build_service_instructions(service, labels, page_width, styles))

        # G) Section 5 — Declarations
        story.extend(_build_declarations(labels, page_width, styles))

        # H) Section 6 — Signature Blocks
        story.extend(_build_signature_blocks(labels, page_width, styles))

        story.append(PageBreak())

        # I) Section 7 — PLAGENOR Validation Block
        story.extend(_build_validation_block(request_obj, service, labels, page_width, styles))

        # J) Footer (handled via page template)
        doc.build(
            story,
            onFirstPage=lambda c, d: make_page_template(c, d, with_page_numbers=True),
            onLaterPages=lambda c, d: make_page_template(c, d, with_page_numbers=True)
        )

        buffer.seek(0)
        pdf_bytes = buffer.read()

        filename = f"PLAGENOR_IBTIKAR_{service.code}_{getattr(request_obj, 'display_id', 'unknown')}.pdf"
        from django.core.files.base import ContentFile
        request_obj.generated_ibtikar_form.save(filename, ContentFile(pdf_bytes), save=True)
        logger.info(f"IBTIKAR PDF generated: {filename}")

        return pdf_bytes

    except Exception as e:
        logger.error(f"PDF generation failed for {getattr(request_obj, 'display_id', '?')}: {e}", exc_info=True)
        raise


def _build_institutional_header(labels, page_width, styles):
    """A) Institutional header: republic, ministry, school, platform, logos."""
    story = []

    essbo_logo = get_essbo_logo(width=2 * cm)
    plagenor_logo = get_plagenor_logo(width=2 * cm)

    def inst_line(text, font_size=9):
        return Paragraph(text, ParagraphStyle(
            'InstLine', fontName=FONT_TIMES, fontSize=font_size,
            textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=1
        ))

    header_lines = [
        inst_line(labels.get('republic_algeria', ''), 9),
        inst_line(labels.get('ministry_higher_education', ''), 8),
        inst_line(labels.get('essbo_full', ''), 9),
        inst_line(labels.get('platform_tech', ''), 8),
    ]

    left_cell = essbo_logo if essbo_logo else Paragraph('', styles['Normal'])
    right_cell = plagenor_logo if plagenor_logo else Paragraph('', styles['Normal'])

    logo_header = Table(
        [[left_cell, '', right_cell]],
        colWidths=[2.5 * cm, page_width - 5 * cm, 2.5 * cm]
    )
    logo_header.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('ALIGN', (2, 0), (2, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(logo_header)

    for line in header_lines:
        story.append(line)

    story.append(HRFlowable(width=page_width, thickness=1, color=COLOR_PRIMARY, spaceAfter=6))
    return story


def _build_form_title(request_obj, service, labels, page_width, styles):
    """B) Form title: reference number, service name, version."""
    story = []

    year = datetime.now().year
    ref_template = labels.get('reference_format', '{year}/IBTIKAR/PLAGENOR/{service}')
    reference = ref_template.format(year=year, service=service.code)
    service_name = service.name or service.code

    ref_para = Paragraph(
        f"<b>{labels.get('request_reference', 'N de la demande')}</b><br/>{reference}",
        ParagraphStyle('Ref', fontName=FONT_COURIER if False else FONT_TIMES, fontSize=9,
                       textColor=COLOR_GRAY, alignment=TA_CENTER, spaceAfter=4)
    )
    story.append(ref_para)

    story.append(Paragraph(
        f"<b>{service_name.upper()}</b>",
        ParagraphStyle('Title', fontName=FONT_TIMES_BOLD, fontSize=13,
                       textColor=COLOR_PRIMARY, alignment=TA_CENTER, spaceAfter=4)
    ))

    form_version = getattr(service, 'form_version', '01')
    version_date = format_date(datetime.now())
    version_row = Table(
        [[
            Paragraph(f"<b>{service.code}</b>",
                      ParagraphStyle('Code', fontName=FONT_TIMES_BOLD, fontSize=10,
                                     textColor=COLOR_TEXT, alignment=TA_CENTER)),
            Paragraph(f"{labels.get('version', 'Version')} {form_version}",
                      ParagraphStyle('Ver', fontName=FONT_HELVETICA, fontSize=8,
                                     textColor=COLOR_GRAY, alignment=TA_CENTER)),
            Paragraph(version_date,
                      ParagraphStyle('Date', fontName=FONT_HELVETICA, fontSize=8,
                                     textColor=COLOR_GRAY, alignment=TA_CENTER)),
        ]],
        colWidths=[page_width * 0.3, page_width * 0.4, page_width * 0.3]
    )
    version_row.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(version_row)
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=8))
    return story


def _build_requester_section(request_obj, labels, page_width, styles):
    """C) Section 1 — Requester Information table."""
    story = []
    story.append(Paragraph(labels.get('section_requester', 'Section 1 - Requester'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))

    requester = request_obj.requester
    if requester:
        full_name = _or_dash(requester.get_full_name() or getattr(requester, 'username', ''))
        institution = _or_dash(getattr(requester, 'organization', '') or getattr(requester, 'institution', ''))
        department = _or_dash(getattr(requester, 'department', ''))
        laboratory = _or_dash(getattr(requester, 'laboratory', ''))
        position = _format_position(getattr(requester, 'position', ''), labels)
        email = _or_dash(getattr(requester, 'email', ''))
        phone = _or_dash(getattr(requester, 'phone', ''))
    else:
        full_name = _or_dash(getattr(request_obj, 'guest_name', ''))
        institution = _or_dash('')
        department = _or_dash('')
        laboratory = _or_dash('')
        position = _or_dash('')
        email = _or_dash(getattr(request_obj, 'guest_email', ''))
        phone = _or_dash(getattr(request_obj, 'guest_phone', ''))

    def lv(label_key, value):
        return [
            Paragraph(labels.get(label_key, label_key), styles['Label']),
            Paragraph(str(value), styles['Value']),
        ]

    data = [
        lv('full_name', full_name),
        lv('institution', institution),
        lv('department', department),
        lv('laboratory', laboratory),
        lv('position', position),
        lv('email', email),
        lv('phone', phone),
    ]
    table = Table(data, colWidths=[page_width * 0.32, page_width * 0.68])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 10))
    return story


def _build_project_section(request_obj, labels, page_width, styles):
    """D) Section 2 — Project Information table."""
    story = []
    story.append(Paragraph(labels.get('section_analysis', 'Section 2 - Project'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))

    def lv(label_key, value):
        return [
            Paragraph(labels.get(label_key, label_key), styles['Label']),
            Paragraph(str(value), styles['Value']),
        ]

    data = [
        lv('project_title', _or_dash(getattr(request_obj, 'title', ''))),
        lv('pi_name', _or_dash(getattr(request_obj, 'pi_name', ''))),
        lv('pi_email', _or_dash(getattr(request_obj, 'pi_email', ''))),
        lv('pi_phone', _or_dash(getattr(request_obj, 'pi_phone', ''))),
    ]
    desc = getattr(request_obj, 'project_description', '') or ''
    if desc:
        data.append(lv('project_description', desc))

    table = Table(data, colWidths=[page_width * 0.32, page_width * 0.68])
    style_label_value_table(table)
    story.append(table)
    story.append(Spacer(1, 10))
    return story


def _build_sample_table(request_obj, service, labels, page_width, styles, lang='fr'):
    """E) Section 3 — Sample Table with dynamic columns from ServiceFormField."""
    story = []
    story.append(Paragraph(labels.get('section_samples', 'Section 3 - Samples'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
    story.append(Spacer(1, 4))

    try:
        sample_fields = service.form_fields.filter(
            field_category='sample_table'
        ).order_by('sort_order', 'order', 'pk')
    except Exception:
        sample_fields = []

    if not sample_fields.exists() if hasattr(sample_fields, 'exists') else not sample_fields:
        sample_fields = []

    column_defs = []
    for f in sample_fields:
        field_label = f.get_label(lang) if hasattr(f, 'get_label') else (
            (f.label_fr if lang == 'fr' and hasattr(f, 'label_fr') else None)
            or (f.label_en if hasattr(f, 'label_en') else None)
            or getattr(f, 'label', str(f))
        )
        column_defs.append((getattr(f, 'name', str(f.pk)), field_label))

    if not column_defs:
        for key, lbl in GENERIC_COLUMNS:
            column_defs.append((key, labels.get(lbl, lbl)))

    header_row = [Paragraph(labels.get('sample_id', 'N'), styles['TableHeader'])]
    column_keys = ['_num_']
    for key, lbl in column_defs:
        header_row.append(Paragraph(lbl, styles['TableHeader']))
        column_keys.append(key)

    samples = getattr(request_obj, 'sample_table', []) or []
    if not isinstance(samples, list):
        samples = []

    data_rows = [header_row]
    for i, sample in enumerate(samples, 1):
        row = [Paragraph(str(i), styles['TableCellCenter'])]
        if isinstance(sample, dict):
            for key in column_keys[1:]:
                val = sample.get(key, '') or ''
                row.append(Paragraph(str(val), styles['TableCell']))
        else:
            for _ in column_keys[1:]:
                row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)

    while len(data_rows) < MIN_SAMPLE_ROWS + 1:
        row_num = len(data_rows)
        row = [Paragraph(str(row_num), styles['TableCellCenter'])]
        for _ in column_keys[1:]:
            row.append(Paragraph('', styles['TableCell']))
        data_rows.append(row)

    num_cols = len(column_keys)
    col_w = page_width / num_cols
    table = Table(data_rows, colWidths=[col_w] * num_cols)
    table.setStyle(get_base_table_style(header_count=1))
    story.append(table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        labels.get('minimum_rows_note', 'Minimum 15 lines required.'),
        ParagraphStyle('Note', fontName=FONT_HELVETICA + '-Oblique', fontSize=8,
                       textColor=COLOR_LIGHT_GRAY, alignment=TA_LEFT)
    ))
    story.append(Spacer(1, 10))
    return story


def _build_service_instructions(service, labels, page_width, styles):
    """F) Section 4 — Service-specific instructions (Très Important block)."""
    story = []

    instr_key = 'ibtikar_instructions_en' if labels is LABELS_EN else 'ibtikar_instructions'
    instructions = getattr(service, instr_key, '') or ''

    if not instructions:
        instructions = getattr(service, 'ibtikar_instructions', '') or ''

    if instructions:
        story.append(Paragraph(labels.get('very_important', 'TRES IMPORTANT'), styles['SectionTitle']))
        story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=4))
        story.append(Spacer(1, 4))
        story.append(ImportantBox(
            width=page_width,
            title=labels.get('very_important', 'TRES IMPORTANT'),
            content=instructions
        ))
        story.append(Spacer(1, 10))
    return story


def _build_declarations(labels, page_width, styles):
    """G) Section 5 — Declarations (accuracy + ethical responsibility)."""
    story = []
    story.append(Paragraph(labels.get('section_ethical', 'Section 5 - Declaration'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=6))
    story.append(Spacer(1, 4))

    decl1_text = labels.get(
        'declaration_text',
        'Je declare par la presente que les informations fournies sont exactes et '
        'completes a ma connaissance. Je comprends que toute divergence peut entrainer '
        'des retards dans le traitement.'
    )
    decl1_en = (
        'I hereby declare that the information provided is accurate and complete to the '
        'best of my knowledge. I understand that any discrepancies may lead to delays in processing.'
    )

    decl2_text = (
        "Par la signature de ce formulaire, le demandeur certifie que tous les echantillons "
        "soumis ont ete collectes, manipules et transferes dans le strict respect de toutes "
        "les normes ethiques et reglementaires applicables. Le demandeur reconnait en outre "
        "l'entiere responsabilite de la nature, de l'origine et de l'utilisation prevue de "
        "ces echantillons, y compris toute implication ethique ou juridique decoulant de leur "
        "traitement, manipulation ou analyse."
    )
    decl2_en = (
        'By signing this form, the applicant hereby certifies that all submitted samples have '
        'been collected, handled, and transferred in strict adherence to all applicable ethical '
        'and regulatory standards. The applicant further acknowledges full responsibility for the '
        'nature, origin, and intended use of these samples, including any ethical or legal '
        'implications arising from their processing, handling, or analysis.'
    )

    story.append(Paragraph(
        f"<b>{labels.get('declaration_1', 'Declaration 1 - Accuracy')}</b><br/>{decl1_text}",
        ParagraphStyle('Decl', fontName=FONT_TIMES, fontSize=9, leading=13,
                       textColor=COLOR_TEXT, alignment=TA_JUSTIFY, spaceAfter=8)
    ))
    if labels is LABELS_EN:
        story.append(Paragraph(decl1_en, ParagraphStyle('DeclEN', fontName=FONT_TIMES, fontSize=8,
                           leading=12, textColor=COLOR_GRAY, alignment=TA_JUSTIFY, spaceAfter=8)))

    story.append(Paragraph(
        f"<b>{labels.get('declaration_2', 'Declaration 2 - Ethical Responsibility')}</b><br/>{decl2_text}",
        ParagraphStyle('Decl2', fontName=FONT_TIMES, fontSize=9, leading=13,
                       textColor=COLOR_TEXT, alignment=TA_JUSTIFY, spaceAfter=8)
    ))
    if labels is LABELS_EN:
        story.append(Paragraph(decl2_en, ParagraphStyle('Decl2EN', fontName=FONT_TIMES, fontSize=8,
                           leading=12, textColor=COLOR_GRAY, alignment=TA_JUSTIFY, spaceAfter=8)))

    story.append(Spacer(1, 10))
    return story


def _build_signature_blocks(labels, page_width, styles):
    """H) Section 6 — Signature Blocks (manual signature space)."""
    story = []
    story.append(Paragraph(labels.get('section_signature', 'Section 6 - Signature'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=6))
    story.append(Spacer(1, 4))

    sig_width = (page_width - 20) / 2

    left_sig = Table([
        [Paragraph(labels.get('submitter_signature', 'Signature du demandeur'),
                    ParagraphStyle('SigL', fontName=FONT_TIMES_BOLD, fontSize=10,
                                   textColor=COLOR_PRIMARY, alignment=TA_CENTER))],
        [Spacer(1, 30)],
        [Paragraph('_' * 40, styles['Normal'])],
        [Paragraph(f"{labels.get('signature_date', 'Date')}: _______________",
                   ParagraphStyle('SigD', fontName=FONT_HELVETICA, fontSize=8,
                                  textColor=COLOR_GRAY, alignment=TA_LEFT))],
    ], colWidths=[sig_width])
    left_sig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    right_sig = Table([
        [Paragraph(labels.get('visa_chef', 'Visa du Chef du Service'),
                   ParagraphStyle('SigR', fontName=FONT_TIMES_BOLD, fontSize=10,
                                  textColor=COLOR_PRIMARY, alignment=TA_CENTER))],
        [Spacer(1, 30)],
        [Paragraph('_' * 40, styles['Normal'])],
        [Paragraph(f"{labels.get('signature_date', 'Date')}: _______________",
                   ParagraphStyle('SigD2', fontName=FONT_HELVETICA, fontSize=8,
                                  textColor=COLOR_GRAY, alignment=TA_LEFT))],
    ], colWidths=[sig_width])
    right_sig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    sig_table = Table([[left_sig, right_sig]], colWidths=[sig_width + 10, sig_width + 10])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (0, 0), 0.5, COLOR_BORDER),
        ('BOX', (1, 0), (1, 0), 0.5, COLOR_BORDER),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 10))
    return story


def _build_validation_block(request_obj, service, labels, page_width, styles):
    """I) Section 7 — PLAGENOR Validation Block (admin ops checklist)."""
    story = []

    story.append(Paragraph(labels.get('section_validation', 'Section 7 - Validation'), styles['SectionTitle']))
    story.append(HRFlowable(width=page_width, thickness=0.5, color=COLOR_BORDER, spaceAfter=6))
    story.append(Spacer(1, 4))

    reserved = Table(
        [[Paragraph(
            f"<b>{labels.get('reserved_plagenor', 'Cadre reserve a PLAGENOR')}</b>",
            styles['ImportantNote']
        )]],
        colWidths=[page_width]
    )
    reserved.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#f5f5f5')),
        ('BOX', (0, 0), (-1, -1), 1, COLOR_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(reserved)
    story.append(Spacer(1, 8))

    checklist = [
        labels.get('checklist_filled', 'Formulaire correctement rempli'),
        labels.get('checklist_samples', 'Echantillons conformes'),
        labels.get('checklist_payment', 'Paiement/budget verifie'),
    ]
    story.append(Paragraph(labels.get('checklist_title', 'Checklist'), styles['Label']))
    story.append(Spacer(1, 4))

    for item_text in checklist:
        cb_row = Table(
            [[Checkbox(size=10), Paragraph(str(item_text), styles['ChecklistItem'])]],
            colWidths=[16, page_width - 16]
        )
        cb_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        story.append(cb_row)

    story.append(Spacer(1, 12))
    story.append(Paragraph(labels.get('operator', 'Operateur'), styles['Label']))
    story.append(Spacer(1, 2))
    story.append(SignatureLine(width=page_width * 0.6,
                               date_label=f"{labels.get('signature_date', 'Date')}:"))
    story.append(Spacer(1, 10))

    visa_width = (page_width - 20) / 2
    left_visa = VisaBlock(visa_width, labels.get('visa_chef', 'Visa du Chef du Service Commun'))
    right_visa = VisaBlock(visa_width, labels.get('visa_directeur', "Visa du Directeur de l'ESSBO"))

    visa_table = Table([[left_visa, right_visa]], colWidths=[visa_width + 10, visa_width + 10])
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


def _or_dash(value):
    """Return value or em-dash if falsy."""
    return value if value else '—'


def _format_position(position_key, labels):
    """Translate a position choice key to display label."""
    POSITION_MAP = {
        'etudiant_doctorant': 'Etudiant/Doctorant',
        'chercheur': 'Chercheur',
        'mca': 'MCA',
        'mcb': 'MCB',
        'professeur': 'Professeur',
        'ingenieur': 'Ingénieur',
        'technicien': 'Technicien',
        'autre': 'Autre',
    }
    if not position_key:
        return '—'
    return labels.get(f'position_{position_key}', POSITION_MAP.get(position_key, position_key)) or '—'


def check_template_status(request_obj):
    """
    Stub for backward compatibility with stale dashboard imports.
    Returns a minimal status dict for the IBTIKAR form.
    """
    from .pdf_generator_ibtikar import check_ibtikar_form_status
    return check_ibtikar_form_status(request_obj)
