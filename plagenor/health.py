"""Lightweight health/readiness endpoints for uptime monitoring.

``/healthz``  — liveness: the process is up and can answer (no DB touch).
``/readyz``   — readiness: also verifies the database connection.

Both are unauthenticated, cheap, and cache-free so an external monitor
(UptimeRobot, Render health check, …) can poll them.
"""
import logging
import os
import re

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.cache import never_cache

logger = logging.getLogger('plagenor')


def revision_response(payload, status=200):
    response = JsonResponse(payload, status=status)
    revision = os.environ.get('RENDER_GIT_COMMIT', '')
    if re.fullmatch(r'[0-9a-fA-F]{40}', revision):
        response['X-PLAGENOR-Revision'] = revision.lower()
    return response


@never_cache
def healthz(request):
    return revision_response({'status': 'ok'})


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
        return revision_response(
            {'status': 'error', 'database': 'unavailable'}, status=503)
    return revision_response({'status': 'ok', 'database': 'ok'})
