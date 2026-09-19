"""Unified commercial document layout for OHB and GENOCLAB.

The generator preserves the complete administrative and financial information
from the source models while presenting it through the shared PLAGENOR 4.0
institutional document system. Textual issuer/footer values remain editable
through PlatformContent.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Optional

from docx.document import Document as DocumentType
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

from documents.document_design import (
    GENOCLAB_THEME, OHB_THEME, add_document_footer, add_document_title,
    add_identity_header, add_section_heading, apply_document_style,
    set_cant_split, set_cell_border, set_cell_fill,
    style_data_table, style_key_value_table,
)

logger = logging.getLogger(__name__)
DOCUMENT_GREEN = RGBColor(0x00, 0xA6, 0x4D)
ESSBO_LOGO = Path(__file__).resolve().parent.parent / 'static' / 'images' / 'essbo_logo.png'
CONTENT_WIDTH = 17.4
_GENOCLAB_LOGO = GENOCLAB_THEME.logo


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






def add_genoclab_header(doc: DocumentType, *, title: str, doc_number: str,
                        doc_date: str, client_name: str = '',
                        client_lines: Optional[Iterable[str]] = None, identity=None) -> None:

    identity = identity or {}
    values = identity.get('values', {})
    get_value = lambda key: values[key] if key in values else cms_get(key)
    ohb = identity.get('billing_channel') == 'OHB'
    theme = OHB_THEME if ohb else GENOCLAB_THEME
    add_identity_header(doc, theme, compact=True)
    subtitle = 'Opération Hors Budget — non assujettie à la TVA' if ohb else 'GENOCLAB — prestation soumise à la TVA'
    add_document_title(doc, title, subtitle=subtitle, code=doc_number, theme=theme)

    add_section_heading(doc, 'Émetteur', theme=theme, level=2)
    issuer = doc.add_table(rows=0, cols=2)
    issuer_rows = [
        ('Organisme', get_value('genoclab_issuer_name')),
        ('Adresse', ' · '.join(filter(None, (get_value('genoclab_issuer_address1'), get_value('genoclab_issuer_address2'), get_value('genoclab_issuer_address3'))))),
        ('Cpte Trésor', get_value('genoclab_issuer_treasury').removeprefix('Cpte Trésor :').strip()),
        ('N.I.F', get_value('genoclab_issuer_nif').removeprefix('N.I.F :').strip()),
        ('Cpte CCP Agent comptable', get_value('genoclab_issuer_ccp').split(':', 1)[-1].strip()),
        ('Téléphone / Fax', get_value('genoclab_issuer_phone').split(':', 1)[-1].strip()),
    ]
    if get_value('genoclab_issuer_legal_details'):
        issuer_rows.append(('Informations administratives', get_value('genoclab_issuer_legal_details')))
    for label, value in issuer_rows:
        cells = issuer.add_row().cells
        cells[0].text, cells[1].text = label, value
    style_key_value_table(issuer, theme=theme, dense=True)

    add_section_heading(doc, 'Document et client', theme=theme, level=2)
    details = doc.add_table(rows=0, cols=2)
    client_rows = [
        ('Date', doc_date), ('N°', doc_number),
        ('Référence demande', identity.get('request_reference', '')),
        ('Client', client_name or identity.get('client_name', '')),
        ('Organisation', identity.get('client_organization', '')),
        ('Laboratoire', identity.get('client_laboratory', '')),
        ('Tél :', identity.get('client_phone', '')),
        ('Fax :', identity.get('client_fax', '')),
        ('Email :', identity.get('client_email', '')),
    ]
    known = {
        str(value).strip() for value in (
            identity.get('client_organization', ''),
            identity.get('client_laboratory', ''),
            identity.get('client_phone', ''),
            identity.get('client_fax', ''),
            identity.get('client_email', ''),
        ) if value
    }
    extras = [
        str(value).strip() for value in (client_lines or [])
        if value and str(value).strip() not in known
    ]
    if extras:
        client_rows.append(('Informations complémentaires', '\n'.join(extras)))
    for label, value in client_rows:
        cells = details.add_row().cells
        cells[0].text, cells[1].text = label, str(value or '—')
    style_key_value_table(details, theme=theme, dense=True)







def add_prestation_table(doc: DocumentType, line_items, *, vat_rate=None, non_taxable=False):
    from core.financial import compute_invoice_totals, parse_money
    from core.exceptions import FinancialValidationError
    theme = OHB_THEME if non_taxable else GENOCLAB_THEME
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
    add_section_heading(doc, 'Prestations', theme=theme, level=2)
    table = doc.add_table(rows=1, cols=4)
    for cell, label in zip(table.rows[0].cells, ('Prestation', 'Quantité', 'Prix unitaire DA', 'Montant DA')):
        cell.text = label
    for item in items:
        cells = table.add_row().cells
        cells[0].text = item['label']
        cells[1].text = _quantity(item['quantity'])
        cells[2].text = _money_int(item['unit_price'])
        cells[3].text = _money_int(item['total'])
    style_data_table(table, theme=theme, dense=True, numeric_cols=(1,2,3))
    summary_rows = [('Total DA', totals['total_ttc'])] if non_taxable else [
        ('Sous-total HT', totals['subtotal_before_tax']),
        (f"TVA ({_quantity(rate*100)} %)", totals['vat_amount']),
        ('Total TTC', totals['total_ttc'])]
    summary = doc.add_table(rows=0, cols=2)
    for label, value in summary_rows:
        cells = summary.add_row().cells
        cells[0].text, cells[1].text = label, _money_int(value)
        set_cant_split(summary.rows[-1])
    style_key_value_table(summary, theme=theme, dense=True)
    for cell in summary.rows[-1].cells:
        set_cell_fill(cell, theme.soft)
        set_cell_border(cell, top=(theme.accent,12), bottom=(theme.accent,12))
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold=True
                r.font.color.rgb=RGBColor.from_string(theme.accent)
    summary.rows[-1].cells[1].paragraphs[0].alignment=WD_ALIGN_PARAGRAPH.RIGHT
    return totals['total_ttc']




def add_genoclab_footer(doc: DocumentType, *, total_amount=None, identity=None, document_kind='invoice') -> None:
    identity = identity or {}
    values = identity.get('values', {})
    get_value = lambda key: values[key] if key in values else cms_get(key)
    ohb = identity.get('billing_channel') == 'OHB'
    theme = OHB_THEME if ohb else GENOCLAB_THEME
    if ohb:
        p=doc.add_paragraph()
        run=p.add_run('Non assujetti à la TVA.')
        run.bold=True
        run.font.color.rgb=RGBColor.from_string(theme.accent)
    legal_text = _amount_notice(get_value('genoclab_footer_legal'), total_amount, document_kind) if total_amount is not None else get_value('genoclab_footer_legal')
    add_section_heading(doc, 'Montant arrêté et conditions', theme=theme, level=2)
    p=doc.add_paragraph(legal_text)
    p.paragraph_format.space_after=Pt(5)
    payment_terms = identity.get('payment_terms', '')
    if payment_terms:
        p = doc.add_paragraph()
        r = p.add_run('Conditions de paiement : ')
        r.bold = True
        p.add_run(payment_terms)
    terms = identity.get('commercial_terms','') or cms_get(
        'genoclab_quote_validity' if document_kind=='quote' else 'genoclab_invoice_validity'
    )
    if terms:
        doc.add_paragraph(terms)
    contact=doc.add_table(rows=4,cols=2)
    office=get_value('genoclab_footer_office').removeprefix('Siège social — ').removeprefix('Siège social - ')
    values=[
        ('Siège social',office),
        ('Coordonnées',get_value('genoclab_footer_contact')),
        ('Cpte CCP Agent comptable',get_value('genoclab_issuer_ccp').split(':',1)[-1].strip()),
        ('Téléphone / Fax',get_value('genoclab_issuer_phone').split(':',1)[-1].strip()),
    ]
    for row,(label,value) in zip(contact.rows,values):
        row.cells[0].text,row.cells[1].text=label,value
    style_key_value_table(contact,theme=theme,dense=True)
    add_document_footer(doc,theme=theme,reference=identity.get('request_reference',''))








def _quantity(value):
    text = format(Decimal(str(value)), 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def render_commercial_document(*, title, number, date, identity, items, vat_rate, document_kind):
    from docx import Document
    doc=Document()
    theme=OHB_THEME if identity.get('billing_channel')=='OHB' else GENOCLAB_THEME
    apply_document_style(doc,theme,dense=True)
    doc.sections[0].bottom_margin=Cm(1.8)
    doc.core_properties.title=title+' '+number
    add_genoclab_header(doc,title=title,doc_number=number,doc_date=date,
                        client_name=identity.get('client_name',''),
                        client_lines=identity.get('client_lines',[]),identity=identity)
    grand_total=add_prestation_table(doc,items,vat_rate=vat_rate,
                                     non_taxable=identity.get('billing_channel')=='OHB')
    add_genoclab_footer(doc,total_amount=grand_total,identity=identity,document_kind=document_kind)
    return doc
