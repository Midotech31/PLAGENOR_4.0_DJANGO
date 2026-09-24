from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from erp.cdc.consultation import FIELDS
from erp.models import CdcDossier, CdcItem, CdcRevision, WorkItem
from erp.services.cdc import create_dossier, save_consultation
from erp.test_operations import OperationFixtures
from notifications.models import Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CdcDelegationHttpTests(OperationFixtures, TestCase):
    def setUp(self):
        self.dossier = create_dossier(self.ops, family='equipment', reference='18/SME/SDFM/SG/ESSBO/2026',
            title='CDC équipements', assignee=self.operator, allow_costs=False,
            due_on=timezone.localdate()+timedelta(days=10), instructions='Préparer les besoins et soumettre à validation.')
        self.work = self.dossier.work

    def test_admin_ops_can_create_and_delegate_from_native_form(self):
        self.client.force_login(self.ops)
        response = self.client.get(reverse('erp:cdc-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Créer et déléguer')
        response = self.client.post(reverse('erp:cdc-create'), {'family': 'equipment',
            'reference': '19/SME/SDFM/SG/ESSBO/2026', 'title': 'Deuxième CDC', 'assignee': self.second.pk,
            'due_on': (timezone.localdate()+timedelta(days=15)).isoformat(), 'priority': 'HIGH',
            'instructions': 'Préparer le dossier technique', 'expected_version': ''})
        self.assertEqual(response.status_code, 302, getattr(response, 'context', None))
        created = CdcDossier.objects.get(reference='19/SME/SDFM/SG/ESSBO/2026')
        self.assertEqual(created.work.assignee_id, self.second.pk)
        self.assertEqual(created.work.status, 'ASSIGNED')
        self.assertTrue(Notification.objects.filter(user=self.second, link_url=reverse('erp:work-detail', args=[created.work_id])).exists())
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:cdc-create')).status_code, 403)

    def test_assigned_member_reads_and_edits_but_has_no_cost_or_final_approval_right(self):
        self.client.force_login(self.operator)
        urls = [reverse('erp:index'), reverse('erp:work-list'), reverse('erp:work-detail', args=[self.work.pk]),
            reverse('erp:cdc-list'), reverse('erp:cdc-detail', args=[self.dossier.pk]),
            reverse('erp:cdc-consultation', args=[self.dossier.pk]), reverse('erp:cdc-clauses', args=[self.dossier.pk]),
            reverse('erp:cdc-revision', args=[self.dossier.revisions.first().pk])]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'Examiner et valider définitivement')
        self.assertEqual(self.client.get(reverse('erp:work-delegate', args=[self.work.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('erp:cdc-approve', args=[self.dossier.pk])).status_code, 403)
        item = self.dossier.lots.first().items.first()
        response = self.client.get(reverse('erp:cdc-item-edit', args=[item.lot_id, item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('estimated_price', response.context['form'].fields)
        self.assertNotIn('tax_rate', response.context['form'].fields)
        data = {'expected_version': self.dossier.version, 'article': '', 'purchase_unit': '',
            'designation': item.designation, 'specifications': item.specifications, 'unit_label': item.unit_label,
            'packaging': item.packaging, 'quantity': '3', 'details': item.details, 'active': 'on',
            'reason': 'Quantité corrigée selon le besoin du laboratoire', 'estimated_price': '999999', 'tax_rate': '19'}
        response = self.client.post(reverse('erp:cdc-item-edit', args=[item.lot_id, item.pk]), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        item.refresh_from_db()
        self.assertEqual(item.quantity, 3)
        self.assertIsNone(item.estimated_price)
        self.assertIsNone(item.tax_rate)
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.revision_number, 2)
        self.assertEqual(self.client.post(reverse('erp:cdc-approve', args=[self.dossier.pk]), {}).status_code, 403)

    def test_admin_ops_reassignment_revokes_previous_member_on_every_dossier_endpoint(self):
        self.client.force_login(self.ops)
        url = reverse('erp:work-delegate', args=[self.work.pk])
        response = self.client.post(url, {'expected_version': self.work.version, 'assignee': self.second.pk,
            'due_on': (timezone.localdate()+timedelta(days=12)).isoformat(), 'priority': 'URGENT',
            'instructions': 'Reprendre la préparation des spécifications', 'allow_costs': 'on',
            'reason': 'Réaffectation validée par Admin Ops'})
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        self.work.refresh_from_db()
        self.assertEqual(self.work.assignee_id, self.second.pk)
        self.assertTrue(self.work.allow_costs)
        self.assertEqual(self.work.priority, 'URGENT')
        self.assertTrue(Notification.objects.filter(user=self.operator, message__contains='retirée').exists())
        item = self.dossier.lots.first().items.first()
        urls = [reverse('erp:work-detail', args=[self.work.pk]), reverse('erp:cdc-detail', args=[self.dossier.pk]),
            reverse('erp:cdc-consultation', args=[self.dossier.pk]), reverse('erp:cdc-lot', args=[item.lot_id]),
            reverse('erp:cdc-item-edit', args=[item.lot_id, item.pk]), reverse('erp:cdc-revision', args=[self.dossier.revisions.first().pk])]
        self.client.force_login(self.operator)
        for target in urls:
            with self.subTest(url=target):
                self.assertEqual(self.client.get(target).status_code, 404)
        self.client.force_login(self.second)
        response = self.client.get(reverse('erp:cdc-item-edit', args=[item.lot_id, item.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('estimated_price', response.context['form'].fields)
        self.assertEqual(self.client.get(reverse('erp:cdc-approve', args=[self.dossier.pk])).status_code, 403)

    def test_consultation_updates_snapshot_and_wrong_versions_are_rejected(self):
        self.client.force_login(self.operator)
        before = self.dossier.revisions.first()
        values = {key: self.dossier.data['consultation'][key] for key in FIELDS}
        values['operation_fr'] = 'Acquisition documentée pour la plateforme'
        values['confirmed'] = True
        data = {**values, 'reference': self.dossier.reference, 'expected_version': self.dossier.version,
                'reason': 'Variables propres au dossier confirmées'}
        data['confirmed'] = 'on'
        response = self.client.post(reverse('erp:cdc-consultation', args=[self.dossier.pk]), data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.data['consultation']['operation_fr'], values['operation_fr'])
        before.refresh_from_db()
        self.assertNotEqual(before.data['consultation']['operation_fr'], values['operation_fr'])
        stale = self.client.post(reverse('erp:cdc-consultation', args=[self.dossier.pk]), data)
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(self.dossier.revisions.count(), 2)

    def test_anonymous_and_unassigned_users_cannot_open_or_mutate_the_dossier(self):
        target = reverse('erp:cdc-detail', args=[self.dossier.pk])
        self.assertEqual(self.client.get(target).status_code, 302)
        for user in (self.second, self.outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(target).status_code, 404)
            self.assertEqual(self.client.post(target, {'action': 'submit', 'expected_version': self.dossier.version}).status_code, 404)
            self.assertEqual(self.client.get(reverse('erp:work-delegate', args=[self.work.pk])).status_code, 403)
        self.work.refresh_from_db()
        self.assertEqual(self.work.status, 'ASSIGNED')

    def test_lot_item_and_clause_forms_preserve_versions_on_rejected_edits(self):
        from erp.cdc.catalog import document
        from erp.cdc.schedule_adapter import managed_ids
        self.client.force_login(self.ops)
        lot = self.dossier.lots.first()
        route = reverse('erp:cdc-lot-edit', args=[lot.pk])
        data = {'expected_version': self.dossier.version+1, 'name': lot.name, 'name_ar': lot.name_ar,
            'reason': 'Intitulé vérifié'}
        self.assertEqual(self.client.post(route, data).status_code, 400)
        data['expected_version'] = self.dossier.version
        self.assertEqual(self.client.post(route, data).status_code, 302)
        self.dossier.refresh_from_db()
        item_data = {'expected_version': self.dossier.version, 'article': self.article.pk,
            'purchase_unit': self.unit.pk, 'designation': '', 'unit_label': '', 'quantity': '2',
            'active': 'on', 'currency': 'DZD', 'reason': 'Besoin documenté'}
        route = reverse('erp:cdc-item-new', args=[lot.pk])
        response = self.client.post(route, item_data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        item = lot.items.get(article=self.article)
        self.assertEqual(item.designation, self.article.name)
        self.assertEqual(item.unit_label, self.unit.name)
        self.assertEqual(self.client.post(route, item_data).status_code, 400)
        managed, _ = managed_ids(self.dossier.family)
        block = next(b for b in document(self.dossier.family).source_index
            if not b['guard'] and b['id'] not in managed and b['text'].strip())
        self.dossier.refresh_from_db()
        paragraph = {'expected_version': self.dossier.version+1, 'paragraph_id': block['id'],
            'value': block['text'], 'reason': 'Relecture de clause'}
        self.assertEqual(self.client.post(reverse('erp:cdc-paragraph', args=[self.dossier.pk]), paragraph).status_code, 400)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:cdc-list')).status_code, 403)

    def test_native_generation_and_explicit_review_approval(self):
        from erp.models import CdcApproval, CdcGeneration
        self.client.force_login(self.ops)
        values = {key: self.dossier.data['consultation'][key] for key in FIELDS}
        values['confirmed'] = True
        save_consultation(self.ops, self.dossier.pk, expected=self.dossier.version, values=values,
            reference=self.dossier.reference, reason='Variables vérifiées pour la recette')
        self.dossier.refresh_from_db()
        from erp.models import CdcCriterion
        from erp.services.cdc_governance import review_revision, save_criterion
        save_criterion(self.ops, self.dossier, expected=self.dossier.version, reason='Grille validée', values={
            'lot': self.dossier.lots.first(), 'code': 'TECH-01', 'category': CdcCriterion.Category.TECHNICAL,
            'title': 'Conformité technique', 'description': 'Contrôle', 'expected_evidence': 'Fiche technique',
            'min_score': Decimal('0'), 'max_score': Decimal('20'), 'weight': Decimal('100'),
            'threshold': Decimal('10'), 'formula': '', 'rounding_rule': 'Deux décimales',
            'eliminatory': False, 'source': 'Grille institutionnelle', 'justification': 'Méthode validée',
            'position': 1, 'active': True})
        self.dossier.refresh_from_db()
        detail = reverse('erp:cdc-detail', args=[self.dossier.pk])
        data = {'expected_version': self.dossier.version+1, 'action': 'generate', 'reason': 'Revue'}
        self.assertEqual(self.client.post(detail, data).status_code, 400)
        data['expected_version'] = self.dossier.version
        response = self.client.post(detail, data)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        generation = CdcGeneration.objects.get(revision__dossier=self.dossier)
        self.assertGreater(generation.pages, 0)
        self.assertTrue(bytes(generation.pdf).startswith(b'%PDF'))
        data['action'] = 'unknown'
        self.assertEqual(self.client.post(detail, data).status_code, 400)
        data['action'] = 'submit'
        self.assertEqual(self.client.post(detail, data).status_code, 302)
        approval = {'expected_version': self.dossier.version, 'generation': generation.pk,
            'reviewed_pages': generation.pages+1, 'statement': 'Revue simulée pour le test automatisé',
            'visual_review': 'on', 'content_review': 'on'}
        route = reverse('erp:cdc-approve', args=[self.dossier.pk])
        self.assertEqual(self.client.get(route).status_code, 200)
        self.assertEqual(self.client.post(route, approval).status_code, 400)
        self.assertFalse(CdcApproval.objects.exists())
        revision = self.dossier.revisions.get(number=self.dossier.revision_number)
        review_revision(self.ops, revision, stage='TECHNICAL', decision='APPROVED', comment='Revue technique')
        review_revision(self.ops, revision, stage='ADMIN', decision='APPROVED', comment='Revue administrative')
        review_revision(self.ops, revision, stage='FINANCIAL', decision='APPROVED', comment='Revue financière')
        self.assertEqual(self.client.post(route, approval).status_code, 400)
        approval['reviewed_pages'] = generation.pages
        response = self.client.post(route, approval)
        self.assertEqual(response.status_code, 302, response.context['form'].errors if response.context else '')
        self.assertEqual(CdcApproval.objects.get().generation_id, generation.pk)
        self.dossier.work.refresh_from_db()
        self.assertEqual(self.dossier.work.status, 'APPROVED')

    def test_scoped_catalog_and_consultation_guards_preserve_revision(self):
        from erp.cdc_forms import CdcItemForm
        from erp.services.cdc import save_cdc_item
        self.work.category = self.category
        self.work.save(update_fields=['category'])
        self.assertEqual(str(self.dossier), self.dossier.reference)
        lot = self.dossier.lots.first()
        self.assertEqual(str(lot), lot.name)
        self.assertEqual(list(CdcItemForm(dossier=self.dossier, user=self.ops).fields['article'].queryset), [self.article])
        before = self.dossier.revision_number
        with self.assertRaisesRegex(ValidationError, 'toutes les rubriques'):
            save_consultation(self.ops, self.dossier.pk, expected=self.dossier.version, values={})
        with self.assertRaises(PermissionDenied):
            save_cdc_item(self.ops, lot.pk, expected=self.dossier.version, values={'quantity': 1},
                article=self.liquid, purchase_unit=self.ml)
        save_cdc_item(self.ops, lot.pk, expected=self.dossier.version, values={'quantity': 1},
            article=self.article, purchase_unit=self.unit)
        self.dossier.refresh_from_db()
        item = lot.items.get(article=self.article)
        with self.assertRaisesRegex(ValidationError, 'unité documentaire'):
            save_cdc_item(self.ops, lot.pk, pk=item.pk, expected=self.dossier.version,
                values={'unit_label': 'Unité incohérente'})
        self.dossier.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.dossier.revision_number, before + 1)
        self.assertEqual(item.unit_label, self.unit.name)
