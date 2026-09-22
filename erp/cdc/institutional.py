"""Versioned institutional decisions applied only to explicitly bound dossiers."""
from __future__ import annotations
import functools
import json
import re
from pathlib import Path
from .docengine import DocumentError, sha

CURRENT_POLICY = 'ESSBO_COORD_LOTS_20260907_V1'
POLICY_SHA256 = '3506566c0a7c12ac5f5a8b12f26b7b2b833c0290014fe74e079f43e612e77b28'
PHONE = re.compile(r'(?<!\d)0\d{2}\.\d{2}\.\d{2}\.\d{2}(?!\d)')
POSTAL = re.compile(r'(?<!\d)31\d{3}(?!\d)')

@functools.lru_cache(maxsize=1)
def policy():
    path = Path(__file__).resolve().parents[1]/'assets/institutional'/f'{CURRENT_POLICY}.json'
    raw = path.read_bytes()
    if sha(raw) != POLICY_SHA256:
        raise DocumentError('Le référentiel institutionnel a changé sans nouvelle version validée.')
    value = json.loads(raw)
    if value.get('schema') != 1 or value.get('id') != CURRENT_POLICY:
        raise DocumentError('Version institutionnelle incohérente.')
    return value

def validate_policy(data):
    if 'institutional_policy' in data:
        if data['institutional_policy'] != CURRENT_POLICY:
            raise DocumentError('Version institutionnelle inconnue : aucune correction implicite appliquée.')
        if policy()['source_sha256'].get(data['family']) != data['source_sha256']:
            raise DocumentError('Le référentiel ne correspond pas à ce modèle institutionnel.')

def _transform(text, binding, values):
    if 'phone_fax' in binding['keys']:
        allowed = set(PHONE.findall(binding['before'])) | {values['phone_fax']}
        found = PHONE.findall(text)
        if not found or not set(found) <= allowed:
            raise DocumentError('Coordonnées en conflit avec le numéro institutionnel validé.')
        text = text.replace('041.24.63.69 /: 041.24.63.76', values['phone_fax'])
        text = PHONE.sub(lambda _: values['phone_fax'], text)
        if PHONE.findall(text) != [values['phone_fax']]:
            raise DocumentError('Plusieurs numéros institutionnels dans un emplacement unique.')
    if 'postal_code' in binding['keys']:
        allowed = set(POSTAL.findall(binding['before'])) | {values['postal_code']}
        found = POSTAL.findall(text)
        if not found or not set(found) <= allowed:
            raise DocumentError('Code postal en conflit avec les coordonnées validées.')
        text = POSTAL.sub(lambda _: values['postal_code'], text)
    if 'reagents_ar_lot_numbers' in binding['keys']:
        if text not in (binding['before'], binding['after']):
            raise DocumentError('Numérotation arabe en conflit avec les lots validés.')
        text = binding['after']
    return text

def resolved_issue(data, issue_id):
    return (data.get('institutional_policy') == CURRENT_POLICY
            and issue_id in policy()['resolved_issue_ids'])

def apply_policy_edits(data, paragraphs, spans):
    validate_policy(data)
    if 'institutional_policy' not in data:
        return paragraphs, spans
    from .catalog import document
    doc = document(data['family'])
    manifest = policy()
    for binding in manifest['bindings'][data['family']]:
        pid, segment = binding['id'], binding['segment']
        if pid not in doc.paragraphs:
            raise DocumentError('Ancrage institutionnel absent du modèle vérifié.')
        islands = doc.editable_segments(pid)
        if segment >= len(islands) or ''.join(n.characters for n in islands[segment]) != binding['before']:
            raise DocumentError('Le texte source institutionnel ne correspond plus à son ancrage.')
        if pid in data.get('omitted', []):
            raise DocumentError('Un emplacement institutionnel obligatoire a été supprimé.')
        if pid in paragraphs:
            paragraphs[pid] = _transform(paragraphs[pid], binding, manifest['values'])
            continue
        operations = spans.get(pid, [])
        existing = next((op for op in operations if op['segment'] == segment), None)
        current = existing['after'] if existing else binding['before']
        after = _transform(current, binding, manifest['values'])
        if existing:
            existing['after'] = after
        elif after != binding['before']:
            spans.setdefault(pid, []).append({'segment': segment, 'before': binding['before'], 'after': after})
    return paragraphs, spans

def policy_report(data):
    if 'institutional_policy' not in data:
        return {'status': 'LEGACY_UNCHANGED', 'reason': 'Aucune nouvelle décision appliquée à une révision ancienne.'}
    manifest = policy()
    bindings = manifest['bindings'][data['family']]
    return {'status': 'APPLIED_SOURCE_BOUND', 'version': manifest['id'],
            'sha256': POLICY_SHA256, 'authority': manifest['authority'],
            'confirmed_utc': manifest['confirmed_utc'],
            'verified_segments': len(bindings),
            'source_corrections': sum(b['before'] != b['after'] for b in bindings),
            'legal_validation': 'NOT_CLAIMED', 'originals_modified': False}
