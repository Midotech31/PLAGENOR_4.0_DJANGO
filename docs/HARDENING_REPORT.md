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
- Removed the reusable email-existence oracle and made guest conversion
  responses account-enumeration resistant.
- Made profile email and member competencies administrator-verified controls
  instead of self-editable assignment inputs.
- Restored CSRF protection on report-delivery telemetry and added rate limits
  to public, registration, report, and TOTP-sensitive operations.
- Made production fail closed when private persistent media storage or SMTP
  delivery is absent, and added subprocess tests for those startup invariants.
- Routed guest IBTIKAR and GENOCLAB creation through the canonical channel
  services so their initial states, histories, identifiers, and financial
  fields match registered submissions.
- Replaced silent exception swallowing in public throttling, CMS, dynamic
  forms, account-reset delivery, and document fallbacks with operator-visible
  logging; account resets now warn the administrator when delivery fails.
- Changed the production container to a non-root user, added a container
  health check, bounded Gunicorn workers, and made CI build and inspect the
  actual image.
- Expanded the suite from 139 to 223 tests. Critical coverage now includes
  state machine 100%, financial engine 98%, pricing 86%, workflow 90%, database
  backup primitives 94%, QR authorization 97%, request messaging 91%, dynamic
  service forms 91%, notification delivery/services 92%/91%, and statistics
  engine/views 94%/92%.
- Added object-level QR and messaging authorization tests, recipient-routing
  tests, role-restricted statistics export tests, and database backup/restore
  primitive tests. A regression test exposed and fixed backup retention pruning
  a newly created SQLite copy because its source modification time was retained.
- Fixed locale-dependent decimal attributes in dynamic service forms so browser
  price calculations receive a dot decimal regardless of the active language.
- Made analyst statistics fail closed when a MEMBER profile is missing. The old
  None filter was omitted by the query builder and could expose global aggregate
  statistics; the repaired scope is empty and regression-tested.
- Raised QR utility coverage from 0% to 98% and verified that generated tracking
  URLs use the implemented query-string route rather than a nonexistent path.

## Residual risks and operational decisions

- Current measured overall coverage is 50.78%; CI enforces a 50% ratchet.
  The required 60% target is not yet reached. The remaining gap is concentrated
  in large document-generation and dashboard view surfaces and must not be
  hidden by exclusions.
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
