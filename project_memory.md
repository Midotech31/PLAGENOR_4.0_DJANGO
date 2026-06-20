# PLAGENOR 4.0 — Project Memory

## Current Objective
- Awaiting next task.

## Configurable activity report (bilan Excel) — done, verified live
- core/bilan.py: configurable engine on top of core.stats. 12 dimensions (channel, period[month/quarter/year], service, service_type, category/nature, analysis_mode, analysis_frame, organism_type, status, organization/établissement, wilaya, gender). Each section = count + part(%) + montant IBTIKAR/GENOCLAB/total + totals row. build_bilan(filters, sections, granularity); available_sections(); DEFAULT_SECTIONS.
- documents/stats_excel.py: openpyxl pro workbook. Synthèse sheet (institution header, période, KPIs) + one styled sheet per dimension (frozen header, autofilter, banded rows, DZD/percent formats, totals).
- dashboard/views/stats.py stats_export: format=xlsx (default) -> bilan Excel with selected sections+granularity; format=docx -> old summary fallback.
- templates/dashboard/stats.html: admin "Générer un bilan (Excel)" configurator (granularity + section checkboxes), carries current filters.
- Verified end-to-end via HTTP: configurator renders, export returns valid xlsx honoring selected dimensions.

## Branding scrub in DB (done)
- seed_content uses get_or_create -> never overwrites existing CMS rows, so source-only fixes don't touch already-seeded DBs.
- Added data migration core/0021_scrub_university_of_oran_branding: replaces in PlatformContent.value: جامعة وهران -> المدرسة العليا للعلوم البيولوجية بوهران; Université d'Oran -> École Supérieure...(ESSBO); University of Oran -> Higher School...(ESSBO). Runs on migrate, cleans every deployment. Verified on data/plagenor.db (now 0 hits all 3 langs).
- KEPT: generic "الجامعة / المؤسسة" (University/Organization) form label in ar .po.

## Shared workflow pipeline stepper (done, verified live)
- Extracted admin_ops "Visual Workflow Tracker" (channel-aware IBTIKAR/GENOCLAB stepper) into templates/includes/workflow_pipeline.html.
- Included full-width on requester + client request_detail (replaced old cramped pipeline-dot cards); admin_ops now includes the partial too.
- "Prochaine étape" badges only render when allowed_transitions in context (admin only) -> not leaked to requester/client.

## RDV confirm + comment-leak fixes (done, verified via live HTTP)
- Multi-line {# #} comments leak as text in Django -> collapsed ALL to single-line across templates (banner, timeline, requester/client/admin_ops/analyst/report_viewer/guest pages).
- RDV desync (status APPOINTMENT_CONFIRMED but flag False) caused "Aucun RDV à confirmer" error. Fix: shared dashboard/utils.confirm_appointment_flow() — idempotent: if status confirmed-or-later sync flag+success; ASSIGNED+date reconcile; PROPOSED->CONFIRMED. requester+client views call it.
- Banner now keyed off view-computed `appointment_pending` (status in PROPOSED/ASSIGNED & not confirmed & date) -> green/no-button when confirmed.

## Institution naming (done)
- Removed false "Université d'Oran" / "University of Oran" affiliation everywhere (ESSBO is independent).
- Replaced with "École Supérieure en Sciences Biologiques d'Oran (ESSBO)" / EN equiv; address -> "ESSBO, Cité Emir Abdelkader (EX-INESSMO), 31000 Oran".
- Files: base_email.html, base_public.html, login.html, superadmin/index.html, contact.html, seed_content.py (FR+EN).
- KEPT (legitimate): generic "Université / Organisation" form labels, "toutes les universités algériennes", ESSBO's own correct name in doc generators. plagenor_data.json CMS values already clean.
- NOTE: live DB CMS may need re-seed if it holds old seeded values (dump is already clean).

## Registration vs guest messaging (done)
- guest_submit.html: value-prop banner + Créer un compte CTA.
- guest_submit_success.html: convert-to-account block.
- guest_tracking_code.html email: fixed FR "Want full access?" leftover + enriched benefits.
- help.html: new "Compte ou invité ?" section + quicknav + enriched FAQ.
- Note: convert_guest auto-attaches existing guest requests to new account.

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
