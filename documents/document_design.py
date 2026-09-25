"""Unified visual system for generated PLAGENOR, ESSBO and GENOCLAB documents."""
from __future__ import annotations
from dataclasses import dataclass
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx.document import Document as DocumentType
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ASSETS = Path(__file__).resolve().parent / "assets"
STATIC_IMAGES = Path(__file__).resolve().parent.parent / "static" / "images"
IBTIKAR_SERVICE_BADGE = ASSETS / "ibtikar_service_badge.png"
IBTIKAR_SECTION_GENERAL = ASSETS / "ibtikar_section_general.png"
IBTIKAR_SECTION_USER = ASSETS / "ibtikar_section_user.png"
IBTIKAR_FONT = "DejaVu Serif"
IBTIKAR_CONTENT_INDENT_CM = 0.75
IBTIKAR_CONTENT_WIDTH_CM = 17.80


@dataclass(frozen=True)
class DocumentTheme:
    key: str
    primary: str
    accent: str
    dark: str
    muted: str
    soft: str
    line: str
    logo: Path | None
    organisation: str
    platform: str


PLAGENOR_THEME = DocumentTheme(
    "plagenor", "24364B", "4F46E5", "172033", "64748B", "F4F6FA", "D9E0E8",
    ASSETS / "institutional_banner.png",
    "École Supérieure en Sciences Biologiques d’Oran (ESSBO)",
    "PLAGENOR — Plateforme Technologique en Génomique",
)
OHB_THEME = DocumentTheme(
    "ohb", "24364B", "2E7D64", "172033", "64748B", "F3F7F5", "D9E0E8",
    STATIC_IMAGES / "essbo_logo.png",
    "École Supérieure en Sciences Biologiques d’Oran (ESSBO)",
    "Opération Hors Budget (OHB)",
)
GENOCLAB_THEME = DocumentTheme(
    "genoclab", "183060", "178C88", "172033", "64748B", "F0F8F7", "D7E5E3",
    ASSETS / "genoclab_logo.png",
    "GENOCLAB",
    "Prestations scientifiques et technologiques",
)


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color.lstrip("#").upper())


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is None:
        flag = OxmlElement("w:tblHeader")
        flag.set(qn("w:val"), "true")
        tr_pr.append(flag)


def set_cant_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def set_cell_fill(cell, color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)


