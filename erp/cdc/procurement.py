"""Source-bound equipment articles, shared by CPTC, BPU and DQE.

The scope of this profile is the two original equipment lots. It never rewrites
fixed clauses, lot declarations, price blanks, table geometry or media. A raw
paragraph edit and an article edit cannot target the same managed table.
"""
from __future__ import annotations

import copy
import functools
import io
import re
import uuid
import zipfile
from decimal import Decimal, InvalidOperation

from .docengine import (Document, DocumentError, NS, apply_byte_edits,
                        edit_text_nodes, guarded_paragraph, own_text_nodes,
                        parse_xml, sha, xml_text)

EQUIPMENT_TABLES = (
    (1, 'Équipements et appareillages scientifiques de laboratoire',
     {'cptc': (6, '9dcea3a84ff4'), 'bpu': (26, 'f134aecb5416'), 'dqe': (28, '5989b2ede9ba')}, 8),
    (2, 'Paillasses de laboratoire',
     {'cptc': (7, '51c10865d1be'), 'bpu': (27, '450998cd2e82'), 'dqe': (29, '6aeaff38e5f0')}, 15),
)
ITEM_KEYS = {'key', 'designation', 'specifications', 'unit', 'quantity'}


def quantity(value: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,10}(?:[.,]\d{1,6})?', value):
        raise DocumentError('Quantité invalide : nombre positif, au plus six décimales.')
    try:
        number = Decimal(value.replace(',', '.'))
    except InvalidOperation as exc:
        raise DocumentError('Quantité invalide.') from exc
    if not Decimal('0') < number <= Decimal('1000000000'):
        raise DocumentError('La quantité doit être supérieure à zéro et ne pas dépasser un milliard.')
    return number


def children(node, name):
    return [n for n in node.children if n.name == NS + name]


def cell_paragraphs(cell):
    return [n for n in cell.descendants(NS + 'p') if n.ancestor(NS + 'tc') is cell]


def paragraph_value(p):
    # Breaks are visible in the editor; a field with complex structure is read-only.
    values = []
    for node in p.descendants():
        if node.ancestor(NS + 'p') is not p:
            continue
        if node.name == NS + 't':
            values.append(node.characters)
        elif node.name in (NS + 'br', NS + 'cr'):
            values.append('\n')
        elif node.name == NS + 'tab':
            values.append('\t')
    return ''.join(values)


def field_value(paragraphs):
    return '\n'.join(paragraph_value(p) for p in paragraphs).strip()


def editable(paragraphs):
    return all(not guarded_paragraph(p) and not any(
        n.name in (NS+'drawing', NS+'object', NS+'bookmarkStart', NS+'bookmarkEnd')
        for n in p.descendants()) for p in paragraphs)


@functools.lru_cache(maxsize=1)
def mapping():
    from .catalog import document
    doc = document('equipment')
    result = []
    for number, label, bindings, count in EQUIPMENT_TABLES:
        tables = {}
        for kind, (index, digest) in bindings.items():
            tid = f'word/document.xml:t{index}:{digest}'
            if tid not in doc.tables:
                raise DocumentError('Le profil des articles ne correspond plus au modèle équipements.')
            _, table = doc.tables[tid]
            rows = children(table, 'tr')
            if len(rows) != count + (4 if kind == 'dqe' else 1):
                raise DocumentError('Nombre de lignes du modèle équipements inattendu.')
            tables[kind] = {'id': tid, 'node': table, 'rows': rows}
        items = []
        for ri in range(1, count + 1):
            cptc = children(tables['cptc']['rows'][ri], 'tc')
            bpu = children(tables['bpu']['rows'][ri], 'tc')
            dqe = children(tables['dqe']['rows'][ri], 'tc')
            if (len(cptc), len(bpu), len(dqe)) != (3, 4, 5):
                raise DocumentError('Structure d’article non reconnue.')
            # BPU price-in-words prompt must stay the final non-empty paragraph.
            bp = cell_paragraphs(bpu[1])
            labels = [i for i, p in enumerate(bp) if 'Prix unitaire en lettres' in paragraph_value(p)]
            if len(labels) != 1 or any(paragraph_value(p).strip() for p in bp[labels[0]+1:]):
                raise DocumentError('Ancrage du prix réservé au soumissionnaire non reconnu.')
            if field_value(cell_paragraphs(bpu[3])) or field_value(cell_paragraphs(dqe[2])) or field_value(cell_paragraphs(dqe[4])):
                raise DocumentError('Le modèle contient un prix : duplication publique refusée.')
            dqp = cell_paragraphs(dqe[1])
            entry = {
                'key': f'source-{number}-{ri}',
                'designation': field_value(cell_paragraphs(cptc[1])),
                'specifications': field_value(cell_paragraphs(cptc[2])),
                'unit': field_value(cell_paragraphs(bpu[2])),
                'quantity': field_value(cell_paragraphs(dqe[3])),
            }
            quantity(entry['quantity'])
            fields = {
                'cptc': {'designation': cell_paragraphs(cptc[1]),
                         'specifications': cell_paragraphs(cptc[2])},
                'bpu': {'designation': bp[:1], 'unit': cell_paragraphs(bpu[2])},
                'dqe': {'designation': dqp[:1], 'quantity': cell_paragraphs(dqe[3])},
            }
            if number == 2:
                fields['bpu']['specifications'] = bp[1:labels[0]]
                fields['dqe']['specifications'] = dqp[1:]
            elif labels[0] != 1:
                raise DocumentError('Désignation BPU équipements non reconnue.')
            items.append({'data': entry, 'row': ri, 'fields': fields})
        result.append({'number': number, 'label': label, 'tables': tables,
                       'count': count, 'items': items})
    return result


