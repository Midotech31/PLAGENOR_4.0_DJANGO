from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from erp.models import (CdcClause, CdcClauseRevision, CdcCriterion, CdcRequirement,
    CdcReviewDecision, WorkItem)
from erp.services.cdc import (approve_dossier, create_clause_revision, create_dossier,
    document_data, duplicate_dossier, governance_findings, review_dossier, review_state,
    save_clause, save_criterion, save_requirement, select_clause)
from erp.services.cdc_exchange import add_lot, arrange_item, restore_revision
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class NativeCdcToolkitGovernanceTests(OperationFixtures, TestCase):
    def setUp(self):
        self.dossier = create_dossier(self.ops, family='equipment',
            reference='91/SME/SDFM/SG/ESSBO/2026', title='CDC Toolkit natif',
            assignee=self.operator, allow_costs=True)
        self.item = self.dossier.lots.filter(active=True).first().items.filter(active=True).first()

    def refresh(self):
        self.dossier.refresh_from_db()
        self.dossier.work.refresh_from_db()
        return self.dossier

    def clause(self):
        clause = save_clause(self.ops, values={'code': 'TECH.CLAUSE', 'name': 'Clause technique',
            'name_en': 'Technical clause', 'name_ar': 'بند تقني',
            'title': 'Compatibilité et réception', 'active': True}, reason='Référentiel ESSBO')
        self.assertEqual(str(clause), 'Compatibilité et réception')
        return clause

    def test_requirement_validation_update_snapshot_and_findings(self):
        with self.assertRaisesRegex(ValidationError, 'preuve'):
            save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
                values={'position': 1, 'kind': CdcRequirement.Kind.MANDATORY,
                    'statement': 'Pureté documentée', 'evidence': '',
                    'verification_method': '', 'justification': '', 'active': True})

        revision = save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            values={'position': 1, 'kind': CdcRequirement.Kind.ELIMINATORY,
                'statement': 'Pureté ≥ 99 %', 'evidence': 'Certificat analyse',
                'verification_method': 'Contrôle du certificat', 'justification': 'Critère critique',
                'active': True}, reason='Exigence de réception')
        requirement = CdcRequirement.objects.get(item=self.item, position=1)
        self.assertIn(str(requirement.pk), str(revision.data))
        self.refresh()
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version, pk=requirement.pk,
            values={'statement': 'Pureté ≥ 99,5 %'}, reason='Valeur corrigée')
        requirement.refresh_from_db()
        self.assertEqual(requirement.version, 2)

        self.refresh()
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            values={'position': 2, 'kind': CdcRequirement.Kind.INFORMATIONAL,
                'statement': 'Couleur indicative', 'evidence': '', 'verification_method': '',
                'justification': '', 'active': True}, reason='Information non bloquante')
        self.assertFalse([row for row in governance_findings(self.dossier)
            if row.get('code', '').startswith('requirement-')])

        invalid = CdcRequirement.objects.create(item=self.item, position=3,
            kind=CdcRequirement.Kind.ELIMINATORY, statement='Test contrôle',
            evidence='', verification_method='', justification='', active=True)
        codes = {row.get('code') for row in governance_findings(self.dossier)}
        self.assertTrue({'requirement-evidence', 'requirement-verification',
                         'requirement-eliminatory-justification'} <= codes)
        invalid.active = False
        invalid.save(update_fields=['active'])

    def test_criteria_scope_weights_foreign_lot_and_eliminatory_evidence(self):
        other = create_dossier(self.ops, family='equipment',
            reference='92/SME/SDFM/SG/ESSBO/2026', title='Autre CDC')
        with self.assertRaisesRegex(ValidationError, 'correspond'):
            save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
                values={'lot': other.lots.first(), 'code': 'X', 'title': 'Étranger',
                    'method': CdcCriterion.Method.BINARY, 'weight': Decimal('100'),
                    'threshold': None, 'eliminatory': False, 'evidence': '',
                    'position': 1, 'active': True})
        with self.assertRaisesRegex(ValidationError, 'justificatif'):
            save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
                values={'lot': None, 'code': 'ELIM', 'title': 'Éliminatoire',
                    'method': CdcCriterion.Method.BINARY, 'weight': Decimal('100'),
                    'threshold': None, 'eliminatory': True, 'evidence': '',
                    'position': 1, 'active': True})

        save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
            values={'lot': None, 'code': 'TECH', 'title': 'Technique',
                'method': CdcCriterion.Method.PROPORTIONAL, 'weight': Decimal('60'),
                'threshold': Decimal('30'), 'eliminatory': False, 'evidence': 'Mémoire technique',
                'position': 1, 'active': True}, reason='Grille')
        self.refresh()
        self.assertIn('criteria-total', {row.get('code') for row in governance_findings(self.dossier)})
        save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
            values={'lot': None, 'code': 'QUAL', 'title': 'Qualité',
                'method': CdcCriterion.Method.BINARY, 'weight': Decimal('40'),
                'threshold': None, 'eliminatory': False, 'evidence': 'Preuve',
                'position': 2, 'active': True}, reason='Compléter grille')
        self.refresh()
        self.assertNotIn('criteria-total', {row.get('code') for row in governance_findings(self.dossier)})

        save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
            values={'lot': self.dossier.lots.first(), 'code': 'LOT', 'title': 'Lot',
                'method': CdcCriterion.Method.INVERSE_PRICE, 'weight': Decimal('100'),
                'threshold': None, 'eliminatory': False, 'evidence': 'Offre',
                'position': 1, 'active': True}, reason='Test périmètre')
        self.refresh()
        self.assertIn('criteria-scope-mixed', {row.get('code') for row in governance_findings(self.dossier)})
        criterion = self.dossier.criteria.get(code='TECH')
        save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version, pk=criterion.pk,
            values={'active': False}, reason='Passage aux grilles par lot')
        criterion.refresh_from_db()
        self.assertEqual(criterion.version, 2)

    def test_clause_library_revision_selection_and_snapshot(self):
        with self.assertRaises(ValidationError):
            save_clause(self.ops, values={'code': '', 'name': '', 'name_en': '',
                'name_ar': '', 'title': '', 'active': True})
        clause = self.clause()
        clause = save_clause(self.ops, pk=clause.pk, values={'title': 'Compatibilité, réception et garantie'},
            reason='Titre précisé')
        self.assertEqual(clause.version, 2)
        with self.assertRaisesRegex(ValidationError, 'source'):
            create_clause_revision(self.ops, clause, text_fr='', source_reference='')

        draft = create_clause_revision(self.ops, clause, text_fr='Texte de travail',
            source_reference='Référence interne', activate=False)
        with self.assertRaises(ValidationError):
            select_clause(self.operator, self.dossier.pk, expected=self.dossier.version,
                revision=draft, reason='Brouillon interdit')
        active = create_clause_revision(self.ops, clause, text_fr='Texte validé',
            text_en='Approved text', text_ar='نص معتمد',
            source_reference='Décision ESSBO 2026', activate=True)
        self.assertEqual(active.number, 2)
        clause.refresh_from_db()
        self.assertEqual(clause.active_revision_id, active.pk)

        select_clause(self.operator, self.dossier.pk, expected=self.dossier.version,
            revision=active, position=2, mandatory=True, note='Applicable',
            reason='Clause institutionnelle')
        self.refresh()
        select_clause(self.operator, self.dossier.pk, expected=self.dossier.version,
            revision=active, position=1, mandatory=False, note='Repositionnée',
            reason='Ordre documentaire')
        selection = self.dossier.clause_selections.get()
        self.assertEqual((selection.position, selection.version), (1, 2))
        data = document_data(self.dossier)
        self.assertEqual(data['clauses'][0]['revision_id'], str(active.pk))
        self.assertEqual(data['clauses'][0]['text_fr'], 'Texte validé')

        with self.assertRaises(ValidationError):
            active.text_fr = 'Altération'
            active.save()

    def test_review_workflow_requires_current_revision_stages(self):
        with self.assertRaisesRegex(ValidationError, 'soumis'):
            review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                stage=CdcReviewDecision.Stage.TECHNICAL,
                outcome=CdcReviewDecision.Outcome.APPROVED, comment='Conforme')

        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        with self.assertRaisesRegex(ValidationError, 'compte rendu'):
            review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                stage=CdcReviewDecision.Stage.TECHNICAL,
                outcome=CdcReviewDecision.Outcome.APPROVED, comment='')

        review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            stage=CdcReviewDecision.Stage.TECHNICAL,
            outcome=CdcReviewDecision.Outcome.APPROVED, comment='Technique conforme')
        with self.assertRaisesRegex(ValidationError, 'déjà'):
            review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                stage=CdcReviewDecision.Stage.TECHNICAL,
                outcome=CdcReviewDecision.Outcome.APPROVED, comment='Doublon')
        review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            stage=CdcReviewDecision.Stage.ADMIN_LEGAL,
            outcome=CdcReviewDecision.Outcome.APPROVED, comment='Administratif conforme')
        self.assertFalse(review_state(self.dossier)['complete'])
        review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            stage=CdcReviewDecision.Stage.FINANCIAL,
            outcome=CdcReviewDecision.Outcome.APPROVED, comment='Financier conforme')
        self.assertTrue(review_state(self.dossier)['complete'])

    def test_review_change_request_and_final_approval_guard(self):
        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        with self.assertRaisesRegex(ValidationError, 'revues'):
            approve_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
                generation_id=self.dossier.pk, reviewed_pages=1, statement='Validation',
                visual_review=True, content_review=True)
        review_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            stage=CdcReviewDecision.Stage.TECHNICAL,
            outcome=CdcReviewDecision.Outcome.CHANGES, comment='Corriger une spécification')
        self.dossier.work.refresh_from_db()
        self.assertEqual(self.dossier.work.status, WorkItem.Status.CHANGES_REQUESTED)

    def test_http_governance_requirement_criterion_clause_and_permissions(self):
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:cdc-governance', args=[self.dossier.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('erp:cdc-requirement-create', args=[self.item.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-requirement-create', args=[self.item.pk]), {
            'expected_version': self.dossier.version, 'position': 1, 'kind': 'MANDATORY',
            'statement': 'Certificat requis', 'evidence': 'Certificat',
            'verification_method': 'Contrôle documentaire', 'justification': '',
            'active': 'on', 'reason': 'Contrôle réception'})
        self.assertEqual(response.status_code, 302)
        self.refresh()
        self.assertEqual(self.client.get(reverse('erp:cdc-criterion-create',
            args=[self.dossier.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-criterion-create', args=[self.dossier.pk]), {
            'expected_version': self.dossier.version, 'lot': '', 'code': 'HTTP',
            'title': 'Critère HTTP', 'method': 'PROPORTIONAL', 'weight': '100',
            'threshold': '', 'evidence': 'Mémoire', 'position': 1, 'active': 'on',
            'reason': 'Grille HTTP'})
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.outsider)
        self.assertIn(self.client.get(reverse('erp:cdc-governance',
            args=[self.dossier.pk])).status_code, (403, 404))
        self.assertEqual(self.client.get(reverse('erp:cdc-clause-library')).status_code, 403)

    def test_http_clause_library_revision_selection_and_review(self):
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(reverse('erp:cdc-clause-library')).status_code, 200)
        response = self.client.post(reverse('erp:cdc-clause-create'), {
            'code': 'HTTP.CLAUSE', 'name': 'Clause HTTP', 'name_en': '',
            'name_ar': '', 'title': 'Clause créée en ligne', 'active': 'on',
            'reason': 'Création'})
        self.assertEqual(response.status_code, 302)
        clause = CdcClause.objects.get(code='HTTP.CLAUSE')
        self.assertEqual(self.client.get(reverse('erp:cdc-clause-edit', args=[clause.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-clause-revision', args=[clause.pk]), {
            'text_fr': 'Texte validé en ligne', 'text_en': '', 'text_ar': '',
            'source_reference': 'Décision en ligne', 'activate': 'on'})
        self.assertEqual(response.status_code, 302)
        revision = CdcClauseRevision.objects.get(clause=clause)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:cdc-clause-select',
            args=[self.dossier.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-clause-select', args=[self.dossier.pk]), {
            'expected_version': self.dossier.version, 'revision': revision.pk,
            'position': 1, 'mandatory': 'on', 'note': 'Test', 'active': 'on',
            'reason': 'Sélection HTTP'})
        self.assertEqual(response.status_code, 302)

        self.refresh()
        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(reverse('erp:cdc-review', args=[self.dossier.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-review', args=[self.dossier.pk]), {
            'expected_version': self.dossier.version, 'stage': 'TECHNICAL',
            'outcome': 'APPROVED', 'comment': 'Revue technique HTTP'})
        self.assertEqual(response.status_code, 302)


    def test_duplicate_dossier_preserves_governance_without_copying_prices(self):
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            values={'position': 1, 'kind': 'MANDATORY', 'statement': 'Exigence source',
                'evidence': 'Certificat', 'verification_method': 'Contrôle',
                'justification': '', 'active': True}, reason='Exigence')
        self.refresh()
        save_criterion(self.operator, self.dossier.pk, expected=self.dossier.version,
            values={'lot': None, 'code': 'DUP', 'title': 'Critère source',
                'method': 'BINARY', 'weight': Decimal('100'), 'threshold': None,
                'eliminatory': False, 'evidence': 'Preuve', 'position': 1,
                'active': True}, reason='Critère')
        clause = self.clause()
        active = create_clause_revision(self.ops, clause, text_fr='Clause stable',
            source_reference='Source stable', activate=True)
        self.refresh()
        select_clause(self.operator, self.dossier.pk, expected=self.dossier.version,
            revision=active, position=1, mandatory=True, reason='Clause')
        self.refresh()
        duplicate = duplicate_dossier(self.ops, self.dossier.pk, expected=self.dossier.version,
            reference='93/SME/SDFM/SG/ESSBO/2026', title='Copie gouvernée',
            assignee=self.operator, allow_costs=True, copy_estimates=False,
            reason='Nouvelle consultation')
        self.assertEqual(CdcRequirement.objects.filter(item__lot__dossier=duplicate, active=True).count(), 1)
        self.assertEqual(duplicate.criteria.filter(active=True).count(), 1)
        self.assertEqual(duplicate.clause_selections.filter(active=True).count(), 1)
        self.assertEqual(document_data(duplicate)['criteria'][0]['code'], 'DUP')

    def test_reused_lot_and_item_move_or_duplicate_keep_requirements(self):
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            values={'position': 1, 'kind': 'MANDATORY', 'statement': 'Exigence portable',
                'evidence': 'Certificat', 'verification_method': 'Contrôle',
                'justification': '', 'active': True}, reason='Exigence')
        self.refresh()
        reused = add_lot(self.operator, self.dossier.pk, expected=self.dossier.version,
            name='Lot réutilisé', source=self.item.lot, reason='Réutilisation contrôlée')
        copied = reused.items.get(active=True)
        self.assertEqual(copied.requirements.get(active=True).statement, 'Exigence portable')

        self.refresh()
        duplicated = arrange_item(self.operator, copied.pk, expected=self.dossier.version,
            destination=self.item.lot, action='duplicate', position=2,
            reason='Même exigence dans un second lot')
        self.assertEqual(duplicated.requirements.get(active=True).statement, 'Exigence portable')

        self.refresh()
        moved = arrange_item(self.operator, duplicated.pk, expected=self.dossier.version,
            destination=reused, action='move', position=2, reason='Réorganisation')
        self.assertEqual(moved.requirements.get(active=True).statement, 'Exigence portable')

    def test_restore_revision_restores_requirements_criteria_and_clause_selection(self):
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            values={'position': 1, 'kind': 'MANDATORY', 'statement': 'Version un',
                'evidence': 'Certificat', 'verification_method': 'Contrôle',
                'justification': '', 'active': True}, reason='Version un')
        source = self.dossier.revisions.order_by('-number').first()
        self.refresh()
        requirement = CdcRequirement.objects.get(item=self.item, position=1)
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version,
            pk=requirement.pk, values={'statement': 'Version deux'}, reason='Version deux')
        self.refresh()
        restored = restore_revision(self.ops, source.pk, expected=self.dossier.version,
            reason='Revenir à la version un')
        requirement.refresh_from_db()
        self.assertEqual(requirement.statement, 'Version un')
        self.assertEqual(restored.data['requirements'][0]['statement'], 'Version un')
