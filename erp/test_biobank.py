from datetime import timedelta
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import MemberProfile
from core.models import Request, Service
from core.ibtikar.models import IbtikarSubmission
from core.ibtikar.schema import get_schema, schema_digest
from erp.models import (BiologicalSample, Capability, Location, PositionReservation, SampleEvent,
    StorageIncident, StoragePosition, StorageTransfer, TemperatureReading, WorkItem)
from erp.services.biobank import (aliquot_sample, biobank_scope, build_positions,
    convert_sample_quantity, receive_sample, reconcile_biobank, reserve_position,
    sample_action, source_samples, transfer_sample)
from erp.services.cold_storage import (apply_transfer_plan, create_incident,
    record_temperature, resolve_incident, transfer_plan)
from erp.services.common import Conflict
from erp.services.storage import save_location
from erp.services.work import create_work
from erp.test_operations import OperationFixtures


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], SECURE_SSL_REDIRECT=False,
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class BiobankTests(OperationFixtures, TestCase):
    def setUp(self):
        self.box_location = save_location(self.admin, {'code': 'CRYO1', 'name': 'Cryoboîte 1',
            'kind': self.storage_kind, 'parent': self.rack, 'grid_rows': 2, 'grid_columns': 3})
        self.target = save_location(self.admin, {'code': 'CRYO2', 'name': 'Cryoboîte 2',
            'kind': self.storage_kind, 'parent': self.freezer, 'grid_rows': 2, 'grid_columns': 3})
        self.workbench = save_location(self.admin, {'code': 'BENCH', 'name': 'Paillasse', 'kind': self.storage_kind, 'parent': self.lab})
        self.positions = list(self.box_location.positions.order_by('row', 'column'))
        self.targets = list(self.target.positions.order_by('row', 'column'))

    def sample(self, code='S-1', amount=100, **changes):
        values = {'key': uuid.uuid4(), 'code': code, 'amount': Decimal(amount), 'unit': self.ul,
            'location': self.box_location, 'position': self.positions[0],
            'received_on': timezone.localdate(), 'reason': 'Réception physique contrôlée',
            'sample_type': 'ADN extrait', 'matrix': 'Culture bactérienne', 'freeze_thaw_limit': 2}
        values.update(changes)
        return receive_sample(self.admin, **values), values

    def test_grids_created_idempotently_and_occupied_positions_are_unique(self):
        self.assertEqual(len(self.positions), 6)
        build_positions(self.admin, self.box_location.pk, expected=self.box_location.version)
        self.assertEqual(self.box_location.positions.count(), 6)
        sample, values = self.sample()
        self.assertEqual(receive_sample(self.admin, **values).pk, sample.pk)
        self.assertEqual(BiologicalSample.objects.count(), 1)
        with self.assertRaises(ValidationError):
            self.sample('S-2')
        with self.assertRaises(ValidationError):
            save_location(self.admin, {'grid_rows': 1, 'grid_columns': 1, 'capacity': 1},
                pk=self.box_location.pk, expected=self.box_location.version)
        with self.assertRaises(ValidationError):
            save_location(self.admin, {'active': False}, pk=self.box_location.pk, expected=self.box_location.version)
        self.assertEqual(reconcile_biobank(self.admin), [])
        self.assertEqual(sample.events.count(), 1)

    def test_position_reservations_expire_and_respect_assignee(self):
        reservation = reserve_position(self.admin, self.positions[0].pk, assignee=self.operator,
            until=timezone.now() + timedelta(hours=1), reason='Réception planifiée')
        with self.assertRaises(ValidationError):
            self.sample()
        self.grant(Capability.MANAGE_BIOBANK, location=self.freezer)
        values = {'key': uuid.uuid4(), 'code': 'S-OP', 'amount': 10, 'unit': self.ul,
            'location': self.box_location, 'position': self.positions[0], 'received_on': timezone.localdate(), 'reason': 'Réception assignée'}
        sample = receive_sample(self.operator, **values)
        reservation.refresh_from_db()
        self.assertFalse(reservation.active)
        self.assertEqual(sample.position_id, self.positions[0].pk)
        with self.assertRaises(PermissionDenied):
            reserve_position(self.operator, self.positions[1].pk, assignee=self.second,
                until=timezone.now()+timedelta(hours=1), reason='Interdit')
        reservation2 = reserve_position(self.admin, self.positions[1].pk, assignee=self.second,
            until=timezone.now()+timedelta(hours=1), reason='À expirer')
        PositionReservation.objects.filter(pk=reservation2.pk).update(until=timezone.now()-timedelta(minutes=1))
        self.sample('S-EXP', position=self.positions[1])
        reservation2.refresh_from_db()
        self.assertFalse(reservation2.active)

    def test_sample_receipt_rejects_invalid_values_atomically(self):
        _, valid = self.sample()
        invalid = [{'amount': 0}, {'amount': 'NaN'}, {'amount': '0.0000001'},
            {'received_on': timezone.localdate()+timedelta(days=1)}, {'position': None},
            {'position': self.targets[0]}, {'collected_on': timezone.localdate()+timedelta(days=1)},
            {'concentration_value': Decimal('5')}, {'temperature_min': 2, 'temperature_max': -20},
            {'source_key': 'unlinked'}, {'reason': ''}]
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                receive_sample(self.admin, **{**valid, 'key': uuid.uuid4(), 'code': 'BAD', 'position': self.positions[1], **values})
            self.assertEqual(BiologicalSample.objects.count(), 1)
            self.assertEqual(SampleEvent.objects.count(), 1)
        with self.assertRaises(Conflict):
            receive_sample(self.admin, **{**valid, 'amount': 101})
        self.assertEqual(convert_sample_quantity(1, self.ml, self.ul), Decimal(1000))
        with self.assertRaises(ValidationError):
            convert_sample_quantity(1, self.unit, self.ml)

    def test_request_source_bridge_has_no_duplicate_and_no_silent_source_update(self):
        service = Service.objects.create(code='EGTP-GDE', name='Extraction')
        profile, _ = MemberProfile.objects.get_or_create(user=self.operator)
        req = Request.objects.create(requester=self.outsider, assigned_to=profile, service=service,
            status='IN_PROGRESS', title='Demande synthétique', sample_table=[{'sample_code': 'B1', 'quantity': '25', 'quantity_unit': 'µL', 'sample_type': 'ADN'}])
        self.grant(Capability.MANAGE_BIOBANK, location=self.freezer)
        source = source_samples(self.operator, req)[0]
        sample, values = self.sample(request=req, source_key=source['key'], source_fingerprint=source['fingerprint'])
        self.assertEqual(sample.origin_request_id, req.pk)
        self.assertEqual(source_samples(self.operator, req)[0]['existing'].pk, sample.pk)
        with self.assertRaises(Conflict):
            receive_sample(self.admin, **{**values, 'key': uuid.uuid4(), 'code': 'DUP', 'position': self.positions[1]})
        req.sample_table[0]['quantity'] = '30'
        req.save(update_fields=['sample_table'])
        self.assertTrue(source_samples(self.operator, req)[0]['source_changed'])
        sample.refresh_from_db()
        self.assertEqual(sample.source_snapshot['row']['quantity'], '25')
        with self.assertRaises(PermissionDenied):
            source_samples(self.second, req)
        self.client.force_login(self.operator)
        response = self.client.get(reverse('erp:sample-sources', args=[req.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'B1')
        req.sample_table = [{'sample_code': 'B1'}, {'sample_code': 'b1'}]
        req.save(update_fields=['sample_table'])
        with self.assertRaises(ValidationError):
            source_samples(self.operator, req)

    def test_ibtikar_source_reordering_keeps_identity_and_stale_receipt_is_rejected(self):
        service = Service.objects.create(code='EGTP-GDE', name='Extraction')
        req = Request.objects.create(requester=self.outsider, service=service, title='IBTIKAR de recette', status='IN_PROGRESS')
        schema = get_schema('EGTP-GDE')
        submission = IbtikarSubmission.objects.create(request=req, schema=schema, schema_hash=schema_digest(schema),
            samples=[{'sample_code': 'A', 'quantity': '10'}, {'sample_code': 'B', 'quantity': '20'}])
        sources = source_samples(self.admin, req)
        submission.samples.reverse()
        submission.save(update_fields=['samples'])
        reordered = source_samples(self.admin, req)
        self.assertEqual(sources[0]['key'], reordered[1]['key'])
        self.assertEqual(sources[0]['fingerprint'], reordered[1]['fingerprint'])
        submission.samples[1]['quantity'] = '50'
        submission.save(update_fields=['samples'])
        with self.assertRaises(Conflict):
            self.sample(request=req, source_key=sources[0]['key'], source_fingerprint=sources[0]['fingerprint'])
        self.assertFalse(BiologicalSample.objects.exists())

    def test_aliquot_parent_volume_conservation_and_idempotent_retry(self):
        parent, _ = self.sample()
        key = uuid.uuid4()
        values = {'key': key, 'code': 'A-1', 'amount': Decimal('0.025'), 'unit': self.ml,
            'location': self.box_location, 'position': self.positions[1], 'reason': 'Aliquot pour analyse'}
        child = aliquot_sample(self.admin, parent.pk, **values)
        self.assertEqual(aliquot_sample(self.admin, parent.pk, **values).pk, child.pk)
        parent.refresh_from_db()
        self.assertEqual((parent.remaining_quantity, child.remaining_quantity), (75, 25))
        self.assertEqual(child.parent_id, parent.pk)
        self.assertEqual(child.root_sample_id, parent.pk)
        self.assertEqual(child.sample_type, '')
        self.assertEqual(child.shared_metadata.sample_type, 'ADN extrait')
        self.assertEqual(reconcile_biobank(self.admin), [])
        with self.assertRaises(ValidationError):
            aliquot_sample(self.admin, parent.pk, **{**values, 'key': uuid.uuid4(), 'code': 'A-2', 'amount': 76, 'unit': self.ul, 'position': self.positions[2]})
        self.assertEqual(BiologicalSample.objects.count(), 2)
        self.assertEqual(reconcile_biobank(self.admin), [])

    def test_chain_of_custody_checkout_return_thaw_and_terminal_consumption(self):
        sample, _ = self.sample()
        checkout = sample_action(self.admin, sample.pk, key=uuid.uuid4(), action='CHECK_OUT', reason='Préparation analyse',
            destination=self.workbench, thawed=True)
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'OUT')
        self.assertIsNone(sample.position_id)
        self.assertEqual(sample.freeze_thaw_cycles, 0)
        BiologicalSample.objects.filter(pk=sample.pk).update(checked_out_at=timezone.now()-timedelta(minutes=15))
        values = {'key': uuid.uuid4(), 'action': 'RETURN', 'reason': 'Retour au froid', 'destination': self.box_location, 'position': self.positions[0]}
        returned = sample_action(self.admin, sample.pk, **values)
        self.assertEqual(sample_action(self.admin, sample.pk, **values).pk, returned.pk)
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'STORED')
        self.assertEqual(sample.freeze_thaw_cycles, 1)
        self.assertGreaterEqual(sample.out_of_storage_seconds, 900)
        self.assertEqual(returned.from_location_id, self.workbench.pk)
        self.assertEqual(returned.to_location_id, self.box_location.pk)
        sample_action(self.admin, sample.pk, key=uuid.uuid4(), action='CONSUMPTION', reason='Analyse consommative', amount=100, unit=self.ul)
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'EXHAUSTED')
        self.assertIsNone(sample.position_id)
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action='CONSUMPTION', reason='Épuisé', amount=1, unit=self.ul)
        self.assertEqual(reconcile_biobank(self.admin), [])
        with self.assertRaises(ValidationError):
            sample.events.all().delete()

    def test_quarantine_requires_admin_release_and_scope_for_both_locations(self):
        sample, _ = self.sample()
        self.grant(Capability.MANAGE_BIOBANK, location=self.box_location)
        sample_action(self.operator, sample.pk, key=uuid.uuid4(), action='QUARANTINE', reason='Anomalie détectée')
        with self.assertRaises(PermissionDenied):
            sample_action(self.operator, sample.pk, key=uuid.uuid4(), action='RELEASE', reason='Auto-validation')
        with self.assertRaises(ValidationError):
            sample_action(self.admin, sample.pk, key=uuid.uuid4(), action='CONSUMPTION', reason='Bloqué', amount=1, unit=self.ul)
        with self.assertRaises(PermissionDenied):
            transfer_sample(self.operator, sample.pk, key=uuid.uuid4(), destination=self.target, position=self.targets[0], reason='Hors périmètre')
        sample_action(self.admin, sample.pk, key=uuid.uuid4(), action='RELEASE', reason='Contrôle concluant')
        key = uuid.uuid4()
        moved = transfer_sample(self.admin, sample.pk, key=key, destination=self.target, position=self.targets[0], reason='Rangement validé')
        self.assertEqual(transfer_sample(self.admin, sample.pk, key=key, destination=self.target, position=self.targets[0], reason='Rangement validé').pk, moved.pk)
        self.assertFalse(biobank_scope(self.operator).filter(pk=sample.pk).exists())
        sample.refresh_from_db()
        self.assertEqual(sample.freeze_thaw_cycles, 0)
        self.assertEqual(reconcile_biobank(self.admin), [])

    def test_mass_transfer_preview_is_atomic_stale_safe_and_idempotent(self):
        first, _ = self.sample('S-1')
        second, _ = self.sample('S-2', position=self.positions[1])
        mapping = transfer_plan(self.admin, self.box_location, self.target)
        self.assertEqual(len(mapping), 2)
        key = uuid.uuid4()
        transfer = apply_transfer_plan(self.admin, key=key, source=self.box_location, destination=self.target,
            mapping=mapping, reason='Maintenance du stockage')
        self.assertEqual(apply_transfer_plan(self.admin, key=key, source=self.box_location, destination=self.target,
            mapping=mapping, reason='Maintenance du stockage').pk, transfer.pk)
        self.assertEqual(BiologicalSample.objects.filter(location=self.target).count(), 2)
        self.assertEqual(SampleEvent.objects.filter(kind='TRANSFER').count(), 2)
        self.assertEqual(reconcile_biobank(self.admin), [])
        back = transfer_plan(self.admin, self.target, self.box_location)
        second.refresh_from_db()
        sample_action(self.admin, second.pk, key=uuid.uuid4(), action='CONSUMPTION', reason='Modification après aperçu', amount=1, unit=self.ul)
        with self.assertRaises(Conflict):
            apply_transfer_plan(self.admin, key=uuid.uuid4(), source=self.target, destination=self.box_location,
                mapping=back, reason='Plan périmé')
        self.assertEqual(BiologicalSample.objects.filter(location=self.target).count(), 2)
        self.assertEqual(StorageTransfer.objects.count(), 1)
        self.assertEqual(SampleEvent.objects.filter(kind='TRANSFER').count(), 2)

    def test_temperatures_snapshot_thresholds_group_incidents_and_require_review(self):
        first = record_temperature(self.admin, location=self.freezer, measured_at=timezone.now(), value=-65)
        second = record_temperature(self.admin, location=self.freezer, measured_at=timezone.now(), value=-64)
        self.assertTrue(first.out_of_range)
        self.assertEqual(first.incident_id, second.incident_id)
        third = record_temperature(self.admin, location=self.freezer, measured_at=timezone.now(), value=-80)
        self.assertFalse(third.out_of_range)
        incident = first.incident
        self.assertIsNone(incident.resolved_at)
        self.freezer.temperature_max = Decimal('-60')
        self.freezer.save(update_fields=['temperature_max'])
        first.refresh_from_db()
        self.assertEqual(first.maximum_snapshot, -70)
        with self.assertRaises(PermissionDenied):
            resolve_incident(self.operator, incident.pk, expected=incident.version,
                resolved_at=timezone.now(), corrective_action='Non habilité')
        resolve_incident(self.ops, incident.pk, expected=incident.version, resolved_at=timezone.now(),
            corrective_action='Sonde vérifiée, équipement stabilisé et impact examiné')
        incident.refresh_from_db()
        self.assertIsNotNone(incident.resolved_at)
        with self.assertRaises(ValidationError):
            TemperatureReading.objects.filter(pk=first.pk).update(value=0)

    def test_delegated_temperature_task_does_not_grant_biobank_access(self):
        work = create_work(self.ops, kind='TEMPERATURE', title='Relever le congélateur', assignee=self.operator, location=self.freezer)
        self.assertFalse(biobank_scope(self.operator).exists())
        reading = record_temperature(self.operator, location=self.freezer, measured_at=timezone.now(), value=-80, work=work)
        self.assertEqual(reading.actor_id, self.operator.pk)
        work.refresh_from_db()
        self.assertEqual(work.status, 'SUBMITTED')
        with self.assertRaises(PermissionDenied):
            record_temperature(self.operator, location=self.target, measured_at=timezone.now(), value=-80)

    def test_ui_access_and_grid_receipt_action_pages(self):
        sample, _ = self.sample()
        self.client.force_login(self.admin)
        routes = [('erp:sample-list', []), ('erp:sample-detail', [sample.pk]),
            ('erp:sample-receive', []), ('erp:sample-operation', [sample.pk, 'action']),
            ('erp:sample-operation', [sample.pk, 'aliquot']), ('erp:sample-operation', [sample.pk, 'transfer']),
            ('erp:storage-maps', []), ('erp:storage-grid', [self.box_location.pk]),
            ('erp:temperature-create', []), ('erp:cold-incidents', []), ('erp:mass-transfer', [])]
        for name, args in routes:
            with self.subTest(name=name, args=args):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)
        response = self.client.get(reverse('erp:position-options'), {'location': self.box_location.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['positions']), 6)
        self.assertTrue(response.json()['positions'][0]['occupied'])
        self.client.force_login(self.outsider)
        for name, args in [('erp:sample-list', []), ('erp:sample-receive', [])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403)
