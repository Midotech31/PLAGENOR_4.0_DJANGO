from datetime import datetime, timedelta
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request
from erp.models import ActivityDependency, ActivitySchedule, AvailabilityBlock, PlanningResource, WorkItem
from erp.services.common import Conflict
from erp.services.planning import (cancel_unavailability, confirm_resources, create_activity, interval,
    readiness, save_resource, save_schedule, save_unavailability, set_dependencies)
from erp.services.work import create_work, delegate_work, transition_work
from erp.test_operations import OperationFixtures
from notifications.models import Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PlanningTests(OperationFixtures, TestCase):
    def setUp(self):
        self.start = timezone.now().replace(second=0, microsecond=0) - timedelta(minutes=5)
        self.end = self.start + timedelta(hours=1)
        self.resource = save_resource(self.ops, {'code': 'SEQ-01', 'name': 'Instrument de recette', 'kind': 'EQUIPMENT', 'location': self.lab})

    def activity(self, **changes):
        values = {'key': uuid.uuid4(), 'kind': 'CONTROL', 'title': 'Contrôle de recette',
            'assignee': self.operator, 'starts_at': self.start, 'ends_at': self.end,
            'resources': [self.resource]}
        values.update(changes)
        return create_activity(self.ops, **values), values

    def checked(self, schedule):
        work = schedule.work
        work.refresh_from_db()
        confirm_resources(self.operator, work.pk, expected=work.version, note='Matériel et documents vérifiés physiquement.')
        work.refresh_from_db()
        return work

    def test_native_calendar_and_single_task_identity(self):
        schedule, _ = self.activity()
        self.assertEqual(WorkItem.objects.count(), 1)
        self.assertEqual(schedule.work.schedule.pk, schedule.pk)
        self.client.force_login(self.ops)
        for mode in ('day', 'week', 'month', 'list'):
            with self.subTest(mode=mode):
                result = self.client.get(reverse('erp:planning'), {'date': timezone.localdate().isoformat(), 'view': mode})
                self.assertEqual(result.status_code, 200)
                self.assertContains(result, 'Contrôle de recette')
                self.assertEqual(result.context['slot_count'], 1)
        for name,args in [('erp:activity-detail',[schedule.work_id]), ('erp:activity-schedule',[schedule.work_id]),
            ('erp:activity-dependencies',[schedule.work_id]), ('erp:planning-resources',[]),
            ('erp:resource-create',[]), ('erp:resource-edit',[self.resource.pk]),
            ('erp:unavailability-create',[]), ('erp:activity-create',[])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name,args=args)).status_code, 200)

    def test_start_checks_and_completion_requires_admin_validation(self):
        schedule, _ = self.activity()
        work = schedule.work
        self.assertFalse(readiness(self.operator, work)['ready'])
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        work = self.checked(schedule)
        self.assertTrue(readiness(self.operator, work)['ready'])
        work = transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='SUBMITTED', reason='')
        work = transition_work(self.operator, work.pk, expected=work.version, state='SUBMITTED', reason='Contrôle effectué, résultat conforme.')
        with self.assertRaises(PermissionDenied):
            transition_work(self.operator, work.pk, expected=work.version, state='APPROVED')
        work = transition_work(self.ops, work.pk, expected=work.version, state='APPROVED', reason='Compte rendu examiné.')
        schedule.refresh_from_db()
        self.assertIsNotNone(schedule.actual_started_at)
        self.assertIsNotNone(schedule.actual_finished_at)
        self.assertEqual(work.approved_by_id, self.ops.pk)
        self.assertIsNotNone(work.approved_at)
        self.assertFalse(work.comments.count() == 0)

    def test_no_overlap_for_person_or_exclusive_resource_and_adjacent_slots_allowed(self):
        schedule, _ = self.activity()
        with self.assertRaises(ValidationError):
            self.activity(assignee=self.second)
        with self.assertRaises(ValidationError):
            self.activity(resources=[])
        adjacent, _ = self.activity(starts_at=self.end, ends_at=self.end+timedelta(hours=1))
        self.assertNotEqual(schedule.pk, adjacent.pk)
        self.assertEqual(ActivitySchedule.objects.count(), 2)
        self.assertEqual(WorkItem.objects.count(), 2)

    def test_creation_retry_is_idempotent_and_key_reuse_is_rejected(self):
        schedule, values = self.activity()
        self.assertEqual(create_activity(self.ops, **values).pk, schedule.pk)
        self.assertEqual(WorkItem.objects.count(), 1)
        with self.assertRaises(Conflict):
            create_activity(self.ops, **{**values, 'title': 'Autre contenu'})
        with self.assertRaises(ValidationError):
            self.activity(key='invalid')

    def test_specialized_tasks_are_scheduled_without_recreating_dossiers(self):
        work = create_work(self.ops, kind='CDC', title='CDC délégué', assignee=self.operator)
        schedule = save_schedule(self.ops, work.pk, expected=work.version, starts_at=self.start, ends_at=self.end)
        self.assertEqual(schedule.work_id, work.pk)
        self.assertEqual(WorkItem.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.activity(kind='CDC', resources=[])
        self.checked(schedule)
        work.refresh_from_db()
        work = transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='SUBMITTED', reason='Contourner le dossier')

    def test_reassignment_revokes_access_and_rechecks_calendar(self):
        schedule, _ = self.activity()
        work = self.checked(schedule)
        occupied, _ = self.activity(assignee=self.second, resources=[])
        with self.assertRaises(ValidationError):
            delegate_work(self.ops, work.pk, expected=work.version, assignee=self.second, reason='Réaffecter')
        other = occupied.work
        transition_work(self.ops, other.pk, expected=other.version, state='CANCELLED', reason='Créneau libéré')
        work = delegate_work(self.ops, work.pk, expected=work.version, assignee=self.second, reason='Réaffectation contrôlée')
        schedule.refresh_from_db()
        self.assertIsNone(schedule.resources_checked_at)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:activity-detail', args=[work.pk])).status_code, 404)
        self.client.force_login(self.second)
        self.assertEqual(self.client.get(reverse('erp:activity-detail', args=[work.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('erp:activity-schedule', args=[work.pk])).status_code, 403)

    def test_maintenance_block_invalidates_review_and_never_reschedules_silently(self):
        schedule, _ = self.activity()
        work = self.checked(schedule)
        block = save_unavailability(self.ops, starts_at=self.start, ends_at=self.end,
            resource=self.resource, reason='Maintenance urgente')
        schedule.refresh_from_db()
        self.assertIsNone(schedule.resources_checked_at)
        self.assertEqual(schedule.starts_at, self.start)
        self.assertTrue(Notification.objects.filter(user=self.operator, message__contains='indisponibilité').exists())
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        cancel_unavailability(self.ops, block.pk, expected=block.version, reason='Maintenance terminée et vérifiée')
        self.assertFalse(AvailabilityBlock.objects.get(pk=block.pk).active)
        self.assertFalse(readiness(self.operator, work)['ready'])
        self.checked(schedule)
        self.assertTrue(readiness(self.operator, work)['ready'])

    def test_member_unavailability_and_disabled_resource_block_booking(self):
        save_unavailability(self.ops, starts_at=self.start, ends_at=self.end, member=self.operator, reason='Absence')
        with self.assertRaises(ValidationError):
            self.activity(resources=[])
        self.resource = save_resource(self.ops, {'active': False}, pk=self.resource.pk, expected=self.resource.version)
        with self.assertRaises(ValidationError):
            self.activity(assignee=self.second)
        with self.assertRaises(ValidationError):
            save_unavailability(self.ops, starts_at=self.start, ends_at=self.end, reason='Pas de cible')

    def test_dependencies_cannot_cycle_or_be_bypassed(self):
        prerequisite = create_work(self.ops, kind='CONTROL', title='Prérequis', assignee=self.second)
        schedule, _ = self.activity()
        work = schedule.work
        work = set_dependencies(self.ops, work.pk, expected=work.version, prerequisites=[prerequisite], reason='Contrôle obligatoire')
        with self.assertRaises(ValidationError):
            set_dependencies(self.ops, prerequisite.pk, expected=prerequisite.version, prerequisites=[work], reason='Cycle interdit')
        self.assertEqual(ActivityDependency.objects.count(), 1)
        with self.assertRaises(ValidationError):
            confirm_resources(self.operator, work.pk, expected=work.version, note='Prérequis pas encore validé')
        prerequisite = transition_work(self.second, prerequisite.pk, expected=prerequisite.version, state='SUBMITTED', reason='Contrôle réalisé')
        transition_work(self.ops, prerequisite.pk, expected=prerequisite.version, state='APPROVED', reason='Contrôle validé')
        confirm_resources(self.operator, work.pk, expected=work.version, note='Préparation vérifiée')
        self.assertTrue(readiness(self.operator, work)['ready'])

    def test_dependency_order_requires_explicit_downstream_rescheduling(self):
        first, _ = self.activity()
        second, _ = self.activity(starts_at=self.end, ends_at=self.end+timedelta(hours=1))
        work = set_dependencies(self.ops, second.work_id, expected=second.work.version, prerequisites=[first.work], reason='Ordre technique')
        with self.assertRaises(ValidationError):
            save_schedule(self.ops, first.work_id, expected=first.work.version, starts_at=self.end+timedelta(hours=2),
                ends_at=self.end+timedelta(hours=3), resources=[], reason='Déplacement incohérent')
        first.refresh_from_db()
        self.assertEqual(first.starts_at, self.start)
        self.assertEqual(second.work.prerequisites.get().prerequisite_id, first.work_id)

    def test_replanning_invalidates_readiness_and_preserves_history(self):
        schedule, _ = self.activity()
        work = self.checked(schedule)
        old_version = work.version
        with self.assertRaises(ValidationError):
            save_schedule(self.ops, work.pk, expected=work.version, starts_at=self.start, ends_at=self.end, resources=[])
        changed = save_schedule(self.ops, work.pk, expected=work.version, starts_at=self.start+timedelta(days=1),
            ends_at=self.end+timedelta(days=1), resources=[], reason='Replanification approuvée')
        self.assertEqual(changed.pk, schedule.pk)
        self.assertIsNone(changed.resources_checked_at)
        with self.assertRaises(Conflict):
            save_schedule(self.ops, work.pk, expected=old_version, starts_at=self.start, ends_at=self.end, reason='Écriture périmée')
        work.refresh_from_db()
        self.assertEqual(work.due_on, timezone.localtime(changed.ends_at).date())

    def test_time_window_and_interval_validation(self):
        for start,end in [(datetime(2026,1,1),datetime(2026,1,2)),(self.end,self.start),
            (self.start,self.start),(self.start,self.start+timedelta(days=367))]:
            with self.subTest(start=start), self.assertRaises(ValidationError):
                interval(start,end)
        schedule, _ = self.activity(starts_at=self.start+timedelta(days=1), ends_at=self.end+timedelta(days=1))
        work = self.checked(schedule)
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')

    def test_live_overrun_blocks_another_start_after_planned_end(self):
        schedule, _ = self.activity()
        work = self.checked(schedule)
        transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        ActivitySchedule.objects.filter(pk=schedule.pk).update(starts_at=self.start-timedelta(hours=2), ends_at=self.start-timedelta(hours=1))
        with self.assertRaises(ValidationError):
            self.activity(assignee=self.second)

    def test_linked_request_permission_is_checked_again_before_start(self):
        profile, _ = MemberProfile.objects.get_or_create(user=self.operator)
        req = Request.objects.create(title='Demande de recette', requester=self.outsider, assigned_to=profile, status='ANALYSIS_STARTED')
        schedule, _ = self.activity(request=req)
        work = self.checked(schedule)
        req.assigned_to = None
        req.save(update_fields=['assigned_to'])
        self.assertFalse(readiness(self.operator, work)['ready'])
        with self.assertRaises(ValidationError):
            transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')

    def test_http_filter_validation_and_cross_role_boundaries(self):
        schedule, _ = self.activity()
        self.client.force_login(self.ops)
        for values in ({'date':'invalid'}, {'date':'1800-01-01'}, {'view':'invalid'}, {'kind':'invalid'}, {'member':'invalid'}):
            with self.subTest(values=values):
                self.assertEqual(self.client.get(reverse('erp:planning'), values).status_code, 404)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(reverse('erp:planning')).status_code, 200)
        for route in ['erp:activity-create','erp:planning-resources','erp:resource-create','erp:unavailability-create']:
            self.assertEqual(self.client.get(reverse(route)).status_code, 403)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('erp:planning')).status_code, 403)
        self.assertEqual(self.client.get(reverse('erp:activity-detail',args=[schedule.work_id])).status_code, 404)

    def test_http_creation_and_review_confirmation(self):
        self.client.force_login(self.ops)
        data={'key':str(uuid.uuid4()),'kind':'MEETING','title':'Réunion de planification',
            'assignee':self.operator.pk,'priority':'NORMAL','frequency':'ONCE','occurrences':'1','starts_at':timezone.localtime(self.start).strftime('%Y-%m-%dT%H:%M'),
            'ends_at':timezone.localtime(self.end).strftime('%Y-%m-%dT%H:%M'),'resources':[str(self.resource.pk)]}
        response=self.client.post(reverse('erp:activity-create'), data)
        self.assertEqual(response.status_code,302,response.context['form'].errors if response.context else '')
        work=WorkItem.objects.get(title=data['title'])
        self.client.force_login(self.operator)
        response=self.client.post(reverse('erp:activity-detail',args=[work.pk]),
            {'expected_version':work.version,'note':'Documents et salle vérifiés','confirmed':'on'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(readiness(self.operator,work)['ready'])


    def test_recurring_creation_is_atomic_and_uses_one_stable_retry_identity(self):
        from erp.services.planning import create_activity_series
        key=uuid.uuid4()
        values={'key':key,'kind':'QUALITY','title':'Contrôle hebdomadaire','assignee':self.operator,
            'starts_at':self.start,'ends_at':self.end,'resources':[self.resource]}
        result=create_activity_series(self.ops,frequency='WEEKLY',occurrences=3,**values)
        self.assertEqual(len(result),3)
        self.assertEqual(result[2].starts_at, self.start+timedelta(days=14))
        replay=create_activity_series(self.ops,frequency='WEEKLY',occurrences=3,**values)
        self.assertEqual([item.pk for item in replay],[item.pk for item in result])
        self.assertEqual(ActivitySchedule.objects.count(),3)
        with self.assertRaises(Conflict):
            create_activity_series(self.ops,frequency='DAILY',occurrences=3,**values)
        with self.assertRaises(Conflict):
            create_activity_series(self.ops,frequency='WEEKLY',occurrences=2,**values)
        blocked={**values,'key':uuid.uuid4(),'starts_at':self.start-timedelta(days=1),'ends_at':self.end-timedelta(days=1)}
        with self.assertRaises(ValidationError):
            create_activity_series(self.ops,frequency='DAILY',occurrences=3,**blocked)
        self.assertEqual(ActivitySchedule.objects.count(),3)
        self.assertEqual(WorkItem.objects.count(),3)

    def test_resource_edit_requires_a_fresh_operational_check(self):
        schedule,_=self.activity()
        self.checked(schedule)
        save_resource(self.ops,{'instructions':'Nouvelles consignes de contrôle'},pk=self.resource.pk,expected=self.resource.version)
        schedule.refresh_from_db()
        self.assertIsNone(schedule.resources_checked_at)

    def test_activity_request_closure_releases_real_run_reservations(self):
        from core.workflow import force_transition
        from erp.services.stock import reserve_stock
        from erp.models import StockReservation
        from unittest.mock import patch
        profile,_=MemberProfile.objects.get_or_create(user=self.operator)
        req=Request.objects.create(title='Demande à clôturer',requester=self.outsider,assigned_to=profile,status='ANALYSIS_STARTED')
        container,_,_=self.receive(quantity=10)
        reserved=reserve_stock(self.ops,container.pk,key=uuid.uuid4(),amount=4,unit=self.unit,reference='Opération future',request=req)
        with patch('core.workflow._post_commit_transition'):
            force_transition(req,'REJECTED',self.admin,notes='Opération annulée par administration')
        reserved.refresh_from_db()
        container.refresh_from_db()
        self.assertEqual(reserved.remaining,0)
        self.assertEqual(container.quantity,10)
        self.assertEqual(container.reserved,0)


    def test_linked_analysis_requires_received_samples_and_usable_reservations(self):
        from decimal import Decimal
        from core.models import Service
        from erp.models import Capability, RunAllocation
        from erp.services.biobank import receive_sample, source_samples
        from erp.services.consumption import create_run, save_profile, save_rule, reserve_run, reservation_proposal, confirm_run
        from erp.services.stock import control_lot, reconcile_stock
        service=Service.objects.create(code='PLAN-GATE',name='Service de recette de planification')
        member,_=MemberProfile.objects.get_or_create(user=self.operator)
        req=Request.objects.create(title='Analyse planifiée',requester=self.outsider,assigned_to=member,service=service,
            status='ANALYSIS_STARTED',sample_table=[{'sample_code':'PLAN-S1'}])
        profile=save_profile(self.ops,{'code':'PLAN-BOM','name':'Consommations de recette','service':service,
            'reference_samples':1,'protocol_reference':'QA-PLAN-01'})
        save_rule(self.ops,profile.pk,{'article':self.article,'quantity':Decimal(2),'unit':self.unit,'basis':'PROPORTIONAL'},expected=profile.version)
        source=source_samples(self.ops,req)[0]
        run=create_run(self.ops,request=req,profile=profile,code='PLAN-RUN',name='Run de recette',sample_count=1,
            planned_on=timezone.localdate(),source_keys=[source['key']])
        container,_,_=self.receive(quantity=10)
        schedule,_=self.activity(kind='ANALYSIS',request=req,run=run)
        work=schedule.work
        self.assertFalse(readiness(self.operator,work,include_confirmation=False)['ready'])
        for cap in (Capability.CONSUME_STOCK,Capability.RESERVE_STOCK):
            self.grant(cap,category=self.category,location=self.freezer)
        self.grant(Capability.MANAGE_BIOBANK,location=self.freezer)
        reserve_run(self.operator,run.pk,expected=run.version,key=uuid.uuid4(),
            allocations=reservation_proposal(self.operator,run)['allocations'],reason='Lots vérifiés pour cette analyse')
        self.assertFalse(readiness(self.operator,work,include_confirmation=False)['ready'])
        receive_sample(self.operator,key=uuid.uuid4(),code='PLAN-RECEIVED',amount=50,unit=self.ul,
            location=self.freezer,received_on=timezone.localdate(),reason='Échantillon reçu et rangé',
            request=req,source_key=source['key'],source_fingerprint=source['fingerprint'])
        self.assertTrue(readiness(self.operator,work,include_confirmation=False)['ready'])
        work=self.checked(schedule)
        lot=container.lot
        lot=control_lot(self.ops,lot.pk,expected=lot.version,status='RECALLED',reason='Anomalie fournisseur')
        with self.assertRaises(ValidationError):
            transition_work(self.operator,work.pk,expected=work.version,state='IN_PROGRESS')
        control_lot(self.ops,lot.pk,expected=lot.version,status='AVAILABLE',reason='Contrôle concluant consigné')
        work=transition_work(self.operator,work.pk,expected=work.version,state='IN_PROGRESS')
        with self.assertRaises(ValidationError):
            transition_work(self.operator,work.pk,expected=work.version,state='SUBMITTED',reason='Consommations non confirmées')
        run.refresh_from_db()
        allocation=RunAllocation.objects.get(requirement__run=run)
        confirm_run(self.operator,run.pk,expected=run.version,key=uuid.uuid4(),actuals={str(allocation.pk):'2'},
            reason='Quantités réelles confirmées',confirmed=True)
        work=transition_work(self.operator,work.pk,expected=work.version,state='SUBMITTED',reason='Analyse terminée et traçabilité vérifiée')
        transition_work(self.ops,work.pk,expected=work.version,state='APPROVED',reason='Résultat et compte rendu examinés')
        container.refresh_from_db()
        self.assertEqual((container.quantity,container.reserved),(8,0))
        self.assertEqual(reconcile_stock(self.ops),[])

    def test_readiness_rejects_missing_owner_expired_slot_and_archived_request(self):
        schedule, _ = self.activity(assignee=None)
        self.assertFalse(readiness(self.ops, schedule.work)['ready'])
        ActivitySchedule.objects.filter(pk=schedule.pk).update(ends_at=timezone.now()-timedelta(minutes=1))
        result = readiness(self.ops, schedule.work)
        self.assertTrue(any('terminé' in str(issue) for issue in result['issues']))
        request = Request.objects.create(title='Clôturée', requester=self.outsider, status='ARCHIVED', archived=True)
        with self.assertRaises(ValidationError):
            save_schedule(self.ops, schedule.work_id, expected=schedule.work.version,
                starts_at=self.start, ends_at=self.end, request=request, reason='Lien interdit')
        ActivitySchedule.objects.filter(pk=schedule.pk).update(request=request)
        self.assertTrue(any('archivée' in str(issue) for issue in readiness(self.ops, schedule.work)['issues']))

    def test_inactive_resource_location_and_invalid_dependency_order_are_rejected(self):
        from erp.models import Location
        first, _ = self.activity()
        second, _ = self.activity(starts_at=self.end, ends_at=self.end+timedelta(hours=1))
        with self.assertRaises(ValidationError):
            set_dependencies(self.ops, first.work_id, expected=first.work.version,
                prerequisites=[second.work], reason='Ordre inversé')
        self.assertFalse(ActivityDependency.objects.exists())
        Location.objects.filter(pk=self.lab.pk).update(active=False)
        self.assertTrue(any('désactivé' in str(issue) for issue in readiness(self.ops, first.work)['issues']))
        Location.objects.filter(pk=self.lab.pk).update(active=True)
        for prerequisites, reason in [([first.work], 'Dépendance sur soi'), ([], '')]:
            with self.subTest(reason=reason), self.assertRaises(ValidationError):
                set_dependencies(self.ops, first.work_id, expected=first.work.version,
                    prerequisites=prerequisites, reason=reason)

    def test_confirmation_note_and_closed_schedule_are_enforced(self):
        schedule, _ = self.activity()
        with self.assertRaises(ValidationError):
            confirm_resources(self.operator, schedule.work_id, expected=schedule.work.version, note='')
        work = self.checked(schedule)
        work = transition_work(self.operator, work.pk, expected=work.version, state='IN_PROGRESS')
        work = transition_work(self.operator, work.pk, expected=work.version, state='SUBMITTED', reason='Compte rendu')
        with self.assertRaises(ValidationError):
            save_schedule(self.ops, work.pk, expected=work.version, starts_at=self.start,
                ends_at=self.end, reason='Modification interdite')
        work = transition_work(self.ops, work.pk, expected=work.version, state='CHANGES_REQUESTED', reason='Revoir le contrôle')
        schedule.refresh_from_db()
        self.assertIsNone(schedule.resources_checked_at)
        self.assertIsNone(schedule.actual_finished_at)
        block = save_unavailability(self.ops, starts_at=self.end, ends_at=self.end+timedelta(hours=1),
            member=self.second, reason='Absence')
        with self.assertRaises(ValidationError):
            cancel_unavailability(self.ops, block.pk, expected=block.version, reason='')
        block.refresh_from_db()
        self.assertTrue(block.active)

    def test_request_assignment_is_checked_during_planning_and_delegation(self):
        member, _ = MemberProfile.objects.get_or_create(user=self.operator)
        request = Request.objects.create(title='Demande assignée', requester=self.outsider,
            assigned_to=member, status='ANALYSIS_STARTED')
        with self.assertRaises(ValidationError):
            self.activity(assignee=self.second, request=request)
        schedule, _ = self.activity(request=request)
        with self.assertRaises(ValidationError):
            delegate_work(self.ops, schedule.work_id, expected=schedule.work.version,
                assignee=self.second, reason='Membre non autorisé')
        schedule.work.refresh_from_db()
        self.assertEqual(schedule.work.assignee_id, self.operator.pk)
