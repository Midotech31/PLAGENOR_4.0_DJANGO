"""Versioned, read-only source profiles and explicit field bindings."""
from __future__ import annotations
import functools,json,re
from pathlib import Path
from .docengine import Document,DocumentError,sha,xml_text
from .institutional import CURRENT_POLICY, validate_policy, apply_policy_edits, resolved_issue, policy_report
from .consultation import initial_consultation, validate_consultation, consultation_edits, consultation_findings
ASSETS=Path(__file__).resolve().parents[1]/'assets'
FAMILIES={'equipment':'Équipements scientifiques','reagents':'Réactifs et consommables','works':'Aménagement et travaux'}
DIGESTS={'equipment':'bb4ea598fe896b6b157ab706d03723236fc16820e093b6b541adb6c208dcf1dc',
'reagents':'62825773e9b1206622136469527e62ffc557575e5b939760a15229c471deb208',
'works':'5b8b04a806ea8add6d32d6bcec5c6432fba5bb6bfba3bbe2ded3663178f90647'}
REF_PATTERN=re.compile(r'(?<!\d)0[123]\s*/SME/(?:SDFM/)?SG/ESSBO/2026(?!\d)',re.I)

@functools.lru_cache(maxsize=3)
def document(family):
    if family not in FAMILIES:raise DocumentError('Famille de document inconnue.')
    return Document((ASSETS/'models'/f'{family}.docx').read_bytes(),DIGESTS[family])

@functools.lru_cache(maxsize=3)
def profile(family):
    if family not in FAMILIES:raise DocumentError('Famille de document inconnue.')
    value=json.loads((ASSETS/'profiles'/f'{family}.json').read_text(encoding='utf-8'))
    if value['source_sha256']!=DIGESTS[family]:raise DocumentError('Profil documentaire incohérent.')
    return value

def initial_data(family):
    return {'format':1,'family':family,'source_sha256':DIGESTS[family],
            'reference':profile(family)['reference'],'paragraphs':{},'rows':{},'omitted':[],
            'notes':'','review_acknowledged':False,'institutional_policy':CURRENT_POLICY,
            'consultation':initial_consultation(family)}

def validate_data(data,family):
    if family not in FAMILIES:
        raise DocumentError('Famille de document inconnue.')
    if not isinstance(data,dict) or type(data.get('format')) is not int or data.get('format')!=1 or data.get('family')!=family or data.get('source_sha256')!=DIGESTS[family]:
        raise DocumentError('Le dossier ne correspond pas au modèle attendu.')
    if set(data)-{'format','family','source_sha256','reference','paragraphs','rows','omitted','notes','review_acknowledged','procurement','lot_catalog','institutional_policy','consultation','structured_sections','requirements','criteria','clauses'}:
        raise DocumentError('Le dossier contient des propriétés non reconnues.')
    validate_policy(data)
    if 'consultation' in data: validate_consultation(data['consultation'], family)
    reference = data.get('reference')
    if not isinstance(reference, str) or not reference.strip() or not re.fullmatch(r'[A-Za-z0-9°/._ -]{1,90}',reference):
        raise DocumentError('Référence invalide : utilisez des lettres, chiffres, espaces ou séparateurs / . _ - .')
    blocks={b['id']:b for b in profile(family)['paragraphs']}
    changes=data.get('paragraphs',{})
    if not isinstance(changes,dict) or len(changes)>10000:raise DocumentError('Modifications trop nombreuses.')
    for pid,value in changes.items():
        b=blocks.get(pid)
        if not b or b['guard']:raise DocumentError('Un bloc est inconnu ou protégé.')
        xml_text(value)
        if any(c in value for c in '\n\r\t'):raise DocumentError('Les blocs sont modifiés paragraphe par paragraphe.')
    row_groups = data.get('rows',{})
    if not isinstance(row_groups,dict) or any(not isinstance(v,list) for v in row_groups.values()):
        raise DocumentError('Ajouts de lignes invalides.')
    if sum(len(v) for v in row_groups.values())>1000:raise DocumentError('Ajouts de lignes invalides.')
    tables={t['id']:t for t in profile(family)['tables']}
    for tid,rows in data.get('rows',{}).items():
        if tid not in tables or not isinstance(rows,list):raise DocumentError('Tableau inconnu.')
        for op in rows:
            if not isinstance(op,dict) or set(op)-{'source_row','after_row','cells'}:raise DocumentError('Opération de ligne invalide.')
            ri=op.get('source_row');ai=op.get('after_row',ri); count=len(tables[tid]['rows'])
            if type(ri)!=int or type(ai)!=int or not 0<=ri<count or not 0<=ai<count:raise DocumentError('Ligne inconnue.')
            source=tables[tid]['rows'][ri]
            if not source['cloneable'] or not isinstance(op.get('cells'),list) or len(op['cells'])!=len(source['cells']):raise DocumentError('Cette ligne complexe ne peut pas être dupliquée.')
            for v in op['cells']:
                xml_text(v)
                if any(c in v for c in '\n\r\t'):raise DocumentError('Une cellule ajoutée doit contenir une ligne de texte.')
    if not isinstance(data.get('omitted',[]),list):raise DocumentError('Liste de sections invalide.')
    for pid in data.get('omitted',[]):
        if not isinstance(pid,str) or pid not in blocks or not blocks[pid].get('omittable'):raise DocumentError('Cette section structurelle ne peut pas être omise.')
        if pid in changes:raise DocumentError('Un bloc ne peut pas être modifié et omis en même temps.')
    if type(data.get('review_acknowledged',False)) is not bool:
        raise DocumentError('État de revue invalide.')
    xml_text(data.get('notes',''))
    if len(json.dumps(data,ensure_ascii=False))>8000000:raise DocumentError('Dossier trop volumineux.')
    from .procurement import validate_procurement
    validate_procurement(data, family)
    if 'lot_catalog' in data:
        if 'procurement' in data:
            raise DocumentError('Deux sources d’articles concurrentes sont présentes dans le dossier.')
        from .lot_catalog import validate_catalog
        from .schedule_adapter import validate_targets
        validate_catalog(data['lot_catalog'])
        validate_targets(data)
    return data

