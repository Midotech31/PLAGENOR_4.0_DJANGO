# PLAGENOR 4.0 hardening repair report

## Scope

This branch applies the production security and integrity repair brief to the
Django repository based on `main` commit `5b94231`. No production database was
read or changed, no deployment was triggered, and Git history was not rewritten.

## Implemented controls

- Removed tracked production-like data and the deterministic bulk password
  reset utility; expanded ignore rules for databases, dumps, backups, and data
  exports.
- Replaced plaintext backup artifacts with validated, age-encrypted PostgreSQL
  backups and added a PostgreSQL restore test to CI.
- Made build, migration, seeding, audit, and security checks blocking.
- Added a reproducible Python 3.11 Docker runtime with LibreOffice, Java, and
  gettext for document/PDF and localization support.
- Separated client payment-proof upload from finance/admin verification, with
  verifier, timestamp, note, state-machine rules, and database constraint.
- Locked workflow rows before validation, kept financial debit and transition
  atomic, and made post-commit side effects explicit.
- Converted pricing calculations to `Decimal` and made malformed authoritative
  configuration fail closed.
- Enforced eligibility checks for member role, active state, availability,
  capacity, and service technique before assignment.
- Added centralized upload validation for size, extension, MIME, magic bytes,
  image/container integrity, and opaque filenames.
- Encrypted TOTP seeds, added an idempotent legacy migration, required MFA for
  privileged roles, strengthened self-disable verification, and audited admin
  resets with a mandatory reason and user notification.
- Removed public/requester exposure of analyst identities and internal workflow
  notes; retained object-level protected media checks.
- Added a staged CSP and hardened SVG rendering against unsafe attributes.
- Added focused regression tests for payment separation, pricing failure,
  upload spoofing, assignment eligibility, MFA controls, and privacy.

## Residual risks and operational decisions

- The current measured coverage floor is 40%. CI enforces that real floor; it
  should be raised incrementally with tests for the large document and dashboard
  surfaces.
- CSP is report-only by default and still permits inline scripts/styles. Move
  inline code to static assets, observe reports, then set `CSP_REPORT_ONLY=false`
  and remove `unsafe-inline` in a dedicated frontend change.
- Historical Git objects may still contain deleted artifacts. Credential
  rotation and any coordinated history purge remain operational follow-up.
- A local PostgreSQL server and container engine were unavailable in the repair
  workspace. PostgreSQL migration/restore and Docker build are therefore CI
  gates rather than locally executed claims.
- External systems such as SMTP, Supabase S3, DNS, provider audit logs, and
  production recovery require environment-owner validation.
