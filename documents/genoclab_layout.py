"""GENOCLAB commercial documents layout (quote + invoice).

Replicates the SAIDAL-style "Facture Proforma" model the platform uses
for commercial billing: GENOCELAB logo top-left, two-column header
(issuer info on the left, client info on the right), prestation table
with columns Prestation / Quantité / Prix unitaire DA / Montant DA,
HT / VAT / TTC totals, and a legal footer with the amount-in-words
line plus the registered-office block.

Every text-only element (issuer name, NIF, bank accounts, footer
legal text, …) is read from PlatformContent so the SuperAdmin can
edit it via /dashboard/home/content/update/ without touching code.
The defaults match the model file supplied by the owner.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

from docx.document import Document as DocumentType
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from documents.docx_helpers import (
    BRAND_DARK,
    BRAND_FONT,
    BRAND_MUTED,
    SIZE_BODY,
    SIZE_CAPTION,
    SIZE_H1,
    SIZE_H2,
    _GENOCLAB_LOGO,
    apply_house_style,
)


logger = logging.getLogger(__name__)
DOCUMENT_GREEN = RGBColor(0x00, 0xA6, 0x4D)
ESSBO_LOGO = Path(__file__).resolve().parent.parent / 'static' / 'images' / 'essbo_logo.png'
CONTENT_WIDTH = 17.4


# Logo colours — sampled from the GENOCLAB asset itself (see comment at
# the bottom of this module for the sampling script). Used in place of
# the PLAGENOR indigo for everything on commercial documents so the
# devis/facture visually descend from the GENOCLAB brand instead of the
# academic one.
GCL_NAVY = RGBColor(0x18, 0x30, 0x60)   # the "CLAB" + DNA helix dark blue
GCL_TEAL = RGBColor(0x18, 0xA8, 0xA8)   # the "GENO" + building turquoise
GCL_TEAL_TINT = 'D8F0F0'                # very-light teal fill for header row


# Default values for every editable string. Kept in lock-step with the
# SAIDAL Proforma model supplied by the platform owner; the SuperAdmin
# can override any of them from the CMS without code changes.
CMS_DEFAULTS = {
    'genoclab_issuer_name':       "École Supérieure en Sciences Biologiques d'Oran (ESSBO)",
    'genoclab_issuer_address1':   "BP 1042 SAIM MOHAMED,",
    'genoclab_issuer_address2':   "Cité Emir Abdelkader (EX-INESSMO)",
    'genoclab_issuer_address3':   "31000 Oran",
    'genoclab_issuer_treasury':   "Cpte Trésor : 00831001131000208471",
    'genoclab_issuer_nif':        "N.I.F : 415020000310784",
    'genoclab_issuer_ccp':        "Cpte CCP Agent comptable de l'ESSBO : 007999990000324044 14",
    'genoclab_issuer_legal_details': '',
    'genoclab_issuer_phone':      "Téléphone / Fax : +213 41 24 63 59",
    'genoclab_quote_title':       "Devis",
    'genoclab_invoice_title':     "Facture",
    'genoclab_footer_legal':      (
        "Arrêtée la présente facture à la somme de "
        "{amount_words} ({amount})."
    ),
    'genoclab_footer_office':     (
        "Siège social — BP 1042 SAIM MOHAMED, Cité Emir Abdelkader (EX-INESSMO), 31000 Oran"
    ),
    'genoclab_footer_contact':    (
        "École Supérieure en Sciences Biologiques d'Oran (ESSBO) · "
        "https://essb-oran.edu.dz/"
    ),
    'genoclab_vat_rate':          "0.19",
    'genoclab_quote_validity':     "Validité du devis : 30 jours à partir de la date d’émission.",
    'genoclab_invoice_validity':   "Validité de la facture : 30 jours à partir de la date d’émission.",
}


def cms_get(key: str, default: str = '') -> str:
    """Read an editable string from PlatformContent. Falls back to the
    CMS_DEFAULTS dict, then to the provided default."""
    try:
        from core.models import PlatformContent
        obj = PlatformContent.objects.filter(key=key, lang='fr').first()
        if obj and (obj.value or '').strip():
            return obj.value
    except Exception:
        logger.exception("Unable to load CMS value key=%s", key)
    return CMS_DEFAULTS.get(key, default)


_UNITS = ('zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept',
          'huit', 'neuf', 'dix', 'onze', 'douze', 'treize', 'quatorze',
          'quinze', 'seize', 'dix-sept', 'dix-huit', 'dix-neuf')
_TENS = ('', '', 'vingt', 'trente', 'quarante', 'cinquante', 'soixante',
         'soixante', 'quatre-vingt', 'quatre-vingt')


def _two_digits(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, units = divmod(n, 10)
    base = _TENS[tens]
    if n == 71:
        return 'soixante et onze'
    if tens in (7, 9):
        # 70-79 → soixante-dix, soixante-onze, …
        # 90-99 → quatre-vingt-dix, quatre-vingt-onze, …
        return f"{base}-{_UNITS[10 + units]}" if units else f"{base}-{_UNITS[10]}"
    if tens == 8 and units == 0:
        return 'quatre-vingts'
    if units == 1 and tens in (2, 3, 4, 5, 6):
        return f"{base} et un"
    if units == 0:
        return base
    return f"{base}-{_UNITS[units]}"


def _three_digits(n: int, *, followed_by_multiplier: bool = False) -> str:
    """Spell out a triplet; suppress plurals only before mille."""
    if n == 0:
        return ''
    if n < 100:
        words = _two_digits(n)
        return words.rstrip('s') if followed_by_multiplier and n == 80 else words
    hundreds, rest = divmod(n, 100)
    if hundreds == 1:
        head = 'cent'
    else:
        head = f"{_UNITS[hundreds]} cent"
        # Plural "s" on "cent" only when it isn't followed by another
        # number (so "deux cents" but "deux cent mille").
        if rest == 0 and not followed_by_multiplier:
            head += 's'
    if rest:
        tail = _two_digits(rest)
        if followed_by_multiplier and rest == 80:
            tail = tail.rstrip('s')
        return f"{head} {tail}"
    return head


def amount_in_words_fr(amount) -> str:
    """Spell out a DZD amount, including dinars and centimes."""
    try:
        amt = Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if not amt.is_finite() or abs(amt) >= Decimal('1000000000000'):
            return ''
    except (InvalidOperation, TypeError, ValueError):
        return ''
    negative = amt < 0
    amt = abs(amt)
    integer_part = int(amt)
    cents = int((amt - integer_part) * 100)
    remaining = integer_part
    groups = []
    for power, label in ((10**9, 'milliard'), (10**6, 'million'),
                         (10**3, 'mille'), (1, '')):
        count, remaining = divmod(remaining, power)
        if count == 0:
            continue
        if label == 'mille':
            groups.append('mille' if count == 1 else
                          f"{_three_digits(count, followed_by_multiplier=True)} mille")
        elif not label:
            groups.append(_three_digits(count))
        else:
            plural = 's' if count > 1 else ''
            groups.append(f"{_three_digits(count)} {label}{plural}")
    words = ' '.join(groups) or 'zéro'
    currency = 'dinar algérien' if integer_part < 2 else 'dinars algériens'
    if integer_part and integer_part % 10**6 == 0:
        currency = 'de ' + currency
    words += ' ' + currency
    if cents:
        unit = 'centime' if cents == 1 else 'centimes'
        words += f" et {_two_digits(cents)} {unit}"
    return ('moins ' if negative else '') + words


def _amount_notice(template, total_amount, document_kind):
    from core.exceptions import FinancialValidationError

    words = amount_in_words_fr(total_amount)
    if not words:
        raise FinancialValidationError('Montant en lettres invalide ou hors limites.')
    introduction = ('Arrêté le présent devis à la somme de' if document_kind == 'quote'
                    else 'Arrêtée la présente facture à la somme de')
    text = template or introduction + ' {amount_words} ({amount}).'
    if document_kind == 'quote':
        text = text.replace('Arrêtée la présente facture', 'Arrêté le présent devis')
    text = re.sub(r'_{5,}', '{amount_words}', text)
    text = re.sub(
        r'\{amount_words\}\s+(?:de\s+)?(?:dinars?(?:\s+alg[ée]riens?)?|DZD|DA)\b',
        '{amount_words}', text, flags=re.IGNORECASE,
    )
    if '{amount_words}' not in text:
        if '{amount}' in text:
            text = text.replace('{amount}', '{amount_words} ({amount})', 1)
        else:
            text = text.rstrip(' .:') + ' : {amount_words} ({amount}).'
    return text.replace('{amount_words}', words).replace('{amount}', _money(total_amount))


# ── End amount-to-words helpers ────────────────────────────────────────────


def _money(value, currency: str = 'DA') -> str:
    try:
        amount = Decimal(str(value or 0))
        if not amount.is_finite():
            return str(value)
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    return _money_int(amount) + ' ' + currency


def _money_int(value) -> str:
    try:
        number = Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if not number.is_finite():
            return str(value)
    except (InvalidOperation, TypeError, ValueError):
        return str(value)
    return format(number, ',.2f').replace(',', ' ').replace('.', ',')


def _set_cell_text(cell, text: str, *, bold: bool = False, size: int = SIZE_BODY,
                   color=None, align=None) -> None:
    """Replace a table cell's content with one styled run."""
    cell.text = ''  # wipe whatever was there
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.0
    if align is not None:
        p.alignment = align
    run = p.add_run(text or '')
    run.font.name = BRAND_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _shade_cell(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tcPr.append(shd)
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)


