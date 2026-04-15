"""
Dynamic PDF field renderer for configurable PLAGENOR documents.

Workflow map (high-level):
- Merge active global fields with optional service-specific overrides by field name.
- Render ordered flowables for IBTIKAR form, platform note, and reception form.
- Keep fallback-safe rendering when optional resources (e.g. image path) are missing.
"""

from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import cm

from documents.pdf_styles import (
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_TEXT,
    FONT_HELVETICA,
    FONT_HELVETICA_BOLD,
    get_logo_dimensions,
)


def get_pdf_fields(pdf_target, service=None):
    """Return active PDF fields merged global+service with service override by name."""
    from core.models import PDFFormField

    global_fields = PDFFormField.objects.filter(
        pdf_target=pdf_target,
        scope_type='global',
        is_active=True,
    ).order_by('order', 'pk')

    if service:
        service_fields = PDFFormField.objects.filter(
            pdf_target=pdf_target,
            scope_type='service',
            service=service,
            is_active=True,
        ).order_by('order', 'pk')

        service_names = set(service_fields.values_list('name', flat=True))
        merged = list(global_fields.exclude(name__in=service_names)) + list(service_fields)
        merged.sort(key=lambda f: (f.order, f.pk))
        return merged

    return list(global_fields)


def render_pdf_fields(story, dynamic_fields, styles, page_width, request_data=None):
    """Render dynamic PDF fields as reportlab flowables and append to story."""
    if not dynamic_fields:
        return

    request_data = request_data or {}
    label_style = styles.get('Label')
    value_style = styles.get('Value')

    title_style = ParagraphStyle(
        'DynamicSectionTitle',
        fontName=FONT_HELVETICA_BOLD,
        fontSize=11,
        textColor=COLOR_PRIMARY,
        alignment=TA_CENTER,
        spaceBefore=8,
        spaceAfter=4,
    )
    normal_style = ParagraphStyle(
        'DynamicNormal',
        fontName=FONT_HELVETICA,
        fontSize=9,
        textColor=COLOR_TEXT,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    for field in dynamic_fields:
        label = field.label_fr or field.name
        value = request_data.get(field.name, field.default_value or '')
        opts = field.options or {}
        kind = field.field_kind

        if kind == 'separator':
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width=page_width, thickness=0.6, color=COLOR_BORDER, spaceAfter=4))
            continue

        if kind == 'section_title':
            story.append(Paragraph(label, title_style))
            continue

        if kind == 'text_line':
            table = Table([
                [Paragraph(label, label_style), Paragraph(str(value), value_style)]
            ], colWidths=[page_width * 0.35, page_width * 0.65])
            table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            story.append(Spacer(1, 4))
            continue

        if kind == 'text_block':
            height = float(opts.get('height', 36))
            story.append(Paragraph(label, label_style))
            box = Table([[Paragraph(str(value), normal_style)]], colWidths=[page_width], rowHeights=[height])
            box.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.8, COLOR_BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(box)
            story.append(Spacer(1, 4))
            continue

        if kind == 'checkbox':
            checked = bool(value) or str(value).lower() in ('1', 'true', 'yes', 'oui', 'x')
            mark = '☑' if checked else '☐'
            story.append(Paragraph(f"{mark} {label}", normal_style))
            continue

        if kind == 'signature':
            sig_height = float(opts.get('height', 40))
            story.append(Paragraph(label, label_style))
            sig_table = Table([
                [Paragraph('Signature: ______________________', normal_style), Paragraph('Date: __________', normal_style)]
            ], colWidths=[page_width * 0.7, page_width * 0.3], rowHeights=[sig_height])
            sig_table.setStyle(TableStyle([
                ('BOX', (0, 0), (-1, -1), 0.8, COLOR_BORDER),
                ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(sig_table)
            story.append(Spacer(1, 4))
            continue

        if kind == 'table_row':
            left = opts.get('left_label', label)
            right = str(value) if value else opts.get('right_label', '')
            row_table = Table([[Paragraph(str(left), normal_style), Paragraph(str(right), normal_style)]], colWidths=[page_width * 0.5, page_width * 0.5])
            row_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(row_table)
            continue

        if kind == 'image':
            image_path = opts.get('path') or (str(value) if value else '')
            width_cm = float(opts.get('width_cm', 2.5))
            if image_path:
                try:
                    target_width = width_cm * cm
                    w, h = get_logo_dimensions(image_path, target_width)
                    story.append(Image(image_path, width=w, height=h))
                except Exception:
                    story.append(Paragraph(label, normal_style))
            else:
                story.append(Paragraph(label, normal_style))
            continue

        story.append(Paragraph(f"{label}: {value}", normal_style))