def initial_procurement():
    return {'schema': 1, 'lots': [
        {'number': lot['number'], 'items': [copy.deepcopy(i['data']) for i in lot['items']]}
        for lot in mapping()]}


def managed_paragraphs():
    from .catalog import document
    doc = document('equipment')
    return {doc.paragraph_id('word/document.xml', p)
            for lot in mapping() for table in lot['tables'].values()
            for p in table['node'].descendants(NS+'p')}


def _text(value, label, limit, multiline=False):
    xml_text(value)
    if not value.strip() or len(value) > limit:
        raise DocumentError(f'{label} : renseignez entre 1 et {limit} caractères.')
    if '\r' in value or '\t' in value or (not multiline and '\n' in value):
        raise DocumentError(f'{label} : caractères de séparation non autorisés.')
    if re.search(r'\{\{|\}\}|\[\[(?:IF|ENDIF):', value):
        raise DocumentError(f'{label} : marqueur de gabarit non autorisé.')


def validate_procurement(data, family):
    value = data.get('procurement')
    if value is None:
        return
    if family != 'equipment':
        raise DocumentError('Le profil d’articles structuré n’est pas qualifié pour cette famille.')
    if not isinstance(value, dict) or set(value) != {'schema', 'lots'} or type(value['schema']) is not int or value['schema'] != 1:
        raise DocumentError('Format des articles invalide.')
    if not isinstance(value['lots'], list) or len(value['lots']) != 2:
        raise DocumentError('Ce profil conserve les deux lots du modèle équipements.')
    total, seen = 0, set()
    for lot_data, source in zip(value['lots'], mapping()):
        if not isinstance(lot_data, dict) or set(lot_data) != {'number', 'items'} or type(lot_data['number']) is not int or lot_data['number'] != source['number']:
            raise DocumentError('Lot inconnu ou déplacé.')
        items = lot_data['items']
        if not isinstance(items, list) or not 1 <= len(items) <= 1000:
            raise DocumentError('Chaque lot doit contenir entre 1 et 1 000 articles.')
        total += len(items)
        baseline = {i['data']['key']: i for i in source['items']}
        for item in items:
            if not isinstance(item, dict) or set(item) != ITEM_KEYS:
                raise DocumentError('Article incomplet ou propriété non reconnue ; les prix sont réservés aux soumissionnaires.')
            key = item['key']
            if not isinstance(key, str) or key in seen:
                raise DocumentError('Identifiant d’article dupliqué ou invalide.')
            seen.add(key)
            if key not in baseline:
                try:
                    if not key.startswith('new-') or str(uuid.UUID(key[4:])) != key[4:]:
                        raise ValueError
                except (ValueError, AttributeError) as exc:
                    raise DocumentError('L’article ne correspond pas à ce lot.') from exc
            _text(item['designation'], 'Désignation', 600, multiline=True)
            _text(item['specifications'], 'Caractéristiques', 30000, multiline=True)
            _text(item['unit'], 'Unité', 100)
            quantity(item['quantity'])
            old = baseline.get(key)
            if old:
                for field, val in item.items():
                    if field == 'key' or val == old['data'][field]:
                        continue
                    if field == 'quantity' and quantity(val) == quantity(old['data'][field]):
                        continue
                    for fields in old['fields'].values():
                        if field in fields and not editable(fields[field]):
                            label = {'designation': 'désignation', 'specifications': 'caractéristiques', 'unit': 'unité', 'quantity': 'quantité'}[field]
                            raise DocumentError(f'{item["designation"][:60]} : champ « {label} » protégé ; modification refusée.')
    if total > 1000:
        raise DocumentError('Le dossier ne peut pas dépasser 1 000 articles.')
    if set(data.get('paragraphs', {})) & managed_paragraphs():
        raise DocumentError('Un paragraphe de CPTC/BPU/DQE est aussi modifié manuellement. Annulez ce conflit avant la saisie structurée.')
    tids = {t['id'] for l in mapping() for t in l['tables'].values()}
    if set(data.get('rows', {})) & tids:
        raise DocumentError('Un tableau d’articles contient aussi des lignes manuelles. Annulez ce conflit avant la saisie structurée.')


