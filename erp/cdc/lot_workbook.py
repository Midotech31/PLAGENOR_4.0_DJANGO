"""Bounded XLSX exchange using a styled, bundled workbook and ordinary OOXML.

No formula, macro, external relationship or user-supplied expression is executed.
The template's styles are shared by every lot sheet; data bindings are signed by
Django in the calling view and never inferred from a filename.
"""
from __future__ import annotations
import copy
import io
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as safe_fromstring
from defusedxml.common import DefusedXmlException
from decimal import Decimal, InvalidOperation, DecimalException
from pathlib import Path, PurePosixPath
from .docengine import DocumentError, safe_zip, sha
from .lot_catalog import FIELDS, MAX_ITEMS, get_catalog, validate_catalog, fingerprint, diff_catalog, replace_catalog
from .procurement import quantity

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
T = 'http://schemas.openxmlformats.org/package/2006/content-types'
Q = '{' + S + '}'
LEGACY_HEADERS = ['Ordre', 'Désignation', 'Caractéristiques techniques', 'Unité de commande',
           'Conditionnement', 'Quantité', 'Informations associées', 'Identifiant interne']
HEADERS = ['Ordre', 'Désignation', 'Caractéristiques techniques', 'Unité de commande',
           'Conditionnement', 'Quantité', 'Informations associées', 'Estimation financière (DZD, facultative)', 'Identifiant interne']
MAX_FILE = 20 * 1024 * 1024
BASE = Path(__file__).resolve().parents[1] / 'assets/excel/lots_base.xlsx'
ET.register_namespace('', S)
ET.register_namespace('r', R)


class WorkbookError(DocumentError):
    def __init__(self, issues):
        self.issues = issues[:200]
        super().__init__(' ; '.join(f'{i["sheet"]}!{i["cell"]} : {i["message"]}' for i in self.issues[:5]))


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise DocumentError('Déclaration XML externe interdite dans le classeur.')
    try:
        return safe_fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise DocumentError('Le classeur contient un XML invalide.') from exc


def dump(node):
    return ET.tostring(node, encoding='utf-8', xml_declaration=True)


def cell(sheet, address, value, numeric=False):
    sheet_data = sheet.find(Q+'sheetData')
    row_num = re.search(r'\d+$', address)[0]
    row = next((r for r in sheet_data if r.get('r') == row_num), None)
    if row is None:
        row = ET.SubElement(sheet_data, Q+'row', {'r': row_num, 'ht': '45', 'customHeight': '1'})
    current = next((c for c in row if c.get('r') == address), None)
    if current is None:
        current = ET.SubElement(row, Q+'c', {'r': address})
    for child in list(current):
        current.remove(child)
    if numeric:
        current.set('t', 'n')
        ET.SubElement(current, Q+'v').text = str(value)
    else:
        current.set('t', 'inlineStr')
        text = ET.SubElement(ET.SubElement(current, Q+'is'), Q+'t')
        text.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        text.text = str(value) if value is not None else ''


def _sheet_paths(archive):
    workbook = xml(archive.read('xl/workbook.xml'))
    rels = xml(archive.read('xl/_rels/workbook.xml.rels'))
    targets = {}
    for rel in rels:
        if rel.get('Type', '').endswith('/worksheet'):
            raw = rel.get('Target', '')
            path = raw.lstrip('/') if raw.startswith('/') else 'xl/' + raw
            if '..' in PurePosixPath(path).parts or path not in archive.namelist():
                raise DocumentError('Relation de feuille invalide.')
            targets[rel.get('Id')] = path
    sheets = workbook.find(Q+'sheets')
    result = {}
    for sheet in sheets:
        name = sheet.get('name')
        if name in result or sheet.get('{'+R+'}id') not in targets:
            raise DocumentError('Noms ou relations de feuilles ambigus.')
        result[name] = targets[sheet.get('{'+R+'}id')]
    if len(result) > 52:
        raise DocumentError('Classeur trop volumineux : trop de feuilles.')
    return result


