"""Consultation metadata must propagate without rewriting unrelated Word structures."""
import copy
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from erp.cdc.catalog import initial_data,generate_document,document,controls
from erp.cdc.consultation import DEFAULTS
from erp.cdc.docengine import Document,DocumentError


def changed(family):
    d=initial_data(family)
    c=d['consultation']
    c.update({'object_fr':'OBJET INSTITUTIONNEL TEST '+family,
              'object_ar':'موضوع مؤسساتي تجريبي '+family,
              'financing_label':'Budget institutionnel test','budget_year':2027,
              'preparation_days':30,'preparation_fr':'Trente (30) jours',
              'preparation_ar':'ثلاثون (30) يوما','deposit_time':'11:30',
              'opening_time':'11:45','validity_months':4,
              'validity_fr':'Quatre (04) mois','validity_ar':'أربعة (04) أشهر'})
    if family!='reagents': c['operation_fr']='OPÉRATION INSTITUTIONNELLE TEST '+family
    c['confirmed']=True
    if family=='reagents': c['withdrawal_ar']=c['withdrawal_ar'].replace('0000324044','00831001131000208471')
    return d

@pytest.mark.parametrize('family',['equipment','reagents','works'])
def test_legacy_without_policy_and_default_consultation_is_byte_identical(family):
    d=initial_data(family);d.pop('institutional_policy',None)
    output,report=generate_document(d)
    assert output==document(family).data
    assert report['consultation']['status']=='UNCHANGED'

@pytest.mark.parametrize('family',['equipment','reagents','works'])
def test_changed_consultation_reaches_source_bound_occurrences(family):
    d=changed(family);output,report=generate_document(d);g=Document(output)
    text='\n'.join(b['text'] for b in g.source_index)
    c=d['consultation']
    assert c['object_fr'] in text and c['object_ar'] in text
    assert c['preparation_fr'] in text and c['preparation_ar'] in text
    assert c['validity_fr'] in text and c['validity_ar'] in text
    assert report['consultation']['status']=='GENERATED'
    assert report['consultation']['fields']['object_fr']>=10

def test_new_dossier_requires_explicit_information_confirmation():
    d=initial_data('equipment')
    errors={x['id'] for x in controls(d) if x['severity']=='error'}
    assert 'CONSULTATION_CONFIRMATION' in errors
    d['consultation']['confirmed']=True
    errors={x['id'] for x in controls(d) if x['severity']=='error'}
    assert 'CONSULTATION_CONFIRMATION' not in errors


def test_reagents_requires_same_withdrawal_account_in_both_languages():
    d=initial_data('reagents');d['consultation']['confirmed']=True
    with pytest.raises(DocumentError,match='même numéro de compte'):
        controls(d)
    d['consultation']['withdrawal_ar']=d['consultation']['withdrawal_ar'].replace('0000324044','00831001131000208471')
    errors={x['id'] for x in controls(d) if x['severity']=='error'}
    assert 'WITHDRAWAL_ACCOUNT_BILINGUAL' not in errors


from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
