import copy
import uuid
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from erp.cdc import institutional, procurement, source_noise
from erp.cdc.docengine import DocumentError, NS


class ProcurementDocumentEdgeCoverageTests(SimpleTestCase):
    def item(self, key="source-1-1", designation="D", specifications="S", unit="u", quantity="1"):
        return {"key":key,"designation":designation,"specifications":specifications,"unit":unit,"quantity":quantity}

    def fake_mapping(self):
        fields = {"cptc":{"designation":[Mock()],"specifications":[Mock()]},
                  "bpu":{"designation":[Mock()],"unit":[Mock()]},
                  "dqe":{"designation":[Mock()],"quantity":[Mock()]}}
        one={"data":self.item("source-1-1"),"fields":fields,"row":1}
        two={"data":self.item("source-2-1"),"fields":copy.deepcopy(fields),"row":1}
        return [
            {"number":1,"items":[one],"tables":{},"count":1},
            {"number":2,"items":[two],"tables":{},"count":1},
        ]

    def data(self):
        return {"family":"equipment","paragraphs":{},"rows":{},"procurement":{
            "schema":1,"lots":[
                {"number":1,"items":[self.item("source-1-1")]},
                {"number":2,"items":[self.item("source-2-1")]},
            ]}}

    def test_quantity_decimal_exception_and_paragraph_descendant_filter(self):
        with patch.object(procurement, "Decimal", side_effect=InvalidOperation):
            with self.assertRaises(DocumentError):
                procurement.quantity("1")
        p=Mock()
        own=Mock(name=NS+"t", characters="own")
        own.ancestor.return_value=p
        foreign=Mock(name=NS+"t", characters="foreign")
        foreign.ancestor.return_value=Mock()
        br=Mock(name=NS+"br")
        br.ancestor.return_value=p
        p.descendants.return_value=[foreign,own,br]
        self.assertEqual(procurement.paragraph_value(p),"own\n")

    def test_validate_procurement_rejects_bad_new_key_protected_field_and_global_limit(self):
        mapping=self.fake_mapping()
        bad=self.data()
        bad["procurement"]["lots"][0]["items"][0]["key"]="new-not-a-uuid"
        with patch.object(procurement,"mapping",return_value=mapping),              patch.object(procurement,"managed_paragraphs",return_value=set()):
            with self.assertRaises(DocumentError):
                procurement.validate_procurement(bad,"equipment")

        protected=self.data()
        protected["procurement"]["lots"][0]["items"][0]["designation"]="Changed"
        with patch.object(procurement,"mapping",return_value=mapping),              patch.object(procurement,"managed_paragraphs",return_value=set()),              patch.object(procurement,"editable",return_value=False):
            with self.assertRaises(DocumentError):
                procurement.validate_procurement(protected,"equipment")

        huge=self.data()
        def fresh():
            return self.item("new-"+str(uuid.uuid4()))
        huge["procurement"]["lots"][0]["items"]=[fresh() for _ in range(501)]
        huge["procurement"]["lots"][1]["items"]=[fresh() for _ in range(500)]
        with patch.object(procurement,"mapping",return_value=mapping),              patch.object(procurement,"managed_paragraphs",return_value=set()),              patch.object(procurement,"_text"),              patch.object(procurement,"quantity",return_value=Decimal("1")):
            with self.assertRaises(DocumentError):
                procurement.validate_procurement(huge,"equipment")

    def test_paragraph_fragment_empty_and_safe_insertion(self):
        p=SimpleNamespace(start=0,end=len(b"<w:p></w:p>"),closing_start=5)
        raw=b"<w:p></w:p>"
        with patch.object(procurement,"guarded_paragraph",return_value=False),              patch.object(procurement,"own_text_nodes",return_value=[]):
            self.assertEqual(procurement._paragraph_fragment(raw,p,""),raw)
            out=procurement._paragraph_fragment(raw,p,"A&B")
            self.assertIn(b"A&amp;B",out)
        p2=SimpleNamespace(start=0,end=len(b"<w:p/>"),closing_start=0)
        with patch.object(procurement,"guarded_paragraph",return_value=False),              patch.object(procurement,"own_text_nodes",return_value=[]):
            with self.assertRaises(DocumentError):
                procurement._paragraph_fragment(b"<w:p/>",p2,"x")

    def test_deleted_bookmark_guard_rejects_crossing_and_referenced_bookmarks(self):
        start=Mock(attrs={NS+"id":"1",NS+"name":"bookmark"})
        end=Mock(attrs={NS+"id":"2"})
        row=Mock()
        row.descendants.side_effect=lambda tag: [start] if tag==NS+"bookmarkStart" else [end] if tag==NS+"bookmarkEnd" else []
        with self.assertRaises(DocumentError):
            procurement._deleted_bookmark_guard(Mock(),row)

        end.attrs={NS+"id":"1"}
        hyperlink=Mock(name=NS+"hyperlink",attrs={NS+"anchor":"bookmark"})
        root=Mock()
        root.descendants.return_value=[hyperlink]
        doc=Mock(parts={"p":(b"",root)})
        with self.assertRaises(DocumentError):
            procurement._deleted_bookmark_guard(doc,row)

        hyperlink.attrs={NS+"anchor":"other"}
        instruction=Mock(name=NS+"instrText",characters="REF bookmark")
        root.descendants.return_value=[instruction]
        with self.assertRaises(DocumentError):
            procurement._deleted_bookmark_guard(doc,row)