def build_workbook(data, dossier_id, revision, sign, filled=True, estimates=None):
    estimates = estimates or {}
    catalog = get_catalog(data)
    validate_catalog(catalog)
    meta = {'schema': 1, 'dossier': str(dossier_id), 'revision': revision,
            'source': data['source_sha256'], 'family': data['family'],
            'data_sha256': fingerprint(data), 'nonce': str(uuid.uuid4()), 'filled': bool(filled),
            'lots': [{'id': l['id'], 'name': l['name'], 'sheet': f'Lot_{l["number"]:02d}'} for l in catalog['lots']]}
    token = sign(meta)
    if not isinstance(token, str) or len(token) > 120000:
        raise DocumentError('Identité du classeur invalide.')
    with safe_zip(BASE.read_bytes()) as base:
        paths = _sheet_paths(base)
        master = xml(base.read(paths['Lot']))
        parts = {n: base.read(n) for n in base.namelist() if n not in paths.values()}
        sheets_to_add = [('Mode_emploi', xml(base.read(paths['Mode_emploi'])), False)]
        for lot, binding in zip(catalog['lots'], meta['lots']):
            sheet = copy.deepcopy(master)
            cell(sheet, 'A1', f'Lot {lot["number"]:02d} — {lot["name"]}')
            cell(sheet, 'A2', f'Référence {data["reference"]} · Révision {revision} · Les noms des lots se modifient dans CDC Studio.')
            for col,header in zip('ABCDEFGHI',HEADERS):cell(sheet,f'{col}6',header)
            sheet_data = sheet.find(Q+'sheetData')
            model_row = copy.deepcopy(next(r for r in sheet_data if r.get('r') == '7'))
            for row in list(sheet_data):
                if int(row.get('r', '0')) >= 7:
                    sheet_data.remove(row)
            items = lot['items'] if filled else []
            count = min(MAX_ITEMS, max(50, len(items)+20))
            for idx in range(count):
                rn = idx + 7
                row = copy.deepcopy(model_row)
                row.set('r', str(rn))
                for c in row:
                    c.set('r', re.sub(r'\d+$', str(rn), c.get('r', '')))
                sheet_data.append(row)
                cell(sheet, f'A{rn}', idx+1, numeric=True)
                if idx < len(items):
                    item = items[idx]
                    price = estimates.get(item['key'])
                    values = [item['designation'], item['specifications'], item['unit'], item['packaging'],
                              item['quantity'], item['details'], '' if price is None else str(price), item['key']]
                    for col, value in zip('BCDEFGHI', values):
                        numeric = col in ('F','H') and value not in ('',None)
                        if col == 'F': value = format(quantity(value), 'f')
                        cell(sheet, f'{col}{rn}', value, numeric=numeric)
            dimension = sheet.find(Q+'dimension')
            if dimension is not None:
                dimension.set('ref', f'A1:I{count+6}')
            cols = sheet.find(Q+'cols')
            for col in cols:
                if col.get('min') == '8' and col.get('max') == '8':
                    col.attrib.pop('hidden', None)
            ET.SubElement(cols, Q+'col', {'min':'9','max':'9','hidden':'1','width':'3','customWidth':'1'})
            dv = sheet.find(Q+'dataValidations')
            if dv is not None:
                for validation in dv:
                    validation.set('sqref', f'D7:D{count+6}')
                    validation.set('showErrorMessage', '0')
            if sheet.find(Q+'autoFilter') is None:
                index = list(sheet).index(sheet_data) + 1
                sheet.insert(index, ET.Element(Q+'autoFilter', {'ref': f'A6:I{count+6}'}))
            sheets_to_add.append((binding['sheet'], sheet, False))
        identity = xml(base.read(paths['_CDC']))
        chunks = [token[i:i+30000] for i in range(0, len(token), 30000)]
        cell(identity, 'B2', len(chunks), numeric=True)
        for i, chunk in enumerate(chunks, 3):
            cell(identity, f'B{i}', chunk)
        dimension = identity.find(Q+'dimension')
        if dimension is not None:
            dimension.set('ref', f'A1:B{2+len(chunks)}')
        sheets_to_add.append(('_CDC', identity, True))
        workbook = xml(parts['xl/workbook.xml'])
        ws = workbook.find(Q+'sheets')
        ws.clear()
        defined = workbook.find(Q+'definedNames')
        if defined is not None:
            workbook.remove(defined)
        rels = xml(parts['xl/_rels/workbook.xml.rels'])
        for rel in list(rels):
            if rel.get('Type', '').endswith('/worksheet'):
                rels.remove(rel)
        types = xml(parts['[Content_Types].xml'])
        for entry in list(types):
            if entry.get('PartName', '').lstrip('/') in paths.values():
                types.remove(entry)
        for number, (name, sheet, hidden) in enumerate(sheets_to_add, 1):
            part = f'xl/worksheets/sheet{number}.xml'
            rid = 'rIdCDC' + str(number)
            attrs = {'name': name, 'sheetId': str(number), '{'+R+'}id': rid}
            if hidden:
                attrs['state'] = 'veryHidden'
            ET.SubElement(ws, Q+'sheet', attrs)
            ET.SubElement(rels, '{'+P+'}Relationship', {'Id': rid, 'Type': R+'/worksheet', 'Target': f'worksheets/sheet{number}.xml'})
            ET.SubElement(types, '{'+T+'}Override', {'PartName': '/'+part, 'ContentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'})
            parts[part] = dump(sheet)
        for view in workbook.iter(Q+'workbookView'):
            view.set('activeTab', '1')
        parts['xl/workbook.xml'] = dump(workbook)
        parts['xl/_rels/workbook.xml.rels'] = dump(rels)
        parts['[Content_Types].xml'] = dump(types)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return out.getvalue()


