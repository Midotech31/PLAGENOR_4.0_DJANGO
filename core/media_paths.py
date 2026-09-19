from pathlib import Path, PurePosixPath
import unicodedata

from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage
from django.utils.translation import gettext_lazy as _


_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} | {
    f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in range(1, 10)
}


def canonical_media_path(value):
    invalid = not isinstance(value, str) or not value or len(value) > 1024
    if not invalid:
        parts = value.split('/')
        invalid = (
            value != unicodedata.normalize('NFC', value)
            or any(char in value for char in ('\\', '%', ':', '?', '#'))
            or any(unicodedata.category(char).startswith('C') for char in value)
            or any(char in value for char in ('⁄', '∕', '／', '＼'))
            or any(not part or part in ('.', '..') or part.endswith((' ', '.'))
                   or part.split('.')[0].upper() in _RESERVED for part in parts)
            or PurePosixPath(value).as_posix() != value
        )
    if invalid:
        raise ValidationError(_('Chemin de fichier invalide.'), code='invalid_media_path')
    return value


def validate_storage_path(storage, value):
    key = canonical_media_path(value)
    if isinstance(storage, FileSystemStorage):
        root = Path(storage.location).resolve()
        candidate = root.joinpath(*key.split('/')).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValidationError(_('Chemin de fichier invalide.'), code='invalid_media_path') from exc
        if relative != key:
            raise ValidationError(_('Chemin de fichier invalide.'), code='invalid_media_path')
    return key
