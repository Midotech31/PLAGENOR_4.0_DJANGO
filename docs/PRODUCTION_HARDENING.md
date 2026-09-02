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

Keep `DEBUG=false` and `PRIVILEGED_MFA_ENFORCEMENT=true`. Losing or rotating
`TOTP_ENCRYPTION_KEY` before re-enrolling users makes existing encrypted TOTP
seeds unreadable.

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
3. Create and verify an encrypted database backup.
4. Deploy the reviewed commit from protected `main`.
5. Smoke-test login, MFA, one request per channel, authorized document access,
   payment-proof review, and the three locales.

If the scheduled `Database Backup` workflow fails at **Require backup
secrets**, restore the repository secrets `DATABASE_URL` and
`BACKUP_AGE_RECIPIENT`, then run the workflow manually. Do not consider backup
coverage restored until the encrypted artifact is produced and a controlled
restore drill succeeds.

To roll back application code, deploy the last known-good commit from Render.
Do not reverse a database migration until its data impact has been reviewed.
Restore data only into a new database first, verify it, then schedule the
production cutover.

## Encrypted backups

The `Database Backup` GitHub Action requires repository secrets
`DATABASE_URL` and `BACKUP_AGE_RECIPIENT`. It creates a PostgreSQL custom dump,
validates its table of contents, encrypts it with `age`, deletes the plaintext
temporary file, and uploads only `*.dump.age` with a 90-day retention.

Keep the matching age private key outside GitHub and Render in an approved
password manager, with a second controlled recovery copy. Quarterly restore
drills are required.

Restore drill:

1. Download the encrypted artifact to a controlled workstation.
2. Decrypt it locally: `age --decrypt -i <identity-file> -o backup.dump backup.dump.age`.
3. Validate it: `pg_restore --list backup.dump`.
4. Create a new isolated PostgreSQL database.
5. Restore with `pg_restore --no-owner --no-privileges --dbname <test-url> backup.dump`.
6. Run `python manage.py check`, data-count checks, and an application smoke test
   against the restored database.
7. Securely remove the plaintext dump and destroy the isolated database.

CI performs a synthetic PostgreSQL dump-and-restore on every pull request. That
test validates mechanics; it does not replace a production-data recovery drill.

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
