"""Source-bound removal of confirmed foreign/template residue."""
from __future__ import annotations
from .docengine import DocumentError

NOISE = {
    'equipment': {
        'word/footer1.xml:p0:6834993004d0': 'Université Djillali Liabès de Sidi Bel-Abbès.     Licence en\u00a0Electrotechnique.     3ème Année.     Semestre 527',
        'word/footer3.xml:p0:5d4a243efdeb': 'Université Djillali Liabès de Sidi Bel-Abbès.  Licence en\u00a0Electrotechnique. 3ème Année, Semestre 527',
    },
    'reagents': {
        'word/footer1.xml:p0:d12df44af6a3': 'Université Djillali Liabès de Sidi Bel-Abbès.     Licence en\u00a0Electrotechnique.     3ème Année.     Semestre 527',
        'word/footer3.xml:p0:e58956bcaa0b': 'Université Djillali Liabès de Sidi Bel-Abbès.  Licence en\u00a0Electrotechnique. 3ème Année, Semestre 527',
    },
    'works': {
        'word/footer1.xml:p0:9ad256d37afc': 'Université Djillali Liabès de Sidi Bel-Abbès. Licence en\u00a0Electrotechnique. 3ème Année.Semestre 527',
    },
}

def noise_ids(family):
    return set(NOISE.get(family, {}))
def apply_noise_spans(family, spans, doc):
    result = {key: list(value) for key, value in spans.items()}
    removed = []
    for pid, expected in NOISE.get(family, {}).items():
        block = next((b for b in doc.source_index if b['id'] == pid), None)
        if block is None or block['part'] == 'word/document.xml' or block['text'] != expected:
            raise DocumentError('Le pied de page parasite ne correspond plus à son ancrage vérifié.')
        segments = doc.editable_segments(pid)
        if len(segments) != 1:
            raise DocumentError('Structure du pied de page parasite non reconnue.')
        before = ''.join(n.characters for n in segments[0])
        if 'Université Djillali Liabès de Sidi Bel-Abbès' not in before:
            raise DocumentError('Texte parasite attendu absent de son segment modifiable.')
        operations = result.setdefault(pid, [])
        if any(op['segment'] == 0 for op in operations):
            raise DocumentError('Conflit de nettoyage du pied de page.')
        operations.append({'segment': 0, 'before': before, 'after': ''})
        removed.append(pid)
    return result, {'status': 'REMOVED_TEXT_PRESERVED_WORD_FIELDS', 'removed': removed}
