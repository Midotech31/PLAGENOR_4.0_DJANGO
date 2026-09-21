"""Repeated CDC metadata is derived once and reused across document pieces."""
import copy,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from erp.cdc.catalog import initial_data,document,controls,profile
from erp.cdc.common_data import canonical_summary,common_ownership,projected_edits,manual_conflicts
from erp.cdc.lot_catalog import get_catalog,replace_catalog

@pytest.mark.parametrize('family,count',[('equipment',2),('reagents',4),('works',1)])
def test_summary_derives_lot_count_and_shared_information(family,count):
    data=initial_data(family);summary=canonical_summary(data)
    assert summary['lots_count']==count
    assert summary['reference']==data['reference']
    assert summary['object_fr']==data['consultation']['object_fr']
    assert len(summary['lots'])==count
    assert summary['postal_code']=='31000'
    assert summary['phone_fax']=='041.24.63.76'

@pytest.mark.parametrize('family',['equipment','reagents','works'])
def test_common_ownership_covers_information_reference_and_policy(family):
    data=initial_data(family);owned=common_ownership(data)
    sources={source for item in owned.values() for source in item['sources']}
    assert {'Informations','Référentiel ESSBO'} <= sources
    assert any('reference' in item['fields'] for item in owned.values())
    assert any('object_fr' in item['fields'] for item in owned.values())


def test_renamed_lot_is_projected_into_document_pieces_without_second_entry():
    data=initial_data('equipment');catalog=get_catalog(data)
    catalog['lots'][0]['name']='Équipements analytiques du projet'
    catalog['lots'][0]['name_ar']='معدات تحليلية للمشروع'
    data=replace_catalog(data,catalog)
    edits=projected_edits(data);owned=common_ownership(data)
    assert any('Équipements analytiques du projet' in text for text in edits.values())
    assert any('معدات تحليلية للمشروع' in text for text in edits.values())
    assert any('Lots et articles' in item['sources'] for item in owned.values())


def test_information_change_is_projected_everywhere_without_manual_copy():
    data=initial_data('equipment');data['reference']='17/SME/SDFM/SG/ESSBO/2027'
    data['consultation']['object_fr']='Acquisition institutionnelle synchronisée en 02 lots'
    edits=projected_edits(data)
    assert sum('17/SME/SDFM/SG/ESSBO/2027' in text for text in edits.values()) >= 5
    assert sum('Acquisition institutionnelle synchronisée en 02 lots' in text for text in edits.values()) >= 5


def test_bidder_lot_choice_remains_bidder_owned():
    data=initial_data('equipment');owned=common_ownership(data);doc=document('equipment')
    blocks=[b for b in doc.source_index if 'Préciser les numéros des lots concernés' in b['text']]
    assert blocks
    assert all(b['id'] not in owned for b in blocks)


def test_manual_override_of_shared_data_is_blocking():
    data=initial_data('equipment');owned=common_ownership(data);blocks={b['id']:b for b in profile('equipment')['paragraphs']};pid=next(pid for pid in owned if pid in blocks and not blocks[pid]['guard'])
    data['paragraphs'][pid]='Texte manuel concurrent'
    conflicts=manual_conflicts(data)
    assert conflicts and conflicts[0]['id']=='COMMON_DATA_MANUAL_OVERRIDE'
    assert any(x['id']=='COMMON_DATA_MANUAL_OVERRIDE' for x in controls(data))


from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
