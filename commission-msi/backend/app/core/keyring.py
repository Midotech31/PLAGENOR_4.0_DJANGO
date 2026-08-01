"""Accès à la clé maîtresse locale."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.crypto import load_or_create_master_key

_key: bytes | None = None


def get_master_key() -> bytes:
    global _key
    if _key is None:
        settings = get_settings()
        settings.ensure_directories()
        _key = load_or_create_master_key(settings.key_path)
    return _key


def reset_master_key() -> None:
    """Oublie la clé mémorisée — utilisé par les tests et la restauration."""
    global _key
    _key = None
