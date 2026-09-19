"""Unified visual system for generated PLAGENOR, ESSBO and GENOCLAB documents."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from docx.document import Document as DocumentType
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ASSETS = Path(__file__).resolve().parent / "assets"
STATIC_IMAGES = Path(__file__).resolve().parent.parent / "static" / "images"


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
                    align=None, before=0, after=0):
    paragraph.text = ""
    run = paragraph.add_run(str(value or ""))
    _font(run, size=size, bold=bold, color=color)
    if align is not None:
        paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(before)
    paragraph.paragraph_format.space_after = Pt(after)
    paragraph.paragraph_format.line_spacing = 1.05
    return paragraph


def apply_document_style(doc: DocumentType, theme: DocumentTheme = PLAGENOR_THEME, *, dense=False) -> None:
    for section in doc.sections:
        section.page_width = Cm(21)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(1.6)
        section.bottom_margin = Cm(1.75)
        section.left_margin = Cm(1.7)
        section.right_margin = Cm(1.7)
        section.header_distance = Cm(0.6)
        section.footer_distance = Cm(0.6)
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
    for name, size, color, before, after in (
        ("Title", 20, theme.primary, 0, 6),
        ("Heading 1", 13.5, theme.primary, 11, 4),
        ("Heading 2", 11.5, theme.dark, 7, 3),
        ("Heading 3", 10.5, theme.muted, 5, 2),
    ):
        try:
            style = doc.styles[name]
        except KeyError:
            continue
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


def add_section_heading(doc: DocumentType, title: str, *, theme=PLAGENOR_THEME, level=1):
    p = doc.add_paragraph(style=f"Heading {min(max(level,1),3)}")
    p.paragraph_format.keep_with_next = True
    r = p.add_run(title)
    _font(r, size=13 if level == 1 else 11.2, bold=True,
          color=theme.primary if level == 1 else theme.dark)
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


def style_data_table(table, *, theme=PLAGENOR_THEME, dense=False, numeric_cols=()) -> None:
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
                          color="FFFFFF" if ri == 0 else theme.dark)


def add_callout(doc: DocumentType, text: str, *, title="", theme=PLAGENOR_THEME, kind="info") -> None:
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
        _paragraph_text(p, title, size=9.5, bold=True, color=accent, after=2)
        p = cell.add_paragraph()
    else:
        p = cell.paragraphs[0]
    _paragraph_text(p, text, size=9.2, color=theme.dark)


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


def add_document_footer(doc: DocumentType, *, theme=PLAGENOR_THEME, reference="") -> None:
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
        _font(run, size=7.5, color=theme.muted)
        if reference:
            run = p.add_run(f"  ·  {reference}")
            _font(run, size=7.5, color=theme.muted)
        p = right.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_after = Pt(0)
        label = p.add_run("Page ")
        _font(label, size=7.5, color=theme.muted)
        _add_field(p, "PAGE", theme)
        sep = p.add_run(" / ")
        _font(sep, size=7.5, color=theme.muted)
        _add_field(p, "NUMPAGES", theme)

def _add_field(paragraph, code, theme):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), code)
    r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), theme.muted)
    rpr.append(color)
    r.append(rpr)
    text = OxmlElement("w:t")
    text.text = "1"
    r.append(text)
    field.append(r)
    paragraph._p.append(field)
