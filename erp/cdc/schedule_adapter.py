"""Source-bound CPTC/BPU/DQE rows; untouched OOXML bytes stay unchanged."""
from __future__ import annotations
import copy
import functools
import io
import re
import zipfile
from collections import Counter
from .docengine import Document, DocumentError, NS, apply_byte_edits, edit_text_nodes, own_text_nodes, parse_xml, sha
from .procurement import (mapping, children, cell_paragraphs, field_value, editable, quantity,
                          _field_patches, _paragraph_fragment, _fresh_identity, _deleted_bookmark_guard)

REAGENTS = (
    (1, (6, '0624d786a962'), (32, 'ba731fef9124'), (36, 'd3e1347cc96d'), 15),
    (2, (7, '829e4107454a'), (33, '87d46667153e'), (37, '90e65257e0cb'), 57),
    (3, (8, '1ec08cbf52c5'), (34, '4886f75727e0'), (38, 'efe5b9722a48'), 38),
    (4, (9, '2df0cbb0b6ae'), (35, 'ff830e89d190'), (39, '709c03d6424e'), 74),
)


def works_mapping():
    from .catalog import document
    doc=document('works');ids={'bpu':'word/document.xml:t16:d9558d28d34a','dqe':'word/document.xml:t17:d08e9d0a0d94'};tables={}
    for kind,tid in ids.items():
        if tid not in doc.tables:raise DocumentError('Le modèle travaux ne correspond plus à ses ancrages BPU/DQE.')
        _,node=doc.tables[tid];tables[kind]={'id':tid,'node':node,'rows':children(node,'tr')}
    def price_rows(kind):
        out=[]
        for ri,row in enumerate(tables[kind]['rows']):
            c=children(row,'tc');v=[field_value(cell_paragraphs(x)).strip() for x in c]
            if kind=='bpu' and len(c)>=6 and v[2] and v[3] and not v[4] and not v[5] and ri!=128:out.append((ri,c))
            if kind=='dqe' and len(c)>=7 and v[2] and v[3] and v[4] and not v[5] and not v[6]:out.append((ri,c))
        return out
    bpu,dqe=price_rows('bpu'),price_rows('dqe')
    if len(bpu)!=249 or len(dqe)!=249:raise DocumentError('Nombre de postes chiffrables travaux inattendu.')
    items=[]
    for seq,((br,bc),(dr,dc)) in enumerate(zip(bpu,dqe),1):
        designation=field_value(cell_paragraphs(bc[2]));unit=field_value(cell_paragraphs(bc[3]));qty=field_value(cell_paragraphs(dc[4])).replace('\u00a0','').replace(' ','');quantity(qty)
        items.append({'data':{'key':f'source-1-{seq}','designation':designation,'specifications':'','packaging':'','unit':unit,'quantity':qty},'row':{'bpu':br,'dqe':dr},'fields':{'bpu':{'designation':cell_paragraphs(bc[2]),'unit':cell_paragraphs(bc[3])},'dqe':{'designation':cell_paragraphs(dc[2]),'unit':cell_paragraphs(dc[3]),'quantity':cell_paragraphs(dc[4])}}})
    return [{'number':1,'label':'Travaux d’aménagement et de rénovation de l’auditorium','tables':tables,'count':len(items),'items':items}]


