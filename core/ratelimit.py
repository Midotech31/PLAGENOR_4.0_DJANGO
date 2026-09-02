"""IP rate limiting for abuse-prone public endpoints.

Production uses a database-backed counter shared by every Gunicorn worker.
Development may use Django's cache for speed. Client addresses are hashed
before persistence and stale buckets are removed opportunistically.
"""
import hashlib
import logging
import math
from datetime import timedelta
from functools import wraps
from ipaddress import ip_address

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.utils import timezone


logger = logging.getLogger(__name__)


def _database_counter(cache_key: str, limit: int, window: int) -> tuple[bool, int]:
    """Increment a cross-worker counter and return (limited, retry_after)."""
    from core.models import RateLimitBucket

    key_hash = hashlib.sha256(cache_key.encode('utf-8')).hexdigest()
    now = timezone.now()
    expires_at = now + timedelta(seconds=window)

    # A concurrent first request can race on INSERT. Retry once after the
    # unique-key winner commits, then lock and increment its row.
    for attempt in range(2):
        try:
            with transaction.atomic():
                bucket = (RateLimitBucket.objects.select_for_update()
                          .filter(key_hash=key_hash).first())
                if bucket is None:
                    RateLimitBucket.objects.create(
                        key_hash=key_hash, count=1, expires_at=expires_at)
                    # Keep the table bounded without storing or inspecting IPs.
                    RateLimitBucket.objects.filter(expires_at__lte=now).exclude(
                        key_hash=key_hash).delete()
                    return False, window
                if bucket.expires_at <= now:
                    bucket.count = 1
                    bucket.expires_at = expires_at
                    bucket.save(update_fields=['count', 'expires_at', 'updated_at'])
                    return False, window
                retry_after = max(
                    1, math.ceil((bucket.expires_at - now).total_seconds()))
                if bucket.count >= limit:
                    return True, retry_after
                bucket.count += 1
                bucket.save(update_fields=['count', 'updated_at'])
                return False, retry_after
        except IntegrityError:
            if attempt:
                raise
    raise RuntimeError("Unable to update rate-limit counter")


def _cache_counter(cache_key: str, limit: int, window: int) -> tuple[bool, int]:
    """Increment the development cache counter."""
    count = cache.get(cache_key, 0)
    if count >= limit:
        return True, window
    if cache.add(cache_key, 1, timeout=window) is False:
        try:
            cache.incr(cache_key)
        except ValueError:
            cache.add(cache_key, 1, timeout=window)
    return False, window


def _limited_response(status: int, retry_after: int) -> HttpResponse:
    message = (
        "Trop de tentatives. Veuillez réessayer plus tard."
        if status == 429 else
        "Service de protection temporairement indisponible."
    )
    response = HttpResponse(message, status=status)
    response['Retry-After'] = str(retry_after)
    return response


def _client_ip(request):
    """Return a normalized client IP without trusting arbitrary XFF input.

    Render appends the connecting client to ``X-Forwarded-For``. Therefore
    the right-most valid address is the only forwarded value consumed when
    proxy trust is explicitly enabled. Unknown deployments keep using the
    socket peer from ``REMOTE_ADDR``.
    """
    candidates = []
    if getattr(settings, 'TRUST_PROXY_HEADERS', False):
        candidates.extend(reversed([
            part.strip() for part in
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')
            if part.strip()
        ]))
    candidates.append(request.META.get('REMOTE_ADDR', ''))
    for candidate in candidates:
        try:
            return ip_address(candidate).compressed
        except ValueError:
            continue
    return 'unknown'


def rate_limit(key: str, limit: int, window: int, methods=('POST',)):
    """Allow at most ``limit`` requests per ``window`` seconds per client IP.

    Only the given HTTP ``methods`` are counted (GET renders pass through).
    On limit exceed, returns HTTP 429 with a Retry-After header.
    """
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method in methods:
                cache_key = f"rl:{key}:{_client_ip(request)}"
                try:
                    backend = getattr(settings, 'RATE_LIMIT_BACKEND', 'cache')
                    counter = (_database_counter if backend == 'database'
                               else _cache_counter)
                    limited, retry_after = counter(cache_key, limit, window)
                    if limited:
                        return _limited_response(429, retry_after)
                except Exception:
                    logger.exception("Rate-limit cache unavailable for key=%s", key)
                    if getattr(settings, 'RATE_LIMIT_FAIL_CLOSED', False):
                        return _limited_response(503, 60)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
