"""Append the structured CDC governance annex to the canonical generated DOCX.

The source-derived institutional document remains authoritative. This module only
adds a bounded appendix before the existing section properties and never evaluates
user expressions or external content.
"""
from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as safe_fromstring
from defusedxml.common import DefusedXmlException

from .docengine import DocumentError

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
Q = '{' + W + '}'
ET.register_namespace('w', W)

MAX_ROWS = 5000
MAX_TEXT = 2000000


def _run(text, *, bold=False, size=None, rtl=False):
    run = ET.Element(Q + 'r')
    props = ET.SubElement(run, Q + 'rPr')
    if bold:
        ET.SubElement(props, Q + 'b')
    if size:
        ET.SubElement(props, Q + 'sz', {Q + 'val': str(size)})
        ET.SubElement(props, Q + 'szCs', {Q + 'val': str(size)})
    if rtl:
        ET.SubElement(props, Q + 'rtl')
    node = ET.SubElement(run, Q + 't')
    node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    node.text = str(text)
    return run


def _paragraph(text='', *, bold=False, size=None, before=0, after=80, page_break=False, rtl=False):
    paragraph = ET.Element(Q + 'p')
    props = ET.SubElement(paragraph, Q + 'pPr')
    ET.SubElement(props, Q + 'spacing', {Q + 'before': str(before), Q + 'after': str(after)})
    if rtl:
        ET.SubElement(props, Q + 'bidi')
    if page_break:
        breaker = ET.SubElement(paragraph, Q + 'r')
        ET.SubElement(breaker, Q + 'br', {Q + 'type': 'page'})
    if text:
        paragraph.append(_run(text, bold=bold, size=size, rtl=rtl))
    return paragraph


def _append_text(body, text, *, bold=False, size=None, before=0, after=80, rtl=False):
    text = str(text or '').strip()
    if text:
        body.insert(max(0, len(body) - 1), _paragraph(
            text, bold=bold, size=size, before=before, after=after, rtl=rtl))


def append_governance_annex(payload, data, revision_number):
    requirements = list(data.get('requirements') or [])
    criteria = list(data.get('criteria') or [])
    clauses = list(data.get('clauses') or [])
    if not requirements and not criteria and not clauses:
        return payload, {'status': 'NOT_REQUIRED', 'requirements': 0, 'criteria': 0, 'clauses': 0}
    if len(requirements) + len(criteria) + len(clauses) > MAX_ROWS:
        raise DocumentError('Annexe CDC trop volumineuse.')
    serialized = repr((requirements, criteria, clauses))
    if len(serialized) > MAX_TEXT:
        raise DocumentError('Annexe CDC trop volumineuse.')

    lots = {row['id']: row for row in data.get('lot_catalog', {}).get('lots', [])}
    items = {}
    for lot in lots.values():
        for item in lot.get('items', []):
            items[item.get('key')] = (lot, item)

    source = io.BytesIO(payload)
    output = io.BytesIO()
    try:
        with zipfile.ZipFile(source, 'r') as archive:
            names = archive.namelist()
            if 'word/document.xml' not in names:
                raise DocumentError('Document Word incomplet : corps principal absent.')
            root = safe_fromstring(archive.read('word/document.xml'))
            body = root.find(Q + 'body')
            if body is None:
                raise DocumentError('Document Word incomplet : corps principal absent.')
            section = body.find(Q + 'sectPr')
            if section is None:
                raise DocumentError('Document Word incomplet : propriétés de section absentes.')

            body.insert(body.index(section), _paragraph(page_break=True))
            _append_text(body, 'ANNEXE — EXIGENCES, CRITÈRES D’ÉVALUATION ET CLAUSES INSTITUTIONNELLES',
                bold=True, size=28, after=120)
            _append_text(body, f'Référence : {data.get("reference", "")} · Révision PLAGENOR : {revision_number}',
                bold=True, size=20, after=160)

            if requirements:
                _append_text(body, '1. Exigences techniques structurées', bold=True, size=24, before=120, after=100)
                for index, row in enumerate(requirements, 1):
                    lot, item = items.get(row.get('item_key'), ({'name': 'Lot'}, {'designation': 'Article'}))
                    _append_text(body, f'{index}. {lot.get("name", "Lot")} — {item.get("designation", "Article")}',
                        bold=True, size=20, before=80, after=40)
                    _append_text(body, f'Type : {row.get("kind", "")} · Exigence : {row.get("statement", "")}', after=30)
                    if row.get('evidence'):
                        _append_text(body, 'Preuve attendue : ' + row['evidence'], after=30)
                    if row.get('verification_method'):
                        _append_text(body, 'Méthode de vérification : ' + row['verification_method'], after=30)
                    if row.get('justification'):
                        _append_text(body, 'Justification : ' + row['justification'], after=60)

            if criteria:
                _append_text(body, '2. Grille d’évaluation', bold=True, size=24, before=140, after=100)
                for index, row in enumerate(criteria, 1):
                    scope = lots.get(row.get('lot'), {}).get('name', 'Grille globale') if row.get('lot') else 'Grille globale'
                    line = (f'{index}. {row.get("code", "")} — {row.get("title", "")} · '
                            f'Périmètre : {scope} · Méthode : {row.get("method", "")} · '
                            f'Pondération : {row.get("weight", "0")} points')
                    if row.get('threshold') is not None:
                        line += f' · Seuil : {row["threshold"]}'
                    if row.get('eliminatory'):
                        line += ' · ÉLIMINATOIRE'
                    _append_text(body, line, bold=bool(row.get('eliminatory')), after=40)
                    if row.get('evidence'):
                        _append_text(body, 'Justificatif attendu : ' + row['evidence'], after=60)

            if clauses:
                _append_text(body, '3. Clauses institutionnelles versionnées', bold=True, size=24, before=140, after=100)
                for index, row in enumerate(clauses, 1):
                    status = 'obligatoire' if row.get('mandatory') else 'applicable'
                    _append_text(body,
                        f'{index}. {row.get("code", "")} — {row.get("title", "")} · R{row.get("revision", "")} · {status}',
                        bold=True, size=20, before=80, after=40)
                    _append_text(body, row.get('text_fr', ''), after=30)
                    if row.get('text_en'):
                        _append_text(body, row['text_en'], after=30)
                    if row.get('text_ar'):
                        _append_text(body, row['text_ar'], rtl=True, after=30)
                    _append_text(body, 'Source : ' + str(row.get('source', '')), after=70)

            changed = ET.tostring(root, encoding='utf-8', xml_declaration=True)
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
                for name in names:
                    target.writestr(name, changed if name == 'word/document.xml' else archive.read(name))
    except (zipfile.BadZipFile, ET.ParseError, DefusedXmlException) as exc:
        raise DocumentError('Document Word invalide pendant la génération de l’annexe CDC.') from exc

    return output.getvalue(), {'status': 'GENERATED', 'requirements': len(requirements),
        'criteria': len(criteria), 'clauses': len(clauses)}
