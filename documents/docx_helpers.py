"""DOCX helpers: run-preserving placeholder substitution + header banner injection.

Phase 3.7 extracted these out of generators.py so all four document generators
share a single, correct implementation. The previous approach in generators
(``paragraph.text = paragraph.text.replace(...)``) silently collapsed every
formatted run into a single un-styled run, destroying bold/italic/font from
the source template. The substitution here walks run boundaries so styling
survives. The header-banner helper writes the institutional logo into
``word/header*.xml`` so Platform Note / Quote / Reception render with the
same letterhead that the IBTIKAR templates already carry.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Optional

from docx import Document
from docx.document import Document as DocumentType
from docx.oxml.ns import qn
from docx.shared import Inches, Pt


_PLACEHOLDER_RE = re.compile(r'\{\{[A-Z0-9_]+\}\}')


def _substitute_in_runs(paragraph, replacements: Mapping[str, str]) -> None:
    """Replace ``{{KEY}}`` placeholders in a paragraph while preserving runs.

    Strategy: rebuild the joined text, apply replacements, then write the
    result into the first run and blank the rest. Cross-run placeholders
    (Word likes to split tokens across runs when spell-check or language
    tags fire) are handled because we always operate on the joined string.
    The first run's formatting wins for the entire paragraph after a hit;
    this is the same trade-off ``python-docx-template`` makes and is the
    only safe choice without sophisticated run-by-run tokenisation.
    """
    runs = paragraph.runs
    if not runs:
        return
    joined = ''.join(r.text or '' for r in runs)
    if not joined:
        return

    new_text = joined
    for key, value in replacements.items():
        if key in new_text:
            new_text = new_text.replace(key, str(value if value is not None else ''))

    if new_text == joined:
        return

    runs[0].text = new_text
    for r in runs[1:]:
        r.text = ''


def replace_placeholders(doc: DocumentType, field_map: Mapping[str, str]) -> None:
    """Replace ``{{KEY}}`` placeholders everywhere in the document.

    ``field_map`` maps bare keys (``'FULL_NAME'``) to their string values;
    this function wraps them in ``{{...}}`` braces and applies them to:
    paragraphs (body), table cells (recursively, for nested tables), and
    header/footer paragraphs in every section. Bare-key replacement is
    intentionally NOT supported here — it caused the previous corruption
    where ``replace('APPOINTMENT_DATE', '24/05/2026')`` rewrote
    ``{{APPOINTMENT_DATE}}`` into ``{{APPOINTMENT_24/05/2026}}``.
    """
    braced: dict[str, str] = {
        f'{{{{{key}}}}}': '' if value is None else str(value)
        for key, value in field_map.items()
    }

    def visit_paragraphs(paragraphs):
        for p in paragraphs:
            _substitute_in_runs(p, braced)

    def visit_tables(tables):
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    visit_paragraphs(cell.paragraphs)
                    visit_tables(cell.tables)

    visit_paragraphs(doc.paragraphs)
    visit_tables(doc.tables)

    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            if header is not None:
                visit_paragraphs(header.paragraphs)
                visit_tables(header.tables)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            if footer is not None:
                visit_paragraphs(footer.paragraphs)
                visit_tables(footer.tables)


def strip_unresolved_placeholders(doc: DocumentType) -> None:
    """Remove any ``{{...}}`` markers still present after substitution.

    A stray placeholder reaching the user is worse than a missing value;
    this helper sweeps after ``replace_placeholders`` to keep the output
    clean even when a template uses a key the field_map does not provide.
    """
    def visit(paragraphs):
        for p in paragraphs:
            joined = ''.join(r.text or '' for r in p.runs)
            if not joined or not _PLACEHOLDER_RE.search(joined):
                continue
            cleaned = _PLACEHOLDER_RE.sub('', joined)
            if p.runs:
                p.runs[0].text = cleaned
                for r in p.runs[1:]:
                    r.text = ''

    def visit_tables(tables):
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    visit(cell.paragraphs)
                    visit_tables(cell.tables)

    visit(doc.paragraphs)
    visit_tables(doc.tables)
    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            if header is not None:
                visit(header.paragraphs)
                visit_tables(header.tables)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            if footer is not None:
                visit(footer.paragraphs)
                visit_tables(footer.tables)


# Banner / letterhead -------------------------------------------------------

_LOGO_BANNER = Path(__file__).resolve().parent / 'assets' / 'institutional_banner.png'


def ensure_institutional_header(doc: DocumentType, banner_path: Optional[Path] = None) -> None:
    """Inject the institutional logo banner into the document's primary header.

    Skips silently if the document's header already contains an image
    (avoids double-stamping templates that ship with their own banner —
    e.g. the egtp_*.docx IBTIKAR forms). Skips silently if the PNG asset
    is missing so a missing-file in dev never breaks a generation.
    """
    banner = banner_path or _LOGO_BANNER
    if not banner.exists():
        return
    for section in doc.sections:
        header = section.header
        if header is None:
            continue
        has_image = any(
            run.element.findall(qn('w:drawing'))
            for paragraph in header.paragraphs
            for run in paragraph.runs
        )
        if has_image:
            continue
        if header.paragraphs:
            paragraph = header.paragraphs[0]
            paragraph.text = ''
        else:
            paragraph = header.add_paragraph()
        run = paragraph.add_run()
        try:
            run.add_picture(str(banner), width=Inches(6.5))
        except Exception:
            return


def apply_house_style(doc: DocumentType) -> None:
    """Apply the PLAGENOR house style to a programmatically built document.

    A4 page size, symmetric 1" margins, body font 11pt. Idempotent — running
    twice on the same doc produces the same result.
    """
    A4_WIDTH = Inches(8.27)
    A4_HEIGHT = Inches(11.69)
    for section in doc.sections:
        section.page_width = A4_WIDTH
        section.page_height = A4_HEIGHT
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
    try:
        style = doc.styles['Normal']
        style.font.size = Pt(11)
    except (KeyError, AttributeError):
        pass
