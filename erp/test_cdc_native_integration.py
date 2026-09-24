from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp.models import (Capability, CdcItem, ProcurementCdcItemLink, ProcurementRequirementLink, RunAllocation,
    StockLot, WorkItem)
from erp.services.biobank import source_samples
from erp.services.cdc import (archive_dossier, create_dossier, duplicate_dossier,
    generate_cdc, save_cdc_item, stock_status)
from erp.services.consumption import (confirm_run, create_run, reservation_proposal,
    reserve_run, save_profile, save_rule)
from erp.services.procurement import (add_plan_article, approve_plan, create_plan,
    decide_plan_line, link_run_shortages, plan_from_cdc, plan_to_cdc, submit_plan)
from erp.services.purchases import (confirm_order, create_order, receive_order_line,
    save_order_line)
from erp.services.stock import control_container, reconcile_stock
from erp.test_operations import OperationFixtures
from notifications.models import Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class CdcNativeIntegrationTests(OperationFixtures, TestCase):
    def structured_cdc(self, reference='71/SME/SDFM/SG/ESSBO/2026', amount=12):
        dossier = create_dossier(self.ops, family='reagents', reference=reference,
            title='CDC natif', assignee=self.operator, allow_costs=True)
        CdcItem.objects.filter(lot__dossier=dossier).update(active=False)
        dossier.refresh_from_db()
        lot = dossier.lots.first()
        save_cdc_item(self.ops, lot.pk, expected=dossier.version,
            values={'quantity': Decimal(amount), 'estimated_price': Decimal(10),
                    'tax_rate': Decimal(19), 'price_source': 'Observation validée',
                    'currency': 'DZD'},
            article=self.article, purchase_unit=self.unit, reason='Article canonique')
        dossier.refresh_from_db()
        return dossier

    def analytical_run(self, *, committed=True, amount=30, planned_on=None, code='CHAIN-RUN'):
        service = Service.objects.create(code=code, name='Chaîne native')
        member, _ = MemberProfile.objects.get_or_create(user=self.operator)
        request = Request.objects.create(service=service, requester=self.outsider,
            assigned_to=member, title='Demande chaîne', status='IN_PROGRESS',
            sample_table=[{'sample_code': code + '-S1'}])
        profile = save_profile(self.ops, {'code': code + '-P', 'name': 'Nomenclature chaîne',
            'service': service, 'reference_samples': 1, 'protocol_reference': 'SOP-CHAIN'})
        save_rule(self.ops, profile.pk, {'article': self.article, 'quantity': Decimal(amount),
            'unit': self.unit, 'basis': 'BATCH'}, expected=profile.version)
        run = create_run(self.ops, request=request, profile=profile, code=code,
            name='Exécution chaîne', sample_count=1,
            planned_on=planned_on or timezone.localdate(),
            source_keys=[source_samples(self.ops, request)[0]['key']],
            committed=committed, incremental_demand=committed)
        return request, run

    def test_cdc_stock_status_controlled_duplication_archive_and_read_only(self):
        dossier = self.structured_cdc()
        self.receive(quantity=5)
        status = stock_status(self.ops, dossier)
        self.assertEqual(status['rows'][0]['status'], 'INSUFFICIENT')
        self.assertEqual(status['rows'][0]['available'], 5)
        self.assertEqual(status['rows'][0]['shortage'], 7)
        self.assertIsNone(stock_status(self.operator, dossier))
        self.grant(Capability.VIEW_STOCK, user=self.operator, location=self.freezer)
        self.assertEqual(stock_status(self.operator, dossier)['rows'][0]['available'], 5)

        with self.assertRaises(ValidationError):
            duplicate_dossier(self.ops, dossier.pk, expected=dossier.version,
                reference='70/SME/SDFM/SG/ESSBO/2026', title='Interdit', reason='')
        duplicate = duplicate_dossier(self.ops, dossier.pk, expected=dossier.version,
            reference='72/SME/SDFM/SG/ESSBO/2026', title='Copie contrôlée',
            assignee=self.second, allow_costs=True, copy_estimates=False,
            reason='Besoin institutionnel distinct')
        copied = CdcItem.objects.get(lot__dossier=duplicate, article=self.article)
        self.assertEqual(copied.article_id, self.article.pk)
        self.assertIsNone(copied.estimated_price)
        self.assertFalse(duplicate.data['consultation']['confirmed'])

        with self.assertRaises(ValidationError):
            archive_dossier(self.ops, dossier.pk, expected=dossier.version, reason='Trop tôt')
        dossier.work.status = WorkItem.Status.APPROVED
        dossier.work.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            archive_dossier(self.ops, dossier.pk, expected=dossier.version, reason='')
        archived = archive_dossier(self.ops, dossier.pk, expected=dossier.version,
            reason='Procédure clôturée')
        self.assertIsNotNone(archived.archived_at)
        with self.assertRaises(ValidationError):
            archive_dossier(self.ops, dossier.pk, expected=archived.version,
                reason='Deuxième archivage')
        with self.assertRaises(ValidationError):
            save_cdc_item(self.ops, dossier.lots.first().pk, expected=archived.version,
                values={'quantity': 1})
        with self.assertRaises(ValidationError):
            generate_cdc(self.ops, dossier.revisions.first().pk)

    def test_cdc_to_procurement_uses_only_real_shortage_and_reuses_canonical_article(self):
        dossier = self.structured_cdc(amount=12)
        self.receive(quantity=5)
        with self.assertRaises(ValidationError):
            plan_from_cdc(self.ops, dossier.pk, expected=dossier.version,
                plan_reference='BAD', year=timezone.localdate().year, reason='')
        plan = plan_from_cdc(self.ops, dossier.pk, expected=dossier.version,
            plan_reference='PLAN-FROM-CDC', year=timezone.localdate().year,
            assignee=self.operator, reason='Déficit stock confirmé')
        line = plan.lines.get()
        self.assertEqual(line.article_id, self.article.pk)
        self.assertEqual(line.proposed_quantity, 7)
        source = ProcurementCdcItemLink.objects.get(line=line)
        self.assertEqual(source.item.article_id, self.article.pk)
        self.assertEqual(source.required_quantity, 12)
        self.assertEqual(source.stock_covered_quantity, 5)
        self.assertEqual(source.shortage_quantity, 7)
        snapshot = plan.revisions.order_by('-number').first().data['lines'][0]['cdc_sources'][0]
        self.assertEqual(snapshot['item'], str(source.item_id))
        self.assertEqual(snapshot['shortage_quantity'], '7.000000')
        self.client.force_login(self.ops)
        detail = self.client.get(reverse('erp:procurement-detail', args=[plan.pk]))
        self.assertContains(detail, 'Source CDC')
        self.assertContains(detail, dossier.reference)
        self.assertEqual(plan_from_cdc(self.ops, dossier.pk, expected=dossier.version,
            plan_reference='IGNORED', year=timezone.localdate().year,
            reason='Idempotent').pk, plan.pk)

        covered = self.structured_cdc('74/SME/SDFM/SG/ESSBO/2026', amount=4)
        with self.assertRaisesRegex(ValidationError, 'couvre déjà'):
            plan_from_cdc(self.ops, covered.pk, expected=covered.version,
                plan_reference='NO-NEED', year=timezone.localdate().year,
                reason='Stock suffisant')

        raw = create_dossier(self.ops, family='reagents',
            reference='75/SME/SDFM/SG/ESSBO/2026', title='CDC non structuré')
        with self.assertRaisesRegex(ValidationError, 'catalogue commun'):
            plan_from_cdc(self.ops, raw.pk, expected=raw.version,
                plan_reference='UNLINKED', year=timezone.localdate().year,
                reason='Impossible sans référentiel')

    def test_request_activity_shortage_procurement_cdc_receipt_stock_execution_chain(self):
        request, run = self.analytical_run()
        self.receive('CHAIN-BASE', quantity=10)
        proposal = reservation_proposal(self.ops, run)
        self.assertEqual(Decimal(proposal['shortages'][0]['quantity']), 20)
        self.assertEqual(proposal['shortages'][0]['requirement'],
            str(run.requirements.get().pk))

        plan = create_plan(self.ops, reference='CHAIN-PLAN',
            year=timezone.localdate().year, title='Approvisionnement chaîne',
            assignee=self.operator, allow_costs=True)
        with self.assertRaises(ValidationError):
            link_run_shortages(self.ops, run.pk, plan.pk,
                expected_run=run.version, reason='')
        linked, count = link_run_shortages(self.ops, run.pk, plan.pk,
            expected_run=run.version, reason='Manque confirmé par le stock réel')
        self.assertEqual(count, 1)
        line = linked.lines.get()
        self.assertEqual(line.article_id, self.article.pk)
        self.assertEqual(line.proposed_quantity, 20)
        trace = ProcurementRequirementLink.objects.get(line=line)
        self.assertEqual(trace.requirement.run_id, run.pk)
        self.assertEqual(trace.shortage_quantity, 20)
        self.assertTrue(Notification.objects.filter(user=self.operator,
            message__contains='manques').exists())
        _, replay = link_run_shortages(self.ops, run.pk, plan.pk,
            expected_run=run.version, reason='Contrôle idempotent')
        self.assertEqual(replay, 0)

        plan.refresh_from_db()
        decide_plan_line(self.operator, line.pk, expected=plan.version,
            values={'retained_quantity': 20, 'included': True,
                    'lot_name': 'Besoins analytiques', 'priority': 'CRITICAL',
                    'estimated_price': 10, 'tax_rate': 19, 'currency': 'DZD',
                    'price_source': 'Devis', 'decision_reason': 'Manque confirmé'})
        plan.refresh_from_db()
        submit_plan(self.operator, plan.pk, expected=plan.version,
            reason='Plan complet')
        plan.refresh_from_db()
        approve_plan(self.ops, plan.pk, expected=plan.version,
            reason='Plan validé')
        plan.refresh_from_db()
        dossier = plan_to_cdc(self.ops, plan.pk, expected=plan.version,
            reference='73/SME/SDFM/SG/ESSBO/2026', family='reagents',
            assignee=self.operator)
        self.assertEqual(dossier.procurement_plan.pk, plan.pk)
        plan.refresh_from_db()

        order = create_order(self.ops, plan.pk, expected=plan.version,
            reference='CHAIN-PO', supplier=self.party,
            ordered_on=timezone.localdate(),
            expected_on=timezone.localdate() + timedelta(days=1))
        order_line = save_order_line(self.ops, order.pk, expected=order.version,
            plan_line=line, quantity=20, unit_price=10, tax_rate=19,
            currency='DZD')
        order.refresh_from_db()
        confirm_order(self.ops, order.pk, expected=order.version,
            reason='Commande confirmée')
        order.refresh_from_db()
        delivery = receive_order_line(self.ops, order_line.pk,
            expected=order.version, key=uuid.uuid4(), amount=20,
            location=self.freezer, lot_code='CHAIN-LOT',
            manufacturer_lot='CHAIN-M', container_code='CHAIN-C',
            received_on=timezone.localdate(), condition='Intact',
            expires_on=timezone.localdate() + timedelta(days=100))
        self.assertTrue(reservation_proposal(self.ops, run)['shortages'])
        container = delivery.receipt.container
        control_container(self.ops, container.pk, expected=container.version,
            status=StockLot.Status.AVAILABLE,
            reason='Réception documentaire et physique conforme')
        proposal = reservation_proposal(self.ops, run)
        self.assertEqual(proposal['shortages'], [])
        self.assertEqual(sum(Decimal(row['quantity']) for row in proposal['allocations']), 30)

        reserve_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            allocations=proposal['allocations'], reason='Ressources disponibles')
        run.refresh_from_db()
        actuals = {str(allocation.pk): str(allocation.reservation.remaining)
            for allocation in RunAllocation.objects.filter(requirement__run=run).select_related('reservation')}
        confirm_run(self.ops, run.pk, expected=run.version, key=uuid.uuid4(),
            actuals=actuals, reason='Analyse réalisée', confirmed=True)
        run.refresh_from_db()
        self.assertEqual(run.status, 'COMPLETED')
        self.assertEqual(reconcile_stock(self.ops), [])
        self.assertEqual(sum(row.quantity for row in run.consumptions.all()), 30)

        self.client.force_login(self.ops)
        page = self.client.get(reverse('erp:procurement-detail', args=[plan.pk]))
        self.assertContains(page, request.display_id)
        self.assertContains(page, run.code)

    def test_shortage_link_guards_other_plan_category_period_commitment_and_stock(self):
        _, open_run = self.analytical_run(committed=False, code='OPEN')
        plan = create_plan(self.ops, reference='GUARD-PLAN',
            year=timezone.localdate().year, title='Guard')
        with self.assertRaisesRegex(ValidationError, 'engagée'):
            link_run_shortages(self.ops, open_run.pk, plan.pk,
                expected_run=open_run.version, reason='Test')

        _, no_shortage = self.analytical_run(code='COVERED')
        self.receive('COVERED', quantity=40)
        with self.assertRaisesRegex(ValidationError, 'couvre déjà'):
            link_run_shortages(self.ops, no_shortage.pk, plan.pk,
                expected_run=no_shortage.version, reason='Test')

        _, next_year = self.analytical_run(code='NEXT',
            planned_on=timezone.localdate().replace(year=timezone.localdate().year + 1))
        with self.assertRaisesRegex(ValidationError, 'période'):
            link_run_shortages(self.ops, next_year.pk, plan.pk,
                expected_run=next_year.version, reason='Test')

        _, mismatch = self.analytical_run(code='MISMATCH')
        plan.work.category = self.other
        plan.work.save(update_fields=['category'])
        with self.assertRaises(PermissionDenied):
            link_run_shortages(self.ops, mismatch.pk, plan.pk,
                expected_run=mismatch.version, reason='Catégorie incompatible')

    def test_http_native_actions_and_archived_filter(self):
        dossier = self.structured_cdc('76/SME/SDFM/SG/ESSBO/2026')
        self.client.force_login(self.ops)
        self.assertEqual(self.client.get(reverse('erp:cdc-duplicate',
            args=[dossier.pk])).status_code, 200)
        response = self.client.post(reverse('erp:cdc-duplicate', args=[dossier.pk]), {
            'expected_version': dossier.version,
            'reference': '77/SME/SDFM/SG/ESSBO/2026',
            'title': 'Duplication HTTP', 'assignee': self.operator.pk,
            'priority': 'NORMAL', 'instructions': 'Nouvelle opération',
            'reason': 'Duplication contrôlée'})
        self.assertEqual(response.status_code, 302)

        response = self.client.post(reverse('erp:cdc-procurement', args=[dossier.pk]), {
            'expected_version': dossier.version, 'plan_reference': 'HTTP-PLAN',
            'year': timezone.localdate().year, 'assignee': self.operator.pk,
            'reason': 'Déficit HTTP'})
        self.assertEqual(response.status_code, 302)

        dossier.work.status = WorkItem.Status.APPROVED
        dossier.work.save(update_fields=['status'])
        response = self.client.post(reverse('erp:cdc-archive', args=[dossier.pk]), {
            'expected_version': dossier.version, 'reason': 'Archivage HTTP'})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse('erp:cdc-list') + '?state=archived'),
            dossier.reference)
        self.assertContains(self.client.get(reverse('erp:cdc-list') + '?state=all'),
            dossier.reference)
        detail = self.client.get(reverse('erp:cdc-detail', args=[dossier.pk]))
        self.assertContains(detail, 'Pièces jointes')
        self.assertContains(detail, 'archivé')
