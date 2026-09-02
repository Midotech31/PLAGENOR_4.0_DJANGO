# PLAGENOR 4.0 — quality and production audit

Audit date: 2026-09-01 UTC

Audited baseline: `main` at `8e64d907a8006dfcff4e301a4a6687665f581ed4`

Repair branch: `codex/plagenor-9-9-audit`

## Executive verdict

- Deployed production baseline: **8.4/10**.
- Corrected branch after local verification: **8.7/10**.
- Requested target: **9.9/10 — not yet substantiated**.

PLAGENOR is a serious production-capable Django platform with strong domain
workflows, financial invariants, role isolation and CI. A 9.9 score would,
however, assert near-perfect operational assurance. That assertion is currently
blocked by failed production backups, a single free-tier web instance, no
independent penetration test, no full browser/accessibility regression suite,
and a CSP that still permits inline scripts and styles.

## Evidence captured

- Public production `/healthz`, `/readyz` and `/` returned HTTP 200.
- `/readyz` reported both application and database status as `ok`.
- Production headers include HSTS, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: same-origin` and COOP.
- The deployed CSP was still report-only at audit time and contained
  `unsafe-inline` for scripts and styles.
- The baseline GitHub Django CI run for the production SHA succeeded.
- The scheduled database-backup runs of 2026-08-24 and 2026-08-31 failed at
  **Require backup secrets**. No claim of recent recoverable production backup
  is therefore made.
- Local repair verification: **257 tests passed**, **80.287%** coverage over
  8,284 statements, no missing migrations, `pip check` clean, no known
  dependency vulnerability, and no Bandit medium/high finding.

## Scoring matrix

| Domain | Production baseline | Corrected branch | Rationale |
|---|---:|---:|---|
| Functional depth and workflows | 9.0 | 9.0 | Complete IBTIKAR/GENOCLAB flows and role dashboards |
| Architecture and maintainability | 8.4 | 8.5 | Sound service modules; several very large views/document builders remain |
| Application security and privacy | 8.6 | 9.1 | MFA, encrypted TOTP, fail-closed production, protected media; reset/demo/restore/CSP repairs added |
| Financial and data integrity | 9.2 | 9.2 | Decimal engines, constraints, locking, audit and idempotent deduction |
| Tests and regression assurance | 8.5 | 8.7 | 257 passing tests and 80.287% overall; browser and accessibility gaps remain |
| CI and software supply chain | 9.2 | 9.2 | SQLite, PostgreSQL, Docker, audit and Bandit gates |
| Operations and disaster recovery | 6.5 | 6.5 | Healthy service, but two failed backups and single free-tier instance |
| UX, accessibility and i18n | 8.0 | 8.1 | FR/EN/AR and RTL present; no complete WCAG/browser evidence |
| Documentation and governance | 8.2 | 8.8 | Operational docs corrected; independent DR/pentest evidence still absent |

The overall values are weighted judgments, not an arithmetic transformation of
coverage. Operational assurance has a deliberately high impact because this
platform handles identities, scientific reports, invoices and payment proofs.

## Repairs implemented in this branch

1. Demo account/request seed commands now refuse to run whenever `DEBUG=False`.
2. Administrative account reset no longer emails a plaintext temporary
   password. It invalidates the old password and sends a signed one-time reset
   URL, expiring after 24 hours by default.
3. Completing a reset clears lockout counters and `must_change_password`.
4. Live database restore over HTTP is disabled by default and hidden from the
   SuperAdmin interface. Recovery remains an isolated operational procedure.
5. The existing same-origin CSP baseline is enforced by default in production;
   report-only mode remains available explicitly for diagnostics.
6. The dashboard now reports the configured database engine rather than
   claiming SQLite in a PostgreSQL deployment.
7. French, English and Arabic reset/backup messages and compiled catalogs were
   updated.
8. Deployment, framework, test and recovery documentation was reconciled with
   the current repository.

## Gates required before any 9.9/10 claim

1. Restore `DATABASE_URL` and `BACKUP_AGE_RECIPIENT` repository secrets, obtain
   a successful encrypted scheduled backup, and complete a timed isolated
   restore drill with recorded RPO/RTO and data-count reconciliation.
2. Merge this branch through a protected pull request, obtain green SQLite,
   PostgreSQL and Docker CI, deploy the exact merge SHA, and repeat authenticated
   production smoke tests.
3. Migrate inline JavaScript/styles to static assets or CSP nonces/hashes, then
   remove `unsafe-inline` while keeping CSP enforced.
4. Add browser E2E tests for every role and both channels, including MFA,
   payment proof, report authorization, password reset and all three locales.
5. Complete WCAG 2.2 AA automated and manual audits on representative desktop
   and mobile viewports, including keyboard-only and RTL flows.
6. Configure shared rate limiting (for example Redis) instead of per-worker
   local memory, with alerting for limiter degradation.
7. Perform an independent penetration test, secret-history review/rotation,
   dependency/SBOM review and remediation retest.
8. Replace the single free-tier instance with a production service level that
   provides monitored availability, durable logs, alerting and a documented
   recovery commitment.

Until those gates have objective evidence, **8.7/10 is the highest defensible
score for the corrected code branch and 8.4/10 for the currently deployed
revision**.
