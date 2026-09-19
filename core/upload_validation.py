import os
from pathlib import Path
import subprocess
import sys
import threading

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


_VALIDATION_SLOT = threading.BoundedSemaphore(1)
DOCUMENT_TIMEOUT = 6


def validate_document(data, extension):
    if not _VALIDATION_SLOT.acquire(timeout=1):
        raise ValidationError(_('Validation occupée. Réessayez dans quelques instants.'))
    try:
        allowed = {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP'}
        environment = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        completed = subprocess.run(
            [sys.executable, '-I', str(Path(__file__).with_name('document_probe.py')), extension],
            input=data, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=DOCUMENT_TIMEOUT, env=environment,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if completed.returncode != 0:
            raise ValidationError(_('Document invalide, protégé ou dépassant les limites de validation.'))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValidationError(_('Le document ne peut pas être validé dans les limites autorisées.')) from exc
    finally:
        _VALIDATION_SLOT.release()