def _fresh_identity(fragment, seed):
    fragment = re.sub(rb'<w:bookmark(?:Start|End)\b[^>]*/>', b'', fragment)
    serial = 0
    def new_id(match):
        nonlocal serial
        serial += 1
        return match[1] + sha(f'{seed}:{serial}'.encode())[:8].upper().encode() + b'"'
    return re.sub(rb'((?:w14:paraId|w14:textId)=")[^"]+"', new_id, fragment)


def _paragraph_fragment(raw, p, value):
    if guarded_paragraph(p):
        raise DocumentError('Un champ Word complexe ne peut pas être réécrit automatiquement.')
    nodes = own_text_nodes(p)
    fragment = raw[p.start:p.end]
    if nodes:
        changes = [(a-p.start, b-p.start, v) for a,b,v in edit_text_nodes(nodes, value, raw)]
        return apply_byte_edits(fragment, changes)
    if not value:
        return fragment
    from xml.sax.saxutils import escape
    if fragment.endswith(b'/>'):
        raise DocumentError('Le modèle de paragraphe vide ne possède pas d’ancrage sûr.')
    run = b'<w:r><w:t xml:space="preserve">' + escape(value).encode() + b'</w:t></w:r>'
    return fragment[:p.closing_start-p.start] + run + fragment[p.closing_start-p.start:]


def _field_patches(raw, paragraphs, value, seed):
    if not paragraphs or not editable(paragraphs):
        raise DocumentError('Ce champ comporte une structure Word qui nécessite une qualification complémentaire.')
    lines = value.split('\n')
    patches = []
    # Reuse existing paragraphs and their properties. Only surplus user-entered
    # lines clone a safe last paragraph; surplus owned paragraphs are removed.
    # Their safety is established by editable(): no fields, bookmarks or drawings.
    for index, p in enumerate(paragraphs):
        replacement = _paragraph_fragment(raw, p, lines[index]) if index < len(lines) else b''
        if index == len(paragraphs)-1 and len(lines) > len(paragraphs):
            for j, extra in enumerate(lines[len(paragraphs):]):
                replacement += _fresh_identity(_paragraph_fragment(raw, p, extra), f'{seed}:extra:{j}')
        patches.append((p.start, p.end, replacement))
    return patches


def _renumber(raw, cell, value):
    from .schedule_adapter import number_patch
    return number_patch(raw, cell, value)


def _deleted_bookmark_guard(doc, row):
    starts = {n.attrs.get(NS+'id') for n in row.descendants(NS+'bookmarkStart')}
    ends = {n.attrs.get(NS+'id') for n in row.descendants(NS+'bookmarkEnd')}
    if starts != ends:
        raise DocumentError('Cet article porte un signet qui traverse sa limite ; suppression refusée.')
    for node in row.descendants(NS+'bookmarkStart'):
        name = node.attrs.get(NS+'name', '')
        if not name:
            continue
        for _, root in doc.parts.values():
            for candidate in root.descendants():
                if candidate.name == NS+'hyperlink' and candidate.attrs.get(NS+'anchor') == name:
                    raise DocumentError('Cet article est visé par un renvoi Word ; suppression refusée.')
                if candidate.name == NS+'instrText' and name in candidate.characters:
                    raise DocumentError('Cet article est visé par un champ Word ; suppression refusée.')


