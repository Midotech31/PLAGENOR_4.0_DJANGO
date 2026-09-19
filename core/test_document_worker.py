import io
import runpy
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from pypdf import PdfWriter
from pypdf.generic import NameObject, NumberObject, ArrayObject, DecodedStreamObject

from core import document_probe as probe
from plagenor.test_documents import valid_pdf_bytes, valid_docx_bytes
from core.test_upload_security import archive_bytes, docx_members


class DocumentWorkerBoundaryTests(SimpleTestCase):
    def kernel(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 77
        kernel.SetInformationJobObject.return_value = True
        kernel.GetCurrentProcess.return_value = 22
        kernel.AssignProcessToJobObject.return_value = True
        return kernel

    def test_windows_resource_contract_and_failures(self):
        kernel = self.kernel()
        with patch('ctypes.WinDLL', return_value=kernel, create=True):
            self.assertEqual(probe._windows_limits(), 77)
        args = kernel.SetInformationJobObject.call_args.args
        self.assertEqual(args[:2], (77, 9))
        limits = args[2]._obj
        self.assertEqual(limits.ProcessMemory, probe.MEMORY_BYTES)
        self.assertEqual(limits.Basic.ProcessTime, probe.CPU_SECONDS * 10_000_000)
        self.assertEqual(limits.Basic.ActiveProcesses, 1)
        self.assertEqual(limits.Basic.Flags, 0x10A)
        kernel.AssignProcessToJobObject.assert_called_once_with(77, 22)
        for function in ('CreateJobObjectW', 'SetInformationJobObject', 'AssignProcessToJobObject'):
            kernel = self.kernel()
            getattr(kernel, function).return_value = 0
            with patch('ctypes.WinDLL', return_value=kernel, create=True):
                with self.assertRaises(OSError): probe._windows_limits()
            if function != 'CreateJobObjectW': kernel.CloseHandle.assert_called_once_with(77)

    def test_resource_limits_select_correct_os_adapter(self):
        resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CPU=2, RLIMIT_FSIZE=3, setrlimit=Mock())
        with patch('core.document_probe.os.name', 'posix'), patch.dict(sys.modules, {'resource': resource}):
            probe.limit_resources()
        self.assertEqual(resource.setrlimit.call_args_list[0].args, (1, (probe.MEMORY_BYTES, probe.MEMORY_BYTES)))
        self.assertEqual(resource.setrlimit.call_count, 3)
        with patch('core.document_probe.os.name', 'nt'), patch.object(probe, '_windows_limits', return_value=77):
            probe.limit_resources()
        self.assertEqual(probe._JOB_HANDLE, 77)

    def test_worker_protocol_valid_empty_oversized_and_unknown_document(self):
        for suffix, data, expected in (('.pdf', valid_pdf_bytes(), 0), ('.docx', valid_docx_bytes(), 0),
                                       ('.pdf', b'', 1), ('.pdf', b'Not a PDF', 1), ('.exe', b'MZ', 1)):
            with patch.object(probe, 'limit_resources'), patch.object(sys, 'argv', ['worker', suffix]), patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(data))):
                self.assertEqual(probe.main(), expected)
        with patch.object(probe, 'limit_resources'), patch.object(probe, 'MAX_INPUT', 10), patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b'x'*11))):
            self.assertEqual(probe.main(), 1)
        with patch.object(probe, 'limit_resources', side_effect=OSError('limits unavailable')):
            self.assertEqual(probe.main(), 1)

    def test_worker_command_entrypoint_reports_failure_without_output(self):
        resource = SimpleNamespace(RLIMIT_AS=1, RLIMIT_CPU=2, RLIMIT_FSIZE=3, setrlimit=Mock())
        with patch.dict(sys.modules, {'resource': resource}), patch('ctypes.WinDLL', return_value=self.kernel(), create=True), patch.object(sys, 'argv', ['worker', '.pdf']), patch.object(sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(b''))):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(Path(probe.__file__)), run_name='__main__')
        self.assertEqual(result.exception.code, 1)

    def test_pdf_page_contents_and_dimensions_are_checked(self):
        for content, valid in ((None, True), ('stream', True), ('array', True), ('invalid', False), ('dimensions', False), ('type', False)):
            writer = PdfWriter()
            page = writer.add_blank_page(width=595, height=842)
            if content in ('stream', 'array'):
                stream = DecodedStreamObject(); stream.set_data(b'q Q')
                indirect = writer._add_object(stream)
                page[NameObject('/Contents')] = ArrayObject([indirect]) if content == 'array' else indirect
            elif content == 'invalid': page[NameObject('/Contents')] = NumberObject(1)
            elif content == 'dimensions': page.mediabox.upper_right = (0, 0)
            elif content == 'type': writer._root_object[NameObject('/Type')] = NameObject('/Invalid')
            target = io.BytesIO(); writer.write(target); writer.close()
            if valid: probe.validate_pdf(target.getvalue())
            else:
                with self.assertRaises(ValueError): probe.validate_pdf(target.getvalue())
        with patch.object(probe, 'MAX_PAGES', 0):
            with self.assertRaises(ValueError): probe.validate_pdf(valid_pdf_bytes())
        reader = Mock()
        reader.__enter__ = Mock(return_value=reader); reader.__exit__ = Mock(return_value=False)
        reader.is_encrypted = False; reader.root_object = {'/Type':'/Catalog','/Pages':{'/Count':1}}
        reader.pages = []
        with patch('pypdf.PdfReader',return_value=reader):
            with self.assertRaises(ValueError): probe.validate_pdf(valid_pdf_bytes())
        reader.pages = [Mock(get=Mock(return_value='/Invalid'), mediabox=[0,0,100,100])]
        with patch('pypdf.PdfReader',return_value=reader):
            with self.assertRaises(ValueError): probe.validate_pdf(valid_pdf_bytes())

    def test_archive_directories_and_metadata_stream_inconsistencies(self):
        members = docx_members()
        probe.validate_docx(archive_bytes(members + [('word/extra/', b'')]))
        for replacement, label in ((b'', 'truncated'), (b'x'*10000, 'extra')):
            archive = zipfile.ZipFile(io.BytesIO(valid_docx_bytes()))
            original = archive.open
            def open_member(member, *args, **kwargs):
                return io.BytesIO(replacement) if member.filename == '[Content_Types].xml' else original(member, *args, **kwargs)
            with patch.object(archive,'open',side_effect=open_member), patch.object(probe.zipfile,'ZipFile',return_value=archive):
                with self.assertRaises(ValueError): probe.validate_docx(valid_docx_bytes())
            archive.close()
