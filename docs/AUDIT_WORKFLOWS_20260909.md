# Workflow and notification audit — 9 September 2026

Baseline: main `7eb86046bea390a5fa1f4f28e4fe267a9f4d52e0`.
This report records reproducible validation, not a guarantee that every possible production failure is absent.

## Corrections

- Submission records and history are atomic; notifications execute after commit. Rollback sends no false confirmation. Guest submission sends one tracking email instead of two.
- Accepting an assignment no longer creates a dateless appointment. Appointment date, time and note persist; proposals and confirmations have distinct email wording. Repeated unchanged proposals send no duplicate. Past dates, closed appointments and late analyst actions are rejected.
- Commercial analysts can request payment after analysis, then upload a report after verified payment. A revision of an already-paid report does not demand payment again. An unpaid or cancelled invoice cannot unlock that shortcut.
- Workflow transitions enforce ownership and analyst assignment in the engine, reject inactive actors, and require the relevant code, assignee, appointment or uploaded document. Superadmin override remains explicit and audited.
- Zero validated IBTIKAR prices no longer fall back to estimates and incorrectly deduct a budget.
- Post-commit logging, email, in-app notification and document effects are isolated: a failure in one does not suppress the others or pretend the committed transition rolled back.
- Active operations/finance staff receive actionable milestone email with their own language and dashboard link. Staff email addresses and overlapping in-app recipients are deduplicated. Payment confirmation also notifies the requester.
- SMTP SSL is configurable and mutually exclusive with STARTTLS. PostgreSQL persistent connections use health checks before reuse. This does not repair an unavailable database server.

## Validation matrix

| Area | Evidence in this audit |
|---|---|
| IBTIKAR | Complete state sequence through closure; code, assignment, appointment and report prerequisites; budget deduction including validated zero |
| GenoClab and OHB | Complete commercial sequence through archival; quote/order/invoice/payment/report dependencies; paid report revision; existing financial and OHB tests rerun |
| Roles and access | Existing authentication, MFA, ownership, protected media and administrative permission tests rerun; direct engine ownership tests added |
| Financial integrity | Existing price visibility, tariff periods, quote snapshots, invoice cancellation and payment verification tests rerun |
| Documents | Existing generation, export, access and financial document regression tests rerun; no new claim of exhaustive visual review of every production document |
| Languages and UI | Existing FR/EN/AR catalog, branding and browser/accessibility checks rerun; notification recipient language and links asserted |
| Email transport | Fourteen new regression tests use a real local TCP SMTP receiver with synthetic addresses; full workflow milestone messages, submission, guest tracking, appointment/rescheduling, staff and password reset |
| Email assertions | Trigger timing, rollback, envelope and To recipient, subject, MIME body, request reference, dashboard/tracking links, duplicate prevention, SMTP 550 handling and continuation of in-app notification |

Local final Django result: **449 tests passed; 9,068 measured executable statements, zero missed; 100.00% line coverage** under the repository's unchanged coverage configuration. The measurement excludes existing test/migration/settings exclusions and is not exhaustive branch coverage or proof of production deliverability.
Django system check, migration drift check and `pip check` passed. Chromium: 28 browser/accessibility checks passed. Local Firefox could not create a browser page; CI must independently validate Firefox and mobile before merge. Refer to the linked PR checks for the final CI and deployment result.

## Production limits that prevent unconditional closure

1. The connected Render service uses the Free plan. Render documents that Free web services block outbound SMTP ports 25, 465 and 587: https://render.com/docs/free and https://render.com/changelog/free-web-services-will-no-longer-allow-outbound-traffic-to-smtp-ports . Actual production SMTP configuration and inbox receipt were not available for verification. The isolated receiver proves application-to-SMTP transport, not delivery from Render to a real recipient mailbox. No external test email was sent during this audit.
2. A production delivery check requires an operational permitted transport (an approved paid instance or a configured HTTPS email provider), a controlled recipient and mailbox/provider receipt evidence. No hosting purchase or credential change was made.
3. Failed sends are logged, and workflow state/in-app notifications survive. There is no durable email outbox or automatic retry guarantee; a later SMTP outage can leave an email unsent. This remains an operational reliability limitation.
4. Production logs contained upstream PostgreSQL connection refusals on 9 September. Connection health checks mitigate stale connections, but persistent provider unavailability requires investigation at the database provider. Deployment readiness must be verified separately.
5. Production backup restoration, real mailbox receipt and authoritative fiscal/bank details are not certified by these application tests. Prior audit claims do not substitute for those proofs.

Consequently, this release cannot honestly be certified as globally interruption-free or assigned 9.9/10 solely from line coverage.
