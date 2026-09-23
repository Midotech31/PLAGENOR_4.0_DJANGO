from datetime import timedelta
import uuid

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from erp.models import ActivitySchedule, AvailabilityBlock, PlanningResource
from erp.services.planning import create_activity, save_resource
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False, STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class PlanningHttpContracts(OperationFixtures, TestCase):
    def setUp(self):
        self.client.force_login(self.ops)
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(days=1)
        self.end = self.start + timedelta(hours=1)
        self.resource = save_resource(self.ops, {'code': 'HTTP-EQ', 'name': 'Instrument',
            'kind': 'EQUIPMENT', 'location': self.lab})

    def dates(self):
        return {'starts_at': timezone.localtime(self.start).isoformat(),
                'ends_at': timezone.localtime(self.end).isoformat()}

    def post(self, name, data, *args, status=302):
        response = self.client.post(reverse(name, args=args), data)
        self.assertEqual(response.status_code, status,
            response.context['form'].errors if response.context and 'form' in response.context else response.content[:300])
        return response

    def test_schedule_edits_and_dependency_conflicts_preserve_previous_state(self):
        work = create_work(self.ops, kind='CONTROL', title='Contrôle', assignee=self.operator)
        data = {**self.dates(), 'expected_version': work.version,
                'resources': [self.resource.pk], 'reason': 'Planning initial'}
        self.post('erp:activity-schedule', data, work.pk)
        slot = ActivitySchedule.objects.get(work=work)
        work.refresh_from_db()
        self.post('erp:activity-schedule', {**data, 'expected_version': work.version, 'reason': ''},
                  work.pk, status=400)
        slot.refresh_from_db()
        self.assertEqual(slot.starts_at, self.start)
        prerequisite = create_work(self.ops, kind='CONTROL', title='Préparation')
        deps = {'expected_version': work.version, 'prerequisites': [prerequisite.pk], 'reason': 'Ordre nécessaire'}
        self.post('erp:activity-dependencies', deps, work.pk)
        self.assertEqual(work.prerequisites.get().prerequisite_id, prerequisite.pk)
        self.post('erp:activity-dependencies', {'expected_version': prerequisite.version,
            'prerequisites': [work.pk], 'reason': 'Cycle interdit'}, prerequisite.pk, status=400)
        self.assertFalse(prerequisite.prerequisites.exists())
        work.refresh_from_db()
        self.post('erp:activity-detail', {'expected_version': work.version,
            'note': 'Vérification avant prérequis', 'confirmed': 'on'}, work.pk, status=400)
        slot.refresh_from_db()
        self.assertIsNone(slot.resources_checked_at)

    def test_resource_updates_reject_stale_versions(self):
        values = {'code': 'HTTP-ROOM', 'name': 'Salle', 'kind': 'ROOM',
                  'location': self.lab.pk, 'active': 'on'}
        self.post('erp:resource-create', values)
        resource = PlanningResource.objects.get(code='HTTP-ROOM')
        update = {**values, 'expected_version': resource.version, 'name': 'Salle mise à jour'}
        self.post('erp:resource-edit', update, resource.pk)
        self.post('erp:resource-edit', {**update, 'name': 'Écrasement périmé'}, resource.pk, status=400)
        resource.refresh_from_db()
        self.assertEqual(resource.name, 'Salle mise à jour')

    def test_unavailability_creation_release_and_stale_release(self):
        self.post('erp:unavailability-create', {**self.dates(),
            'resource': self.resource.pk, 'reason': 'Maintenance'})
        block = AvailabilityBlock.objects.get(resource=self.resource)
        url = reverse('erp:unavailability-end', args=[block.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.post('erp:unavailability-end', {'expected_version': block.version + 1,
            'reason': 'Version périmée'}, block.pk, status=400)
        block.refresh_from_db()
        self.assertTrue(block.active)
        self.post('erp:unavailability-end', {'expected_version': block.version,
            'reason': 'Maintenance terminée'}, block.pk)
        block.refresh_from_db()
        self.assertFalse(block.active)
        self.post('erp:unavailability-create', {**self.dates(),
            'resource': self.resource.pk, 'member': self.operator.pk, 'reason': 'Deux cibles'}, status=400)

    def test_creation_conflict_and_filtered_pending_request(self):
        create_activity(self.ops, key=uuid.uuid4(), kind='CONTROL', title='Occupée',
            assignee=self.operator, starts_at=self.start, ends_at=self.end, resources=[self.resource])
        self.post('erp:activity-create', {**self.dates(), 'key': uuid.uuid4(), 'kind': 'MEETING',
            'title': 'Conflit', 'assignee': self.operator.pk, 'resources': [self.resource.pk],
            'priority': 'NORMAL', 'frequency': 'ONCE', 'occurrences': 1}, status=400)
        self.assertEqual(ActivitySchedule.objects.count(), 1)
        member, _ = MemberProfile.objects.get_or_create(user=self.operator)
        service = Service.objects.create(code='HTTP-PLAN', name='Analyse')
        request = Request.objects.create(requester=self.outsider, assigned_to=member,
            service=service, title='Demande à planifier', status='IN_PROGRESS')
        response = self.client.get(reverse('erp:activity-create'), {'request': request.pk})
        self.assertEqual(response.context['form'].initial['request'], request)
        response = self.client.get(reverse('erp:planning'), {'kind': 'CONTROL',
            'member': self.operator.pk, 'q': 'Occupée', 'date': self.start.date().isoformat()})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['slot_count'], 1)
        self.assertEqual(response.context['sources'][0]['request'], request)
