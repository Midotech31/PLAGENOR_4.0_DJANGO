import io,sys,zipfile
from pathlib import Path
from lxml import etree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from erp.cdc.catalog import initial_data,generate_document,document
from erp.cdc.word_layout import normalize_word_layout,W
NS={'w':W};Q=lambda n:f'{{{W}}}{n}'

def test_output_only_layout_centers_headers_footers_and_requests_field_refresh():
    raw,_=generate_document(initial_data('reagents'));normalized,report=normalize_word_layout(raw)
    assert report['update_fields'] and report['headers_centered']+report['footers_centered']>0
    assert document('reagents').data!=b''
    with zipfile.ZipFile(io.BytesIO(normalized)) as z:
        settings=etree.fromstring(z.read('word/settings.xml'))
        assert settings.find(Q('updateFields')).get(Q('val'))=='true'
        for name in z.namelist():
            if not ((name.startswith('word/header') or name.startswith('word/footer')) and name.endswith('.xml')):continue
            root=etree.fromstring(z.read(name))
            for p in root.xpath('.//w:p',namespaces=NS):
                if not (''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip() or p.xpath('.//w:fldChar|.//w:instrText',namespaces=NS)):continue
                jc=p.find('./w:pPr/w:jc',NS);assert jc is not None and jc.get(Q('val'))=='center'

def test_layout_normalization_is_idempotent():
    raw,_=generate_document(initial_data('equipment'));first,_=normalize_word_layout(raw);second,report=normalize_word_layout(first)
    assert second==first and report['update_fields']

from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
