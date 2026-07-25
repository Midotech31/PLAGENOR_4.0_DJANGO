"""DOCX → PDF conversion via headless LibreOffice (soffice).

Two backends, selected by ``settings.DOCUMENT_PDF_BACKEND``:

* ``'spawn'`` (default) — spawn ``soffice --convert-to pdf`` per call with a
  throw-away user profile. Stateless and self-healing: every call is
  independent, one bad conversion can't poison the next. Pays LibreOffice's
  full cold-start (~1.5–5 s) every time. This is the safe, zero-dependency
  path and stays the default.

* ``'uno'`` — keep ONE headless LibreOffice listener warm per Python process
  and drive it over the UNO bridge. ~6–7× faster (~0.25 s warm) because the
  office binary is loaded once. Needs the ``uno`` python module (ships with
  the LibreOffice install). **Any UNO failure transparently falls back to the
  spawn path**, so enabling it can never make a download fail — at worst it's
  as slow as ``'spawn'``.

Production needs ``libreoffice-writer`` + ``default-jre-headless`` on the
image; without them BOTH backends log a warning and return the DOCX path
unchanged so callers can still serve *something*.
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from django.conf import settings


logger = logging.getLogger('plagenor.documents')


def _soffice_bin() -> Optional[str]:
    return shutil.which('soffice') or shutil.which('libreoffice')


# ---------------------------------------------------------------------------
# Backend: spawn (default) — one soffice process per call, throw-away profile
# ---------------------------------------------------------------------------

def _convert_via_spawn(docx_path: Path, out_dir: Path) -> Path:
    """Spawn ``soffice --convert-to pdf``. Returns the DOCX path on failure."""
    expected = out_dir / (docx_path.stem + '.pdf')
    soffice = _soffice_bin()
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
                cmd, check=False, capture_output=True, timeout=120, text=True,
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


# ---------------------------------------------------------------------------
# Backend: uno — one warm soffice listener per process, driven over UNO
# ---------------------------------------------------------------------------

class _UnoConversionError(Exception):
    """Raised inside the UNO path so the caller can fall back to spawn."""


class _LibreOfficeDaemon:
    """Lazily-started, per-process headless LibreOffice listener.

    Isolation is per-process via a named pipe keyed on the PID, so several
    gunicorn workers never contend on a TCP port or a shared profile lock.
    A health check before every conversion restarts a dead office; an
    ``atexit`` hook tears it down on a clean interpreter exit.
    """

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._pipe = f"plagenor_lo_{os.getpid()}"
        self._profile = Path(tempfile.gettempdir()) / f"plagenor_lo_profile_{os.getpid()}"
        self._lock = threading.Lock()
        self._desktop = None  # cached UNO Desktop component

    # -- lifecycle ---------------------------------------------------------

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _start(self) -> None:
        soffice = _soffice_bin()
        if soffice is None:
            raise _UnoConversionError("soffice not on PATH")
        self._profile.mkdir(parents=True, exist_ok=True)
        accept = f"pipe,name={self._pipe};urp;StarOffice.ComponentContext"
        self._proc = subprocess.Popen(
            [
                soffice, '--headless', '--norestore', '--nologo', '--invisible',
                '--nodefault', '--nofirststartwizard',
                f'-env:UserInstallation=file://{self._profile}',
                f'--accept={accept}',
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._desktop = None  # force re-resolve against the new instance

    def _connect_desktop(self):
        """Resolve (and cache) the UNO Desktop for the running listener."""
        if self._desktop is not None:
            return self._desktop
        import uno  # provided by the LibreOffice install
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext(
            "com.sun.star.bridge.UnoUrlResolver", local)
        url = (f"uno:pipe,name={self._pipe};urp;StarOffice.ComponentContext")
        last = None
        for _ in range(40):  # up to ~10 s for first cold start
            try:
                ctx = resolver.resolve(url)
                smgr = ctx.ServiceManager
                self._desktop = smgr.createInstanceWithContext(
                    "com.sun.star.frame.Desktop", ctx)
                return self._desktop
            except Exception as exc:  # bridge not ready yet
                last = exc
                time.sleep(0.25)
        raise _UnoConversionError(f"UNO bridge never came up: {last}")

    def _ensure_running(self) -> None:
        if not self._alive():
            self._start()

    def shutdown(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=10)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            self._desktop = None

    # -- conversion --------------------------------------------------------

    def convert(self, docx_path: Path, out_dir: Path) -> Path:
        """Convert via the warm listener. Raises ``_UnoConversionError`` on any
        failure so the public entry point can fall back to spawn."""
        import uno
        from com.sun.star.beans import PropertyValue

        def prop(name, value):
            p = PropertyValue()
            p.Name = name
            p.Value = value
            return p

        expected = out_dir / (docx_path.stem + '.pdf')
        with self._lock:
            # One retry: a stale/crashed office is restarted once.
            for attempt in (1, 2):
                try:
                    self._ensure_running()
                    desktop = self._connect_desktop()
                    in_url = uno.systemPathToFileUrl(str(docx_path.resolve()))
                    out_url = uno.systemPathToFileUrl(str(expected.resolve()))
                    doc = desktop.loadComponentFromURL(
                        in_url, "_blank", 0, (prop("Hidden", True),))
                    if doc is None:
                        raise _UnoConversionError("loadComponentFromURL returned None")
                    try:
                        doc.storeToURL(
                            out_url, (prop("FilterName", "writer_pdf_Export"),))
                    finally:
                        doc.close(False)
                    if not expected.exists():
                        raise _UnoConversionError("no PDF produced")
                    return expected
                except _UnoConversionError:
                    raise
                except Exception as exc:
                    # Bridge/office died mid-call — drop it and retry once.
                    self._desktop = None
                    self.shutdown()
                    if attempt == 2:
                        raise _UnoConversionError(str(exc))
            raise _UnoConversionError("unreachable")


_daemon: Optional[_LibreOfficeDaemon] = None
_daemon_lock = threading.Lock()


def _get_daemon() -> _LibreOfficeDaemon:
    global _daemon
    if _daemon is None:
        with _daemon_lock:
            if _daemon is None:
                _daemon = _LibreOfficeDaemon()
                atexit.register(_daemon.shutdown)
    return _daemon


def _convert_via_uno(docx_path: Path, out_dir: Path) -> Path:
    """UNO conversion with transparent fallback to spawn on any failure."""
    try:
        import uno  # noqa: F401  — probe availability before starting anything
    except Exception:
        logger.warning("python 'uno' module unavailable; using spawn backend.")
        return _convert_via_spawn(docx_path, out_dir)
    try:
        return _get_daemon().convert(docx_path, out_dir)
    except _UnoConversionError as exc:
        logger.warning("UNO conversion failed (%s); falling back to spawn.", exc)
        return _convert_via_spawn(docx_path, out_dir)
    except Exception as exc:  # defensive: never let the UNO path crash a download
        logger.exception("Unexpected UNO error (%s); falling back to spawn.", exc)
        return _convert_via_spawn(docx_path, out_dir)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def convert_docx_to_pdf(docx_path: Path, output_dir: Optional[Path] = None) -> Path:
    """Convert a DOCX to PDF, returning the PDF path.

    Dispatches on ``settings.DOCUMENT_PDF_BACKEND`` ('spawn' default, 'uno'
    opt-in). On any failure the source DOCX path is returned unchanged so
    callers can still serve *something*.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")

    if not getattr(settings, 'DOCUMENT_PDF_ENABLED', True):
        return docx_path

    out_dir = Path(output_dir) if output_dir else docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    backend = str(getattr(settings, 'DOCUMENT_PDF_BACKEND', 'spawn')).lower()
    if backend == 'uno':
        return _convert_via_uno(docx_path, out_dir)
    return _convert_via_spawn(docx_path, out_dir)
