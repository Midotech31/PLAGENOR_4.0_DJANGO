# PLAGENOR 4.0 — Project Memory

## Current Objective
- Awaiting next task. Last unit of work (timeline anonymity + unify) shipped.

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
