"""Canonical lots and items shared by Excel intake and document generation."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid
from .docengine import DocumentError, xml_text
from .procurement import quantity

MAX_LOTS = 50
MAX_ITEMS = 1000
FIELDS = ('designation', 'specifications', 'unit', 'packaging', 'quantity', 'details')
DEFAULT_NAMES = {
    'equipment': ['Equipements et appareillages scientifiques de laboratoire', 'Paillasses de laboratoire'],
    'reagents': ['Réactifs de génomique', 'Réactifs de biologie moléculaire, cellulaire et de séquençage', 'Produits chimiques de laboratoire', 'Consommables de laboratoire'],
    'works': ['Travaux d’aménagement et de rénovation de l’auditorium'],
}
DEFAULT_AR = {
    'equipment': ['أجهزة ومعدات علمية مخبرية', 'المقاعد المخبرية للقيام بالأشغال التطبيقية'],
    'reagents': ['كواشف الجينوميك', 'كواشف البيولوجيا الجزيئية والخلوية والتسلسل', 'مواد كيميائية مخبرية', 'مستلزمات مخبرية'],
    'works': [''],
}

def fingerprint(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def text(value, label, limit, required=False, multiline=False):
    if not isinstance(value, str):
        raise DocumentError(label + ' : texte attendu.')
    xml_text(value)
    if len(value) > limit or (required and not value.strip()):
        raise DocumentError(f'{label} : champ requis ou longueur supérieure à {limit} caractères.')
    if '\r' in value or '\t' in value or ('\n' in value and not multiline):
        raise DocumentError(label + ' : séparateur de texte non autorisé.')
    if re.search(r'\{\{|\}\}|\[\[(?:IF|ENDIF):', value):
        raise DocumentError(label + ' : marqueur de modèle interdit.')


def valid_uuid(value):
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def get_catalog(data):
    if 'lot_catalog' in data:
        return copy.deepcopy(data['lot_catalog'])
    family = data['family']
    lots = []
    for number, name in enumerate(DEFAULT_NAMES[family], 1):
        lot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, data['source_sha256'] + ':' + str(number)))
        lots.append({'id': lot_id, 'number': number, 'name': name,
                     'name_ar': DEFAULT_AR[family][number-1], 'source_slot': number, 'items': []})
    if family in ('equipment', 'reagents', 'works'):
        from .schedule_adapter import source_mapping
        for lot, source in zip(lots, source_mapping(family)):
            for position, entry in enumerate(source['items'], 1):
                item = entry['data']
                if family == 'equipment' and data.get('procurement'):
                    original = next(x for x in data['procurement']['lots'] if x['number'] == lot['number'])
                    lot['items'] = [{**copy.deepcopy(i), 'position': n, 'packaging': '', 'details': ''}
                                    for n, i in enumerate(original['items'], 1)]
                    break
                lot['items'].append({**copy.deepcopy(item), 'position': position,
                                    'packaging': item.get('packaging', ''), 'details': ''})
    return {'schema': 1, 'lots': lots}


def validate_catalog(value):
    if not isinstance(value, dict) or set(value) != {'schema', 'lots'} or type(value['schema']) is not int or value['schema'] != 1:
        raise DocumentError('Format du catalogue de lots non reconnu.')
    lots = value['lots']
    if not isinstance(lots, list) or not 1 <= len(lots) <= MAX_LOTS:
        raise DocumentError(f'Définissez entre 1 et {MAX_LOTS} lots.')
    lot_ids, names, keys, total = set(), set(), set(), 0
    for position, lot in enumerate(lots, 1):
        if not isinstance(lot, dict) or set(lot) != {'id', 'number', 'name', 'name_ar', 'source_slot', 'items'}:
            raise DocumentError('Lot incomplet ou propriété non reconnue.')
        if not valid_uuid(lot['id']) or lot['id'] in lot_ids:
            raise DocumentError('Identifiant de lot invalide ou dupliqué.')
        lot_ids.add(lot['id'])
        if type(lot['number']) is not int or lot['number'] != position:
            raise DocumentError('La numérotation des lots doit être continue.')
        text(lot['name'], f'Lot {position} : nom', 180, required=True)
        text(lot['name_ar'], f'Lot {position} : nom arabe', 240)
        name_key = ' '.join(lot['name'].split()).casefold()
        if name_key in names:
            raise DocumentError(f'Lot {position} : ce nom de lot existe déjà.')
        names.add(name_key)
        if type(lot['source_slot']) is not int or not 0 <= lot['source_slot'] <= MAX_LOTS:
            raise DocumentError('Emplacement documentaire du lot invalide.')
        if not isinstance(lot['items'], list) or len(lot['items']) > MAX_ITEMS:
            raise DocumentError(f'Lot {position} : liste des articles invalide.')
        total += len(lot['items'])
        for number, item in enumerate(lot['items'], 1):
            if not isinstance(item, dict) or set(item) != set(FIELDS) | {'key', 'position'}:
                raise DocumentError(f'Lot {position}, article {number} : colonnes non reconnues ; les prix ne sont pas des données de besoin.')
            key = item['key']
            if not isinstance(key, str) or key in keys or not re.fullmatch(r'(?:source-[1-9]\d?-[1-9]\d{0,3}|new-[0-9a-f-]{36})', key):
                raise DocumentError(f'Lot {position}, article {number} : identifiant invalide ou dupliqué.')
            if key.startswith('new-') and not valid_uuid(key[4:]):
                raise DocumentError('Identifiant du nouvel article invalide.')
            keys.add(key)
            if type(item['position']) is not int or item['position'] != number:
                raise DocumentError('La numérotation des articles doit être continue dans chaque lot.')
            label = f'Lot {position}, article {number}'
            text(item['designation'], label + ' : désignation', 30000, required=True, multiline=True)
            text(item['specifications'], label + ' : caractéristiques', 30000, required=False, multiline=True)
            text(item['unit'], label + ' : unité', 100, required=True)
            text(item['packaging'], label + ' : conditionnement', 600, multiline=True)
            text(item['details'], label + ' : informations associées', 10000, multiline=True)
            quantity(item['quantity'])
    if total > MAX_ITEMS:
        raise DocumentError(f'Le dossier ne peut pas dépasser {MAX_ITEMS} articles.')
    return value


def replace_catalog(data, catalog):
    validate_catalog(catalog)
    result = copy.deepcopy(data)
    result.pop('procurement', None)
    result['lot_catalog'] = copy.deepcopy(catalog)
    return result


def diff_catalog(before, after):
    old_lots = {lot['id']: lot for lot in before['lots']}
    rows, totals = [], {'added': 0, 'updated': 0, 'removed': 0, 'unchanged': 0}
    for lot in after['lots']:
        previous = old_lots.get(lot['id'], {'items': []})
        old = {i['key']: i for i in previous['items']}
        new = {i['key']: i for i in lot['items']}
        for key in dict.fromkeys([*new, *old]):
            action = 'added' if key not in old else 'removed' if key not in new else 'unchanged' if new[key] == old[key] else 'updated'
            totals[action] += 1
            if action != 'unchanged':
                item = new.get(key, old.get(key))
                fields = [f for f in (*FIELDS, 'position') if key in old and key in new and old[key][f] != new[key][f]]
                rows.append({'lot': lot['name'], 'number': item['position'], 'designation': item['designation'],
                             'action': action, 'fields': fields, 'before': old.get(key), 'after': new.get(key)})
    return {'totals': totals, 'rows': rows, 'lots': len(after['lots']), 'items': sum(len(l['items']) for l in after['lots'])}
