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

# Re-exports for callers: positional insertion primitives live in this
# module so the generators only need a single import statement. See
# ``add_paragraph_after`` / ``_find_anchor_for_position`` further down.


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


# Positional paragraph insertion -------------------------------------------

# Anchor matching: case-insensitive, whitespace-collapsed substring match
# against the visible text of a heading-shaped paragraph. A paragraph counts
# as "heading-shaped" when its style is Heading[N], OR its leading text
# matches "<digit>." (the egtp_*.docx IBTIKAR templates use plain-text
# numbered titles like "1. Informations du demandeur" instead of Heading
# styles), OR one of its runs has font size >= 14pt and is bold.
_NUMBERED_HEADING_RE = re.compile(r'^\s*\d+[.)]\s')

_ANCHOR_KEYWORDS = {
    'AFTER_REQUESTER': (
        'demandeur', 'déposant', 'client', 'requester', 'requérant',
        'المُقدم', 'الطالب', 'العميل',
    ),
    'AFTER_SAMPLES': (
        'échantillon', 'samples', 'sample', 'tableau des échantillons',
        'العينات', 'عينة',
    ),
}


def _is_heading_shaped(paragraph) -> bool:
    style_name = (getattr(getattr(paragraph, 'style', None), 'name', '') or '').strip()
    if style_name.startswith('Heading') or style_name in ('Title', 'Subtitle'):
        return True
    text = (paragraph.text or '').strip()
    if not text:
        return False
    if _NUMBERED_HEADING_RE.match(text):
        return True
    for run in paragraph.runs:
        if not run.bold:
            continue
        size = run.font.size
        if size is not None and size.pt is not None and size.pt >= 14:
            return True
    return False


def _is_section_heading(paragraph) -> bool:
    """A section-level heading: Heading 2+ or a numbered list-style title.

    Excludes Heading 1 / Title (the document banner) so an AFTER_SAMPLES
    anchor doesn't latch onto a title like
    "Fiche de Réception d'Échantillons".
    """
    if not _is_heading_shaped(paragraph):
        return False
    style_name = (getattr(getattr(paragraph, 'style', None), 'name', '') or '').strip()
    if style_name in ('Heading 1', 'Title'):
        return False
    return True


def _matches_anchor(paragraph, keywords) -> bool:
    if not _is_section_heading(paragraph):
        return False
    text = (paragraph.text or '').lower()
    return any(kw.lower() in text for kw in keywords)


def _find_section_end(doc: DocumentType, anchor_heading) -> Optional[object]:
    """Return the paragraph that starts the NEXT section, or None at end.

    Used to compute "after the X section" positions: the block is inserted
    immediately before the next section-level heading that follows
    ``anchor_heading``. If no such next section exists the section runs to
    end-of-document and the caller falls back to appending.

    Compares via the underlying ``_element`` (XML node identity) rather
    than Python ``is`` because ``doc.paragraphs`` constructs fresh
    ``Paragraph`` wrappers on every access — two wrappers around the
    same XML element are never the same object.
    """
    anchor_elem = anchor_heading._element
    seen = False
    for p in doc.paragraphs:
        if not seen:
            if p._element is anchor_elem:
                seen = True
            continue
        if _is_section_heading(p):
            return p
    return None


def _find_anchor_for_position(doc: DocumentType, position: str):
    """Resolve a position label to an insertion anchor.

    Returns a tuple ``(reference_paragraph, where)`` where ``where`` is
    ``'before'``, ``'after'``, or ``'end'``. The caller uses ``where`` to
    decide whether to ``addprevious``, ``addnext`` or append a new paragraph.
    Falls back to ``(None, 'end')`` when a semantic anchor can't be found.
    """
    paragraphs = list(doc.paragraphs)
    if not paragraphs:
        return None, 'end'

    if position == 'TOP':
        # First heading-shaped paragraph (e.g. the H1 title). Insert AFTER
        # it so the block lands under the title but above the first section.
        for p in paragraphs:
            if _is_heading_shaped(p):
                return p, 'after'
        # Pathological — no headings at all. Drop the block at the start.
        return paragraphs[0], 'before'

    if position == 'BOTTOM':
        return None, 'end'

    if position == 'BEFORE_FOOTER':
        # The "Document généré automatiquement par PLAGENOR 4.0 …" line is
        # the very last non-empty paragraph in the body. Insert above it.
        for p in reversed(paragraphs):
            if (p.text or '').strip():
                return p, 'before'
        return None, 'end'

    if position in _ANCHOR_KEYWORDS:
        keywords = _ANCHOR_KEYWORDS[position]
        for p in paragraphs:
            if _matches_anchor(p, keywords):
                next_heading = _find_section_end(doc, p)
                if next_heading is not None:
                    return next_heading, 'before'
                return None, 'end'
        return None, 'end'

    return None, 'end'


def add_paragraph_after(reference_paragraph, text: str = '', *, bold: bool = False,
                        font_size_pt: Optional[float] = None) -> object:
    """Insert a new paragraph immediately after ``reference_paragraph``.

    python-docx doesn't expose a public API for mid-body insertion, so we
    manipulate the underlying OOXML element directly. Returns a
    :class:`docx.text.paragraph.Paragraph` wrapping the new element so the
    caller can add runs / set style.
    """
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    new_p = OxmlElement('w:p')
    reference_paragraph._element.addnext(new_p)
    paragraph = Paragraph(new_p, reference_paragraph._parent)
    if text:
        run = paragraph.add_run(text)
        if bold:
            run.bold = True
        if font_size_pt is not None:
            run.font.size = Pt(font_size_pt)
    return paragraph


