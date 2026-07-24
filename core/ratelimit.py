"""Minimal, dependency-free IP rate limiting backed by Django's cache.

Fails OPEN: any cache error allows the request, so throttling can never take
the site down. Intended for abuse-prone public POST endpoints (login,
password reset, guest submission) as defence-in-depth on top of the
per-account login lockout — not as a hard security boundary.

Note: the default LocMemCache is per-process, so with N gunicorn workers the
effective limit is up to N× the configured value. That is fine for slowing
brute-force / email-bombing; use a shared cache (Redis) for exactness.
"""
from functools import wraps

from django.core.cache import cache
from django.http import HttpResponse


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


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
                    pass  # fail open — never block on cache trouble
            return view(request, *args, **kwargs)
        return wrapped
    return decorator
