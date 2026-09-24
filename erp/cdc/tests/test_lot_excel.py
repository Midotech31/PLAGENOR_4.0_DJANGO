"""Round-trip, fail-closed intake and source-layout regressions for Excel lots."""
import copy
import io
import json
import sys
import uuid
import zipfile
from pathlib import Path
from decimal import Decimal
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'app'))
from erp.cdc.catalog import initial_data, document, generate_document, validate_data, controls
from erp.cdc.docengine import Document, DocumentError, NS, sha
from erp.cdc.lot_catalog import get_catalog, replace_catalog, validate_catalog, fingerprint
from erp.cdc.lot_workbook import build_workbook, parse_workbook, xml, dump, cell, Q, WorkbookError
from erp.cdc.schedule_adapter import source_mapping, children, cell_paragraphs, field_value

DOSSIER = str(uuid.UUID('56d41149-6756-4c7a-a435-121089d0259e'))

def state(family='equipment'):
    d=initial_data(family)
    return replace_catalog(d,get_catalog(d))


def book(d, filled=True):
    return build_workbook(d,DOSSIER,2,json.dumps,filled=filled)


def read(b,d,mode='merge'):
    return parse_workbook(b,'articles.xlsx',d,DOSSIER,2,json.loads,mode=mode)


def change(b, sheet, updates=None, mutator=None):
    out=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(b)) as z,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as result:
        for info in z.infolist():
            raw=z.read(info.filename)
            if info.filename==f'xl/worksheets/sheet{sheet+1}.xml':
                root=xml(raw)
                for address,value in (updates or {}).items():cell(root,address,value)
                if mutator:mutator(root)
                raw=dump(root)
            result.writestr(info,raw)
    return out.getvalue()


@pytest.mark.parametrize('family,count',[('equipment',23),('reagents',184)])
def test_filled_excel_roundtrip_keeps_entire_source_byte_identical(family,count):
    d=state(family);d.pop('institutional_policy',None);p=read(book(d),d)
    assert p['diff']['totals']=={'added':0,'updated':0,'removed':0,'unchanged':count}
    result,report=generate_document(p['data'])
    assert result==document(family).data
    assert report['lot_catalog']['status']=='UNCHANGED'


@pytest.mark.parametrize('family',['equipment','reagents','works'])
def test_named_lots_have_dedicated_sheets_with_signed_metadata(family):
    d=state(family);b=book(d,False)
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        workbook=xml(z.read('xl/workbook.xml'));names=[s.get('name') for s in workbook.find(Q+'sheets')]
        assert names==['Mode_emploi',*[f'Lot_{i:02d}' for i in range(1,len(d['lot_catalog']['lots'])+1)],'_CDC']
        assert list(workbook.find(Q+'sheets'))[-1].get('state')=='veryHidden'
        assert not any(n.lower().endswith(('.ttf','.otf','.woff','.woff2')) for n in z.namelist())


def test_addition_uses_one_record_in_all_three_pieces_and_retains_unmodified_parts():
    d=state();d.pop('institutional_policy',None);b=book(d)
    b=change(b,1,{'B15':'Étagère de démonstration','C15':'Deux compartiments.\nFinition lisse.','D15':'U','F15':'2,5','E15':'Une pièce','G15':'Documentation de test.'})
    p=read(b,d);assert p['diff']['totals']['added']==1
    output,report=generate_document(p['data']);generated=Document(output);original=document('equipment')
    changed_tables=[t for t in report['lot_catalog']['tables'] if t['lot']==1]
    assert {t['piece'] for t in changed_tables}=={'CPTC','BPU','DQE'}
    for kind,t in source_mapping('equipment')[0]['tables'].items():
        node=next(n for part,n in generated.tables.values() if part=='word/document.xml' and n.index==t['node'].index)
        assert 'Étagère de démonstration' in node.text
        if kind=='cptc':assert 'Documentation de test.' in node.text
    for name in original.z.namelist():
        if name!='word/document.xml':assert original.z.read(name)==generated.z.read(name)


