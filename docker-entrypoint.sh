#!/usr/bin/env sh
set -eu

python manage.py collectstatic --no-input
python manage.py migrate --noinput
python manage.py migrate_totp_secrets
python manage.py seed_services
python manage.py seed_content
python manage.py ensure_superuser

if [ "${PLAGENOR_INVENTORY_BOOTSTRAP:-0}" = "1" ]; then
  echo "PLAGENOR inventory bootstrap requested; running fail-closed production import."
  python scripts/production_inventory_bootstrap.py
fi

exec gunicorn plagenor.wsgi:application \
  --workers "${WEB_CONCURRENCY:-3}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
  --max-requests "${GUNICORN_MAX_REQUESTS:-1000}" \
  --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-100}" \
  --access-logfile - --error-logfile - --capture-output