def add_genoclab_header(doc: DocumentType, *, title: str, doc_number: str,
                        doc_date: str, client_name: str = '',
                        client_lines: Optional[Iterable[str]] = None, identity=None) -> None:
    get_value = lambda key: identity['values'].get(key, '') if identity else cms_get(key)
    ohb = bool(identity and identity.get('billing_channel') == 'OHB')
    title_table = _fixed_table(doc, [10.4, 7.0])
    left, right = title_table.rows[0].cells
    _set_cell_text(left, title, bold=True, size=27, color=DOCUMENT_GREEN)
    left.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    logo = ESSBO_LOGO if ohb else _GENOCLAB_LOGO
    if logo.exists():
        from PIL import Image
        with Image.open(logo) as image:
            width = min(5.2, 2.4 * image.width / image.height)
        p = right.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.add_run().add_picture(str(logo), width=Cm(width))
    _spacer(doc, 8)
    issuer = _fixed_table(doc, [CONTENT_WIDTH]).rows[0].cells[0]
    _multi_para(issuer, [
        (get_value('genoclab_issuer_name'), {'bold': True, 'size': 11}),
        (get_value('genoclab_issuer_address1'), {'size': 10}),
        (get_value('genoclab_issuer_address2'), {'size': 10}),
        (get_value('genoclab_issuer_address3'), {'size': 10}),
        (get_value('genoclab_issuer_treasury'), {'size': 9.5}),
        (get_value('genoclab_issuer_nif'), {'size': 9.5}),
        (get_value('genoclab_issuer_ccp'), {'size': 9.5}),
        (get_value('genoclab_issuer_legal_details'), {'size': 9.5}),
        (get_value('genoclab_issuer_phone'), {'size': 9.5}),
    ])
    _spacer(doc, 10)
    details = _fixed_table(doc, [7.1, 10.3])
    date_cell, client_cell = details.rows[0].cells
    _shade_cell(date_cell, 'F2F3F3'); _shade_cell(client_cell, 'E7E9E8')
    _multi_para(date_cell, [(f'Date : {doc_date}', {'bold': True, 'size': 10}),
                           (f'N° : {doc_number}', {'bold': True, 'size': 10})])
    rows = [('Client', {'bold': True, 'size': 10})]
    if client_name:
        rows.append((client_name, {'bold': True, 'size': 10}))
    rows.extend((str(line), {'size': 9.5}) for line in (client_lines or []) if line)
    if identity and identity.get('payment_terms'):
        rows.append((identity['payment_terms'], {'size': 9.5}))
    _multi_para(client_cell, rows)
    _spacer(doc, 10)