@pytest.mark.parametrize('family',['equipment','reagents'])
def test_new_items_in_every_lot_and_safe_number_cells(family):
    d=state(family)
    for lot in d['lot_catalog']['lots']:
        lot['items'].append({'key':'new-'+str(uuid.uuid4()),'position':len(lot['items'])+1,
                            'designation':'Article neutre de test','specifications':'Caractéristiques de test.\nDeux éléments.',
                            'unit':'U','quantity':'3','packaging':'Une pièce','details':''})
    output,report=generate_document(d);g=Document(output)
    assert len(report['lot_catalog']['tables'])==len(d['lot_catalog']['lots'])*3
    for source,lot in zip(source_mapping(family),d['lot_catalog']['lots']):
        for kind,t in source['tables'].items():
            node=next(n for part,n in g.tables.values() if part=='word/document.xml' and n.index==t['node'].index)
            rows=children(node,'tr');assert len(rows)==len(lot['items'])+(4 if kind=='dqe' else 1)
            assert 'Article neutre de test' in node.text
            for row in rows[1:len(lot['items'])+1]:
                cells=children(row,'tc')
                indices=(3,) if kind=='bpu' else (2,4) if kind=='dqe' and family=='equipment' else (2,5) if kind=='dqe' else ()
                for idx in indices:assert field_value(cell_paragraphs(cells[idx]))==''


def test_names_propagate_to_cover_annexes_and_arabic_without_style_rebuild():
    d=state();d['lot_catalog']['lots'][0].update(name='Équipements du projet pilote',name_ar='تجهيزات المشروع التجريبي')
    output,report=generate_document(d);g=Document(output)
    count=sum('Équipements du projet pilote' in b['text'] for b in g.source_index)
    reported=next(x['paragraphs'] for x in report['lot_catalog']['lot_names'] if x['lot']==1 and x['language']=='fr')
    assert count==reported and count>=20
    assert any('تجهيزات المشروع التجريبي' in b['text'] for b in g.source_index)
    original=document('equipment')
    for name in ('word/styles.xml','word/numbering.xml'):
        assert g.z.read(name)==original.z.read(name)
    for name in original.z.namelist():
        if name.startswith('word/media/'):assert g.z.read(name)==original.z.read(name)


def test_changed_lot_name_accepts_existing_arabic_but_blank_arabic_blocks():
    d=state();d['lot_catalog']['lots'][0]['name']='Nouveau nom'
    assert not any(f['id']=='LOT_AR_NAME' for f in controls(d))
    assert len(book(d))>1000
    generate_document(d)
    d['lot_catalog']['lots'][0]['name_ar']=''
    assert any(f['id']=='LOT_AR_NAME' for f in controls(d))
    with pytest.raises(DocumentError):generate_document(d)
    d=state();d['lot_catalog']['lots'].pop()
    assert any(f['id']=='LOT_ANNEX_MAPPING' for f in controls(d))
    with pytest.raises(DocumentError):generate_document(d)


@pytest.mark.parametrize('field,value,address', [('quantity','0','F7'),('quantity','-1','F7'),('quantity','0,0000001','F7'),('quantity','','F7'),('designation','','B7'),('specifications','','C7'),('unit','','D7')])
def test_exact_cell_errors_and_no_input_mutation(field,value,address):
    d=state();before=fingerprint(d);b=change(book(d),1,{address:value})
    with pytest.raises(WorkbookError) as e:read(b,d)
    assert any(i['sheet']=='Lot_01' and i['cell']==address for i in e.value.issues)
    assert fingerprint(d)==before


def test_formula_refused_even_when_cached_value_exists():
    d=state()
    def inject(root):
        import xml.etree.ElementTree as ET
        c=next(c for c in root.iter(Q+'c') if c.get('r')=='F7');ET.SubElement(c,Q+'f').text='1+1'
    with pytest.raises(DocumentError,match='formules'):read(change(book(d),1,mutator=inject),d)


