"""Lightweight health/readiness endpoints for uptime monitoring.

``/healthz``  — liveness: the process is up and can answer (no DB touch).
``/readyz``   — readiness: also verifies the database connection.

Both are unauthenticated, cheap, and cache-free so an external monitor
(UptimeRobot, Render health check, …) can poll them.
"""
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    return JsonResponse({'status': 'ok'})


@never_cache
def readyz(request):
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
            cur.fetchone()
    except Exception as exc:  # pragma: no cover - exercised via DB-down only
        return JsonResponse(
            {'status': 'error', 'database': str(exc)[:200]}, status=503)
    return JsonResponse({'status': 'ok', 'database': 'ok'})
