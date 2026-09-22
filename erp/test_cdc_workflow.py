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