def apply_procurement(payload: bytes, data: dict):
    value = data.get('procurement')
    if value is None:
        return payload, {'status': 'NOT_REQUESTED'}
    validate_procurement(data, data['family'])
    from .catalog import document
    doc = document('equipment')
    if value == initial_procurement():
        return payload, {'status': 'UNCHANGED', 'tables': []}
    current = Document(payload)
    raw = doc.parts['word/document.xml'][0]
    current_raw = current.parts['word/document.xml'][0]
    replacements, affected = [], []
    for lot_data, source in zip(value['lots'], mapping()):
        lookup = {i['data']['key']: i for i in source['items']}
        original_order = list(lookup)
        target_order = [i['key'] for i in lot_data['items']]
        reordered = original_order != target_order
        for kind, table in source['tables'].items():
            old_table = table['node']
            # Reference replacement outside these tables can shift byte offsets.
            candidates = [n for part,n in current.tables.values()
                          if part == 'word/document.xml' and n.index == old_table.index]
            if len(candidates) != 1:
                raise DocumentError('Tableau géré non retrouvé dans la copie.')
            target = candidates[0]
            if current_raw[target.start:target.end] != raw[old_table.start:old_table.end]:
                raise DocumentError('Conflit de modification sur un tableau d’articles.')
            changed = reordered
            fragments = []
            for sequence, item in enumerate(lot_data['items'], 1):
                original = lookup.get(item['key'])
                is_new = original is None
                original = original or source['items'][0]
                row = table['rows'][original['row']]
                changes = []
                for field, paragraphs in original['fields'][kind].items():
                    same = item[field] == original['data'][field]
                    if field == 'quantity':
                        same = quantity(item[field]) == quantity(original['data'][field])
                    if same and not is_new:
                        continue
                    new_text = item[field]
                    if field == 'quantity':
                        new_text = format(quantity(new_text), 'f').replace('.', ',')
                    changes.extend(_field_patches(raw, paragraphs, new_text, f'{item["key"]}:{kind}:{field}'))
                if reordered:
                    number_cell = children(row, 'tc')[0]
                    width = 2 if (kind == 'bpu' or source['number'] == 2) else 1
                    changes.append(_renumber(raw, number_cell, str(sequence).zfill(width)))
                fragment = apply_byte_edits(raw[row.start:row.end],
                                            [(a-row.start,b-row.start,v) for a,b,v in changes])
                if is_new:
                    if any(n.name in (NS+'drawing', NS+'object', NS+'vMerge', NS+'fldChar', NS+'sectPr') for n in row.descendants()):
                        raise DocumentError('Ligne source non duplicable de façon sûre.')
                    fragment = _fresh_identity(fragment, f'{item["key"]}:{kind}')
                if changes or is_new:
                    changed = True
                fragments.append(fragment)
            if changed:
                for removed in set(original_order) - set(target_order):
                    _deleted_bookmark_guard(doc, table['rows'][lookup[removed]['row']])
                first = table['rows'][1]
                last = table['rows'][source['count']]
                new_table = raw[old_table.start:first.start] + b''.join(fragments) + raw[last.end:old_table.end]
                replacements.append((target.start, target.end, new_table))
                affected.append({'lot': source['number'], 'piece': kind.upper(),
                                 'source_items': source['count'], 'output_items': len(fragments),
                                 'table_source': table['id']})
    if not replacements:
        return payload, {'status': 'UNCHANGED', 'tables': []}
    changed_raw = apply_byte_edits(current_raw, replacements)
    root = parse_xml(changed_raw)
    # New paragraphs must not duplicate Word identity attributes. Existing source
    # duplicates (if any) are not silently fixed by this engine.
    attr = 'http://schemas.microsoft.com/office/word/2010/wordml|paraId'
    baseline_ids = [n.attrs[attr] for n in current.parts['word/document.xml'][1].descendants() if attr in n.attrs]
    output_ids = [n.attrs[attr] for n in root.descendants() if attr in n.attrs]
    from collections import Counter
    before, after = Counter(baseline_ids), Counter(output_ids)
    if any(count > max(1, before.get(key, 0)) for key,count in after.items()):
        raise DocumentError('Un identifiant Word a été dupliqué ; génération annulée.')
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as out:
        out.comment = current.z.comment
        for info in current.z.infolist():
            out.writestr(copy.copy(info), changed_raw if info.filename == 'word/document.xml' else current.z.read(info.filename))
    output = result.getvalue()
    return output, {'status': 'GENERATED', 'tables': affected,
                    'scope': 'Articles des deux lots équipements ; CPTC, BPU et DQE.',
                    'bidder_prices': 'PRESERVED_EMPTY', 'lot_annexes': 'RETAINED_UNCHANGED'}


def editor_lots(data):
    """Presentation model; no mutation of a revision or the cached source mapping."""
    value = data.get('procurement') or initial_procurement()
    result = []
    for target, source in zip(value['lots'], mapping()):
        originals = {i['data']['key']: i for i in source['items']}
        items = []
        for item in target['items']:
            old = originals.get(item['key'])
            frozen = set()
            if old:
                for fields in old['fields'].values():
                    frozen.update(f for f,ps in fields.items() if not editable(ps))
            items.append({**item, 'locked_designation': 'designation' in frozen,
                          'locked_specifications': 'specifications' in frozen})
        result.append({'number': target['number'], 'label': source['label'], 'items': items})
    return result