@functools.lru_cache(maxsize=2)
def source_mapping(family):
    if family == 'equipment':
        return mapping()
    if family == 'works':
        return works_mapping()
    if family != 'reagents':
        raise DocumentError('Famille d’articles inconnue.')
    from .catalog import document
    from .lot_catalog import DEFAULT_NAMES
    doc = document(family)
    result = []
    for number, cpt, bpt, dqt, count in REAGENTS:
        tables = {}
        for kind, (index, digest) in zip(('cptc', 'bpu', 'dqe'), (cpt, bpt, dqt)):
            tid = f'word/document.xml:t{index}:{digest}'
            if tid not in doc.tables:
                raise DocumentError('Le modèle réactifs ne correspond plus à ses ancrages vérifiés.')
            _, node = doc.tables[tid]
            rows = children(node, 'tr')
            if len(rows) != count + (4 if kind == 'dqe' else 1):
                raise DocumentError('Nombre de lignes du modèle réactifs inattendu.')
            tables[kind] = {'id': tid, 'node': node, 'rows': rows}
        items = []
        for ri in range(1, count + 1):
            c, b, d = [children(tables[k]['rows'][ri], 'tc') for k in ('cptc', 'bpu', 'dqe')]
            if (len(c), len(b), len(d)) != (4, 4, 6):
                raise DocumentError('Structure des colonnes réactifs inattendue.')
            bp = cell_paragraphs(b[1])
            labels = [i for i, p in enumerate(bp) if 'Prix unitaire en lettres' in field_value([p])]
            if len(labels) != 1 or labels[0] < 1 or any(field_value([p]) for p in bp[labels[0]+1:]):
                raise DocumentError('Mention de prix en lettres du BPU non reconnue.')
            if any(field_value(cell_paragraphs(x)) for x in (b[3], d[2], d[5])):
                raise DocumentError('Prix prérempli dans le modèle : export public refusé.')
            item = {'key': f'source-{number}-{ri}', 'designation': field_value(cell_paragraphs(c[1])),
                    'specifications': field_value(cell_paragraphs(c[2])), 'packaging': field_value(cell_paragraphs(c[3])),
                    'unit': field_value(cell_paragraphs(b[2])), 'quantity': field_value(cell_paragraphs(d[4]))}
            quantity(item['quantity'])
            fields = {'cptc': {'designation': cell_paragraphs(c[1]), 'specifications': cell_paragraphs(c[2]), 'packaging': cell_paragraphs(c[3])},
                      'bpu': {'designation': bp[:labels[0]], 'unit': cell_paragraphs(b[2])},
                      'dqe': {'designation': cell_paragraphs(d[1]), 'unit': cell_paragraphs(d[3]), 'quantity': cell_paragraphs(d[4])}}
            items.append({'data': item, 'row': ri, 'fields': fields})
        result.append({'number': number, 'label': DEFAULT_NAMES[family][number-1], 'tables': tables, 'count': count, 'items': items})
    return result


def managed_ids(family):
    if family not in ('equipment', 'reagents', 'works'):
        return set(), set()
    from .catalog import document
    doc = document(family)
    tables = {t['id'] for lot in source_mapping(family) for t in lot['tables'].values()}
    paragraphs = {doc.paragraph_id('word/document.xml', p) for lot in source_mapping(family)
                  for t in lot['tables'].values() for p in t['node'].descendants(NS+'p')}
    return paragraphs, tables


def binding_findings(data):
    if 'lot_catalog' not in data:
        return []
    from .lot_catalog import DEFAULT_NAMES, DEFAULT_AR, get_catalog
    value, family = data['lot_catalog'], data['family']
    base = {k: v for k, v in data.items() if k != 'lot_catalog'}
    if family == 'works':
        source=get_catalog(base)
        if len(value['lots'])!=1 or value['lots'][0]['source_slot']!=1:
            return [{'severity':'error','id':'WORKS_LOT_MAPPING','message':'Le modèle travaux comporte un lot unique. Un autre allotissement nécessite un nouveau modèle documentaire approuvé.'}]
        expected=[i['key'] for i in source['lots'][0]['items']];actual=[i['key'] for i in value['lots'][0]['items']]
        if actual!=expected:
            return [{'severity':'error','id':'WORKS_STRUCTURE_MAPPING','message':'Le BPU/DQE travaux conserve actuellement les 249 postes du modèle. Les ajouts, suppressions ou réordonnancements nécessitent une qualification des sous-totaux par corps d’état.'}]
        return []
    findings = []
    expected = list(range(1, len(DEFAULT_NAMES[family])+1))
    if [l['source_slot'] for l in value['lots']] != expected:
        findings.append({'severity': 'error', 'id': 'LOT_ANNEX_MAPPING', 'message': f'Ce cahier complet conserve {len(expected)} emplacements de lots. Un allotissement différent nécessite la correspondance de toutes les annexes et avis bilingues ; aucun ancien lot ne sera conservé silencieusement.'})
    for lot in value['lots']:
        if not lot['items']:
            findings.append({'severity': 'error', 'id': 'LOT_EMPTY', 'message': f'Lot {lot["number"]} — {lot["name"]} : renseignez au moins un article.'})
        slot = lot['source_slot']
        if 1 <= slot <= len(DEFAULT_NAMES[family]) and lot['name'] != DEFAULT_NAMES[family][slot-1]:
            if not lot['name_ar'].strip():
                findings.append({'severity': 'error', 'id': 'LOT_AR_NAME', 'message': f'Lot {lot["number"]} : renseignez la désignation arabe. Aucune traduction n’est inventée automatiquement.'})
    return findings


