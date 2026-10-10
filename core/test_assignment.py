"""Regression contracts for translated scientific qualifications."""
from django.test import TestCase
from django.utils.translation import override

from accounts.models import Technique, User
from core.assignment import (compute_member_score, get_assignment_candidates,
                             get_recommended_members, member_ineligibility_reasons,
                             member_is_eligible, technique_matches_service)
from core.models import Service


class ScientificAssignmentTests(TestCase):
    def setUp(self):
        self.member = User.objects.create_user('qualification-fixture', role='MEMBER').member_profile
        self.service = Service.objects.create(
            code='EGTP-IMT', name_fr='Identification microbienne via MALDI-TOF MS',
            name_en='Microbial Identification by MALDI-TOF MS',
            name_ar='التعرّف على الكائنات الحية الدقيقة بتقنية MALDI-TOF MS')

    def test_shorter_scientific_name_matches_in_every_interface_language(self):
        technique = Technique.objects.create(name_fr='MALDI–TOF')
        self.member.techniques.add(technique)
        for language in ('fr', 'en', 'ar'):
            with self.subTest(language=language), override(language):
                self.assertTrue(member_is_eligible(self.member, self.service))
                self.assertEqual(get_recommended_members(self.service), [self.member])
                self.assertGreaterEqual(compute_member_score(self.member, self.service), 80)

    def test_translation_matching_does_not_depend_on_selected_display_name(self):
        technique = Technique.objects.create(name_fr='Qualification scientifique', name_en='MALDI TOF')
        self.member.techniques.add(technique)
        with override('fr'):
            self.assertTrue(member_is_eligible(self.member, self.service))

    def test_inactive_and_unrelated_qualifications_are_rejected(self):
        technique = Technique.objects.create(name_fr='MALDI-TOF', active=False)
        self.member.techniques.add(technique)
        self.assertFalse(member_is_eligible(self.member, self.service))
        self.assertEqual(compute_member_score(self.member, self.service), 40)
        technique.active = True
        technique.name_fr = 'Séquençage Sanger'
        technique.save()
        self.assertFalse(member_is_eligible(self.member, self.service))
        self.assertEqual(compute_member_score(self.member, self.service), 52)

    def test_service_codes_and_full_words_do_not_match_partial_identifiers(self):
        for name, expected in [('Certification EGTP-IMT', True), ('EGTP', False),
                               ('EGTP-IMT-extra', True), ('EGTP-IMTX', False),
                               ('ALDI', False), ('', False)]:
            with self.subTest(name=name):
                technique = Technique(name_fr=name)
                self.assertEqual(technique_matches_service(technique, self.service), expected)
        unrelated = Service(code='', name_fr='')
        self.assertFalse(technique_matches_service(Technique(name_fr='MALDI-TOF'), unrelated))

    def test_longer_certification_and_accents_match_complete_service_name(self):
        service = Service(code='CUSTOM', name_fr='Séquençage Sanger')
        self.assertTrue(technique_matches_service(Technique(name_fr='Certification Sequencage Sanger'), service))

    def test_every_blocking_criterion_is_explained_and_current_assignee_excluded(self):
        self.member.user.is_active = False
        self.member.user.role = 'FINANCE'
        self.member.available = False
        self.member.current_load = self.member.max_load
        reasons = member_ineligibility_reasons(self.member, self.service)
        self.assertEqual(len(reasons), 5)
        candidates = get_assignment_candidates(self.service, members=[self.member])
        self.assertEqual(candidates, [{'member': self.member, 'reasons': reasons}])
        self.assertEqual(get_assignment_candidates(self.service, self.member.pk, [self.member]), [])
        self.assertEqual(len(get_assignment_candidates(self.service)), 1)
        self.assertFalse(member_is_eligible(self.member))