def effective_edits(data):
    """Text-only UI view of the exact generation plan; never a DOCX renderer."""
    paragraphs, spans = generation_edits(data)
    doc = document(data['family'])
    for pid, operations in spans.items():
        _, paragraph = doc.paragraphs[pid]
        from .docengine import own_text_nodes
        nodes = own_text_nodes(paragraph)
        offsets, cursor = {}, 0
        for node in nodes:
            offsets[id(node)] = cursor
            cursor += len(node.characters)
        text = ''.join(node.characters for node in nodes)
        patches = []
        segments = doc.editable_segments(pid)
        for op in operations:
            selected = segments[op['segment']]
            start = offsets[id(selected[0])]
            end = offsets[id(selected[-1])] + len(selected[-1].characters)
            if text[start:end] != op['before']:
                raise DocumentError('Ancrage de prévisualisation incohérent.')
            patches.append((start, end, op['after']))
        for start, end, after in sorted(patches, reverse=True):
            text = text[:start] + after + text[end:]
        paragraphs[pid] = text
    return paragraphs

def controls(data):
    family=data['family'];validate_data(data,family);p=profile(family)
    result=[]
    consultation_confirmed = bool(data.get('consultation',{}).get('confirmed'))
    for issue in p['issues']:
        if resolved_issue(data, issue['id']):
            continue
        if family=='reagents' and consultation_confirmed and issue['id'] in {'ESSBO-004','ESSBO-005'}:
            continue
        result.append({'severity':'warning','id':issue['id'],'message':issue['summary']})
    if data['reference']!=p['reference'] and not CANONICAL_REFERENCE.fullmatch(data['reference']):
        result.append({'severity':'error','id':'AR_MAPPING_REQUIRED','message':'Utilisez la structure numéro/SME/SDFM/SG/ESSBO/année. Un autre code nécessite une correspondance bilingue approuvée.'})
    from .schedule_adapter import binding_findings
    result.extend(binding_findings(data))
    result.extend(consultation_findings(data))
    from .common_data import manual_conflicts
    result.extend(manual_conflicts(data))
    edits=effective_edits(data)
    markers=re.compile(r'\{\{.+?\}\}|\[\[IF:|\[\[ENDIF:')
    for pid,text in edits.items():
        if markers.search(text):result.append({'severity':'error','id':'UNRESOLVED_MARKER','block':pid,'message':'Un marqueur applicatif reste dans ce paragraphe.'})
    return result


AR_REF_PATTERN = re.compile(
    r'(?<!\d)(?P<number>0[123])(?P<code>\s*/[\u0600-\u06ff. /]{4,90}/)(?P<year>2026)(?!\d)')
CANONICAL_REFERENCE = re.compile(r'(?P<number>[0-9]{1,4})/SME/SDFM/SG/ESSBO/(?P<year>[0-9]{4})')