def validate_targets(data):
    family = data['family']
    paragraphs, tables = managed_ids(family)
    if set(data.get('paragraphs', {})) & paragraphs or set(data.get('omitted', [])) & paragraphs or set(data.get('rows', {})) & tables:
        raise DocumentError('Un tableau CPTC/BPU/DQE comporte aussi une modification manuelle. Résolvez ce conflit avant de confirmer le catalogue Excel.')
    if family not in ('equipment', 'reagents', 'works'):
        return
    sources = {lot['number']: lot for lot in source_mapping(family)}
    for lot in data['lot_catalog']['lots']:
        source = sources.get(lot['source_slot'])
        if source is None:
            continue
        originals = {i['data']['key']: i for i in source['items']}
        for item in lot['items']:
            old = originals.get(item['key'])
            if item['key'].startswith('source-') and old is None:
                raise DocumentError(f'Lot {lot["number"]} : cet identifiant d’article appartient à un autre lot.')
            if old:
                target = expanded_item(item, family)
                for fields in old['fields'].values():
                    for field, ps in fields.items():
                        previous = old['data'].get(field, '')
                        equal = quantity(target[field]) == quantity(previous) if field == 'quantity' else target[field] == previous
                        if not equal and not editable(ps):
                            raise DocumentError(f'Lot {lot["number"]}, article {item["position"]} : le champ {field} contient une structure Word protégée. Les autres données n’ont pas été appliquées.')


def expanded_item(item, family):
    result = dict(item)
    if family == 'works':
        extras=[]
        if item.get('specifications'): extras.append(item['specifications'])
        if item.get('packaging'): extras.append('Conditionnement : '+item['packaging'])
        if item.get('details'): extras.append(item['details'])
        result['designation']=item['designation'] + (('\n'+'\n'.join(extras)) if extras else '')
        return result
    extras = []
    if family == 'equipment' and item['packaging']:
        extras.append('Conditionnement : ' + item['packaging'])
    if item['details']:
        extras.append('Informations associées : ' + item['details'])
    if extras:
        result['specifications'] += '\n' + '\n'.join(extras)
    return result


def safe_number_paragraph(p):
    forbidden = {NS+n for n in ('instrText', 'fldChar', 'fldSimple', 'drawing', 'object', 'ins', 'del', 'br', 'cr')}
    return not p.attrs.get('_protected_field') and not any(n.name in forbidden or (n.name == NS+'tab' and n.ancestor(NS+'tabs') is None) for n in p.descendants())


def number_patch(raw, cell, value):
    ps = cell_paragraphs(cell)
    nonempty = [p for p in ps if field_value([p])]
    # Source number cells can contain trailing empty paragraphs; keep them intact.
    p = nonempty[0] if len(nonempty) == 1 else ps[0] if not nonempty and ps else None
    if p is None or not safe_number_paragraph(p):
        raise DocumentError('Cellule de numérotation Word non qualifiée.')
    fragment = raw[p.start:p.end]
    nodes = own_text_nodes(p)
    if nodes:
        fragment = apply_byte_edits(fragment, [(a-p.start,b-p.start,v) for a,b,v in edit_text_nodes(nodes,value,raw)])
    else:
        from xml.sax.saxutils import escape
        properties = next((n for n in p.descendants(NS+'rPr') if n.parent.name == NS+'pPr'), None)
        run_properties = raw[properties.start:properties.end] if properties else b''
        run = b'<w:r>' + run_properties + b'<w:t>' + escape(value).encode() + b'</w:t></w:r>'
        fragment = fragment[:p.closing_start-p.start] + run + fragment[p.closing_start-p.start:]
    fragment = re.sub(rb'<w:numPr\b[^>]*>.*?</w:numPr>', b'', fragment, flags=re.S)
    return p.start, p.end, fragment


def prototype(source):
    forbidden = {NS+n for n in ('drawing', 'object', 'vMerge', 'fldChar', 'fldSimple', 'sectPr', 'ins', 'del')}
    for candidate in source['items']:
        if not all(editable(ps) and ps for fields in candidate['fields'].values() for ps in fields.values()):
            continue
        if all(not any(n.name in forbidden for n in table['rows'][candidate['row']].descendants())
               and all(safe_number_paragraph(p) for p in cell_paragraphs(children(table['rows'][candidate['row']], 'tc')[0]))
               for table in source['tables'].values()):
            return candidate
    raise DocumentError('Aucune ligne modèle suffisamment simple pour ajouter cet article sans altérer Word.')


