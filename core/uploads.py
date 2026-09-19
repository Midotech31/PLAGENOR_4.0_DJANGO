"""Central validation for untrusted uploaded files.

Extension checks alone are not security checks.  This module validates size,
declared MIME type, magic bytes, and container/image integrity, then replaces
the client-supplied filename with an opaque UUID.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from core.upload_validation import validate_document
from PIL import Image, UnidentifiedImageError


POLICIES = {
    "business_document": {
        ".pdf": {"application/pdf"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
    },
    "report": {
        ".pdf": {"application/pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
        },
    },
    "docx_template": {
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
        },
    },
    "image": {
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
    },
}


def _validate_signature(ext: str, data: bytes) -> None:
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise ValidationError("Le contenu du fichier ne correspond pas à un PDF.")
    if ext == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValidationError("Le contenu du fichier ne correspond pas à une image PNG.")
    if ext in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff"):
        raise ValidationError("Le contenu du fichier ne correspond pas à une image JPEG.")
    if ext == ".docx" and not data.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        raise ValidationError(_("Le fichier DOCX est invalide."))



def validate_upload(upload, policy: str, *, max_bytes: int | None = None):
    """Validate and rewind an uploaded file, returning the same object."""
    allowed = POLICIES.get(policy)
    if not allowed:
        raise ValueError(f"Unknown upload policy: {policy}")
    limit = max_bytes or getattr(settings, "UPLOAD_MAX_BYTES", 10 * 1024 * 1024)
    size = getattr(upload, "size", 0) or 0
    if size <= 0:
        raise ValidationError("Le fichier est vide.")
    if size > limit:
        raise ValidationError(f"Le fichier dépasse la taille maximale de {limit // (1024 * 1024)} Mo.")

    ext = Path(upload.name or "").suffix.lower()
    if ext not in allowed:
        raise ValidationError("Type de fichier non autorisé.")
    content_type = (getattr(upload, "content_type", "") or "").lower()
    if content_type and content_type not in allowed[ext]:
        raise ValidationError("Le type MIME du fichier est invalide.")

    try:
        data = upload.read(limit + 1)
    finally:
        upload.seek(0)
    if not data or len(data) > limit:
        raise ValidationError(_("La taille réelle du fichier est invalide."))
    _validate_signature(ext, data)
    if ext in {'.pdf', '.docx'}:
        validate_document(data, ext)
    if ext in {".png", ".jpg", ".jpeg"}:
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ValidationError("L'image est invalide ou endommagée.") from exc

    upload.name = f"{uuid.uuid4().hex}{ext}"
    return upload
