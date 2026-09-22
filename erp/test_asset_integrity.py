from pathlib import Path
from django.test import SimpleTestCase
from erp.cdc.catalog import DIGESTS, document
from erp.cdc.institutional import POLICY_SHA256, policy
from erp.cdc.docengine import sha


class CanonicalAssetIntegrityTests(SimpleTestCase):
    def test_pinned_policy_bytes_and_parsed_identity(self):
        source=Path(__file__).resolve().parent/'assets/institutional/ESSBO_COORD_LOTS_20260907_V1.json'
        self.assertEqual(sha(source.read_bytes()),POLICY_SHA256)
        self.assertEqual(policy()['id'],'ESSBO_COORD_LOTS_20260907_V1')

    def test_all_document_models_preserve_the_approved_source_hash(self):
        for family,digest in DIGESTS.items():
            with self.subTest(family=family):
                self.assertEqual(sha(document(family).data),digest)
