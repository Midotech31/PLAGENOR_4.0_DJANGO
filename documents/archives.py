"""Persist and verify issued document originals independently of later settings."""
import hashlib
import tempfile
from pathlib import Path
from django.core.exceptions import ValidationError
from core.models import IssuedDocument


def restore_original(kind, number):
    if not number:
        return None
    row = IssuedDocument.objects.filter(kind=kind, number=number).first()
    if row is None:
        return None
    data = bytes(row.content)
    if hashlib.sha256(data).hexdigest() != row.sha256:
        raise ValidationError('Intégrité du document archivé non vérifiée.')
    with tempfile.NamedTemporaryFile(prefix='plagenor-original-', suffix='.docx', delete=False) as output:
        output.write(data)
        return output.name


def preserve_original(kind, number, path):
    data = Path(path).read_bytes()
    IssuedDocument.objects.get_or_create(kind=kind, number=number,
        defaults={'content': data, 'sha256': hashlib.sha256(data).hexdigest()})