def add_paragraph_before(reference_paragraph, text: str = '', *, bold: bool = False,
                         font_size_pt: Optional[float] = None) -> object:
    """Insert a new paragraph immediately before ``reference_paragraph``."""
    from docx.oxml import OxmlElement
    from docx.text.paragraph import Paragraph

    new_p = OxmlElement('w:p')
    reference_paragraph._element.addprevious(new_p)
    paragraph = Paragraph(new_p, reference_paragraph._parent)
    if text:
        run = paragraph.add_run(text)
        if bold:
            run.bold = True
        if font_size_pt is not None:
            run.font.size = Pt(font_size_pt)
    return paragraph


# Legacy IBTIKAR forms — label-text substitution ---------------------------

# The egtp_*.docx templates ship as blank printable forms: each profile
# field is encoded as a French label followed by ``: *`` and (optionally) a
# Microsoft Word "instructional text" hint such as ``Nom complet du
# demandeur``. They contain no ``{{KEY}}`` markers, so the standard
# substitution pass leaves them empty. This map injects the actual values
# inline while preserving the original label text and asterisk.
#
# Pattern semantics:
# * The regex matches the FULL "Label : *  hint" line including any trailing
#   instructional text — Word inserts a non-breaking space (``\xa0``) and
#   sometimes a tab between ``*`` and the hint.
# * The replacement format keeps the label and asterisk so the form still
#   reads as an official fillable form (the value sits in the hint slot).
# * If the field is empty (e.g. a guest submission with no laboratory),
#   the original hint is preserved so the line still makes sense.

_LEGACY_LABEL_RULES = [
    # (regex, field_map_key, label_template)
    # 1. Personal info section
    (re.compile(r'Nom et prénom\s*:\s*\*[^\n]*', re.IGNORECASE),
     'FULL_NAME', 'Nom et prénom : * {value}'),
    (re.compile(r'(?:Université\s*/\s*École|Établissement)\s*:\s*\*[^\n]*', re.IGNORECASE),
     'ETABLISSEMENT', 'Université / École : * {value}'),
    (re.compile(r'Laboratoire\s*:\s*\*?[^\n]*', re.IGNORECASE),
     'LABORATORY', 'Laboratoire : {value}'),
    (re.compile(r'Fonction\s*/\s*Poste\s*:\s*\*[^\n]*', re.IGNORECASE),
     'STUDENT_LEVEL', 'Fonction / Poste : * {value}'),
    (re.compile(r'Adresse\s+e-?mail\s*:\s*\*[^\n]*', re.IGNORECASE),
     'EMAIL', 'Adresse e-mail : * {value}'),
    (re.compile(r'Numéro de téléphone(?:\s+du\s+demandeur)?\s*:\s*\*[^\n]*', re.IGNORECASE),
     'PHONE', 'Numéro de téléphone : * {value}'),
    # Optional DGRSDT identifier (only inserted if the requester filled it)
    (re.compile(r'(?:Identifiant\s+IBTIKAR|ID(?:GRSDT)?)\s*:\s*\*?[^\n]*', re.IGNORECASE),
     'IBTIKAR_ID', 'Identifiant IBTIKAR : {value}'),
    # 2. Request details
    (re.compile(r'Titre du projet\s*:\s*\*[^\n]*', re.IGNORECASE),
     'TITLE', 'Titre du projet : * {value}'),
    (re.compile(r'Directeur de recherche\s*:\s*\*[^\n]*', re.IGNORECASE),
     'SUPERVISOR', 'Directeur de recherche : * {value}'),
]

# Plain string substitutions for the request-number header and date stamps
# that aren't in label form.
_LEGACY_TEXT_RULES = [
    # (find_pattern, replacement using field_map keys)
    (re.compile(r'……\.+/(\d{4})/IBTIKAR/PLAGENOR/ESSBO'),
     r'{DISPLAY_ID}/\1/IBTIKAR/PLAGENOR/ESSBO'),
]


def apply_legacy_label_substitution(doc: DocumentType, field_map: Mapping[str, str]) -> None:
    """Fill the literal-label fields in legacy egtp_*.docx IBTIKAR forms.

    Idempotent. Skips fields whose value is empty/N/A so we never overwrite
    a meaningful hint with an empty string (the requester or operator can
    still complete those by hand). Only applied when the active template
    is one of the egtp_*.docx forms — the generic and programmatic paths
    use ``{{KEY}}`` substitution instead and don't need this layer.
    """

    def _substitute(paragraph) -> None:
        joined = ''.join(r.text or '' for r in paragraph.runs)
        if not joined:
            return
        original = joined

        # Apply label-based rules (replace the whole label line).
        for pattern, key, template in _LEGACY_LABEL_RULES:
            value = field_map.get(key, '')
            if not value or value in ('N/A', 'Non défini', 'Non assigné'):
                continue
            joined = pattern.sub(template.format(value=value), joined)

        # Apply free-text rules (request number etc.).
        for pattern, template in _LEGACY_TEXT_RULES:
            try:
                joined = pattern.sub(template.format(**field_map), joined)
            except (KeyError, IndexError):
                pass

        if joined == original:
            return
        if paragraph.runs:
            paragraph.runs[0].text = joined
            for r in paragraph.runs[1:]:
                r.text = ''

    def _visit(paragraphs):
        for p in paragraphs:
            _substitute(p)

    def _visit_tables(tables):
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    _visit(cell.paragraphs)
                    _visit_tables(cell.tables)

    _visit(doc.paragraphs)
    _visit_tables(doc.tables)
    for section in doc.sections:
        for header in (section.header, section.first_page_header, section.even_page_header):
            if header is not None:
                _visit(header.paragraphs)
                _visit_tables(header.tables)
        for footer in (section.footer, section.first_page_footer, section.even_page_footer):
            if footer is not None:
                _visit(footer.paragraphs)
                _visit_tables(footer.tables)
