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


def matching_step(secret, code, now=None):
    import re
    import time
    import pyotp
    from django.utils.crypto import constant_time_compare

    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code) or not secret:
        return None
    totp = pyotp.TOTP(secret)
    current = int((time.time() if now is None else now) // totp.interval)
    for step in (current, current - 1, current + 1):
        if step >= 0 and constant_time_compare(totp.at(step * totp.interval), code):
            return step
    return None


def consume_totp(user, code, *, disable=False, now=None):
    from django.db.models import Q
    from accounts.models import User

    if not user.is_active or not user.totp_enabled or not user.totp_secret:
        return False
    step = matching_step(user.get_totp_secret(), code, now)
    if step is None:
        return False
    values = {'totp_last_step': step}
    if disable:
        values.update(totp_enabled=False, totp_secret='')
    accepted = User.objects.filter(
        pk=user.pk, is_active=True, totp_enabled=True,
        totp_secret=user.totp_secret, password=user.password,
    ).filter(Q(totp_last_step__isnull=True) | Q(totp_last_step__lt=step)).update(**values)
    if accepted:
        for name, value in values.items():
            setattr(user, name, value)
    return bool(accepted)


def enable_totp(user, secret, code, *, now=None):
    from accounts.models import User

    step = matching_step(secret, code, now)
    if step is None:
        return False
    values = {'totp_secret': encrypt_secret(secret), 'totp_enabled': True, 'totp_last_step': step}
    accepted = User.objects.filter(
        pk=user.pk, is_active=True, totp_enabled=False,
        totp_secret=user.totp_secret, password=user.password,
    ).update(**values)
    if accepted:
        for name, value in values.items():
            setattr(user, name, value)
    return bool(accepted)
