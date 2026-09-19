import io
from pathlib import Path
import subprocess
import sys
import zipfile
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from core.document_probe import validate_docx, validate_pdf
from core.upload_validation import validate_document
from core.uploads import validate_upload
from plagenor.test_documents import valid_docx_bytes, valid_pdf_bytes


DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


def archive_bytes(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, contents in entries:
            archive.writestr(name, contents)
    return output.getvalue()


def docx_members():
    with zipfile.ZipFile(io.BytesIO(valid_docx_bytes())) as archive:
        return [(name, archive.read(name)) for name in archive.namelist()]


class UploadStructureTests(SimpleTestCase):
    def assertRejected(self, data, extension, kind='report', mime=None):
        upload = SimpleUploadedFile('upload' + extension, data, mime or (DOCX_MIME if extension == '.docx' else 'application/pdf'))
        with self.assertRaises(ValidationError):
            validate_upload(upload, kind)
        self.assertEqual(upload.tell(), 0)
        if mime is None:
            with self.assertRaises(Exception):
                (validate_docx if extension == '.docx' else validate_pdf)(data)

    def test_valid_pdf_is_preserved_and_renamed(self):
        upload = SimpleUploadedFile('customer-file.pdf', valid_pdf_bytes(), 'application/pdf')
        self.assertIs(validate_upload(upload, 'business_document'), upload)
        self.assertRegex(upload.name, r'^[a-f0-9]{32}\.pdf$')
        self.assertEqual(upload.tell(), 0)
        self.assertEqual(upload.read(), valid_pdf_bytes())
        validate_pdf(valid_pdf_bytes())

    def test_pdf_fake_truncated_header_only_and_misnamed_formats(self):
        for data in (b'%PDF-1.7\nnot a document', b'%PDF-1.7', valid_pdf_bytes()[:-24],
                     b'<html>not a PDF</html>', valid_docx_bytes(), valid_pdf_bytes().replace(b'/Type /Page', b'/Type /Fake')):
            with self.subTest(length=len(data)):
                self.assertRejected(data, '.pdf')
        with override_settings(UPLOAD_MAX_BYTES=100):
            self.assertRejected(valid_pdf_bytes(), '.pdf', mime='application/pdf')
        self.assertRejected(valid_pdf_bytes(), '.pdf', mime='text/html')

    def test_pdf_encrypted_and_invalid_page_trees_are_rejected(self):
        from pypdf import PdfWriter
        for encrypted, pages in ((True, 1), (False, 0)):
            writer = PdfWriter()
            if pages:
                writer.add_blank_page(width=595, height=842)
            if encrypted:
                writer.encrypt('Synthetic-password')
            buffer = io.BytesIO(); writer.write(buffer); writer.close()
            self.assertRejected(buffer.getvalue(), '.pdf')
        for data in (b'%PDF-1.7\nstartxref 1\n%%EOF', valid_pdf_bytes().replace(b'startxref', b'invalidxx')):
            with self.assertRaises(Exception):
                validate_pdf(data)

    def test_docx_structure_xml_and_relationships(self):
        upload = SimpleUploadedFile('normal.docx', valid_docx_bytes(), DOCX_MIME)
        self.assertIs(validate_upload(upload, 'report'), upload)
        validate_docx(valid_docx_bytes())
        cases = [[], [('word/document.xml', '<document/>')],
                 [('[Content_Types].xml', '<Types/>'), ('word/document.xml', '<document/>')]]
        members = docx_members()
        for path in ('word/document.xml', '[Content_Types].xml', '_rels/.rels'):
            cases.append([(name, b'<invalid') if name == path else (name, data) for name, data in members])
        cases.append([(name, b'<document/>') if name == 'word/document.xml' else (name, data) for name, data in members])
        cases.append([(name, b'<Types/>') if name == '[Content_Types].xml' else (name, data) for name, data in members])
        cases.append([(name, data.replace(b'word/document.xml', b'word/other.xml')) if name == '_rels/.rels' else (name, data) for name, data in members])
        cases.append(members + [('word/extra.xml', b'<!DOCTYPE x [<!ENTITY e "value">]><x>&e;</x>')])
        for entries in cases:
            with self.subTest(names=[name for name, _ in entries]):
                self.assertRejected(archive_bytes(entries), '.docx')

    def test_docx_entry_count_sizes_ratio_and_paths_are_bounded(self):
        members = docx_members()
        cases = [members + [('word/extra/%s.bin' % i, b'x') for i in range(2000)],
                 members + [('word/large.bin', b'X' * (9 * 1024 * 1024))],
                 members + [('word/compressed.bin', b'X' * (2 * 1024 * 1024))]]
        for entries in cases:
            self.assertRejected(archive_bytes(entries), '.docx')
        for path in ('../outside.xml', 'word/../outside.xml', 'word\\outside.xml', '/absolute.xml',
                     'C:/absolute.xml', 'word/%2e%2e/out.xml', 'word/file. ', 'WORD/document.xml',
                     'word/vbaProject.bin', 'word/embeddings/object.bin'):
            self.assertRejected(archive_bytes(members + [(path, b'content')]), '.docx')
        with patch('core.document_probe.MAX_EXPANDED_BYTES', len(valid_docx_bytes())):
            with self.assertRaises(ValueError):
                validate_docx(valid_docx_bytes())

    def test_worker_failures_are_fail_closed_without_environment_secrets(self):
        with patch('core.upload_validation.subprocess.run') as run:
            run.return_value.returncode = 0
            with patch.dict('os.environ', {'DATABASE_URL': 'test-secret-not-production', 'SMTP_PASSWORD': 'fixture-secret'}):
                validate_document(valid_pdf_bytes(), '.pdf')
            self.assertNotIn('DATABASE_URL', run.call_args.kwargs['env'])
            self.assertNotIn('SMTP_PASSWORD', run.call_args.kwargs['env'])
            self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)
            run.return_value.returncode = 1
            with self.assertRaises(ValidationError): validate_document(valid_pdf_bytes(), '.pdf')
            for error in (OSError('missing worker'), subprocess.TimeoutExpired('worker', 6)):
                run.side_effect = error
                with self.assertRaises(ValidationError): validate_document(valid_pdf_bytes(), '.pdf')
        with patch('core.upload_validation._VALIDATION_SLOT') as slot:
            slot.acquire.return_value = False
            with self.assertRaises(ValidationError): validate_document(valid_pdf_bytes(), '.pdf')
            slot.release.assert_not_called()

    def test_worker_memory_limit_is_effective_in_separate_process(self):
        path = str(Path(__file__).with_name('document_probe.py'))
        code = ('import runpy\nd=runpy.run_path(' + repr(path) + ')\nd["limit_resources"]()\n'
                'try:\n data=bytearray(256*1024*1024)\nexcept MemoryError:\n print("BOUNDED")\n')
        result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, stdin=subprocess.DEVNULL, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'BOUNDED')
