from datetime import timedelta
from decimal import Decimal
import uuid
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfWriter

from erp import cdc_views, consumption_views
from erp.consumption_forms import RunProcurementForm
from erp.models import (
    Capability, CdcClauseSelection, CdcGeneration, CdcRequirement,
    CdcReviewDecision, ProcurementRequirementLink, WorkItem,
)
from erp.services.cdc import (
    _dossier, approve_dossier, create_clause_revision, create_dossier,
    dossier_findings, dossier_scope, generate_cdc, governance_findings,
    restore_governance_snapshot, review_dossier, save_cdc_item, save_clause,
    save_requirement, stock_status,
)
from erp.services.procurement import link_run_shortages, plan_from_cdc
from erp.services.safety import require_target
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
)
class CdcFinalCoverageTests(OperationFixtures, TestCase):
    def setUp(self):
        self.dossier = create_dossier(
            self.ops,
            family='equipment',
            reference='951/SME/SDFM/SG/ESSBO/2026',
            title='Fermeture couverture CDC',
            assignee=self.operator,
            location=self.freezer,
            category=self.article.category,
            allow_costs=True,
        )
        self.item = self.dossier.lots.filter(active=True).first().items.filter(active=True).first()

    def refresh(self):
        self.dossier.refresh_from_db()
        self.dossier.work.refresh_from_db()
        return self.dossier

    def clause(self, code='FINAL.CLAUSE'):
        return save_clause(self.ops, values={
            'code': code,
            'name': 'Clause finale',
            'name_en': 'Final clause',
            'name_ar': 'بند نهائي',
            'title': 'Clause de couverture finale',
            'active': True,
        }, reason='Référentiel de qualification')

    def test_review_scope_read_guards_archived_edit_and_stock_denial(self):
        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        self.grant(
            Capability.REVIEW_CDC_FINANCIAL,
            user=self.second,
            category=self.article.category,
            location=self.freezer,
        )
        self.assertTrue(dossier_scope(self.second).filter(pk=self.dossier.pk).exists())

        with self.assertRaises(PermissionDenied):
            _dossier(self.outsider, self.dossier.pk)

        self.dossier.work.status = WorkItem.Status.ASSIGNED
        self.dossier.work.save(update_fields=['status'])
        self.dossier.archived_at = timezone.now()
        self.dossier.save(update_fields=['archived_at', 'updated_at'])
        with self.assertRaises(ValidationError):
            _dossier(self.operator, self.dossier.pk, edit=True)
        with self.assertRaises(PermissionDenied):
            cdc_views._require_editable_dossier(self.operator, self.dossier)

        self.dossier.archived_at = None
        self.dossier.save(update_fields=['archived_at', 'updated_at'])
        self.refresh()
        with self.assertRaises(PermissionDenied):
            stock_status(self.outsider, self.dossier)

    def test_governance_inactive_clause_restore_fallbacks_and_requirement_update(self):
        clause = self.clause()
        draft = create_clause_revision(
            self.ops, clause, text_fr='Brouillon', source_reference='Source brouillon', activate=False)
        CdcClauseSelection.objects.create(
            dossier=self.dossier, revision=draft, position=1, mandatory=False, active=True)
        self.assertIn('clause-not-active', {row['code'] for row in governance_findings(self.dossier)})
        self.assertIn('clause-not-active', {row['code'] for row in dossier_findings(self.dossier)})

        active = create_clause_revision(
            self.ops, clause, text_fr='Texte actif', source_reference='Décision active', activate=True)
        restore_governance_snapshot(self.ops, self.dossier, {
            'requirements': [{
                'item_key': 'missing-item',
                'position': 1,
                'kind': 'MANDATORY',
                'statement': 'Ignorée',
            }],
            'criteria': [],
            'clauses': [
                {
                    'revision_id': str(uuid.uuid4()),
                    'code': clause.code,
                    'revision': active.number,
                    'position': 2,
                    'mandatory': True,
                },
                {
                    'revision_id': str(uuid.uuid4()),
                    'code': 'MISSING.CLAUSE',
                    'revision': 999,
                    'position': 3,
                    'mandatory': False,
                },
            ],
        })
        selection = self.dossier.clause_selections.get(revision=active)
        self.assertTrue(selection.active)

        self.refresh()
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version, values={
            'position': 1,
            'kind': 'MANDATORY',
            'statement': 'Exigence initiale',
            'evidence': 'Certificat',
            'verification_method': 'Contrôle',
            'justification': '',
            'active': True,
        }, reason='Création')
        self.refresh()
        requirement = CdcRequirement.objects.get(item=self.item, position=1)
        save_requirement(self.operator, self.item.pk, expected=self.dossier.version, pk=requirement.pk, values={
            'statement': 'Exigence mise à jour',
        }, reason='Mise à jour')
        requirement.refresh_from_db()
        self.assertEqual(requirement.version, 2)

    def test_review_invalid_stages_supplier_guard_and_incomplete_approval(self):
        with self.assertRaisesRegex(ValidationError, 'inconnue'):
            review_dossier(
                self.ops, self.dossier.pk, expected=self.dossier.version,
                stage='UNKNOWN', outcome='APPROVED', comment='x')

        self.dossier.work.allow_costs = False
        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['allow_costs', 'status'])
        with self.assertRaisesRegex(ValidationError, 'pas applicable'):
            review_dossier(
                self.ops, self.dossier.pk, expected=self.dossier.version,
                stage=CdcReviewDecision.Stage.FINANCIAL,
                outcome=CdcReviewDecision.Outcome.APPROVED,
                comment='Non applicable',
            )

        self.dossier.work.status = WorkItem.Status.ASSIGNED
        self.dossier.work.allow_costs = True
        self.dossier.work.save(update_fields=['status', 'allow_costs'])
        self.party.active = False
        self.party.save(update_fields=['active'])
        with self.assertRaisesRegex(ValidationError, 'fournisseur actif'):
            save_cdc_item(
                self.operator,
                self.item.lot_id,
                expected=self.dossier.version,
                pk=self.item.pk,
                values={'estimate_supplier': self.party},
                reason='Fournisseur invalide',
            )
        self.party.active = True
        self.party.save(update_fields=['active'])

        self.refresh()
        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        generation = CdcGeneration.objects.create(
            revision=revision,
            actor=self.ops,
            docx=b'docx',
            pdf=b'pdf',
            docx_sha256='0' * 64,
            pdf_sha256='1' * 64,
            pages=1,
            checks={},
        )
        with self.assertRaisesRegex(ValidationError, 'revues obligatoires'):
            approve_dossier(
                self.ops,
                self.dossier.pk,
                expected=self.dossier.version,
                generation_id=generation.pk,
                reviewed_pages=1,
                statement='Validation',
                visual_review=True,
                content_review=True,
            )

    def test_generated_governance_annex_report_paths(self):
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)

        def fake_convert(source):
            target = source.with_suffix('.pdf')
            writer = PdfWriter()
            writer.add_blank_page(width=595.28, height=841.89)
            with open(target, 'wb') as handle:
                writer.write(handle)
            return target

        with patch('erp.services.cdc.controls', return_value=[]), \
             patch('erp.services.cdc.governance_snapshot_findings', return_value=[]), \
             patch('erp.services.cdc.generate_document', return_value=(b'word', {})), \
             patch('erp.services.cdc.append_governance_annex', return_value=(
                 b'word',
                 {'status': 'GENERATED', 'requirements': 1, 'criteria': 1, 'clauses': 1},
             )), \
             patch('erp.services.cdc.normalize_word_layout', return_value=(b'word', {})), \
             patch('erp.services.cdc.convert_docx_to_pdf', side_effect=fake_convert):
            generation = generate_cdc(self.ops, revision.pk)
        report = generation.checks['source_report']
        self.assertIn('word/document.xml', report['changed_parts'])
        self.assertEqual(report['changes'][0]['kind'], 'cdc_governance_annex')

    def test_cdc_view_error_and_redirect_branches(self):
        self.client.force_login(self.ops)

        duplicate_payload = {
            'expected_version': self.dossier.version,
            'reference': '952/SME/SDFM/SG/ESSBO/2026',
            'title': 'Copie finale',
            'assignee': '',
            'due_on': '',
            'priority': 'NORMAL',
            'location': '',
            'category': '',
            'instructions': '',
            'reason': 'Test erreur contrôlée',
        }
        with patch('erp.cdc_views.duplicate_dossier', side_effect=ValidationError('dup')):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-duplicate', args=[self.dossier.pk]), duplicate_payload).status_code,
                400,
            )

        archive_payload = {'expected_version': self.dossier.version, 'reason': 'Archivage contrôlé'}
        with patch('erp.cdc_views.archive_dossier', side_effect=ValidationError('archive')):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-archive', args=[self.dossier.pk]), archive_payload).status_code,
                400,
            )
        with patch('erp.cdc_views.archive_dossier', return_value=self.dossier):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-archive', args=[self.dossier.pk]), archive_payload).status_code,
                302,
            )

        existing = Mock(pk=uuid.uuid4())
        with patch('erp.cdc_views.ProcurementPlan.objects.filter') as query:
            query.return_value.first.return_value = existing
            self.assertEqual(
                self.client.get(reverse('erp:cdc-procurement', args=[self.dossier.pk])).status_code,
                302,
            )

        procurement_payload = {
            'expected_version': self.dossier.version,
            'plan_reference': 'PLAN-FINAL',
            'year': timezone.localdate().year,
            'assignee': '',
            'reason': 'Déficit qualifié',
        }
        with patch('erp.cdc_views.ProcurementPlan.objects.filter') as query, \
             patch('erp.services.procurement.plan_from_cdc', side_effect=ValidationError('plan')):
            query.return_value.first.return_value = None
            self.assertEqual(
                self.client.post(reverse('erp:cdc-procurement', args=[self.dossier.pk]), procurement_payload).status_code,
                400,
            )

        requirement_payload = {
            'expected_version': self.dossier.version,
            'position': 1,
            'kind': 'MANDATORY',
            'statement': 'Exigence HTTP',
            'evidence': 'Preuve',
            'verification_method': 'Contrôle',
            'justification': '',
            'active': 'on',
            'reason': 'Erreur simulée',
        }
        with patch('erp.cdc_views.save_requirement', side_effect=ValidationError('requirement')):
            self.assertEqual(
                self.client.post(
                    reverse('erp:cdc-requirement-create', args=[self.item.pk]), requirement_payload
                ).status_code,
                400,
            )

        criterion_payload = {
            'expected_version': self.dossier.version,
            'lot': '',
            'code': 'FINAL',
            'title': 'Critère final',
            'method': 'BINARY',
            'weight': '100',
            'threshold': '',
            'evidence': 'Mémoire',
            'position': 1,
            'active': 'on',
            'reason': 'Erreur simulée',
        }
        with patch('erp.cdc_views.save_criterion', side_effect=ValidationError('criterion')):
            self.assertEqual(
                self.client.post(
                    reverse('erp:cdc-criterion-create', args=[self.dossier.pk]), criterion_payload
                ).status_code,
                400,
            )

        clause = self.clause('HTTP.FINAL')
        active = create_clause_revision(
            self.ops, clause, text_fr='Clause active', source_reference='Source', activate=True)
        clause_payload = {
            'expected_version': self.dossier.version,
            'revision': str(active.pk),
            'position': 1,
            'mandatory': 'on',
            'note': 'Note',
            'active': 'on',
            'reason': 'Erreur simulée',
        }
        with patch('erp.cdc_views.select_clause', side_effect=ValidationError('selection')):
            self.assertEqual(
                self.client.post(
                    reverse('erp:cdc-clause-select', args=[self.dossier.pk]), clause_payload
                ).status_code,
                400,
            )

        self.dossier.work.status = WorkItem.Status.SUBMITTED
        self.dossier.work.save(update_fields=['status'])
        review_payload = {
            'expected_version': self.dossier.version,
            'stage': 'TECHNICAL',
            'outcome': 'APPROVED',
            'comment': 'Revue HTTP',
        }
        with patch('erp.cdc_views.review_dossier', side_effect=ValidationError('review')):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-review', args=[self.dossier.pk]), review_payload).status_code,
                400,
            )

        clause_definition = {
            'code': 'HTTP.ERROR',
            'name': 'Clause erreur',
            'name_en': '',
            'name_ar': '',
            'title': 'Clause erreur',
            'active': 'on',
            'reason': 'Erreur simulée',
        }
        with patch('erp.cdc_views.save_clause', side_effect=ValidationError('clause')):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-clause-create'), clause_definition).status_code,
                400,
            )

        revision_payload = {
            'text_fr': 'Texte',
            'text_en': '',
            'text_ar': '',
            'source_reference': 'Source',
            'activate': 'on',
        }
        with patch('erp.cdc_views.create_clause_revision', side_effect=ValidationError('revision')):
            self.assertEqual(
                self.client.post(reverse('erp:cdc-clause-revision', args=[clause.pk]), revision_payload).status_code,
                400,
            )

    def test_run_procurement_form_view_procurement_guards_and_safety(self):
        run = Mock(version=3, planned_on=timezone.localdate(), pk=uuid.uuid4(), code='RUN-FINAL')
        form = RunProcurementForm(user=self.ops, run=run)
        self.assertEqual(form.fields['expected_version'].initial, 3)

        original = consumption_views.run_procurement
        while hasattr(original, '__wrapped__'):
            original = original.__wrapped__

        plan = Mock(pk=uuid.uuid4())
        fake_form = Mock()
        fake_form.is_valid.return_value = True
        fake_form.cleaned_data = {
            'plan': plan,
            'expected_version': 3,
            'reason': 'Transfert',
        }
        request = RequestFactory().post('/erp/runs/final/procurement/')
        request.user = self.ops
        with patch('erp.consumption_views.require_manager'), \
             patch('erp.consumption_views.get_object_or_404', return_value=run), \
             patch('erp.consumption_views.forms.RunProcurementForm', return_value=fake_form), \
             patch('erp.services.procurement.link_run_shortages', return_value=(plan, 1)):
            response = original(request, run.pk)
        self.assertEqual(response.status_code, 302)

        with patch('erp.consumption_views.require_manager'), \
             patch('erp.consumption_views.get_object_or_404', return_value=run), \
             patch('erp.consumption_views.forms.RunProcurementForm', return_value=fake_form), \
             patch('erp.services.procurement.link_run_shortages', side_effect=ValidationError('stock')), \
             patch('erp.consumption_views.add_validation') as add_validation, \
             patch('erp.consumption_views._form', return_value=HttpResponse('invalid', status=400)):
            response = original(request, run.pk)
        self.assertEqual(response.status_code, 400)
        add_validation.assert_called_once()

        self.dossier.archived_at = timezone.now()
        self.dossier.save(update_fields=['archived_at', 'updated_at'])
        with self.assertRaisesRegex(ValidationError, 'archivé'):
            plan_from_cdc(
                self.ops,
                self.dossier.pk,
                expected=self.dossier.version,
                plan_reference='ARCHIVED',
                year=timezone.localdate().year,
                reason='Interdit',
            )
        self.dossier.archived_at = None
        self.dossier.save(update_fields=['archived_at', 'updated_at'])

        with patch('erp.services.cdc.stock_status', return_value={
            'unlinked': 0,
            'rows': [{
                'article': self.article,
                'shortage': Decimal('1'),
                'available': Decimal('0'),
            }],
        }):
            with self.assertRaisesRegex(ValidationError, 'ventilation'):
                plan_from_cdc(
                    self.ops,
                    self.dossier.pk,
                    expected=self.dossier.version,
                    plan_reference='MISMATCH-FINAL',
                    year=timezone.localdate().year,
                    reason='Ventilation volontairement incomplète',
                )

        with self.assertRaisesRegex(ValidationError, 'Justifiez'):
            link_run_shortages(
                self.ops, uuid.uuid4(), uuid.uuid4(), expected_run=1, reason='')

        requirement = Mock(pk=uuid.uuid4(), article=self.article, unit=self.unit)
        mocked_run = Mock(
            committed=True,
            status='PLANNED',
            planned_on=timezone.localdate(),
            version=1,
        )
        mocked_run.requirements.select_related.return_value = [requirement]
        mocked_plan = Mock(
            starts_on=timezone.localdate() - timedelta(days=1),
            ends_on=timezone.localdate() + timedelta(days=1),
        )
        mocked_plan.work.category_id = None
        previous = Mock()
        previous.line.plan.work.status = WorkItem.Status.IN_PROGRESS
        relation_query = Mock()
        relation_query.select_related.return_value.exclude.return_value.first.return_value = previous
        run_query = Mock()
        run_query.select_related.return_value.get.return_value = mocked_run

        with patch('erp.services.procurement.AnalysisRun.objects.select_for_update', return_value=run_query), \
             patch('erp.services.procurement.check_version'), \
             patch('erp.services.procurement._plan', return_value=mocked_plan), \
             patch('erp.services.consumption.reservation_proposal', return_value={
                 'shortages': [{
                     'requirement': str(requirement.pk),
                     'quantity': Decimal('1'),
                 }],
             }), \
             patch('erp.services.procurement.ProcurementRequirementLink.objects.filter', return_value=relation_query):
            with self.assertRaisesRegex(ValidationError, 'déjà pris en charge'):
                link_run_shortages(
                    self.ops,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    expected_run=1,
                    reason='Déjà couvert',
                )

        work = create_work(
            self.ops,
            kind=WorkItem.Kind.CONTROL,
            title='Dossier non CDC',
            assignee=self.operator,
        )
        with self.assertRaises(PermissionDenied):
            require_target(self.outsider, 'work', work.pk)
