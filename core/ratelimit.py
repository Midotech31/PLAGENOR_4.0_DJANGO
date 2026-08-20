"""Minimal, dependency-free IP rate limiting backed by Django's cache.

Fails OPEN: any cache error allows the request, so throttling can never take
the site down. Intended for abuse-prone public POST endpoints (login,
password reset, guest submission) as defence-in-depth on top of the
per-account login lockout — not as a hard security boundary.

Note: the default LocMemCache is per-process, so with N gunicorn workers the
effective limit is up to N× the configured value. That is fine for slowing
brute-force / email-bombing; use a shared cache (Redis) for exactness.
"""
import logging
from functools import wraps
from ipaddress import ip_address

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


logger = logging.getLogger(__name__)


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
                    count = cache.get(cache_key, 0)
                    if count >= limit:
                        resp = HttpResponse(
                            "Trop de tentatives. Veuillez réessayer plus tard.",
                            status=429)
                        resp['Retry-After'] = str(window)
                        return resp
                    # add() sets only if absent (starts the window); then incr.
                    if cache.add(cache_key, 1, timeout=window) is False:
                        try:
                            cache.incr(cache_key)
                        except ValueError:
                            cache.add(cache_key, 1, timeout=window)
                except Exception:
                    # This limiter deliberately fails open, but the degraded
                    # security control must remain visible to operators.
                    logger.exception("Rate-limit cache unavailable for key=%s", key)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
