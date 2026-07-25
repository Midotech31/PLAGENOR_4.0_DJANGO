# PLAGENOR 4.0 — Complete Technical Reference

> The exhaustive, codebase-derived reference for PLAGENOR 4.0. For the shorter
> orientation guide see **`PROJECT_GUIDE.md`**; for deploy/ops gotchas see
> **`HANDOVER.md`**; for the per-feature changelog see **`project_memory.md`**.
>
> _Generated 2026-06-28 from the live codebase (branch `claude/great-newton-6Ce7v`)._

---

## Table of contents
1. Overview & domain
2. System architecture
3. Data model (every model, every field)
4. URL / route map
5. Workflow state machines + role-permission matrix
6. Pricing engine
7. Financial & IBTIKAR budget logic
8. Documents & reports
9. Media storage & the citation gate
10. CMS & internationalisation
11. Notifications & gamification
12. Management commands
13. Settings & environment variables
14. Deployment pipeline
15. Testing & CI
16. Conventions, gotchas & glossary

---

## 1. Overview & domain

PLAGENOR 4.0 manages genomic-analysis service requests for **ESSBO** (École
Supérieure en Sciences Biologiques d'Oran), an independent institution. Two
channels share one workflow engine:

- **IBTIKAR** (academic/DGRSDT): students & researchers; a **virtual budget**
  the requester self-declares, capped at `IBTIKAR_BUDGET_CAP` (200 000 DA). No
  real money; budget is *deducted* when the report is received.
- **GENOCLAB** (commercial): external clients; **real invoicing** — quote →
  purchase order → invoice (19% VAT) → payment receipt → report.

Both channels converge on a shared analyst sub-workflow (assignment →
appointment → sample reception → analysis → report → validation → delivery →
rating). Guests may submit without an account and convert later.

Core domain objects: **Service** (what's offered) → **Request** (an order) →
**RequestHistory** (audit trail) → **Invoice** (GENOCLAB) / budget deduction
(IBTIKAR) → report file delivered via a tokenised public page.

---

## 2. System architecture

```
Browser ── HTTPS ──> Render (gunicorn, Django 5.1) ── Postgres ──> Supabase DB
                              │
                              ├── Supabase Storage (S3, private bucket "media")
                              ├── WhiteNoise (static)
                              └── SMTP / console (email), Sentry (optional)
```

- **5 Django apps**: `accounts`, `core`, `dashboard`, `documents`,
  `notifications` (+ `modeltranslation`, `django_htmx`).
- **Rendering**: server-side templates + Alpine.js + htmx; one CSS file
  (`static/css/main.css`, cache-busted with `?v=N`).
- **Auth**: custom `accounts.User` (`AUTH_USER_MODEL`, table `users`).
- **Request lifecycle** is a finite state machine (`core/state_machine.py`)
  enforced by `core/workflow.transition()` with a role-permission matrix.

---

## 3. Data model

### accounts.User  (table `users`, extends `AbstractUser`)
| Field | Type | Notes |
|-------|------|-------|
| role | char(20) | `SUPER_ADMIN/PLATFORM_ADMIN/MEMBER/FINANCE/REQUESTER/CLIENT` (default REQUESTER) |
| organization | char(200) | free text |
| organization_type | char(20) | `academique/entreprise/laboratoire/particulier/autre` |
| organization_type_other | char(200) | required when type = `autre` |
| country | char(2) | ISO 3166-1 (default `DZ`); list in `accounts/countries.py` |
| phone | char(50) | |
| student_level | char(100) | IBTIKAR: master/ingenieur/doctorat |
| supervisor, laboratory | char(200) | IBTIKAR academic fields |
| ibtikar_id | char(20) | DGRSDT id (format `IDGRSTDXXXXX`) |
| gender | char(1) | M/F (stats) |
| wilaya | char(2) | Algerian wilaya code 01–58 (stats) |
| avatar | image | `avatars/` |
| last_seen | datetime | presence |
| login_attempts, locked_until | int / datetime | lockout security |
| must_change_password | bool | forces password reset on next login |
| preferred_language | char(5) | ''/fr/en/ar |
| ibtikar_declared_balance | decimal(12,2) | self-declared residual budget (nullable) |
| ibtikar_balance_declared_at | datetime | last declaration time |

### accounts.MemberProfile  (analyst, 1-1 with User where role=MEMBER)
`user`, `max_load`(5), `current_load`, `available`, `techniques`(M2M Technique),
`productivity_score`(50.0), `productivity_status`, `total_points`,
`gift_unlocked`, `gift_image`, `gift_collected`.
Auto-created by signal `ensure_member_profile` whenever a MEMBER is saved.

### accounts.Technique / PointsHistory / Cheer
`Technique(name, category, active)`; `PointsHistory(member, points, reason,
awarded_by, created_at)`; `Cheer(member, message, from_user, created_at)`.

### core.Service  (UUID pk)
`code`(unique), `name`, `description`, `channel_availability`(BOTH/IBTIKAR/
GENOCLAB), `service_type`, `ibtikar_price`/`genoclab_price`(decimal — flat
fallback), `turnaround_days`, `image`, `active`, `pricing_data`(JSON — admin
base price + multipliers), timestamps. Translatable name/description.

### core.ServiceFormField  (per-service dynamic form)
`service`(FK), `name`, `label`, `field_type`(text/number/enum/…), `field_category`,
`options`(JSON), `required`, `sort_order`, `affects_pricing`,
`price_modifier_type`, `price_modifier_value`, `condition_note_fr/en`,
`option_pricing`(JSON), `conditional_logic`(JSON).

### core.ServicePricing  (priced tiers — highest precedence)
`service`(FK), `pricing_type`, `channel`(IBTIKAR/GENOCLAB/BOTH), `name`,
`description`, `amount`, `unit`, `min_quantity`/`max_quantity`,
`min_amount`/`max_amount`, `is_active`, `priority`, audit fields.

### core.Request  (UUID pk) — the central object
Identity: `display_id`(unique, e.g. IBT-2026-0001), `title`, `description`,
`channel`, `status`(default DRAFT), `urgency`, `service`(FK).
People: `requester`(FK user), `assigned_to`(FK MemberProfile),
`informed_members`(M2M — read-only observers).
Money: `budget_amount`, `declared_ibtikar_balance`, `quote_amount`,
`quote_detail`(JSON), `admin_validated_price`(nullable override).
GENOCLAB files: `order_file`+`order_uploaded_at`, `payment_receipt_file`+
`payment_uploaded_at`.
Appointment: `appointment_date`, `appointment_proposed_by`,
`appointment_confirmed`(+at), `alt_date_proposed`, `alt_date_note`.
Assignment: `assignment_accepted`(+at), `assignment_declined`(+reason).
Report: `report_file`(`reports/`), `report_token`(UUID, unique — public link),
`report_delivered`(+at), `admin_revision_notes`.
Rating/receipt: `service_rating`(1–5), `rating_comment`, `rated_at`,
`receipt_confirmed`(+at), `citation_acknowledged` (IBTIKAR gate).
Guest: `submitted_as_guest`, `guest_token`(UUID), `guest_name`, `guest_email`,
`guest_phone`, plus `requester_data`(JSON — captures org/org_type/country/
ibtikar_id/declared balance for guests).

### core.RequestHistory  (immutable audit)
`request`(FK), `from_status`, `to_status`, `actor`, `notes`, `forced`(bool),
`created_at`.

### core.Invoice  (UUID pk, GENOCLAB)
`invoice_number`(unique), `request`(FK), `client`(FK), `line_items`(JSON),
`subtotal_ht`, `vat_rate`(0.19), `vat_amount`, `total_ttc`,
`payment_status`(PENDING/…), `locked`(True — immutable by design),
`created_at`, `created_by`.

### core.PlatformContent  (CMS)  — unique (`key`,`lang`)
`key`, `lang`(fr/en/ar), `value`(text), `updated_at`, `updated_by`.

### Other core models
`PaymentMethod(name, active)`; `Message(...)` (internal messaging);
`SequenceCounter` (per-channel/year display-id sequence);
`RevenueArchive(month, year, channel, total_revenue, request_count,
archived_at)`.

### documents
`ServiceTemplate`, `TemplatePlaceholder`, `DocumentBlock` — manage uploaded
DOCX templates + reusable blocks used by the generators.

### notifications.Notification
Typed (INFO/WORKFLOW/SYSTEM/ASSIGNMENT/STATUS_CHANGE/APPOINTMENT/REPORT/
PAYMENT/REWARD) with computed `icon`/`accent` properties; `user`, `message`,
`request`, read flag, timestamps.

---

## 4. URL / route map (by include)

**Public** (`dashboard/urls_public.py`): `home, about, services, contact, help,
track, guest_submit, guest_ibtikar_code, service_detail, service_landing,
switch_language`.

**Accounts** (`accounts/urls.py`): `login, logout, register, profile,
convert_guest, convert_guest_verify, check_email, force_change_password`.

**Root** (`plagenor/urls.py`): `report_view, report_mark_delivered, report_rate,
report_acknowledge, report_download` (tokenised), `protected_report_media`
(`/media/reports/<path>`), `serve_media` (`/media/<path>`), `admin/`, `jsi18n/`.

**Dashboard** (`dashboard/urls.py`) — by role:
- *Super Admin*: `superadmin`, `superadmin_user_toggle/_create/_edit/
  _reset_account`, `superadmin_member_toggle/_techniques`,
  `superadmin_service_create/_edit/_delete/_reactivate`,
  `superadmin_technique_create/_edit/_delete/_reactivate`,
  `superadmin_content_update/_save/_delete/_delete_key`,
  `superadmin_force_transition`, `superadmin_budget_override`,
  `superadmin_payment_method_create`, `superadmin_template_upload/_download`,
  `superadmin_backup/_restore/_reset_revenue/_export_emails`, `audit_log`,
  `revenue_archives`, `stats`, `stats_export`.
- *Admin ops*: `admin_ops`, `admin_request_detail`, `admin_transition`,
  `admin_assign`, `admin_manage_observers`, `admin_platform_note`,
  `download_quote`, `download_invoice`, `admin_report_review`,
  `admin_adjust_cost`, `admin_modify_appointment`, `admin_prepare_quote`,
  `admin_generate_invoice`, `admin_confirm_payment`, `admin_award_points`,
  `admin_send_cheer`, `admin_upload_gift`.
- *Analyst*: `analyst`, `analyst_accept/_decline`, `analyst_action`,
  `analyst_upload_report`, `analyst_suggest_appointment`,
  `analyst_accept_alt_date/_decline_alt_date`, `analyst_request_detail`,
  `analyst_collect_gift`.
- *Finance*: `finance`, `finance_validate`, `finance_payment_status`.
- *Requester*: `requester`, `requester_request_detail`, `requester_create`,
  `requester_confirm`, `requester_rate`, `requester_confirm_appointment`,
  `requester_ibtikar_code`, `requester_declare_balance`, `requester_alt_date`.
- *Client*: `client`, `client_request_detail`, `client_create`,
  `client_accept_quote/_reject_quote`, `client_upload_order/_upload_payment`,
  `client_confirm_appointment`, `client_confirm`, `client_rate`,
  `client_alt_date`.
- *Shared/API*: `service_form_fragment`, `pricing_list_api/_add_api/
  _update_api/_delete_api`, `report_qr`, `send_message`.

**Documents** (`documents/urls.py`): `ibtikar_form, platform_note, quote,
reception_form, template_list/_create/_detail/_edit/_delete/_toggle,
block_list/_create/_edit/_delete/_toggle`.

---

## 5. Workflow state machines + role permissions

### IBTIKAR graph (`IBTIKAR_TRANSITIONS`)
```
DRAFT → SUBMITTED → {VALIDATION_PEDAGOGIQUE | REJECTED}
VALIDATION_PEDAGOGIQUE → {VALIDATION_FINANCE | REJECTED}
VALIDATION_FINANCE → {PLATFORM_NOTE_GENERATED | REJECTED}
PLATFORM_NOTE_GENERATED → IBTIKAR_SUBMISSION_PENDING → IBTIKAR_CODE_SUBMITTED → ASSIGNED
ASSIGNED → APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED
SAMPLE_RECEIVED → ANALYSIS_STARTED → ANALYSIS_FINISHED → REPORT_UPLOADED
REPORT_UPLOADED → {REPORT_VALIDATED | ANALYSIS_STARTED(revision)}
REPORT_VALIDATED → SENT_TO_REQUESTER → COMPLETED → CLOSED
CLOSED / REJECTED = terminal
```
Budget deduction fires on `→ COMPLETED` (`_deduct_ibtikar_on_complete`).

### GENOCLAB graph (`GENOCLAB_TRANSITIONS`)
```
REQUEST_CREATED → {QUOTE_DRAFT | REJECTED}
QUOTE_DRAFT → {QUOTE_SENT | REJECTED}
QUOTE_SENT → {QUOTE_VALIDATED_BY_CLIENT | QUOTE_REJECTED_BY_CLIENT}
QUOTE_REJECTED_BY_CLIENT → QUOTE_DRAFT (renegotiate)
QUOTE_VALIDATED_BY_CLIENT → ORDER_UPLOADED → {INVOICE_GENERATED | ASSIGNED}
INVOICE_GENERATED → ASSIGNED
ASSIGNED → APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED
SAMPLE_RECEIVED → ANALYSIS_STARTED → ANALYSIS_FINISHED → PAYMENT_PENDING
PAYMENT_PENDING → PAYMENT_CONFIRMED → REPORT_UPLOADED
REPORT_UPLOADED → {REPORT_VALIDATED | ANALYSIS_STARTED(revision)}
REPORT_VALIDATED → SENT_TO_CLIENT → COMPLETED → ARCHIVED
ARCHIVED / REJECTED = terminal
```

### Enforcement (`core/workflow.py`)
- `transition(req, to, actor, notes='', force=False)`: validates the edge is in
  the channel graph **and** `check_role_permission` (the `ROLE_PERMISSIONS`
  matrix, keyed by `(from, to)` → allowed roles), then atomically updates status
  + writes `RequestHistory`, logs to audit, and fires (all guarded): IBTIKAR
  deduction, transition emails, in-app notifications.
- `SUPER_ADMIN` bypasses the role matrix. Unknown `(from,to)` edges are
  **denied by default** (fail-closed, logged).
- `force_transition()` skips graph+role checks (SUPER_ADMIN only at the view),
  records `forced=True`. Target must still be a declared status.

### Role-permission highlights (`ROLE_PERMISSIONS`)
- Requester can: `DRAFT→SUBMITTED`, `IBTIKAR_SUBMISSION_PENDING→
  IBTIKAR_CODE_SUBMITTED`, `SENT_TO_REQUESTER→COMPLETED`, confirm appointment.
- Client can: validate/reject quote, `QUOTE_VALIDATED→ORDER_UPLOADED`,
  `PAYMENT_PENDING→PAYMENT_CONFIRMED`, `SENT_TO_CLIENT→COMPLETED`.
- Member (analyst): appointment, sampling, analysis steps, `→REPORT_UPLOADED`.
- Finance: finance validation, `ORDER_UPLOADED→INVOICE_GENERATED`, payment.
- Admins: everything else (quote drafting, assignment, validation, delivery).

---

## 6. Pricing engine (`core/pricing.py`)

`resolve_cost(service, channel, sample_table=None, service_params=None,
urgency='Normal') -> {total, source, breakdown, …}` — the single entry point
used by every submission path (requester, client, guest). Precedence:
1. **`db_tiers`** — active `ServicePricing` rows for (service, channel/BOTH)
   → `calculate_cost_from_db()`.
2. **`service_pricing_data`** — `Service.pricing_data` (admin-authored base
   price + multipliers) fed through `calculate_price()`.
3. **`yaml_registry`** — `services_registry/<code>.yaml` for the 9 legacy
   IBTIKAR services.
4. **`flat`** — `ibtikar_price`/`genoclab_price` × max(1, sample count).

`calculate_price(service_def, params, sample_table)` supports two models:
- `per_sample_table_row_with_multiplier`: `base_price × multiplier × n_samples`
  (base chosen by pathogenic flag; multiplier from analysis_mode/qc_level/etc,
  defaults to 1.0 so a typo never zeroes a quote).
- `per_sample_fixed`: `unit_price × n`.
Raises `ValueError` on missing def/pricing/model, empty samples, unknown model.

Channel normalisation: unknown channel → starts with 'g' ⇒ GENOCLAB, else
IBTIKAR. Never raises on bad input — falls through to flat and logs.

---

## 7. Financial & IBTIKAR budget (`core/financial.py`)

- `compute_invoice_totals(line_items, admin_fees, report_fees, vat_rate=0.19)`
  — **Decimal** arithmetic, **ROUND_HALF_UP** to 2 dp; returns JSON-safe floats.
  Used by the quote builder and invoice generator. `total = HT + fees + VAT`.
- `check_ibtikar_budget(amount, requester)` — compares against the requester's
  **declared** balance (NOT a flat 200K, because the DGRSDT budget is shared
  across platforms). Returns `{declared, cap, amount, projected, exceeded,
  remaining, pct_used, needs_declaration}`. Undeclared ⇒ `exceeded=True,
  needs_declaration=True` (view must block + prompt declaration).
- `deduct_ibtikar_balance(requester, amount, reason)` — reduces declared
  balance, floors at 0, stamps time; no-op (logged) if undeclared. Called on
  `→COMPLETED` for IBTIKAR (idempotency via the workflow trigger).
- Revenue: GENOCLAB real revenue from invoices; IBTIKAR "virtual revenue" for
  reporting; `RevenueArchive` + `archive_revenue` snapshot monthly totals.

---

## 8. Documents & reports (`documents/`)

- `generators.py` builds DOCX on demand into `MEDIA_ROOT/documents/` and streams
  them (transient — regenerated as needed): platform note, quote/devis, invoice/
  facture, IBTIKAR form, reception form, stats report. House style +
  institutional header/footer applied centrally.
- `stats_excel.py` (+ `core/bilan.py`): configurable activity report (bilan)
  across 12 dimensions, with charts; exported as XLSX from the stats page.
- `pdf_converter.py`: DOCX→PDF (LibreOffice headless; optional in prod).
- The **report deliverable** (`Request.report_file`) is the analyst's uploaded
  report, persisted in storage and delivered via the tokenised public page.

---

## 9. Media storage & citation gate

- **Storage**: `plagenor/storages.py:SupabaseMediaStorage` (subclass of
  django-storages S3) overrides `url()` to return `/media/<name>` so files are
  always served **through Django**, never via public/signed S3 URLs. Enabled
  when `SUPABASE_S3_*` env vars are present; else local `FileSystemStorage`.
  Bucket is **private**.
- **Serving** (`dashboard/views/report.py`): `serve_media` streams ordinary
  media; `protected_report_media` (route declared first) gates report files.
- **Citation gate**: an IBTIKAR requester must `acknowledge_citation` before
  `download_report` / `protected_report_media` will serve the PDF; GENOCLAB
  clients and internal staff (`_is_internal_staff`) are exempt. The public
  `report_view` page (token `report_token`) shows the clause + a persuasive
  rating step; `mark_report_delivered` is a POST beacon (so crawlers can't flip
  the flag).

---

## 10. CMS & i18n

- **CMS**: `PlatformContent(key, lang, value)` rendered by
  `{% cms 'key' 'default' %}` (`core/templatetags/cms.py`). In-process cache
  with **60s TTL** + `clear_cms_cache()` on every write (handles multi-worker).
  Managed in Super Admin → **Content** tab (FR/EN/AR side-by-side, search,
  add/delete-by-key, missing-language badges). ~158 seeded keys; 52 wired into
  templates. Roadmap: `plans/cms_audit.md` (Phase A done).
- **i18n**: FR is the source language. `{% trans %}` strings compiled in
  `locale/{fr,en,ar}/LC_MESSAGES/django.po` (EN+AR fully translated). Model
  content uses `modeltranslation` (`_en`/`_ar` columns, fallback FR→EN). RTL via
  logical CSS. Language switch: `switch_language`; per-user `preferred_language`.

---

## 11. Notifications & gamification

- `notifications.Notification` — created on workflow transitions
  (`_create_notifications`), report consult, assignments, payments, rewards.
  Typed, each type maps to an icon + accent in the topbar dropdown.
- **Gamification** (analysts): `PointsHistory` (admin awards points), `Cheer`
  (encouragement), `productivity_score`/`_status`, and a gift unlock
  (`gift_unlocked`/`gift_image`/`gift_collected`) collected via
  `analyst_collect_gift`.

---

## 12. Management commands (`core/management/commands/`)

| Command | Purpose |
|---------|---------|
| `seed_services` | Seed `Service` objects from the YAML registry |
| `seed_content` | Seed CMS `PlatformContent` (get_or_create — never overwrites) |
| `seed_accounts` | Create/refresh one demo user per role |
| `seed_demo_request` | Seed a demo IBTIKAR request assigned to the demo analyst |
| `seed_notifications` | Welcome notifications for existing users |
| `ensure_superuser` | Idempotently create SUPER_ADMIN from `DJANGO_SUPERUSER_*` |
| `create_docx_templates` | Generate the physical DOCX template files |
| `backup_db` / `restore_db` | Backup/restore DB (SQLite or Postgres) to `data/backups/` |
| `archive_revenue` | Snapshot monthly revenue into `RevenueArchive` |

---

## 13. Settings & environment variables (`plagenor/settings.py`)

| Var | Role |
|-----|------|
| `SECRET_KEY` | required in prod (dev fallback only when DEBUG) |
| `DEBUG` | default False |
| `DATABASE_URL` | Postgres (Supabase); empty ⇒ SQLite `data/plagenor.db` |
| `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | auto-derived (Render host + https) |
| `SUPABASE_S3_ENDPOINT/_REGION/_ACCESS_KEY_ID/_SECRET_ACCESS_KEY/_BUCKET` | Supabase Storage; absent ⇒ local disk |
| `DJANGO_SUPERUSER_USERNAME/_PASSWORD/_EMAIL` | admin bootstrap on deploy |
| `SENTRY_DSN/_ENVIRONMENT/_TRACES_SAMPLE_RATE` | error monitoring (dormant if unset) |
| `SMTP_HOST/_PORT/_USER/_PASSWORD/SMTP_FROM`, `EMAIL_BACKEND` | email (console if no host) |
| `IBTIKAR_BUDGET_CAP` (200000), `VAT_RATE` (0.19), `INVOICE_PREFIX` | business config |
| `LANGUAGE_CODE` (fr), `LOG_LEVEL`, `SECURE_*` | locale / logging / header overrides |

Security (prod, DEBUG off): SSL redirect, secure cookies, HSTS 1y,
nosniff, `X-Frame-Options: DENY`, referrer policy, SAMESITE=Lax,
`SECURE_PROXY_SSL_HEADER` for Render's proxy. `STORAGES` dict selects Supabase
vs filesystem; WhiteNoise compressed-manifest static.

---

## 14. Deployment pipeline

- Push to **`claude/great-newton-6Ce7v`** → Render auto-build → `./build.sh`
  (`pip install` → `collectstatic` → `migrate` → `seed_services` →
  `seed_content` → `ensure_superuser`) → `gunicorn plagenor.wsgi` (3 workers).
- Files: `render.yaml`, `build.sh`, `Procfile`, `runtime.txt` (py3.11.9).
- Migrations on deploy are non-destructive; seeds are idempotent.
- **Push note**: pushing requires a user PAT; workflow files need `workflow`
  scope. Render free tier: cold starts + ephemeral disk (⇒ Supabase Storage).

---

## 15. Testing & CI

- **49 tests**: `core/tests.py` (pricing, invoice/VAT Decimal, IBTIKAR budget +
  deduction, workflow transitions/permissions), `dashboard/tests.py` (report
  gate, serve_media), `accounts/tests.py` (registration org-type/country, dup
  email). Run: `SECRET_KEY=dummy DEBUG=true python manage.py test`.
- **CI** (`.github/workflows/django.yml`): Python 3.11, on push to `main` /
  `claude/**` and PRs to `main`; runs `check` + tests + non-blocking
  `pip-audit`. **Dependabot** opens weekly dependency PRs.

---

## 16. Conventions, gotchas & glossary

**Conventions**
- French UI; no emojis in code/commits; no gratuitous refactors.
- Template comments single-line (`{# #}` multi-line leaks as text).
- Bump `?v=N` in `base.html` + `base_public.html` after CSS/template changes.
- Money in `Decimal` (`compute_invoice_totals`); JSON stores floats.
- New `{% trans %}` → makemessages → fill EN/AR → compilemessages → commit `.mo`.
- Don't put a model identifier in commits/PRs/code. Commit trailer:
  `Co-Authored-By: Claude <noreply@anthropic.com>`.

**Gotchas**
- The deploy branch is `claude/great-newton-6Ce7v`, NOT `main`.
- Don't change pricing/workflow/invoicing without tests + explicit sign-off.
- Media must stay private + served through Django or the citation gate breaks.
- Supabase free project pauses after ~1 week idle (data kept; unpause).

**Glossary** — *IBTIKAR*: academic channel (virtual budget). *GENOCLAB*:
commercial channel (real invoicing). *Bilan*: configurable activity report
(Excel). *HT/TTC*: pre-/post-VAT. *Display ID*: human-readable request number.
*Citation gate*: clause an IBTIKAR requester signs before downloading a report.
*Observer*: a member added read-only to a request (`informed_members`).
