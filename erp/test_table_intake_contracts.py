"""Import boundary validation, including worker failures and semaphore recovery."""
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from erp.services import table_intake as intake


class TableIntakeContracts(SimpleTestCase):
    def test_unknown_schema_and_invalid_upload_sizes(self):
        with self.assertRaises(ValidationError):
            intake.schema('UNKNOWN')
        for data in (None, '', b'', b'x' * (intake.MAX_FILE + 1)):
            with self.subTest(size=len(data) if data is not None else None), self.assertRaises(ValidationError):
                intake.parse_table('LOCATIONS', 'locations.csv', data)

    def test_csv_headers_and_unlabelled_cells(self):
        for data in (b'code,name\nA,Room\n', b'code,name,kind_code\nA,Room,ROOM,unlabelled\n',
                     b'code,name,kind_code\n', b'code,name,kind_code\n,,\n'):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                intake.parse_table('LOCATIONS', 'locations.csv', data)
        rows = intake.parse_table('LOCATIONS', 'locations.csv',
            b'code,name,kind_code,\nA,Room,ROOM,\n,,,\nB,Freezer,FREEZER,\n,,,\n')
        self.assertEqual([row['data']['code'] for row in rows], ['A', 'B'])
        self.assertEqual([row['row'] for row in rows], [2, 4])

    def test_worker_failures_release_validation_slot(self):
        failures = [OSError('Worker unavailable'), subprocess.TimeoutExpired('worker', 8)]
        for error in failures:
            with self.subTest(error=type(error).__name__), patch.object(intake, '_VALIDATION_SLOT') as slot:
                slot.acquire.return_value = True
                with patch('subprocess.run', side_effect=error), self.assertRaises(ValidationError):
                    intake.read_matrix(b'data', '.csv')
                slot.release.assert_called_once_with()
        for output in (b'not json', b'x' * (6 * 1024 * 1024 + 1)):
            with patch('subprocess.run', return_value=SimpleNamespace(stdout=output, returncode=0)):
                with self.assertRaises(ValidationError):
                    intake.read_matrix(b'data', '.csv')
        self.assertTrue(intake._VALIDATION_SLOT.acquire(blocking=False))
        intake._VALIDATION_SLOT.release()

    def test_busy_worker_is_not_started(self):
        with patch.object(intake, '_VALIDATION_SLOT') as slot, patch('subprocess.run') as worker:
            slot.acquire.return_value = False
            with self.assertRaises(ValidationError):
                intake.read_matrix(b'data', '.csv')
            worker.assert_not_called()
            slot.release.assert_not_called()

    def test_defensive_matrix_contract_from_worker(self):
        header = ['code', 'name', 'kind_code']
        for matrix in ([header], [header] + [['A', 'Room', 'ROOM']] * 501,
                       [header, ['', '', '']], [header, []]):
            with self.subTest(rows=len(matrix)), patch.object(intake, 'read_matrix', return_value=matrix):
                with self.assertRaises(ValidationError):
                    intake.parse_table('LOCATIONS', 'locations.csv', b'data')
