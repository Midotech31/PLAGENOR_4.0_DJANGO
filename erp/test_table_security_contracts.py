"""Reject oversized archives before workbook interpretation."""
import io
import json
import runpy
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from django.test import SimpleTestCase
from erp import table_probe
from erp.services.table_intake import parse_table
from erp.test_coverage_completion_pure import workbook_bytes, rewrite_zip


class TableSecurityContracts(SimpleTestCase):
    def test_archive_count_expansion_and_unsupported_relationships(self):
        helpers = runpy.run_path(str(Path(table_probe.__file__).resolve().parents[1] / 'core/document_probe.py'))
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, 'w'):
            pass
        crowded = io.BytesIO()
        with zipfile.ZipFile(crowded, 'w') as archive:
            for index in range(513):
                archive.writestr(f'{index}.txt', b'')
        payload = workbook_bytes()
        cases = [empty.getvalue(), crowded.getvalue(),
            rewrite_zip(payload, additions=[('large.txt', b'x' * (8 * 1024 * 1024 + 1))]),
            rewrite_zip(payload, additions=[('compressed.txt', b'x' * (1024 * 1024 + 1))])]
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaisesRegex(ValueError, 'SIZE'):
                table_probe.xlsx_rows(data, helpers)
        # Connections are forbidden even without executable VBA or external links.
        data = rewrite_zip(payload, additions=[('xl/connections.xml', b'<connections/>')])
        with self.assertRaisesRegex(ValueError, 'ACTIVE'):
            table_probe.xlsx_rows(data, helpers)

    def test_matrix_limit_and_command_line_protocol(self):
        with patch.object(table_probe, 'csv_rows', return_value=[['value']] * 502):
            with self.assertRaisesRegex(ValueError, 'SIZE'):
                table_probe.read_matrix(b'valid input', '.csv', {})
        output = Mock(buffer=io.BytesIO())
        helpers = {'limit_resources': Mock()}
        with patch.object(sys, 'stdin', Mock(buffer=io.BytesIO(b'a,b\n1,2\n'))), \
             patch.object(sys, 'stdout', output), patch.object(sys, 'argv', ['probe', '.csv']), \
             patch('runpy.run_path', return_value=helpers):
            # Obtain the entry-point code before replacing runpy.run_path.
            code = compile(Path(table_probe.__file__).read_text(), table_probe.__file__, 'exec')
            with self.assertRaises(SystemExit) as exited:
                exec(code, {'__name__': '__main__', '__file__': table_probe.__file__})
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(json.loads(output.buffer.getvalue()), {'rows': [['a', 'b'], ['1', '2']]})

    def test_blank_middle_rows_preserve_spreadsheet_row_numbers(self):
        matrix = [['code', 'name', 'category_code', 'base_unit_code'], [], ['A', 'Article', 'REAGENTS', 'PIECE']]
        with patch('erp.services.table_intake.read_matrix', return_value=matrix):
            rows = parse_table('CATALOG', 'input.csv', b'input')
        self.assertEqual(rows, [{'row': 3, 'data': dict(zip(matrix[0], matrix[2]))}])
