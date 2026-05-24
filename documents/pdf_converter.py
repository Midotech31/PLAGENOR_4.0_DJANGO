"""DOCX → PDF conversion via headless LibreOffice (soffice).

Production needs ``libreoffice-writer`` + ``default-jre-headless`` on the
container/image; without them the function falls back to returning the DOCX
path unchanged and logs a warning so the operator can fix the deploy.

A per-process lock serialises calls because LibreOffice holds a single
user-profile lock per ``-env:UserInstallation``; concurrent invocations
without distinct profile dirs race and one of them ``Error: source file
could not be loaded``. Using a temp profile per call sidesteps this.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from django.conf import settings


logger = logging.getLogger('plagenor.documents')


def convert_docx_to_pdf(docx_path: Path, output_dir: Optional[Path] = None) -> Path:
    """Convert a DOCX to PDF, returning the PDF path.

    On failure (LibreOffice missing, exit non-zero, no output) the source
    DOCX path is returned unchanged so callers can still serve *something*.
    The failure is logged with enough context to diagnose.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    if not getattr(settings, 'DOCUMENT_PDF_ENABLED', True):
        return docx_path

    out_dir = Path(output_dir) if output_dir else docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = out_dir / (docx_path.stem + '.pdf')

    soffice = shutil.which('soffice') or shutil.which('libreoffice')
    if soffice is None:
        logger.warning(
            "soffice/libreoffice not found on PATH; PDF conversion disabled. "
            "Install libreoffice-writer + default-jre-headless to enable."
        )
        return docx_path

    with tempfile.TemporaryDirectory(prefix='lo_profile_') as profile_dir:
        cmd = [
            soffice,
            '--headless',
            '--norestore',
            '--nologo',
            f'-env:UserInstallation=file://{profile_dir}',
            '--convert-to', 'pdf',
            '--outdir', str(out_dir),
            str(docx_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                timeout=120,
                text=True,
            )
        except subprocess.TimeoutExpired:
            logger.error("LibreOffice PDF conversion timed out for %s", docx_path)
            return docx_path
        except Exception as exc:
            logger.exception("LibreOffice PDF conversion crashed: %s", exc)
            return docx_path

    if result.returncode != 0 or not expected.exists():
        logger.error(
            "LibreOffice PDF conversion failed for %s (rc=%s):\nstdout=%s\nstderr=%s",
            docx_path, result.returncode, result.stdout, result.stderr,
        )
        return docx_path

    return expected
