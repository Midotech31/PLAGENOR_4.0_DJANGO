"""Encryption helpers for TOTP seeds stored in the user table."""

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PREFIX = "fernet$"


def _key() -> bytes:
    configured = os.getenv("TOTP_ENCRYPTION_KEY", "").strip()
    if configured:
        key = configured.encode()
    elif settings.DEBUG or os.getenv('DEBUG', '').lower() == 'true':
        key = base64.urlsafe_b64encode(
            hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    else:
        raise ImproperlyConfigured(
            "TOTP_ENCRYPTION_KEY is required in production for encrypted 2FA seeds.")
    try:
        Fernet(key)
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(
            "TOTP_ENCRYPTION_KEY must be a valid Fernet key.") from exc
    return key


def encrypt_secret(secret: str) -> str:
    if not secret or secret.startswith(PREFIX):
        return secret
    return PREFIX + Fernet(_key()).encrypt(secret.encode()).decode()


def decrypt_secret(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        return value
    try:
        return Fernet(_key()).decrypt(value[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            "Unable to decrypt a TOTP seed with TOTP_ENCRYPTION_KEY.") from exc