class InstitutionalPolicyEdgeCoverageTests(SimpleTestCase):
    def test_validate_policy_mismatch_and_transform_conflicts(self):
        with self.assertRaises(DocumentError):
            institutional.validate_policy({"institutional_policy":"BAD","family":"equipment","source_sha256":"x"})
        binding={"keys":["phone_fax"],"before":"041.24.63.69 /: 041.24.63.76"}
        values={"phone_fax":"041.00.00.00","postal_code":"31000"}
        with self.assertRaises(DocumentError):
            institutional._transform("042.11.11.11",binding,values)
        with self.assertRaises(DocumentError):
            institutional._transform("041.24.63.69 041.24.63.76",binding,values)

        postal={"keys":["postal_code"],"before":"31000"}
        with self.assertRaises(DocumentError):
            institutional._transform("31999",postal,values)
        ar={"keys":["reagents_ar_lot_numbers"],"before":"A","after":"B"}
        with self.assertRaises(DocumentError):
            institutional._transform("C",ar,values)
        self.assertEqual(institutional._transform("A",ar,values),"B")

    def test_policy_report_legacy_and_resolved_issue(self):
        self.assertEqual(institutional.policy_report({})["status"],"LEGACY_UNCHANGED")
        with patch.object(institutional,"policy",return_value={"resolved_issue_ids":["I1"]}):
            self.assertTrue(institutional.resolved_issue({"institutional_policy":institutional.CURRENT_POLICY},"I1"))
            self.assertFalse(institutional.resolved_issue({},"I1"))


class SourceNoiseEdgeCoverageTests(SimpleTestCase):
    def test_noise_missing_anchor_structure_text_and_conflict(self):
        pid,expected=next(iter(source_noise.NOISE["works"].items()))
        doc=Mock(source_index=[])
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans("works",{},doc)

        block={"id":pid,"part":"word/footer1.xml","text":expected}
        doc=Mock(source_index=[block])
        doc.editable_segments.return_value=[[],[]]
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans("works",{},doc)

        node=Mock(characters="different")
        doc.editable_segments.return_value=[[node]]
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans("works",{},doc)

        node.characters=expected
        with self.assertRaises(DocumentError):
            source_noise.apply_noise_spans("works",{pid:[{"segment":0,"before":expected,"after":"x"}]},doc)
        spans,report=source_noise.apply_noise_spans("works",{},doc)
        self.assertEqual(report["removed"],[pid])
        self.assertEqual(spans[pid][0]["after"],"")
