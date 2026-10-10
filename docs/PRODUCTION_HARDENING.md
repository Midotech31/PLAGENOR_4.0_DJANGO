# PLAGENOR 4.0 production hardening and operations

## Required production configuration

Set these as secret environment variables in Render. Never place their values
in Git, tickets, screenshots, or chat:

- `DATABASE_URL`: PostgreSQL connection URI. Production refuses the SQLite
  fallback when this is absent.
- `SECRET_KEY`: stable, randomly generated Django secret.
- `TOTP_ENCRYPTION_KEY`: stable Fernet key used to encrypt TOTP seeds. Generate
  it with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`: the exact production domains.
- Supabase S3 credentials. Production sets
  `REQUIRE_PERSISTENT_MEDIA_STORAGE=true` and refuses an ephemeral media
  fallback.
- SMTP host, user, password, and sender. Production sets `REQUIRE_SMTP=true`
  and refuses the console backend so recovery and tracking tokens cannot be
  written to service logs.
- `TRUST_PROXY_HEADERS=true` on Render only; rate limiting then consumes the
  right-most valid address added by the trusted proxy.
- `RATE_LIMIT_BACKEND=database` shares public POST throttles across every
  worker without storing raw client addresses. Keep
  `RATE_LIMIT_FAIL_CLOSED=true` so a limiter failure returns HTTP 503 rather
  than silently bypassing the protection.

Keep `DEBUG=false`. MFA is optional for every account and is strongly
recommended in the account security settings, especially for administrative
and staff accounts. Losing or rotating `TOTP_ENCRYPTION_KEY` before
re-enrolling users makes existing encrypted TOTP seeds unreadable.

Django's `/admin/` requires an active staff account whose application role is
`SUPER_ADMIN`. Technical `is_staff` / `is_superuser` flags alone cannot grant
Admin Ops or another role access. Its login redirects to the application's
login so enrolled TOTP, account lockout and IP throttling apply equally.

Keep `CSP_REPORT_ONLY=false` after the validated baseline is deployed. The
current policy is enforced in production while inline frontend code is migrated
incrementally toward a nonce/hash policy. Password-reset links expire after
`PASSWORD_RESET_TIMEOUT=86400` seconds by default.

`ALLOW_WEB_DATABASE_RESTORE` must remain `false` in normal operation. A live
database restore inside an HTTP request is intentionally disabled; use the
isolated recovery procedure below. The `seed_accounts` and
`seed_demo_request` commands also refuse to run whenever `DEBUG` is false.

## Deploy and rollback

Render deploys the Docker image described by `Dockerfile`. Its entrypoint runs
collectstatic, migrations, the idempotent TOTP migration, reference-data seeds,
and then Gunicorn. Any failed command stops the release.

Before a production deploy:

1. Confirm CI passes on SQLite and PostgreSQL.
2. Confirm `/healthz` and `/readyz` on the current release.
3. Set `SMTP_SMOKE_RECIPIENT` to a monitored mailbox and run
   `python manage.py verify_email_delivery` from a one-off production shell.
   Record the command result and the received-message timestamp; the command
   never includes user or request data.
4. Create and verify an encrypted database backup.
5. Deploy the reviewed commit from protected `main`.
6. Smoke-test login, MFA, one request per channel, authorized document access,
   payment-proof review, and the three locales.

The Render Free service blocks outbound SMTP ports 25, 465 and 587 (see
https://render.com/docs/free). Configured credentials and a passing readiness
probe do not prove that mail can leave the service. Qualify a provider-supported
transport or an appropriate compute plan before relying on password recovery
and email notifications. A smoke message requires an explicitly authorized
test recipient and confirmation of receipt.

To roll back application code, deploy the last known-good commit from Render.
Do not reverse a database migration until its data impact has been reviewed.
Restore data only into a new database first, verify it, then schedule the
production cutover.

## Encrypted backups

The current `Database Backup` Action runs weekly and on demand. GitHub holds
no production database credential or encryption key. A short-lived GitHub OIDC
token calls `/ops/github/database-backup/`; the application verifies signature,
repository, main ref, workflow and event claims before creating the dump.

The production container creates a PostgreSQL custom dump, checks its table of
contents with `pg_restore --list`, encrypts it with Fernet using a key derived
from the stable TOTP encryption key, and stores it under `database_backups/`
in private persistent storage. It reads the object back and checks ciphertext
and decrypted content digests. The Action retains only non-secret metadata
for 90 days. This verifies backup creation and storage; it does not execute a
production-data restore.

Keep recovery access to `TOTP_ENCRYPTION_KEY` in the approved secret manager,
with a second controlled recovery copy. Do not rotate or lose it without a
recovery and re-encryption plan. Quarterly isolated restore drills remain
required. Investigate failed OIDC authorization, production readiness,
PostgreSQL tools and private storage before retrying a failed backup Action;
do not add obsolete database/age secrets to GitHub.

Restore drill:

1. Retrieve the encrypted object and its verified metadata from private storage
   on a controlled workstation.
2. Decrypt using the same Fernet/HKDF derivation defined in
   `scripts.production_inventory_bootstrap._backup_fernet`, with the recovery
   key supplied securely; never print keys or place them in command arguments.
3. Validate it: `pg_restore --list backup.dump`.
4. Create a new isolated PostgreSQL database.
5. Restore with `pg_restore --no-owner --no-privileges --dbname <test-url> backup.dump`.
6. Run `python manage.py check`, data-count checks, and an application smoke test
   against the restored database.
7. Securely remove the plaintext dump and destroy the isolated database.

CI performs a synthetic PostgreSQL dump-and-restore on every pull request. That
test validates mechanics; it does not replace a production-data recovery drill.

The first scientific-stock upgrade runs through
`scripts.production_stock_upgrade`. On existing Render/PostgreSQL data it
requires the verified private backup, locks the historical ERP tables, compares
all historical field values and row digests before/after additive migrations,
and persists private aggregate evidence. A mismatch or backup failure rolls
back the migration. Only after commit does it emit
`scientific_stock_upgrade_verified`. Preserve this event and the matching
`/readyz` commit in the release evidence; do not reverse the migrations to roll
back application code without reviewing new stock history.

## Sensitive-history follow-up

The hardening branch removes the tracked data export `plagenor_data.json` and
the unsafe bulk password-reset script `reset_passwords.py`. Git history shows
these files existed in earlier commits. Deleting them in a new commit does not
erase old objects. Treat any credentials or personal data they contained as
exposed: rotate affected credentials and review legal/data-governance duties.

History rewriting is intentionally not performed by this repair because it is
disruptive to every clone and open branch. If governance requires purging the
objects, schedule a separate coordinated `git filter-repo` operation, revoke
old credentials first, notify collaborators, force-update all refs, and expire
host caches according to the Git provider's documented process.

## Incident response minimum

For suspected account, database, or storage compromise: restrict access,
preserve logs, rotate affected secrets, invalidate sessions, review audit and
provider logs, identify impacted records, restore from a verified clean point
when necessary, and document notifications and corrective actions. Do not edit
or delete evidence during triage.
