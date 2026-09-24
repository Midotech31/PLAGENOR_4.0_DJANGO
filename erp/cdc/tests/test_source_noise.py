import sys
from erp.cdc.catalog import initial_data,generate_document,document
from erp.cdc.source_noise import NOISE,noise_ids


def _all_text(payload):
    from erp.cdc.docengine import Document
    return '\n'.join(block['text'] for block in Document(payload).source_index)


def test_confirmed_foreign_footer_is_removed_from_generated_copies():
    for family in ('equipment','reagents','works'):
        data=initial_data(family)
        payload,report=generate_document(data)
        text=_all_text(payload)
        assert 'Université Djillali Liabès de Sidi Bel-Abbès' not in text
        assert 'Licence en\u00a0Electrotechnique' not in text
        assert report['source_sha256']==document(family).digest


def test_original_models_are_not_modified():
    for family in ('equipment','reagents','works'):
        original=document(family).data
        assert 'Université Djillali Liabès de Sidi Bel-Abbès' in _all_text(original)
        generate_document(initial_data(family))
        assert document(family).data==original


def test_only_reviewed_footer_ids_are_classified_as_noise():
    assert len(noise_ids('equipment'))==2
    assert len(noise_ids('reagents'))==2
    assert len(noise_ids('works'))==1
    assert all(pid.startswith('word/footer') for family in NOISE for pid in noise_ids(family))


def test_noise_cleanup_preserves_word_field_structure():
    from erp.cdc.docengine import Document,NS
    for family in ('equipment','reagents','works'):
        original=document(family)
        payload,_=generate_document(initial_data(family))
        generated=Document(payload)
        for pid in noise_ids(family):
            part,p=original.paragraphs[pid]
            old_field=sum(1 for n in p.descendants() if n.name in (NS+'fldChar',NS+'instrText'))
            block=next(b for b in generated.source_index if b['part']==part and b['index']==p.index)
            _,q=generated.paragraphs[block['id']]
            new_field=sum(1 for n in q.descendants() if n.name in (NS+'fldChar',NS+'instrText'))
            assert old_field>0 and new_field==old_field


from .adapter import source_suite

def load_tests(loader, tests, pattern):
    return source_suite(sys.modules[__name__])
