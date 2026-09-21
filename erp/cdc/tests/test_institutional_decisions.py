"""User-approved coordinates and Arabic lot numbering; no template mutation."""
import copy
import re
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from erp.cdc.catalog import initial_data, document, generate_document, effective_edits, controls
from erp.cdc.docengine import Document, DocumentError, NS, sha
from erp.cdc.institutional import CURRENT_POLICY, policy
from erp.cdc.source_noise import noise_ids

@pytest.mark.parametrize('family,changes', [('equipment',3),('reagents',6),('works',5)])
def test_approved_corrections_are_complete_and_only_touch_authorized_text(family, changes):
    data = initial_data(family)
    assert data['institutional_policy'] == CURRENT_POLICY
    before_data = copy.deepcopy(data)
    original = document(family)
    output, report = generate_document(data)
    generated = Document(output)
    assert data == before_data
    assert report['institutional_policy']['source_corrections'] == changes
    assert report['institutional_policy']['status'] == 'APPLIED_SOURCE_BOUND'
    texts = '\n'.join(b['text'] for b in generated.source_index)
    assert set(re.findall(r'041\.24\.63\.\d{2}', texts)) == {'041.24.63.76'}
    assert not re.search(r'(?<!\d)31003(?!\d)', texts)
    assert '31000' in texts
    assert '041.24.63.76 /: 041.24.63.76' not in texts
    assert len(original.source_index) == len(generated.source_index)
    authorized = {b['id'] for b in policy()['bindings'][family] if b['before'] != b['after']} | noise_ids(family)
    actual = set()
    for old, new in zip(original.source_index, generated.source_index):
        assert (old['part'], old['index']) == (new['part'], new['index'])
        if old['text'] != new['text']:
            actual.add(old['id'])
        else:
            part, p = original.paragraphs[old['id']]
            _, q = generated.paragraphs[new['id']]
            assert original.parts[part][0][p.start:p.end] == generated.parts[part][0][q.start:q.end]
    assert actual == authorized
    noise_parts={original.paragraphs[pid][0] for pid in noise_ids(family)}
    for name in original.z.namelist():
        if name != 'word/document.xml' and name not in noise_parts:
            assert original.z.read(name) == generated.z.read(name)
    redact_text = lambda raw: re.sub(rb'(<w:t\b[^>]*>).*?(</w:t>)', rb'\1\2', raw, flags=re.S)
    assert redact_text(original.z.read('word/document.xml')) == redact_text(generated.z.read('word/document.xml'))
    if family == 'reagents':
        labels = [b['text'] for b in generated.source_index if b['part']=='word/document.xml' and b['index'] in (671,673,675,677)]
        assert labels == ['الحصة 01','الحصة 02','الحصة 03','الحصة 04']
    assert sha(original.data) == original.digest

@pytest.mark.parametrize('family', ['equipment','reagents','works'])
def test_legacy_revision_is_never_silently_corrected(family):
    data = initial_data(family)
    data.pop('institutional_policy')
    output, report = generate_document(data)
    assert output == document(family).data
    assert report['institutional_policy']['status'] == 'LEGACY_UNCHANGED'

@pytest.mark.parametrize('family', ['equipment','reagents','works'])
def test_new_reference_and_confirmed_coordinates_compose(family):
    data = initial_data(family)
    data['reference'] = '17/SME/SDFM/SG/ESSBO/2027'
    output, report = generate_document(data)
    texts = '\n'.join(b['text'] for b in Document(output).source_index)
    assert '17/SME/SDFM/SG/ESSBO/2027' in texts
    assert set(re.findall(r'041\.24\.63\.\d{2}', texts)) == {'041.24.63.76'}
    assert report['reference_propagation']['status'] == 'PASS'

def test_unknown_policy_and_manual_conflict_are_rejected():
    data = initial_data('equipment')
    data['institutional_policy'] = 'UNAPPROVED'
    with pytest.raises(DocumentError):
        generate_document(data)
    data = initial_data('equipment')
    data['paragraphs']['word/document.xml:p29:c09c36f58ad8'] = 'Tél/ Fax : 044.22.11.00'
    with pytest.raises(DocumentError, match='conflit'):
        generate_document(data)

def test_only_confirmed_issue_is_closed_and_preview_uses_same_plan():
    data = initial_data('reagents')
    ids = {f['id'] for f in controls(data)}
    assert 'ESSBO-006' not in ids
    assert {'ESSBO-004','ESSBO-005'} <= ids
    edits = effective_edits(data)
    assert edits['word/document.xml:p675:1322f6553c77'] == 'الحصة 03'
    assert '041.24.63.76' in edits['word/document.xml:p719:0b8ee579e8b0']


from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