def _repack(doc, replacements):
    result = io.BytesIO()
    with zipfile.ZipFile(result, 'w') as out:
        out.comment = doc.z.comment
        for info in doc.z.infolist():
            out.writestr(copy.copy(info), replacements.get(info.filename, doc.z.read(info.filename)))
    return result.getvalue()



def lot_label_projection(data):
    """Project canonical lot names onto source paragraph text for UI synchronization."""
    from .catalog import document
    from .lot_catalog import DEFAULT_NAMES, DEFAULT_AR, get_catalog
    family=data['family']
    if family not in DEFAULT_NAMES:
        return {}, {}
    current=document(family)
    item_tables={t['node'].index for l in source_mapping(family) for t in l['tables'].values()}
    projected={}; ownership={}
    for lot in get_catalog(data)['lots']:
        slot=lot['source_slot']
        if not 1 <= slot <= len(DEFAULT_NAMES[family]):
            continue
        aliases=[DEFAULT_NAMES[family][slot-1]]
        if family=='equipment' and slot==1:
            aliases += ['Équipements et appareillages scientifiques de laboratoire',
                        'Equipements et appareillages scientifique de laboratoire',
                        'Equipements et appareillages de laboratoire']
        languages=[('fr',aliases,lot['name'])]
        if DEFAULT_AR[family][slot-1]:
            languages.append(('ar',[DEFAULT_AR[family][slot-1]],lot['name_ar']))
        for language,old_values,new in languages:
            if not new:
                continue
            for b in current.source_index:
                part,p=current.paragraphs[b['id']]
                owner=p.ancestor(NS+'tbl')
                if part=='word/document.xml' and owner is not None and owner.index in item_tables:
                    continue
                before=b['text']
                heading=(language=='fr' and re.match(r'^\s*Lot\s*(?:n[°º]\s*)?0?'+str(slot)+r'\s*:',before,re.I))
                exact=before.strip().rstrip('.') in old_values
                contains=any(old and old in before for old in old_values)
                if not heading and not exact and not contains:
                    continue
                pattern='|'.join(re.escape(old) for old in sorted(old_values,key=len,reverse=True) if old)
                after=re.sub(pattern,lambda _:new,before) if pattern else before
                projected[b['id']]=after
                ownership[b['id']]={'source':'Lots et articles','fields':[f'lot_{slot}_{language}'],'lot':lot['number']}
    return projected, ownership

def rename_labels(payload, data):
    from .lot_catalog import DEFAULT_NAMES, DEFAULT_AR
    family = data['family']
    current = Document(payload)
    item_tables = {t['node'].index for l in source_mapping(family) for t in l['tables'].values()}
    edits = {}
    changed = []
    for lot in data['lot_catalog']['lots']:
        slot = lot['source_slot']
        if not 1 <= slot <= len(DEFAULT_NAMES[family]):
            continue
        aliases = [DEFAULT_NAMES[family][slot-1]]
        if family == 'equipment' and slot == 1:
            aliases += ['Équipements et appareillages scientifiques de laboratoire', 'Equipements et appareillages scientifique de laboratoire', 'Equipements et appareillages de laboratoire']
        for language, old_values, new in [('fr', aliases, lot['name']), ('ar', [DEFAULT_AR[family][slot-1]], lot['name_ar'])]:
            default = DEFAULT_NAMES[family][slot-1] if language == 'fr' else DEFAULT_AR[family][slot-1]
            if new == default or not new:
                continue
            count = 0
            for b in current.source_index:
                part, p = current.paragraphs[b['id']]
                before = b['text']
                owner = p.ancestor(NS+'tbl')
                if part == 'word/document.xml' and owner is not None and owner.index in item_tables:
                    continue
                heading = re.match(r'^\s*Lot\s*(?:n[°º]\s*)?0?'+str(slot)+r'\s*:', before, re.I)
                exact_name = before.strip().rstrip('.') in old_values
                contains_name = any(old and old in before for old in old_values)
                if not heading and not exact_name and not contains_name:
                    continue
                pattern = '|'.join(re.escape(old) for old in sorted(old_values, key=len, reverse=True) if old)
                after = re.sub(pattern, lambda _: new, before) if pattern else before
                if after != before:
                    # Cached TOC text may change; field instructions, bookmarks and runs do not.
                    patches = edit_text_nodes(own_text_nodes(p), after, current.parts[part][0])
                    edits.setdefault(part, []).extend(patches)
                    count += 1
            if count == 0:
                raise DocumentError(f'Nom du lot {lot["number"]} ({language}) : aucun ancrage exact reconnu.')
            changed.append({'lot': lot['number'], 'language': language, 'paragraphs': count})
    replacements = {part: apply_byte_edits(current.parts[part][0], ps) for part, ps in edits.items()}
    return (_repack(current, replacements) if replacements else payload), changed



