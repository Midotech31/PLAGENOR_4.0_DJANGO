# PLAGENOR 4.0 — Project Memory

## Current Objective
- Awaiting next task.

## Verification (handoff items, 2026-06-19)
- Platform note: gating + 4 fields + admin reprice + sample summary = ALL implemented (verified in code). No change needed.
- Appointment banner: implemented, date prominent. No change needed.
- Requester confirm appointment: normal flow (APPOINTMENT_PROPOSED) works on great-newton (proven via shell). ROOT CAUSE of recurring "cannot accept" = desync state where date set but status stuck at ASSIGNED -> confirm transition invalid. FIXED: requester+client confirm_appointment views now reconcile ASSIGNED+date -> APPOINTMENT_PROPOSED (force) before confirming, + friendly msg if no RDV. Commit pending.

## Security Findings (2026-06-19)
- CRITICAL: `.env.supabase` tracked in git w/ REAL DATABASE_URL (live Supabase cred). Fix: rotate pw + `git rm --cached` + gitignore + purge history.
- MED: 2 GitHub PATs exposed in chat transcript — revoke.
- MED: report_token links never expire, allow rating/citation writes (capability link by design).
- LOW: `as_json` filter mark_safe(json.dumps) — XSS-safe only b/c admin input; HSTS_PRELOAD off; bare except in _notify_report_consulted.
- GOOD: DEBUG/SECRET_KEY secure-by-default, full SECURE_* when prod, no raw SQL/eval, report download server-side gated, UUID4 tokens.

## Completed Tasks
- Switched to branch `claude/great-newton-6Ce7v` (user-authorized).
- Verified NO "sample received" button exists on requester/client (only pipeline dots + legit "Confirmer la réception du rapport" at SENT_TO_REQUESTER).
- Verified appointment banner + URL wiring correct (compile-checked).
- Fixed anonymity leak: timeline actor column now gated by `show_actor` (requester/client no longer see analyst name).
- Unified analyst `request_detail.html` to reuse `includes/workflow_timeline.html`.
- Committed `b8246b8`, pushed to origin via direct PAT (verified via GitHub API).

## Key Decisions / Architecture
- Stack: Django 5.1, python-docx, LibreOffice headless, pypdfium2, PIL.
- Channels: IBTIKAR (academic/DGRSDT) + GENOCLAB (commercial).
- Active branch: `claude/great-newton-6Ce7v` (NOT festive-wozniak, which is local-only).
- Anonymat: requester/client must never see analyst identity.
- French UI everywhere; no emojis in code/commits; no gratuitous refactors.
- Verify with: `SECRET_KEY=dummy-for-check DEBUG=true python manage.py check`.
- PUSH BLOCKER: proxy push + MCP push_files both 403 in this env. Only working path = direct `https://x-access-token:TOKEN@github.com/...` with a user PAT (one-shot, never store in .git/config).

## Pending / Next Steps
- Awaiting next task from user.
- SECURITY: revoke both PATs exposed in chat transcript (prior-session token + this-session token). Do NOT store literal tokens in this file (triggers GitHub push protection).