@functools.lru_cache(maxsize=3)
def reference_spans(family):
    """Bindings are rebuilt from hash-verified originals, including cover breaks."""
    doc = document(family)
    bindings = []
    for block in doc.source_index:
        for index, nodes in enumerate(doc.editable_segments(block['id'])):
            before = ''.join(n.characters for n in nodes)
            french = list(REF_PATTERN.finditer(before))
            arabic = list(AR_REF_PATTERN.finditer(before))
            if french or arabic:
                bindings.append({'id': block['id'], 'segment': index, 'before': before,
                                 'french': len(french), 'arabic': len(arabic)})
    return bindings

def reference_replacement(text, data):
    target = data['reference']
    match = CANONICAL_REFERENCE.fullmatch(target)
    text = REF_PATTERN.sub(lambda _: target, text)
    if match:
        text = AR_REF_PATTERN.sub(lambda old: match['number']+old['code']+match['year'], text)
    return text

def generation_edits(data):
    """One plan for UI review and generation; editable islands preserve layout."""
    validate_data(data, data['family'])
    family=data['family']; paragraphs=dict(data.get('paragraphs', {})); spans={}
    if data['reference'] != profile(family)['reference']:
        for binding in reference_spans(family):
            pid=binding['id']
            if pid in data.get('omitted', []): continue
            if pid in paragraphs:
                paragraphs[pid]=reference_replacement(paragraphs[pid], data); continue
            after=reference_replacement(binding['before'], data)
            if after != binding['before']:
                spans.setdefault(pid, []).append({'segment':binding['segment'],'before':binding['before'],'after':after})
    paragraphs,spans=apply_policy_edits(data, paragraphs, spans)
    spans,_=consultation_edits(data, spans, document(family))
    if data.get('institutional_policy') == CURRENT_POLICY:
        from .source_noise import apply_noise_spans
        spans,_=apply_noise_spans(family, spans, document(family))
    return paragraphs,spans

def generate_document(data):
    """Generate a complete source-derived copy, then independently scan references."""
    family = data['family']
    paragraphs, spans = generation_edits(data)
    output, report = document(family).generate(paragraphs, data.get('rows'),
                                              data.get('omitted'), span_edits=spans)
    from .procurement import apply_procurement
    output, procurement_report = apply_procurement(output, data)
    report['procurement'] = procurement_report
    if procurement_report['status'] == 'GENERATED':
        if 'word/document.xml' not in report['changed_parts']:
            report['changed_parts'].append('word/document.xml')
        report['preserved_parts'].pop('word/document.xml', None)
        report['changes'].append({'kind': 'equipment_articles', 'tables': procurement_report['tables']})
        report['output_sha256'] = sha(output)
    from .schedule_adapter import apply_catalog
    output, lot_report = apply_catalog(output, data)
    report['lot_catalog'] = lot_report
    from .source_noise import noise_ids
    report['source_noise']={'status':('REMOVED_TEXT_PRESERVED_WORD_FIELDS' if data.get('institutional_policy') == CURRENT_POLICY else 'LEGACY_UNCHANGED'), 'removed':sorted(noise_ids(family)) if data.get('institutional_policy') == CURRENT_POLICY else []}
    if lot_report['status'] == 'GENERATED':
        generated = Document(output)
        for name in generated.z.namelist():
            if generated.z.read(name) != document(family).z.read(name):
                if name not in report['changed_parts']:
                    report['changed_parts'].append(name)
                report['preserved_parts'].pop(name, None)
        report['changes'].append({'kind': 'lot_catalog', 'tables': lot_report['tables'], 'lot_names': lot_report['lot_names']})
        report['output_sha256'] = sha(output)
    updated = document(family) if output == document(family).data else Document(output)
    stale = []
    if data['reference'] != profile(family)['reference']:
        for block in updated.source_index:
            if REF_PATTERN.search(block['text']) or AR_REF_PATTERN.search(block['text']):
                # Matching the original number/year is harmless only when those
                # identifiers actually remain the requested values.
                transformed = reference_replacement(block['text'], data)
                if transformed != block['text']:
                    stale.append({'part': block['part'], 'paragraph': block['index']})
        if stale:
            raise DocumentError('Une ancienne référence subsiste ; génération annulée.')
        if not CANONICAL_REFERENCE.fullmatch(data['reference']):
            raise DocumentError('La nouvelle référence nécessite une correspondance arabe explicite ; génération annulée.')
    report['reference_propagation'] = {'status': 'PASS' if data['reference'] != profile(family)['reference'] else 'NOT_REQUESTED', 'remaining_stale': stale,
                                     'bindings': len(reference_spans(family)),
                                     'arabic_translation_changed': False}
    report['institutional_policy'] = policy_report(data)
    _, consultation_report = consultation_edits(data, {}, document(family))
    report['consultation'] = consultation_report
    return output, report
