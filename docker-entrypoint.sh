#!/usr/bin/env sh
set -eu

python manage.py collectstatic --no-input
python manage.py migrate --noinput
python manage.py migrate_totp_secrets
python manage.py seed_services
python manage.py seed_content
python manage.py ensure_superuser

exec gunicorn plagenor.wsgi:application \
  --workers "${WEB_CONCURRENCY:-3}" --bind "0.0.0.0:${PORT:-8000}"