def read_cells(archive, path, strings):
    sheet = xml(archive.read(path))
    values, count = {}, 0
    for c in sheet.iter(Q+'c'):
        count += 1
        address = c.get('r', '')
        if not re.fullmatch(r'[A-I][1-9]\d{0,3}', address) or count > 8500 or address in values:
            raise DocumentError('Adresse ou nombre de cellules hors limites dans ' + path + '.')
        if c.find(Q+'f') is not None:
            raise DocumentError(f'{path}!{address} : les formules sont refusées ; collez leurs valeurs.')
        typ = c.get('t', 'n')
        value = c.findtext(Q+'v', '')
        if typ == 's':
            try:
                index = int(value)
                if index < 0:
                    raise ValueError
                value = strings[index]
            except (ValueError, IndexError) as exc:
                raise DocumentError('Chaîne partagée Excel invalide.') from exc
        elif typ == 'inlineStr':
            value = ''.join(t.text or '' for t in c.iter(Q+'t'))
        elif typ not in ('n', 'str'):
            if value:
                raise DocumentError(f'{path}!{address} : texte ou nombre attendu, pas une erreur, date ou valeur logique.')
        if len(value) > 32767:
            raise DocumentError('Une cellule dépasse la limite Excel.')
        values[address] = {'value': value, 'type': typ, 'style': c.get('s', '0')}
    return values


