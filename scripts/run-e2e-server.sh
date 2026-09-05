#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SETTINGS_MODULE=plagenor.settings_e2e
export DEBUG=true
export SECRET_KEY=e2e-only-secret-key

db_path="data/plagenor-e2e.sqlite3"
server_pid=""
cleanup() {
  if [ -n "$server_pid" ]; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  rm -f -- "$db_path" "$db_path-wal" "$db_path-shm"
}
trap cleanup EXIT INT TERM
cleanup

python manage.py migrate --noinput
python manage.py seed_services >/dev/null
python manage.py seed_content >/dev/null
python manage.py seed_accounts --quiet >/dev/null
python manage.py runserver 127.0.0.1:8001 --noreload &
server_pid="$!"
wait "$server_pid"
