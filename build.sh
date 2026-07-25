#!/usr/bin/env bash
# Render/Railway build step: install deps, collect static, run migrations.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
# Seed reference data (idempotent: get_or_create) — services + CMS content.
python manage.py seed_services || true
python manage.py seed_content || true
# Provision the admin account from DJANGO_SUPERUSER_* env vars (idempotent;
# no-op if the vars are unset). Lets us create the superuser without a shell.
python manage.py ensure_superuser || true
