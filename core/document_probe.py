from __future__ import annotations

import io
import math
import os
from pathlib import PurePosixPath
import re
import stat
import sys
import unicodedata
import zipfile

MAX_INPUT = 32 * 1024 * 1024
MAX_ENTRIES = 512
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_PAGES = 1000
MEMORY_BYTES = 192 * 1024 * 1024
CPU_SECONDS = 3
_JOB_HANDLE = None


def _windows_limits():
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [('ProcessTime', ctypes.c_longlong), ('JobTime', ctypes.c_longlong),
                    ('Flags', wintypes.DWORD), ('MinWorkingSet', ctypes.c_size_t),
                    ('MaxWorkingSet', ctypes.c_size_t), ('ActiveProcesses', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('Priority', wintypes.DWORD),
                    ('Scheduling', wintypes.DWORD)]

    class IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('ReadOperations', 'WriteOperations', 'OtherOperations',
                     'ReadBytes', 'WriteBytes', 'OtherBytes')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('Basic', BasicLimits), ('IO', IOCounters),
                    ('ProcessMemory', ctypes.c_size_t), ('JobMemory', ctypes.c_size_t),
                    ('PeakProcessMemory', ctypes.c_size_t), ('PeakJobMemory', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise OSError('Cannot create document validation limits')
    limits = ExtendedLimits()
    limits.Basic.Flags = 0x00000002 | 0x00000008 | 0x00000100
    limits.Basic.ProcessTime = CPU_SECONDS * 10_000_000
    limits.Basic.ActiveProcesses = 1
    limits.ProcessMemory = MEMORY_BYTES
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        kernel.CloseHandle(job)
        raise OSError('Cannot configure document validation limits')
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        kernel.CloseHandle(job)
        raise OSError('Cannot apply document validation limits')
    return job


def limit_resources():
    global _JOB_HANDLE
    if os.name == 'nt':
        _JOB_HANDLE = _windows_limits()
    else:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def validate_pdf(data):
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject, StreamObject

    if not re.match(rb'%PDF-(?:1\.[0-7]|2\.0)[\r\n]', data):
        raise ValueError('Invalid PDF header')
    tail = re.search(rb'startxref\s+([0-9]+)\s+%%EOF\s*\Z', data[-4096:])
    if not tail or not 0 < int(tail[1]) < len(data):
        raise ValueError('Invalid PDF trailer')
    with PdfReader(io.BytesIO(data), strict=True) as reader:
        if reader.is_encrypted or reader.root_object.get('/Type') != '/Catalog':
            raise ValueError('Unsupported PDF structure')
        pages_root = reader.root_object['/Pages']
        if not 1 <= int(pages_root.get('/Count', 0)) <= MAX_PAGES:
            raise ValueError('Invalid PDF page count')
        pages = reader.pages
        if not 1 <= len(pages) <= MAX_PAGES:
            raise ValueError('Invalid PDF page tree')
        for page in pages:
            box = page.mediabox
            if page.get('/Type') != '/Page' or not all(math.isfinite(float(v)) for v in box):
                raise ValueError('Invalid PDF page')
            if box.width <= 0 or box.height <= 0:
                raise ValueError('Invalid PDF dimensions')
            contents = page.get('/Contents')
            if contents is not None:
                contents = contents.get_object()
                parts = contents if isinstance(contents, ArrayObject) else [contents]
                if not all(isinstance(part.get_object(), StreamObject) for part in parts):
                    raise ValueError('Invalid PDF page contents')


def _entry_key(info):
    name = info.filename
    key = name[:-1] if name.endswith('/') else name
    if (not key or key != unicodedata.normalize('NFC', key)
            or any(char in key for char in ('\\', ':', '%', '\x00'))
            or any(unicodedata.category(char).startswith('C') for char in key)
            or any(part in ('', '.', '..') or part.endswith((' ', '.')) for part in key.split('/'))
            or PurePosixPath(key).as_posix() != key or key.startswith('/')
            or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR)
            or info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
        raise ValueError('Invalid archive member')
    if key.lower().endswith('vbaproject.bin') or key.startswith('word/embeddings/'):
        raise ValueError('Active embedded content is unsupported')
    return key


def _xml(data):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False)
    root = etree.fromstring(data, parser)
    if root.getroottree().docinfo.doctype:
        raise ValueError('Document type declarations are unsupported')
    return root


def validate_docx(data):
    essential = {'[Content_Types].xml', '_rels/.rels', 'word/document.xml'}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if not 1 <= len(entries) <= MAX_ENTRIES:
            raise ValueError('Archive member limit exceeded')
        keys = set()
        total = 0
        for info in entries:
            key = _entry_key(info)
            if key.casefold() in keys:
                raise ValueError('Duplicate archive member')
            keys.add(key.casefold())
            total += info.file_size
            if (info.file_size > MAX_ENTRY_BYTES or total > MAX_EXPANDED_BYTES
                    or info.file_size > 1024 * 1024 and info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO):
                raise ValueError('Expanded archive limit exceeded')
        if not essential.issubset(archive.namelist()):
            raise ValueError('Required DOCX members missing')
        roots = {}
        for info in entries:
            if info.is_dir():
                continue
            with archive.open(info) as stream:
                remaining = info.file_size
                pieces = []
                is_xml = info.filename.endswith(('.xml', '.rels'))
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk:
                        raise ValueError('Truncated archive member')
                    remaining -= len(chunk)
                    if is_xml:
                        pieces.append(chunk)
                if stream.read(1):
                    raise ValueError('Archive size mismatch')
            if is_xml:
                xml_root = _xml(b''.join(pieces))
                if info.filename in essential:
                    roots[info.filename] = xml_root
        content_ns = '{http://schemas.openxmlformats.org/package/2006/content-types}'
        types = roots['[Content_Types].xml']
        if types.tag != content_ns + 'Types' or not any(
                item.get('PartName') == '/word/document.xml'
                and item.get('ContentType') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'
                for item in types.findall(content_ns + 'Override')):
            raise ValueError('Invalid DOCX content types')
        rel_ns = '{http://schemas.openxmlformats.org/package/2006/relationships}'
        rels = roots['_rels/.rels']
        document_rels = [item for item in rels.findall(rel_ns + 'Relationship')
                         if item.get('Type') in (
                             'http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument',
                             'http://purl.oclc.org/ooxml/officeDocument/relationships/officeDocument')]
        if (rels.tag != rel_ns + 'Relationships' or len(document_rels) != 1
                or document_rels[0].get('TargetMode', 'Internal') != 'Internal'
                or document_rels[0].get('Target') not in ('word/document.xml', '/word/document.xml')):
            raise ValueError('Invalid DOCX document relationship')
        document = roots['word/document.xml']
        namespaces = ('http://schemas.openxmlformats.org/wordprocessingml/2006/main',
                      'http://purl.oclc.org/ooxml/wordprocessingml/main')
        if not any(document.tag == '{' + ns + '}document' and document.find('{' + ns + '}body') is not None for ns in namespaces):
            raise ValueError('Invalid DOCX document XML')


def main():
    try:
        limit_resources()
        data = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT or not data:
            return 1
        validators = {'.pdf': validate_pdf, '.docx': validate_docx}
        validators[sys.argv[1]](data)
        return 0
    except Exception:
        return 1


if __name__ == '__main__':
    sys.exit(main())
