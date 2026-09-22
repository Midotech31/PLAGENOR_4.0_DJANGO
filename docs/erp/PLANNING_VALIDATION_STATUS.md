# PLAGENOR 4.0 — central operational planning

The implementation extends PLAGENOR itself, using its accounts, requests,
WorkItem tasks, inventories, CDC dossiers and analytical runs. It is not a
separate application or a second authentication system.

## Implemented vertical workflow

Admin Ops can inspect scheduled and unscheduled work, assign responsibility,
reserve equipment and rooms, record unavailability, define prerequisites,
review readiness, follow execution and approve completion. Members access their
own assignments and cannot grant themselves final approval. Existing CDC and
inventory tasks can be scheduled without recreating their business dossiers.
CDC cost access remains an independent delegation option.

Daily and weekly recurrence creates a bounded, atomic set of explicit activities.
Conflicts reject the entire creation batch. Stable request identities protect
retries, including changes to the recurrence definition. Rescheduling does not
silently move dependent activities. Resource changes and reassignment invalidate
the previous operational check.

Analytical readiness checks inspect received samples and usable reservations.
The calendar never equates planned quantities with actual consumption. A linked
analytical activity cannot be submitted before its consumption record is confirmed.

## Verified locally before PostgreSQL validation

- 54 targeted Django tests passed in the previous local validation, covering
  planning, CDC delegation, inventories, stock, biobank and analytical consumption.
- Six subsequent browser scenarios passed on desktop and mobile Edge Chromium:
  assignment through final approval, English planning and Arabic RTL planning.
  These scenarios include WCAG-labelled automated accessibility checks and a
  document-width overflow assertion. Desktop and Arabic mobile screenshots were
  inspected; an empty-calendar text contrast issue was corrected.
- The planning strings have English and Arabic translations. This does not
  establish translation completeness for every earlier operational-module screen.
- Further tests cover received samples, reservation recall, repeat creation and
  encoded XML declarations. Their latest results belong in the subsequent CI
  evidence, not in the earlier foundation CI result.

## Concurrency decisions

Task identifiers are immutable. Task edits use PostgreSQL FOR NO KEY UPDATE to
serialize edits without preventing foreign-key checks from concurrent dependency
creation. The dependency graph and exclusive resource bookings have explicit
transactional serialization. Dedicated TransactionTestCase races test concurrent
bookings, competing dependencies, stock consumption, receipt retries and occupied
biobank positions. SQLite results do not prove PostgreSQL locking behavior.

## Release boundary

This is a draft development branch. The old green foundation CI applies only to
commit 7d77622, not to this extension. The repository-wide 100% statement coverage
floor remains enforced; coverage evidence is retained even if that gate fails.
No merge to main, deployment or production data mutation is authorised by a
partial test result.

Forecasting, annual procurement planning, the complete purchasing chain, some
operational imports/exports and full CDC PDF visual acceptance still need work.
The entire master specification must not be presented as completed by this
planning vertical slice.