def test_metadata_changed_cross_dossier_and_stale_revision_rejected():
    d=state();b=book(d)
    with pytest.raises(DocumentError,match='autre dossier'):parse_workbook(b,'a.xlsx',d,str(uuid.uuid4()),2,json.loads)
    with pytest.raises(DocumentError,match='changé'):parse_workbook(b,'a.xlsx',d,DOSSIER,3,json.loads)
    d2=copy.deepcopy(d);d2['notes']='Une note nouvelle.'
    with pytest.raises(DocumentError,match='changé'):read(b,d2)
    with pytest.raises(DocumentError,match='identité'):parse_workbook(b,'a.xlsx',d,DOSSIER,2,lambda _:(_ for _ in ()).throw(ValueError()))


def test_wrong_sheet_header_identity_and_duplicate_keys_rejected():
    d=state();b=book(d)
    with pytest.raises(DocumentError,match='en-têtes'):read(change(b,1,{'B6':'Prix'}),d)
    with pytest.raises(DocumentError,match='nom du lot'):read(change(b,1,{'A1':'Lot incorrect'}),d)
    with pytest.raises(WorkbookError):read(change(b,1,{'I8':'source-1-1'}),d)
    with pytest.raises(WorkbookError):read(change(b,1,{'I8':'source-2-1'}),d)


def test_replace_preview_detects_deletions_but_merge_keeps_absent_rows():
    d=state();b=book(d)
    updates={f'{c}8':'' for c in 'BCDEFGH'}
    p=read(change(b,1,updates),d,'replace');assert p['diff']['totals']['removed']==1
    merged=read(change(b,1,updates),d,'merge');assert merged['diff']['totals']['removed']==0
    assert len(merged['data']['lot_catalog']['lots'][0]['items'])==8


def test_empty_workbook_never_clears_existing_items():
    d=state()
    with pytest.raises(DocumentError):read(book(d,False),d,'replace')
    with pytest.raises(DocumentError):read(book(d,False),d,'merge')


def test_decimal_exponent_bomb_rejected_without_expansion():
    d=state()
    def bomb(root):cell(root,'F7','1E-99999999',numeric=True)
    with pytest.raises(WorkbookError):read(change(book(d),1,mutator=bomb),d)


def test_custom_lots_can_be_prepared_in_excel_without_silent_document_substitution():
    d=state('works');d['lot_catalog']['lots'][0]['name']='Travaux de test'
    new=copy.deepcopy(d['lot_catalog']['lots'][0]);new.update(id=str(uuid.uuid4()),number=2,name='Autre corps d’état',source_slot=0,items=[])
    d['lot_catalog']['lots'].append(new)
    b=book(d,False);b=change(b,1,{'B7':'Élément de test','C7':'Descriptif fourni.','D7':'U','F7':'2'})
    p=read(b,d);assert p['diff']['totals']['added']==1
    with pytest.raises(DocumentError,match='travaux'):generate_document(p['data'])

@pytest.mark.parametrize('family',['equipment','reagents'])
def test_entire_source_article_lists_can_be_replaced_without_orphan_bookmarks(family):
    d=state(family)
    for lot in d['lot_catalog']['lots']:
        lot['items']=[{'key':'new-'+str(uuid.uuid4()),'position':1,'designation':'Mobilier de test',
                       'specifications':'Surface plane.\nAssemblage de test.','unit':'U','quantity':'2',
                       'packaging':'Une pièce','details':''}]
    output,report=generate_document(d);g=Document(output)
    assert len(report['lot_catalog']['tables'])==len(d['lot_catalog']['lots'])*3
    root=g.parts['word/document.xml'][1]
    starts={n.attrs.get(NS+'id') for n in root.descendants(NS+'bookmarkStart')}
    ends={n.attrs.get(NS+'id') for n in root.descendants(NS+'bookmarkEnd')}
    old=document(family).parts['word/document.xml'][1]
    old_starts={n.attrs.get(NS+'id') for n in old.descendants(NS+'bookmarkStart')}
    old_ends={n.attrs.get(NS+'id') for n in old.descendants(NS+'bookmarkEnd')}
    assert (starts^ends) <= (old_starts^old_ends)


def test_works_excel_roundtrip_keeps_source_identical():
    d=state('works');d.pop('institutional_policy',None);assert len(d['lot_catalog']['lots'][0]['items'])==249
    parsed=read(book(d),d)
    output,report=generate_document(parsed['data'])
    assert output==document('works').data
    assert report['lot_catalog']['status']=='UNCHANGED'