def repair_removed_bookmarks(current, updated):
    """Remove only unused survivors of bookmark ranges intersecting removed items."""
    before_root = current.parts['word/document.xml'][1]
    after_root = parse_xml(updated)
    def index(root, tag):
        result = {}
        for n in root.descendants(NS+tag):
            result.setdefault(n.attrs.get(NS+'id'), []).append(n)
        return result
    old_start, old_end = index(before_root, 'bookmarkStart'), index(before_root, 'bookmarkEnd')
    new_start, new_end = index(after_root, 'bookmarkStart'), index(after_root, 'bookmarkEnd')
    roots = [after_root] + [root for part, (_,root) in current.parts.items() if part != 'word/document.xml']
    anchors = {n.attrs.get(NS+'anchor') for root in roots for n in root.descendants(NS+'hyperlink')}
    instructions = ''.join(n.characters for root in roots for n in root.descendants(NS+'instrText'))
    patches, repaired = [], []
    for key, starts in old_start.items():
        if len(starts) != 1 or len(old_end.get(key, [])) != 1:
            continue
        remaining = new_start.get(key, []) + new_end.get(key, [])
        if len(remaining) == 2:
            continue
        name = starts[0].attrs.get(NS+'name', '')
        if name and (name in anchors or re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])', instructions)):
            raise DocumentError('Un article retiré appartient à un signet utilisé par un renvoi Word. La génération est annulée, sans modifier le dossier.')
        patches.extend((n.start, n.end, b'') for n in remaining)
        repaired.append({'id': key, 'name': name, 'remaining_markers_removed': len(remaining)})
    return apply_byte_edits(updated, patches), repaired


def apply_works_updates(payload, data):
    source=source_mapping('works')[0];target_lot=data['lot_catalog']['lots'][0]
    expected=[i['data']['key'] for i in source['items']]
    if [i['key'] for i in target_lot['items']]!=expected:
        raise DocumentError('La structure des postes travaux a changé ; sous-totaux non qualifiés.')
    from .catalog import document
    base=document('works');current=Document(payload);raw=base.parts['word/document.xml'][0];current_raw=current.parts['word/document.xml'][0]
    replacements=[];affected=[]
    for kind,table in source['tables'].items():
        original=table['node'];target=next((n for part,n in current.tables.values() if part=='word/document.xml' and n.index==original.index),None)
        if target is None or current_raw[target.start:target.end]!=raw[original.start:original.end]:raise DocumentError('Conflit sur le tableau travaux '+kind.upper()+'.')
        changes=[]
        for item,old in zip(target_lot['items'],source['items']):
            values=expanded_item(item,'works');ri=old['row'][kind]
            for field,ps in old['fields'][kind].items():
                oldv=old['data'].get(field,'');newv=values[field]
                equal=quantity(oldv)==quantity(newv) if field=='quantity' else oldv==newv
                if not equal:
                    if field=='quantity':newv=format(quantity(newv),'f').replace('.',',')
                    changes.extend(_field_patches(raw,ps,newv,f'{item["key"]}:{kind}:{field}'))
        if changes:
            fragment=apply_byte_edits(raw[original.start:original.end],[(a-original.start,b-original.start,v) for a,b,v in changes])
            replacements.append((target.start,target.end,fragment));affected.append({'lot':1,'piece':kind.upper(),'output_items':len(target_lot['items']),'source_items':len(source['items'])})
    if replacements:
        current_raw=apply_byte_edits(current_raw,replacements);payload=_repack(current,{'word/document.xml':current_raw})
    payload,names=rename_labels(payload,data)
    return payload,{'status':'GENERATED' if replacements or names else 'UNCHANGED','tables':affected,'lot_names':names,'removed_item_bookmarks':[],'bidder_prices':'PRESERVED_EMPTY','source_layout':'ORIGINAL_OOXML','scope':'Travaux : mises à jour des 249 postes BPU/DQE et des intitulés de lot ; CPTC narratif conservé.'}