def parse_workbook(payload, filename, data, dossier_id, revision, unsign, mode='merge'):
    if mode not in ('merge', 'replace'):
        raise DocumentError('Mode d’import inconnu.')
    if not filename.lower().endswith('.xlsx') or len(payload) > MAX_FILE:
        raise DocumentError('Choisissez un fichier XLSX de 20 Mo maximum.')
    with safe_zip(payload, 64*1024*1024) as archive:
        for name in archive.namelist():
            low = name.lower()
            if any(x in low for x in ('vbaproject', 'externallinks/', 'embeddings/', 'activex/', 'connections.xml')):
                raise DocumentError('Macros, connexions ou objets incorporés interdits.')
            if name.endswith('.rels'):
                if any(r.get('TargetMode') == 'External' for r in xml(archive.read(name))):
                    raise DocumentError('Les liens externes ne sont pas acceptés dans le modèle Excel.')
        paths = _sheet_paths(archive)
        if '_CDC' not in paths:
            raise DocumentError('Ce classeur ne provient pas du modèle de lots téléchargé pour ce dossier.')
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(t.text or '' for t in si.iter(Q+'t')) for si in xml(archive.read('xl/sharedStrings.xml')).findall(Q+'si')]
            if len(strings) > 10000 or sum(map(len, strings)) > 8000000:
                raise DocumentError('Chaînes du classeur trop volumineuses.')
        all_cells = {name: read_cells(archive, path, strings) for name, path in paths.items()}
        styles = xml(archive.read('xl/styles.xml')) if 'xl/styles.xml' in archive.namelist() else None
        xfs = list(styles.find(Q+'cellXfs')) if styles is not None and styles.find(Q+'cellXfs') is not None else []
        custom_formats = {n.get('numFmtId'): n.get('formatCode','') for n in styles.iter(Q+'numFmt')} if styles is not None else {}
        def date_style(style_id):
            try:
                index = int(style_id)
                if not 0 <= index < len(xfs):
                    return False
                fmt = xfs[index].get('numFmtId', '0')
                if fmt in {str(n) for n in (*range(14, 23), 45, 46, 47)}:
                    return True
                code = re.sub(r'"[^"]*"|\\.', '', custom_formats.get(fmt, '')).lower()
                return bool(re.search(r'[ydhs]', code))
            except (ValueError, IndexError):
                return False
        metadata = all_cells['_CDC']
        val = lambda cells, at: cells.get(at, {}).get('value', '')
        if val(metadata, 'A1') != 'CDCSTUDIO_LOTS_V1':
            raise DocumentError('Format du classeur non reconnu.')
        try:
            count = int(val(metadata, 'B2'))
            if not 1 <= count <= 4:
                raise ValueError
            meta = unsign(''.join(val(metadata, f'B{i}') for i in range(3, count+3)))
        except Exception as exc:
            raise DocumentError('L’identité du classeur est invalide, altérée ou expirée.') from exc
        if (not isinstance(meta, dict) or meta.get('schema') != 1 or meta.get('dossier') != str(dossier_id)
                or meta.get('family') != data['family'] or meta.get('source') != data['source_sha256']):
            raise DocumentError('Ce classeur appartient à un autre dossier, une autre famille ou un autre modèle.')
        if meta.get('revision') != revision or meta.get('data_sha256') != fingerprint(data):
            raise DocumentError('Le dossier a changé depuis le téléchargement. Exportez sa révision actuelle avant de réimporter ; rien n’a été écrasé.')
        catalog = get_catalog(data)
        bindings = meta.get('lots', [])
        expected = [{'id': l['id'], 'name': l['name'], 'sheet': f'Lot_{l["number"]:02d}'} for l in catalog['lots']]
        if bindings != expected or set(paths) != {'Mode_emploi', '_CDC', *(b['sheet'] for b in bindings)}:
            raise DocumentError('Les feuilles ou les lots ont changé. Téléchargez un nouveau modèle depuis l’application.')
        candidate = copy.deepcopy(catalog)
        issues, imported, incoming_count, financial = [], [], 0, {}
        for lot, binding in zip(candidate['lots'], bindings):
            name, cells = binding['sheet'], all_cells[binding['sheet']]
            header9=[val(cells,c+'6') for c in 'ABCDEFGHI'];header8=[val(cells,c+'6') for c in 'ABCDEFGH']
            modern=header9==HEADERS
            legacy=header8==LEGACY_HEADERS and not val(cells,'I6')
            if not modern and not legacy:
                raise DocumentError(f'{name}!A6:I6 : les en-têtes ont changé ; utilisez ceux du modèle.')
            key_col='I' if modern else 'H';price_col='H' if modern else None
            if val(cells, 'A1') != f'Lot {lot["number"]:02d} — {lot["name"]}':
                raise DocumentError(f'{name}!A1 : modifiez le nom du lot dans l’application, pas dans le classeur.')
            old = {i['key']: i for i in lot['items']}
            seen, order_seen, rows = set(), set(), []
            numbers = sorted({int(re.search(r'\d+$', a)[0]) for a in cells if int(re.search(r'\d+$', a)[0]) >= 7})
            has_internal_ids = any(val(cells, f'{key_col}{rn}') for rn in numbers)
            for rn in numbers:
                raw = [val(cells, col+str(rn)).replace('\n','\n') for col in 'BCDEFG'] + [val(cells,f'{key_col}{rn}')]
                raw_price = val(cells,f'{price_col}{rn}') if price_col else ''
                if not any(raw) or not any(raw[:6]):
                    # A visible empty row is absence, not an article. In merge mode the
                    # current article is preserved; in replace mode it is omitted.
                    continue
                incoming_count += 1
                if incoming_count > MAX_ITEMS:
                    raise DocumentError(f'{MAX_ITEMS} articles au maximum par dossier.')
                try:
                    order = int(val(cells, f'A{rn}') or rn-6)
                    if not 1 <= order <= MAX_ITEMS or order in order_seen:
                        raise ValueError
                    order_seen.add(order)
                except ValueError:
                    issues.append({'sheet': name, 'cell': f'A{rn}', 'message': 'Ordre entier positif, unique dans ce lot, attendu.'})
                    continue
                key = raw[6]
                if not key and not has_internal_ids and meta.get('filled', True) and 1 <= order <= len(lot['items']):
                    # Some spreadsheet programs can strip the hidden identifier column.
                    # If the whole sheet lost it, recover existing identities by stable order.
                    candidate_key = lot['items'][order-1]['key']
                    if candidate_key not in seen:
                        key = candidate_key
                if key and (key not in old or key in seen):
                    issues.append({'sheet': name, 'cell': f'{key_col}{rn}', 'message': 'Identifiant inconnu, déplacé vers un autre lot ou dupliqué.'})
                    continue
                if not key:
                    key = 'new-' + str(uuid.uuid5(uuid.UUID(meta['nonce']), lot['id'] + ':' + str(rn)))
                seen.add(key)
                item = {'key': key, 'position': 1, 'designation': raw[0].strip(), 'specifications': raw[1].strip(),
                        'unit': raw[2].strip(), 'packaging': raw[3].strip(), 'quantity': raw[4].strip(), 'details': raw[5].strip()}
                required_fields=(('designation','unit','quantity') if data['family']=='works' else ('designation','specifications','unit','quantity'))
                for field, col in zip(required_fields, ('BDF' if data['family']=='works' else 'BCDF')):
                    if not item[field]:
                        issues.append({'sheet': name, 'cell': f'{col}{rn}', 'message': 'Champ obligatoire manquant.'})
                if data['family'] == 'reagents' and not item['packaging']:
                    issues.append({'sheet': name, 'cell': f'E{rn}', 'message': 'Le conditionnement est requis pour le CPTC des réactifs.'})
                try:
                    if date_style(cells.get(f'F{rn}', {}).get('style', '0')):
                        raise InvalidOperation
                    if cells.get(f'F{rn}', {}).get('type') == 'n' and item['quantity']:
                        if len(item['quantity']) > 64:
                            raise InvalidOperation
                        number = Decimal(item['quantity'])
                        if (not number.is_finite() or number.copy_abs() > Decimal('1000000000')
                                or not -6 <= number.as_tuple().exponent <= 10):
                            raise InvalidOperation
                        item['quantity'] = format(number, 'f')
                    quantity(item['quantity'])
                    if key in old and quantity(item['quantity']) == quantity(old[key]['quantity']):
                        item['quantity'] = old[key]['quantity']
                except (DocumentError, DecimalException):
                    issues.append({'sheet': name, 'cell': f'F{rn}', 'message': 'Quantité strictement positive, au plus six décimales, attendue.'})
                if price_col and raw_price not in ('',None):
                    try:
                        price=Decimal(str(raw_price).replace(' ','').replace(',','.'))
                        if not price.is_finite() or price < 0 or price > Decimal('999999999999.99'):raise InvalidOperation
                        financial[key]=format(price.quantize(Decimal('0.01')),'f')
                    except (InvalidOperation,DecimalException):issues.append({'sheet':name,'cell':f'{price_col}{rn}','message':'Estimation financière facultative : nombre positif ou zéro attendu.'})
                elif price_col: financial[key]=None
                rows.append((order, rn, item))
            incoming = [item for _, _, item in sorted(rows)]
            if mode == 'replace' and not incoming and lot['items']:
                issues.append({'sheet': name, 'cell': 'B7', 'message': 'Une feuille vide ne supprime pas les articles existants. Supprimez le lot explicitement dans l’application.'})
            if mode == 'merge':
                updates = {i['key']: i for i in incoming}
                result = [updates.get(i['key'], i) for i in lot['items']]
                result += [i for i in incoming if i['key'] not in old]
            else:
                result = incoming
            for position, item in enumerate(result, 1):
                item['position'] = position
            lot['items'] = result
            imported.append({'lot': lot['number'], 'sheet': name, 'rows': len(incoming)})
        if issues:
            raise WorkbookError(issues)
        if not incoming_count:
            raise DocumentError('Aucun article renseigné dans le classeur ; le dossier reste inchangé.')
        validate_catalog(candidate)
        result = replace_catalog(data, candidate)
        from .catalog import validate_data
        validate_data(result, data['family'])
        return {'data': result, 'diff': diff_catalog(catalog, candidate), 'file_sha256': sha(payload),
                'mode': mode, 'imported': imported, 'base_revision': revision, 'financial': financial}