def test_works_updates_bpu_dqe_without_rebuilding_cptc_or_prices():
    d=state('works');d.pop('institutional_policy',None);item=d['lot_catalog']['lots'][0]['items'][0]
    item['designation']='Dépose contrôlée du faux plafond existant'
    item['specifications']='Évacuation comprise et protection des locaux.'
    item['quantity']='451'
    output,report=generate_document(d);g=Document(output);src=document('works')
    assert {x['piece'] for x in report['lot_catalog']['tables']}=={'BPU','DQE'}
    for idx in (16,17):
        table=next(n for part,n in g.tables.values() if part=='word/document.xml' and n.index==idx)
        assert 'Dépose contrôlée du faux plafond existant' in table.text
    assert '451' in next(n for part,n in g.tables.values() if part=='word/document.xml' and n.index==17).text
    for name in src.z.namelist():
        if name!='word/document.xml':assert src.z.read(name)==g.z.read(name)



def test_merge_ignores_visible_empty_row_that_keeps_hidden_identifier():
    d=state('reagents');b=book(d)
    updates={f'{c}17':'' for c in 'BCDEFG'}  # H17 keeps source-1-11
    parsed=read(change(b,1,updates),d,'merge')
    lot=parsed['data']['lot_catalog']['lots'][0]
    assert len(lot['items'])==15
    assert lot['items'][10]['key']=='source-1-11'
    assert lot['items'][10]['designation']==d['lot_catalog']['lots'][0]['items'][10]['designation']


def test_missing_entire_hidden_identifier_column_recovers_existing_ids_by_order():
    d=state('reagents');b=book(d)
    updates={f'H{row}':'' for row in range(7,191)}
    parsed=read(change(b,1,updates),d,'merge')
    lot=parsed['data']['lot_catalog']['lots'][0]
    assert [i['key'] for i in lot['items']]==[i['key'] for i in d['lot_catalog']['lots'][0]['items']]
    assert parsed['diff']['totals']['added']==0


@pytest.mark.parametrize('family,new_name',[('equipment','LOT TEST EQUIPMENT'),('works','LOT TEST WORKS')])
def test_custom_lot_name_replaces_all_canonical_occurrences_outside_item_tables(family,new_name):
    d=state(family);d.pop('institutional_policy',None)
    lot=d['lot_catalog']['lots'][0];old=lot['name'];lot['name']=new_name
    if family=='equipment':lot['name_ar']='حصة اختبار'
    output,report=generate_document(d);g=Document(output)
    assert any(x['lot']==1 and x['language']=='fr' for x in report['lot_catalog']['lot_names'])
    item_tables={t['node'].index for src in source_mapping(family) for t in src['tables'].values()}
    residual=[]
    for b in g.source_index:
        part,p=g.paragraphs[b['id']];owner=p.ancestor(NS+'tbl')
        if part=='word/document.xml' and owner is not None and owner.index in item_tables:continue
        if old in b['text']:residual.append(b['id'])
    assert not residual


def test_optional_financial_estimate_roundtrip_never_enters_document_data():
    d=state();key=d['lot_catalog']['lots'][0]['items'][0]['key'];marker='987654321.12'
    b=build_workbook(d,DOSSIER,2,json.dumps,filled=True,estimates={key:Decimal(marker)})
    parsed=read(b,d)
    assert parsed['financial'][key]==marker
    assert 'financial' not in parsed['data'] and 'estimated_unit_price' not in json.dumps(parsed['data'])
    output,_=generate_document(parsed['data'])
    assert marker.encode() not in output


def test_legacy_eight_column_workbook_still_imports_without_financial_values():
    d=state();b=book(d);lot=d['lot_catalog']['lots'][0]
    updates={'H6':'Identifiant interne','I6':''}
    for row,item in enumerate(lot['items'],7):updates[f'H{row}']=item['key'];updates[f'I{row}']=''
    parsed=read(change(b,1,updates),d)
    assert set(parsed['financial']).isdisjoint({i['key'] for i in lot['items']})
    assert all(value is None for value in parsed['financial'].values())
    assert parsed['diff']['totals']['updated']==0


from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
