import hashlib
import os
import tempfile
from pathlib import Path
from django.conf import settings
from core.upload_validation import validate_document


def materialize_template(template):
    """Read the stored source, including object storage, before using a local copy."""
    limit = getattr(settings, 'UPLOAD_MAX_BYTES', 10 * 1024 * 1024)
    with template.file.open('rb') as source:
        content = source.read(limit + 1)
    if not content or len(content) > limit:
        raise ValueError('Le fichier du modèle est vide ou trop volumineux.')
    validate_document(content, '.docx')
    digest = hashlib.sha256(content).hexdigest()
    directory = Path(settings.MEDIA_ROOT) / 'template_sources'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (digest + '.docx')
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        return target
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.docx', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