def _multi_para(cell, items) -> None:
    cell.text = ''
    populated = False
    for text, opts in items:
        if not text:
            continue
        p = cell.add_paragraph() if populated else cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(str(text))
        run.font.name = BRAND_FONT
        run.font.size = Pt(opts.get('size', SIZE_BODY))
        run.font.bold = opts.get('bold', False)
        run.font.color.rgb = opts.get('color', BRAND_DARK)
        populated = True


def _clear_table_borders(table) -> None:
    """Remove every border from a python-docx table (used for layout
    tables that shouldn't look like data tables)."""
    for row in table.rows:
        for cell in row.cells:
            tcPr = cell._tc.get_or_add_tcPr()
            tcBorders = tcPr.find(qn('w:tcBorders'))
            if tcBorders is None:
                tcBorders = OxmlElement('w:tcBorders')
                tcPr.append(tcBorders)
            for side in ('top', 'left', 'bottom', 'right',
                         'insideH', 'insideV'):
                el = tcBorders.find(qn(f'w:{side}'))
                if el is None:
                    el = OxmlElement(f'w:{side}')
                    tcBorders.append(el)
                el.set(qn('w:val'), 'nil')


def add_prestation_table(doc: DocumentType, line_items, *, vat_rate=None, non_taxable=False):
    from core.financial import compute_invoice_totals, parse_money
    from core.exceptions import FinancialValidationError
    if vat_rate is None:
        vat_rate = 0 if non_taxable else cms_get('genoclab_vat_rate', '0.19')
    rate = parse_money(vat_rate, field='Taux de TVA')
    if non_taxable and rate != 0:
        raise FinancialValidationError('Une opération OHB ne peut pas comporter de TVA.')
    items = []
    for item in line_items:
        qty = parse_money(item.get('quantity', 0), field='Quantité')
        unit = parse_money(item.get('unit_price', 0), field='Prix unitaire')
        amount = item.get('total')
        total = parse_money(qty * unit if amount is None else amount, field='Montant de ligne')
        items.append({'label': str(item.get('label') or item.get('description') or ''),
                      'quantity': qty, 'unit_price': unit, 'total': total})
    totals = compute_invoice_totals(items, vat_rate=rate)
    table = _fixed_table(doc, [8.5, 2.4, 3.0, 3.5], rows=1 + len(items) + (1 if non_taxable else 3))
    header = table.rows[0]
    header._tr.get_or_add_trPr().append(OxmlElement('w:tblHeader'))
    for index, text in enumerate(('Prestation', 'Quantité', 'Prix unitaire DA', 'Montant DA')):
        _set_cell_text(header.cells[index], text, bold=True, size=10,
                       align=WD_ALIGN_PARAGRAPH.LEFT if index == 0 else WD_ALIGN_PARAGRAPH.RIGHT)
        _cell_border(header.cells[index], 'bottom', '222222', 6)
    for row_index, item in enumerate(items, 1):
        row = table.rows[row_index]
        _set_cell_text(row.cells[0], item['label'], size=10)
        _set_cell_text(row.cells[1], _quantity(item['quantity']), size=10, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _set_cell_text(row.cells[2], _money_int(item['unit_price']), size=10, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _set_cell_text(row.cells[3], _money_int(item['total']), size=10, align=WD_ALIGN_PARAGRAPH.RIGHT)
        for cell in row.cells:
            _cell_border(cell, 'bottom', 'D7DBD9', 3)
        if len(item['label']) < 500:
            row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
    total_rows = [('Total DA', totals['total_ttc'])] if non_taxable else [
        ('Sous-total HT', totals['subtotal_before_tax']),
        (f'TVA ({_quantity(rate * 100)} %)', totals['vat_amount']), ('Total TTC', totals['total_ttc'])]
    for offset, (label, value) in enumerate(total_rows, 1 + len(items)):
        row = table.rows[offset]
        merged = row.cells[0].merge(row.cells[2])
        big = offset == len(table.rows) - 1
        _set_cell_text(merged, label, bold=True, size=11 if big else 10,
                       color=DOCUMENT_GREEN if big else BRAND_DARK, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _set_cell_text(row.cells[3], _money_int(value), bold=True, size=11 if big else 10,
                       color=DOCUMENT_GREEN if big else BRAND_DARK, align=WD_ALIGN_PARAGRAPH.RIGHT)
        row._tr.get_or_add_trPr().append(OxmlElement('w:cantSplit'))
        if not big:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.keep_with_next = True
    return totals['total_ttc']




def add_genoclab_footer(doc: DocumentType, *, total_amount=None, identity=None, document_kind='invoice') -> None:
    get_value = lambda key: identity['values'].get(key, '') if identity else cms_get(key)
    _spacer(doc, 10)
    if identity and identity.get('billing_channel') == 'OHB':
        p = doc.add_paragraph('Non assujetti à la TVA.')
        p.paragraph_format.space_after = Pt(7)
        for run in p.runs:
            run.bold = True; run.font.size = Pt(10)
    if total_amount is not None:
        legal_text = _amount_notice(get_value('genoclab_footer_legal'), total_amount, document_kind)
    else:
        legal_text = get_value('genoclab_footer_legal')
    p = doc.add_paragraph(legal_text)
    p.paragraph_format.space_after = Pt(7)
    for run in p.runs:
        run.font.size = Pt(10)
    terms = (identity or {}).get('commercial_terms', '')
    if not terms:
        terms = cms_get('genoclab_quote_validity' if document_kind == 'quote' else 'genoclab_invoice_validity')
    if terms:
        p = doc.add_paragraph(terms)
        for run in p.runs: run.font.size = Pt(9)
    footer = doc.sections[0].footer
    paragraph = footer.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(3)
    table = footer.add_table(rows=1, cols=2, width=Cm(CONTENT_WIDTH))
    table.autofit = False
    for column, width in zip(table.columns, (7.1, 10.3)):
        column.width = Cm(width)
    for cell, width in zip(table.rows[0].cells, (7.1, 10.3)):
        cell.width = Cm(width)
    _clear_table_borders(table)
    office = get_value('genoclab_footer_office')
    if not office:
        office = '\n'.join(get_value('genoclab_issuer_address' + str(index)) for index in (1, 2, 3))
    office = office.removeprefix('Siège social — ').removeprefix('Siège social - ')
    contact = get_value('genoclab_footer_contact')
    _multi_para(table.cell(0, 0), [('Siège social', {'bold': True, 'size': 8.5}), (office, {'size': 8})])
    _multi_para(table.cell(0, 1), [('Coordonnées', {'bold': True, 'size': 8.5}), (contact, {'size': 8}),
                                 (get_value('genoclab_issuer_ccp'), {'size': 8})])
    for cell in table.rows[0].cells:
        _cell_border(cell, 'bottom', '00A64D', 18)
    pages = footer.add_paragraph()
    pages.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    pages.paragraph_format.space_before = Pt(3)
    for text in ('Page ', ' / '):
        run = pages.add_run(text); run.font.size = Pt(8)
        field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE' if text == 'Page ' else 'NUMPAGES')
        pages._p.append(field)


def _spacer(doc, size):
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.paragraph_format.line_spacing = 1
    paragraph.add_run().font.size = Pt(size)


def _fixed_table(doc, widths, rows=1):
    table = doc.add_table(rows=rows, cols=len(widths))
    table.autofit = False
    _clear_table_borders(table)
    for column, width in zip(table.columns, widths): column.width = Cm(width)
    for row in table.rows:
        for cell, width in zip(row.cells, widths): cell.width = Cm(width)
    return table


def _cell_border(cell, edge, color, size):
    properties = cell._tc.get_or_add_tcPr()
    borders = properties.find(qn('w:tcBorders'))
    if borders is None:
        borders = OxmlElement('w:tcBorders'); properties.append(borders)
    border = borders.find(qn('w:' + edge))
    if border is None:
        border = OxmlElement('w:' + edge); borders.append(border)
    for key, value in (('val', 'single'), ('sz', str(size)), ('color', color)):
        border.set(qn('w:' + key), value)


def _quantity(value):
    text = format(Decimal(str(value)), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def render_commercial_document(*, title, number, date, identity, items, vat_rate, document_kind):
    from docx import Document
    doc = Document()
    apply_house_style(doc)
    section = doc.sections[0]
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(3.2)
    section.footer_distance = Cm(0.7)
    doc.core_properties.title = title + ' ' + number
    add_genoclab_header(doc, title=title, doc_number=number, doc_date=date,
                        client_name=identity.get('client_name', ''), client_lines=identity.get('client_lines', []), identity=identity)
    grand_total = add_prestation_table(doc, items, vat_rate=vat_rate,
                                      non_taxable=identity.get('billing_channel') == 'OHB')
    add_genoclab_footer(doc, total_amount=grand_total, identity=identity, document_kind=document_kind)
    return doc
