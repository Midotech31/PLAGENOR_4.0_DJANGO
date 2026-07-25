"""Lightweight health/readiness endpoints for uptime monitoring.

``/healthz``  — liveness: the process is up and can answer (no DB touch).
``/readyz``   — readiness: also verifies the database connection.

Both are unauthenticated, cheap, and cache-free so an external monitor
(UptimeRobot, Render health check, …) can poll them.
"""
import logging

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger('plagenor')


@never_cache
def healthz(request):
    return JsonResponse({'status': 'ok'})


@never_cache
def readyz(request):
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except Exception:  # pragma: no cover - exercised via DB-down only
        # Log the detail server-side; never return it — the driver message can
        # disclose the host, database and user to an unauthenticated caller.
        logger.exception('readyz: database check failed')
        return JsonResponse(
            {'status': 'error', 'database': 'unavailable'}, status=503)
    return JsonResponse({'status': 'ok', 'database': 'ok'})