def set_cell_margins(cell, top=90, start=105, bottom=90, end=105) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    old = tc_pr.find(qn("w:tcMar"))
    if old is not None:
        tc_pr.remove(old)
    margins = OxmlElement("w:tcMar")
    for name, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = OxmlElement(f"w:{name}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        margins.append(node)
    tc_pr.append(margins)


def set_cell_border(cell, *, top=None, bottom=None, start=None, end=None, inside=None) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    values = {"top": top, "bottom": bottom, "start": start, "end": end}
    for name, spec in values.items():
        if spec is None:
            continue
        node = borders.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            borders.append(node)
        color, size = spec
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:color"), color)


def _font(run, *, size=10.5, bold=False, color="172033", name="Arial"):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = rgb(color)
    rpr = run._r.get_or_add_rPr()
    fonts = rpr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{key}"), name)


def _paragraph_text(paragraph, value, *, size=10.5, bold=False, color="172033",
                    align=None, before=0, after=0, name="Arial"):
    paragraph.text = ""
    run = paragraph.add_run(str(value or ""))
    _font(run, size=size, bold=bold, color=color, name=name)
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.05
    return paragraph


def _pil_font(size: int, *, bold=False):
    filename = "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path(r"C:\Windows\Fonts") / filename,
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python311"
        / "Lib" / "site-packages" / "matplotlib" / "mpl-data" / "fonts" / "ttf" / filename,
        Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312"
        / "Lib" / "site-packages" / "matplotlib" / "mpl-data" / "fonts" / "ttf" / filename,
    ]
    candidates.extend([
        Path(r"C:\Windows\Fonts\georgiab.ttf" if bold else r"C:\Windows\Fonts\georgia.ttf"),
        Path(r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf" if bold
             else "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
    ])
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()  # pragma: no cover - last-resort platform fallback


def _paste_contain(canvas, source_path: Path, box):
    source = Image.open(source_path).convert("RGBA")
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    source.thumbnail((width, height), Image.Resampling.LANCZOS)
    x = left + (width - source.width) // 2
    y = top + (height - source.height) // 2
    canvas.alpha_composite(source, (x, y))


def _render_ibtikar_master_header(form_title, service_label, service_title, service_code):
    """Render the first-page IBTIKAR identity/title block as one stable image."""
    width, height = 1800, 420
    image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    navy = "#123F75"
    blue = "#1462B4"
    pale = "#F1F5FA"
    line = "#C9D9E9"

    # Pale DNA watermark at the right edge, matching the supplied master.
    dna = Image.new("RGBA", (190, height), (255, 255, 255, 0))
    dd = ImageDraw.Draw(dna)
    points_a, points_b = [], []
    import math
    for yy in range(-20, height + 20, 4):
        phase = yy / 55.0
        points_a.append((92 + int(46 * math.sin(phase)), yy))
        points_b.append((92 - int(46 * math.sin(phase)), yy))
    dd.line(points_a, fill=(191, 211, 232, 55), width=12)
    dd.line(points_b, fill=(191, 211, 232, 55), width=12)
    for yy in range(15, height, 36):
        phase = yy / 55.0
        xa = 92 + int(46 * math.sin(phase))
        xb = 92 - int(46 * math.sin(phase))
        dd.line((xa, yy, xb, yy), fill=(191, 211, 232, 42), width=7)
    image.alpha_composite(dna, (1610, 0))

    _paste_contain(image, STATIC_IMAGES / "essbo_logo.png", (55, 12, 260, 190))
    draw.multiline_text(
        (157, 181), "École Supérieure en Sciences\nBiologiques d’Oran",
        font=_pil_font(20), fill=navy, anchor="ma", align="center", spacing=1,
    )

    cx = 900
    center_lines = [
        ("People’s Democratic Republic of Algeria", 24, False),
        ("Ministry of Higher Education and Scientific Research", 23, False),
        ("Higher School of Biological Sciences of Oran", 24, True),
        ("Genomics Technology Platform", 24, True),
    ]
    y = 18
    for value, size, bold in center_lines:
        draw.text((cx, y), value, font=_pil_font(size, bold=bold),
                  fill="#0E1420", anchor="ma")
        y += 32
    draw.line((635, 144, 1165, 144), fill=line, width=2)
    draw.text((cx, 167), "RESEARCH     |     INNOVATION     |     IMPACT",
              font=_pil_font(18), fill=navy, anchor="ma")

    _paste_contain(image, STATIC_IMAGES / "plagenor_logo.png", (1440, 6, 1735, 185))
    draw.text((1588, 190), service_code, font=_pil_font(27, bold=True),
              fill=blue, anchor="ma")

    draw.line((35, 228, 1765, 228), fill="#E0E8F0", width=2)
    draw.text((50, 286), form_title, font=_pil_font(48, bold=True),
              fill="#0B335E", anchor="lm")
    draw.line((865, 248, 865, 365), fill=navy, width=4)

    badge = Image.open(IBTIKAR_SERVICE_BADGE).convert("RGBA")
    badge.thumbnail((118, 118), Image.Resampling.LANCZOS)
    image.alpha_composite(badge, (892, 245))

    draw.rounded_rectangle((1020, 245, 1695, 362), radius=55, fill=pale)
    draw.text((1055, 266), service_label, font=_pil_font(24, bold=True),
              fill=navy, anchor="la")
    # Service names are allowed to use up to two lines while preserving the master geometry.
    service_font = _pil_font(40, bold=True)
    max_width = 605
    while draw.textbbox((0, 0), service_title, font=service_font)[2] > max_width and getattr(service_font, "size", 28) > 28:
        service_font = _pil_font(service_font.size - 1, bold=True)
    draw.text((1055, 313), service_title, font=service_font, fill=blue, anchor="lm")
    draw.line((35, 385, 1765, 385), fill=blue, width=2)

    stream = io.BytesIO()
    image.convert("RGB").save(stream, format="PNG", optimize=True)
    stream.seek(0)
    return stream


def add_ibtikar_master_header(
    doc: DocumentType, *, form_title, service_label, service_title, service_code,
) -> None:
    """Exact IBTIKAR master identity block used on page one."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run()
    run.add_picture(
        _render_ibtikar_master_header(form_title, service_label, service_title, service_code),
        width=Cm(19.15),
    )
    description = f"{form_title} - {service_label}: {service_title} - {service_code}"
    for doc_pr in run._r.xpath('.//wp:docPr'):
        doc_pr.set('title', form_title)
        doc_pr.set('descr', description)


def add_invisible_header_drawing(doc: DocumentType) -> None:
    """Keep the generated-document header drawing contract without a visible duplicate."""
    stream = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 255, 255, 0)).save(stream, format="PNG")
    stream.seek(0)
    header = doc.sections[0].header
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.add_run().add_picture(stream, width=Cm(0.01))


def add_ibtikar_section_heading(
    doc: DocumentType, title: str, *, icon="general", theme=PLAGENOR_THEME,
):
    """IBTIKAR section strip matching the supplied master design."""
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.columns[0].width = Cm(1.12)
    table.columns[1].width = Cm(17.78)
    icon_cell, title_cell = table.rows[0].cells
    icon_cell.width, title_cell.width = Cm(1.12), Cm(17.78)
    for cell in (icon_cell, title_cell):
        set_cell_fill(cell, "F6F9FC")
        set_cell_margins(cell, top=80, bottom=65, start=70, end=70)
        set_cell_border(cell, bottom=(theme.line, 3))
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = icon_cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    asset = IBTIKAR_SECTION_USER if icon == "user" else IBTIKAR_SECTION_GENERAL
    p.add_run().add_picture(str(asset), width=Cm(0.78))
    p = title_cell.paragraphs[0]
    _paragraph_text(p, title, size=13.0, bold=True, color="123F75")
    for run in p.runs:
        _font(run, size=13.0, bold=True, color="123F75", name=IBTIKAR_FONT)
    ppr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), "8FB7DA")
    borders.append(bottom)
    ppr.append(borders)
    return table


def add_ibtikar_subheading(doc: DocumentType, title: str, *, theme=PLAGENOR_THEME):
    """Compact DejaVu Serif subheading on the same axis as IBTIKAR content tables."""
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.left_indent = Cm(0)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(title)
    _font(run, size=11.0, bold=True, color=theme.dark, name=IBTIKAR_FONT)
    return p


def style_ibtikar_key_value_table(table, *, dense=False) -> None:
    for row in table.rows:
        set_cant_split(row)
        for col, cell in enumerate(row.cells):
            set_cell_margins(cell, top=65 if dense else 85, bottom=65 if dense else 85,
                             start=105, end=105)
            set_cell_border(cell, bottom=("C9D9E9", 3), start=("D7E3EE", 2), end=("D7E3EE", 2))
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if col == 0:
                set_cell_fill(cell, "EDF3F8")
            else:
                set_cell_fill(cell, "FFFFFF")
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for run in p.runs:
                    _font(run, size=9.0 if dense else 9.5, bold=(col == 0),
                          color="173A63" if col == 0 else "172033",
                          name=IBTIKAR_FONT)


def align_ibtikar_content_table(table, widths_cm=None) -> None:
    """Apply one deterministic content axis to every IBTIKAR body table."""
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_pr = table._tbl.tblPr
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "0")
    tbl_ind.set(qn("w:type"), "dxa")
    tbl_width = tbl_pr.find(qn("w:tblW"))
    preferred_width = sum(widths_cm) if widths_cm else IBTIKAR_CONTENT_WIDTH_CM
    tbl_width.set(qn("w:type"), "dxa")
    tbl_width.set(qn("w:w"), str(Cm(preferred_width).twips))
    if widths_cm:
        for column, width in zip(table.columns, widths_cm):
            column.width = Cm(width)
        for row in table.rows:
            for cell, width in zip(row.cells, widths_cm):
                cell.width = Cm(width)


def add_ibtikar_signature_grid(doc: DocumentType, labels, *, theme=PLAGENOR_THEME) -> None:
    """Signature/visa grid aligned exactly with IBTIKAR body tables."""
    table = doc.add_table(rows=1, cols=len(labels))
    widths = [IBTIKAR_CONTENT_WIDTH_CM / max(len(labels), 1)] * max(len(labels), 1)
    align_ibtikar_content_table(table, widths)
    row = table.rows[0]
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    row.height = Cm(2.45)
    for i, label in enumerate(labels):
        cell = row.cells[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
        set_cell_fill(cell, "FAFBFC")
        set_cell_border(cell, top=(theme.line, 3), bottom=(theme.line, 3),
                        start=(theme.line, 3), end=(theme.line, 3))
        set_cell_margins(cell, top=100, bottom=120, start=90, end=90)
        _paragraph_text(cell.paragraphs[0], label, size=8.5, bold=True, color=theme.primary)
        for run in cell.paragraphs[0].runs:
            _font(run, size=8.5, bold=True, color=theme.primary, name=IBTIKAR_FONT)


def apply_document_style(doc: DocumentType, theme: DocumentTheme = PLAGENOR_THEME, *, dense=False) -> None:
    for section in doc.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(1.35 if dense else 1.6)
        section.bottom_margin = Cm(1.45 if dense else 1.75)
        section.left_margin = Cm(1.6 if dense else 1.7)
        section.right_margin = Cm(1.6 if dense else 1.7)
        section.header_distance = Cm(0.5 if dense else 0.6)
        section.footer_distance = Cm(0.5 if dense else 0.6)
    normal = doc.styles["Normal"]
    normal.font.name = "Arial"
    normal.font.size = Pt(9.8 if dense else 10.5)
    normal.font.color.rgb = rgb(theme.dark)
    normal.paragraph_format.line_spacing = 1.08 if dense else 1.12
    normal.paragraph_format.space_after = Pt(3 if dense else 4)
    rpr = normal.element.get_or_add_rPr()
    fonts = rpr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{key}"), "Arial")
    heading_metrics = (
        ("Title", 20, theme.primary, 0, 5 if dense else 6),
        ("Heading 1", 13.5, theme.primary, 7 if dense else 11, 3 if dense else 4),
        ("Heading 2", 11.5, theme.dark, 5 if dense else 7, 2 if dense else 3),
        ("Heading 3", 10.5, theme.muted, 4 if dense else 5, 1 if dense else 2),
    )
    for name, size, color, before, after in heading_metrics:
        style = doc.styles[name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = rgb(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
    cp = doc.core_properties
    cp.author = "ESSBO — PLAGENOR"
    cp.subject = theme.organisation
    cp.keywords = "ESSBO, PLAGENOR, IBTIKAR, GENOCLAB"


def add_identity_header(doc: DocumentType, theme: DocumentTheme, *, compact=False) -> None:
    section = doc.sections[0]
    header = section.header
    header_text = ' '.join(paragraph.text for paragraph in header.paragraphs)
    has_drawing = any(run.element.findall(qn('w:drawing')) for paragraph in header.paragraphs for run in paragraph.runs)
    if theme.platform in header_text or (theme.key == 'plagenor' and has_drawing):
        return
    paragraph = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    paragraph.text = ""
    if theme.key == "plagenor" and theme.logo and theme.logo.exists():
        run = paragraph.add_run()
        try:
            run.add_picture(str(theme.logo), width=Cm(16.9))
        except Exception:
            _paragraph_text(paragraph, theme.organisation, size=8.5, bold=True, color=theme.primary)
    else:
        table = header.add_table(rows=1, cols=2, width=Cm(17.6))
        table.autofit = False
        left, right = table.rows[0].cells
        left.width, right.width = Cm(11.6), Cm(6.0)
        _paragraph_text(left.paragraphs[0], theme.organisation, size=8.6, bold=True, color=theme.primary)
        p = left.add_paragraph()
        _paragraph_text(p, theme.platform, size=7.7, color=theme.muted)
        if theme.logo and theme.logo.exists():
            p = right.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            try:
                p.add_run().add_picture(str(theme.logo), width=Cm(3.2 if compact else 4.0))
            except Exception:
                _paragraph_text(p, theme.key.upper(), size=10, bold=True, color=theme.accent,
                                align=WD_ALIGN_PARAGRAPH.RIGHT)
        for cell in (left, right):
            set_cell_border(cell, bottom=(theme.accent, 12))
            set_cell_margins(cell, top=30, bottom=70, start=0, end=0)


def add_document_title(doc: DocumentType, title: str, *, subtitle="", code="", theme=PLAGENOR_THEME) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    left, right = table.rows[0].cells
    left.width, right.width = Cm(13.5), Cm(3.9)
    _paragraph_text(left.paragraphs[0], title, size=18, bold=True, color=theme.primary)
    if subtitle:
        _paragraph_text(left.add_paragraph(), subtitle, size=9.2, color=theme.muted, after=0)
    if code:
        _paragraph_text(right.paragraphs[0], code, size=9.5, bold=True, color=theme.accent,
                        align=WD_ALIGN_PARAGRAPH.RIGHT)
    for cell in (left, right):
        set_cell_border(cell, bottom=(theme.accent, 14))
        set_cell_margins(cell, top=50, bottom=80, start=0, end=0)


def add_section_heading(doc: DocumentType, title: str, *, theme=PLAGENOR_THEME, level=1,
                        font_name="Arial"):
    p = doc.add_paragraph(style=f"Heading {min(max(level,1),3)}")
    p.paragraph_format.keep_with_next = True
    r = p.add_run(title)
    _font(r, size=13 if level == 1 else 11.2, bold=True,
          color=theme.primary if level == 1 else theme.dark, name=font_name)
    if level == 1:
        ppr = p._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "10")
        bottom.set(qn("w:space"), "2")
        bottom.set(qn("w:color"), theme.accent)
        borders.append(bottom)
        ppr.append(borders)
    return p


def style_key_value_table(table, *, theme=PLAGENOR_THEME, label_width=None, dense=False) -> None:
    for idx, row in enumerate(table.rows):
        set_cant_split(row)
        for col, cell in enumerate(row.cells):
            set_cell_margins(cell, top=65 if dense else 85, bottom=65 if dense else 85)
            set_cell_border(cell, bottom=(theme.line, 3))
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if col == 0:
                set_cell_fill(cell, theme.soft)
            for p in cell.paragraphs:
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for run in p.runs:
                    _font(run, size=9.2 if dense else 9.8, bold=(col == 0),
                          color=theme.primary if col == 0 else theme.dark)


def style_data_table(table, *, theme=PLAGENOR_THEME, dense=False, numeric_cols=(),
                     font_name="Arial") -> None:
    if not table.rows:
        return
    set_repeat_table_header(table.rows[0])
    for ri, row in enumerate(table.rows):
        set_cant_split(row)
        for ci, cell in enumerate(row.cells):
            set_cell_margins(cell, top=50 if dense else 70, bottom=50 if dense else 70,
                             start=70, end=70)
            set_cell_border(cell, bottom=(theme.line, 3))
            if ri == 0:
                set_cell_fill(cell, theme.primary)
            elif ri % 2 == 0:
                set_cell_fill(cell, "FAFBFC")
            for p in cell.paragraphs:
                if ci in numeric_cols:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                p.paragraph_format.space_after = Pt(0)
                p.paragraph_format.line_spacing = 1.0
                for run in p.runs:
                    _font(run, size=8.7 if dense else 9.2, bold=(ri == 0),
                          color="FFFFFF" if ri == 0 else theme.dark, name=font_name)


def add_callout(doc: DocumentType, text: str, *, title="", theme=PLAGENOR_THEME, kind="info",
                font_name="Arial"):
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    fill = theme.soft if kind != "warning" else "FFF8E8"
    accent = theme.accent if kind != "warning" else "B7791F"
    set_cell_fill(cell, fill)
    set_cell_border(cell, start=(accent, 18), top=(theme.line, 2),
                    bottom=(theme.line, 2), end=(theme.line, 2))
    set_cell_margins(cell, top=100, bottom=100, start=150, end=130)
    cell.text = ""
    if title:
        p = cell.paragraphs[0]
        _paragraph_text(p, title, size=9.5, bold=True, color=accent, after=2, name=font_name)
        p = cell.add_paragraph()
    else:
        p = cell.paragraphs[0]
    _paragraph_text(p, text, size=9.2, color=theme.dark, name=font_name)
    return table


def add_signature_grid(doc: DocumentType, labels, *, theme=PLAGENOR_THEME, min_height=1.65) -> None:
    table = doc.add_table(rows=1, cols=len(labels))
    table.autofit = False
    width = 17.4 / max(len(labels), 1)
    for i, label in enumerate(labels):
        cell = table.rows[0].cells[i]
        cell.width = Cm(width)
        set_cell_fill(cell, "FAFBFC")
        set_cell_border(cell, top=(theme.line, 3), bottom=(theme.line, 3),
                        start=(theme.line, 3), end=(theme.line, 3))
        set_cell_margins(cell, top=100, bottom=220, start=90, end=90)
        _paragraph_text(cell.paragraphs[0], label, size=8.8, bold=True, color=theme.primary)
        p = cell.add_paragraph(" ")
        p.paragraph_format.space_after = Pt(18 * min_height)


def add_document_footer(doc: DocumentType, *, theme=PLAGENOR_THEME, reference="",
                        font_name="Arial") -> None:
    for section in doc.sections:
        footer = section.footer
        for child in list(footer._element):
            footer._element.remove(child)
        table = footer.add_table(rows=1, cols=2, width=Cm(17.4))
        table.autofit = False
        left, right = table.rows[0].cells
        left.width, right.width = Cm(12.5), Cm(4.9)
        for cell in (left, right):
            set_cell_margins(cell, top=70, bottom=20, start=0, end=0)
            set_cell_border(cell, top=(theme.accent, 8))
        p = left.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(theme.platform)
        _font(run, size=7.5, color=theme.muted, name=font_name)
        if reference:
            run = p.add_run(f"  ·  {reference}")
            _font(run, size=7.5, color=theme.muted, name=font_name)
        p = right.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(0)
        label = p.add_run("Page ")
        _font(label, size=7.5, color=theme.muted, name=font_name)
        _add_field(p, "PAGE", theme, font_name=font_name)
        sep = p.add_run(" / ")
        _font(sep, size=7.5, color=theme.muted, name=font_name)
        _add_field(p, "NUMPAGES", theme, font_name=font_name)

def _add_field(paragraph, code, theme, *, font_name="Arial"):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), code)
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), theme.muted)
    rpr.append(color)
    fonts = OxmlElement("w:rFonts")
    for key in ("ascii", "hAnsi", "cs", "eastAsia"):
        fonts.set(qn(f"w:{key}"), font_name)
    rpr.append(fonts)
    r.append(rpr)
    text = OxmlElement("w:t")
    text.text = "1"
    r.append(text)
    field.append(r)
    paragraph._p.append(field)