def apply_catalog(payload, data):
    if 'lot_catalog' not in data:
        return payload, {'status': 'NOT_REQUESTED'}
    findings = binding_findings(data)
    if findings:
        raise DocumentError(' '.join(x['message'] for x in findings))
    validate_targets(data)
    family = data['family']
    if family == 'works':
        return apply_works_updates(payload,data)
    from .catalog import document
    doc, current = document(family), Document(payload)
    raw, current_raw = doc.parts['word/document.xml'][0], current.parts['word/document.xml'][0]
    replacements, affected = [], []
    for target_lot, source in zip(data['lot_catalog']['lots'], source_mapping(family)):
        lookup = {i['data']['key']: i for i in source['items']}
        target_keys = [i['key'] for i in target_lot['items']]
        reordered = target_keys != list(lookup)
        for kind, table in source['tables'].items():
            original_table = table['node']
            target = next((n for part, n in current.tables.values() if part == 'word/document.xml' and n.index == original_table.index), None)
            if target is None or current_raw[target.start:target.end] != raw[original_table.start:original_table.end]:
                raise DocumentError('Conflit de modification sur le tableau partagé ' + kind.upper() + '.')
            fragments, changed = [], reordered
            for sequence, item in enumerate(target_lot['items'], 1):
                old = lookup.get(item['key'])
                is_new = old is None
                old = old or prototype(source)
                row = table['rows'][old['row']]
                values, changes = expanded_item(item, family), []
                for field, ps in old['fields'][kind].items():
                    old_value, new_value = old['data'].get(field, ''), values[field]
                    equal = quantity(old_value) == quantity(new_value) if field == 'quantity' else old_value == new_value
                    if not equal or is_new:
                        if field == 'quantity':
                            new_value = format(quantity(new_value), 'f').replace('.', ',')
                        changes.extend(_field_patches(raw, ps, new_value, f'{item["key"]}:{kind}:{field}'))
                if reordered:
                    width = 2 if family == 'equipment' and (kind == 'bpu' or source['number'] == 2) else 1
                    changes.append(number_patch(raw, children(row, 'tc')[0], str(sequence).zfill(width)))
                fragment = apply_byte_edits(raw[row.start:row.end], [(a-row.start, b-row.start, v) for a, b, v in changes])
                if is_new:
                    fragment = _fresh_identity(fragment, item['key'] + ':' + kind)
                changed = changed or bool(changes) or is_new
                fragments.append(fragment)
            if changed:
                first, last = table['rows'][1], table['rows'][source['count']]
                replacement = raw[original_table.start:first.start] + b''.join(fragments) + raw[last.end:original_table.end]
                replacements.append((target.start, target.end, replacement))
                affected.append({'lot': target_lot['number'], 'piece': kind.upper(), 'output_items': len(fragments), 'source_items': source['count']})
    bookmark_changes = []
    if replacements:
        updated = apply_byte_edits(current_raw, replacements)
        updated, bookmark_changes = repair_removed_bookmarks(current, updated)
        parsed = parse_xml(updated)
        attr = 'http://schemas.microsoft.com/office/word/2010/wordml|paraId'
        before = Counter(n.attrs[attr] for n in current.parts['word/document.xml'][1].descendants() if attr in n.attrs)
        after = Counter(n.attrs[attr] for n in parsed.descendants() if attr in n.attrs)
        if any(count > max(1, before.get(k, 0)) for k, count in after.items()):
            raise DocumentError('Identifiant Word dupliqué ; génération annulée.')
        payload = _repack(current, {'word/document.xml': updated})
    payload, names = rename_labels(payload, data)
    return payload, {'status': 'GENERATED' if replacements or names else 'UNCHANGED', 'tables': affected,
                     'lot_names': names, 'removed_item_bookmarks': bookmark_changes, 'bidder_prices': 'PRESERVED_EMPTY', 'source_layout': 'ORIGINAL_OOXML',
                     'scope': 'Emplacements des lots du modèle source ; articles et noms variables.'}
