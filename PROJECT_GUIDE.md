# PLAGENOR 4.0 — Project Guide (collaboration reference)

> A single, self-contained reference for working on PLAGENOR 4.0 — with a human
> collaborator or with Claude (Opus). Pair it with:
> - **`HANDOVER.md`** — deployment + operational gotchas (push path, DB, secrets)
> - **`project_memory.md`** — per-feature changelog (what changed, when, why)
> - **`plans/`** — audits and build plans (e.g. `plans/cms_audit.md`)
>
> _Last updated: 2026-06-28._

---

## 1. What the app is

**PLAGENOR 4.0** is a Django platform for the **ESSBO** (École Supérieure en
Sciences Biologiques d'Oran) — an **independent** institution (NOT affiliated
with "Université d'Oran"; that branding was scrubbed, incl. a DB migration). It
manages genomic-analysis service requests end to end (submission → validation →
appointment → sampling → analysis → report → delivery → rating), across two
channels:

- **IBTIKAR** — academic / DGRSDT. Students & researchers. **Virtual budget**
  (per-student declared balance, hard cap `IBTIKAR_BUDGET_CAP` = 200 000 DA).
- **GENOCLAB** — commercial. External clients. **Real invoicing** (quote →
  order → invoice with 19% VAT → payment).

Guests can submit without an account (tracking code by email) and later convert
to a full account.

---

## 2. Live deployment

| Thing | Value |
|-------|-------|
| Host | **Render** (free web service `plagenor`, region **Frankfurt**) |
| URL | https://plagenor.onrender.com |
| Database | **Supabase Postgres** (free) via `DATABASE_URL` |
| Media | **Supabase Storage** (S3-compatible, **private** bucket `media`) |
| Deploy branch | **`main`** (Render auto-deploys the protected canonical branch) |
| Build | `./build.sh` → `gunicorn plagenor.wsgi` |
| Repo | `Midotech31/PLAGENOR_4.0_DJANGO` |

`build.sh` (idempotent): `pip install` → `collectstatic` → `migrate` →
`seed_services` → `seed_content` → `ensure_superuser`.

> Render free tier: **spins down on inactivity** (~50s cold start), **single
> instance**, **ephemeral disk** (so media MUST live on Supabase Storage).
> Supabase free tier: **pauses a project after ~1 week idle** (data kept; just
> unpause). Keep backups on.

---

## 3. Tech stack

- **Django 5.2 LTS**, Python **3.11**
- DB: PostgreSQL (`dj-database-url`, `psycopg2-binary`); SQLite fallback in dev
- Storage: `django-storages` + `boto3` (Supabase S3); WhiteNoise for static
- Docs: `python-docx`, `openpyxl` (Excel bilans), `qrcode`, `Pillow`
- Frontend: server-rendered templates + **Alpine.js** + **htmx**; single
  `static/css/main.css`; emojis via **Twemoji** CDN
- i18n: `django-modeltranslation` (`_en`/`_ar` columns) + gettext `.po`
  (FR source, EN/AR translated); RTL via logical CSS properties
- Monitoring: **Sentry** (optional, dormant unless `SENTRY_DSN` set)

---

## 4. Apps & models

| App | Models | Responsibility |
|-----|--------|----------------|
| **accounts** | `User`, `MemberProfile`, `Technique`, `PointsHistory`, `Cheer` | Auth, roles, analyst profiles, gamification |
| **core** | `Service`, `ServiceFormField`, `ServicePricing`, `Request`, `RequestHistory`, `RequestComment`, `Invoice`, `PlatformContent`, `PaymentMethod`, `Message`, `SequenceCounter`, `RevenueArchive` | Domain heart: requests, pricing, invoicing, CMS content, workflow data |
| **dashboard** | (views only) | Role dashboards, admin ops, report serving, stats |
| **documents** | `ServiceTemplate`, `TemplatePlaceholder`, `DocumentBlock` | DOCX generation (quotes, invoices, notes, reports, bilans) |
| **notifications** | `Notification` | In-app notifications (typed, with icons) |

Key business modules (not models):
- `core/pricing.py` — `resolve_cost()` (canonical resolver: DB tiers → YAML →
  flat) + `calculate_price()` (pricing engine).
- `core/financial.py` — `check_ibtikar_budget()`, `deduct_ibtikar_balance()`,
  `compute_invoice_totals()` (Decimal, ROUND_HALF_UP), revenue dashboards.
- `core/workflow.py` — `transition()`, `force_transition()`, role permissions.
- `core/state_machine.py` — the IBTIKAR / GENOCLAB transition graphs.
- `core/bilan.py` + `documents/stats_excel.py` — configurable activity report.
- `documents/generators.py` — DOCX builders.

---

## 5. Roles (`User.role`, table `users`)

| Role | Who | Can |
|------|-----|-----|
| `SUPER_ADMIN` | Platform owner | Everything, incl. force transitions, user creation, CMS, backups |
| `PLATFORM_ADMIN` | Operations admin | Manage requests/workflow, assign analysts, quotes |
| `MEMBER` | Analyst / operator | Accept assignments, appointments, run analysis, upload reports |
| `FINANCE` | Finance officer | Validate finance step, invoices, payments |
| `REQUESTER` | IBTIKAR student/researcher | Submit & track IBTIKAR requests, declare budget |
| `CLIENT` | GENOCLAB external client | Submit & track GENOCLAB requests, validate quotes, pay |

- Public registration (`/inscription`) only creates **REQUESTER** or **CLIENT**.
- **Staff are created by a Super Admin** (dashboard → Users tab → Create user),
  which accepts any role. Creating a `MEMBER` auto-creates its `MemberProfile`
  (signal `accounts/signals.py:ensure_member_profile`).
- Anonymity rule: requesters/clients must **never** see the analyst's identity.

---

## 6. Workflow state machines (`core/state_machine.py`)

**IBTIKAR:** `DRAFT → SUBMITTED → VALIDATION_PEDAGOGIQUE → VALIDATION_FINANCE →
PLATFORM_NOTE_GENERATED → IBTIKAR_SUBMISSION_PENDING → IBTIKAR_CODE_SUBMITTED →
ASSIGNED → APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED →
ANALYSIS_STARTED → ANALYSIS_FINISHED → REPORT_UPLOADED → REPORT_VALIDATED →
SENT_TO_REQUESTER → COMPLETED → CLOSED` (+ `REJECTED`).
Budget is **deducted on `COMPLETED`** (receipt confirmed).

**GENOCLAB:** `REQUEST_CREATED → QUOTE_DRAFT → QUOTE_SENT →
QUOTE_VALIDATED_BY_CLIENT → ORDER_UPLOADED → INVOICE_GENERATED → ASSIGNED →
APPOINTMENT_* → SAMPLE_RECEIVED → ANALYSIS_* → PAYMENT_PENDING →
PAYMENT_CONFIRMED → REPORT_UPLOADED → REPORT_VALIDATED → SENT_TO_CLIENT →
COMPLETED → ARCHIVED` (+ `QUOTE_REJECTED_BY_CLIENT`, `REJECTED`).

Transitions are validated against the graph **and** a role-permission map
(`core/workflow.ROLE_PERMISSIONS`, fail-closed). `SUPER_ADMIN` bypasses; forced
transitions skip both and are recorded with `forced=True` in `RequestHistory`.

---

## 7. Key subsystems

- **Pricing** — every submission path calls `resolve_cost(service, channel, …)`.
  Precedence: active `ServicePricing` tiers → `pricing_data`/YAML registry →
  flat `ibtikar_price`/`genoclab_price` × sample count.
- **Report citation gate** — IBTIKAR requesters must accept an authorship/
  citation clause before downloading their report; GENOCLAB clients and internal
  staff are exempt. Enforced server-side in `dashboard/views/report.py`
  (`download_report`, `protected_report_media`). Media is served **through
  Django** (`/media/...`) so this gate can't be bypassed by a direct URL.
- **Media storage** — `plagenor/storages.py:SupabaseMediaStorage` keeps URLs at
  `/media/<name>` (private bucket, no public/signed S3 links). `serve_media`
  streams non-report media; `protected_report_media` streams gated reports.
- **CMS** — editable text via `PlatformContent (key, lang, value)` rendered with
  `{% cms 'key' 'default' %}` (`core/templatetags/cms.py`, 60s TTL cache +
  `clear_cms_cache()` on write). Managed in the Super Admin **Content** tab
  (FR/EN/AR side-by-side; see `plans/cms_audit.md` for the phased plan).
- **i18n** — `{% trans %}` strings live in `locale/<lang>/LC_MESSAGES/django.po`;
  CMS text + modeltranslation columns cover editable/data content.
- **Documents** — generated on demand into `MEDIA_ROOT/documents/` (transient)
  and streamed; the report deliverable (`Request.report_file`) is persisted.

---

## 8. Project structure (key paths)

```
plagenor/         settings.py (STORAGES, Sentry, security), urls.py, wsgi.py, storages.py
accounts/         models.py (User…), forms.py (RegistrationForm), signals.py, countries.py
core/             models.py, pricing.py, financial.py, workflow.py, state_machine.py,
                  bilan.py, registry.py, audit.py, templatetags/cms.py,
                  management/commands/ (seed_*, backup_db, restore_db, ensure_superuser…)
dashboard/        views/ (superadmin, admin_ops, analyst, finance, client, requester,
                  report, stats…), views_public.py (guest), urls.py, urls_public.py
documents/        generators.py, stats_excel.py, pdf_converter.py, models.py, views.py
notifications/    models.py, views.py
templates/        base.html, base_public.html, accounts/, dashboard/, pages/, includes/
static/css/main.css   (single stylesheet; bump ?v=N cache-buster on changes)
locale/{fr,en,ar}/LC_MESSAGES/django.po
services_registry/*.yaml   (9 legacy IBTIKAR service definitions)
render.yaml, build.sh, Procfile, runtime.txt, requirements.txt
.github/workflows/django.yml, .github/dependabot.yml
```

---

## 9. Environment variables

| Var | Purpose |
|-----|---------|
| `SECRET_KEY` | Required in prod (fails fast if missing & not DEBUG) |
| `DEBUG` | `false` in prod |
| `DATABASE_URL` | Supabase Postgres (session pooler; encode `@` as `%40`) |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Auto-derived from host; leave empty |
| `SUPABASE_S3_ENDPOINT` / `_REGION` / `_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_BUCKET` | Persistent media (leave empty → local disk in dev) |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` / `_EMAIL` | Bootstraps the Super Admin on deploy |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` | Error monitoring (optional) |
| `SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` / `SMTP_FROM` | Email (else console backend) |
| `IBTIKAR_BUDGET_CAP`, `VAT_RATE`, `INVOICE_PREFIX` | Business config |
| `LOG_LEVEL`, `SECURE_*` | Logging / security header overrides |

See `.env.example` for the annotated list. **Secrets only go in Render/Supabase
panels — never in commits or chat.**

---

## 10. Local development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
SECRET_KEY=dev DEBUG=true python manage.py migrate
SECRET_KEY=dev DEBUG=true python manage.py seed_services   # optional sample data
SECRET_KEY=dev DEBUG=true python manage.py seed_content
SECRET_KEY=dev DEBUG=true python manage.py runserver
```
Dev DB = `data/plagenor.db` (SQLite, gitignored) when `DATABASE_URL` is empty.
gettext is required for i18n commands (`apt-get install gettext`).

**Verify before pushing:**
```bash
SECRET_KEY=dummy DEBUG=true python manage.py check
SECRET_KEY=dummy DEBUG=true DATABASE_URL="" python manage.py test
```

---

## 11. Tests & CI

- More than **250 tests** across the Django apps cover pricing, budgets,
  workflows, invoices, protected reports/media, role isolation, MFA, uploads,
  notifications, backups and operational commands. Overall coverage is gated
  at **80%** without excluding the large dashboard/document modules.
- CI runs on every branch push and pull request. It validates SQLite and
  PostgreSQL, migrations, templates, translations, dependency vulnerabilities,
  Bandit findings, a synthetic PostgreSQL backup/restore, and the non-root
  production Docker image. **Dependabot** opens weekly update PRs.

---

## 12. Conventions (read before editing)

- **French UI** everywhere. **No emojis** in code/commits. No gratuitous refactors.
- Keep Django template comments **single-line** (`{# … #}` multi-line leaks as text).
- After CSS/template changes, **bump the `?v=N` cache-buster** in `base.html`
  AND `base_public.html`.
- Money in **`Decimal`** (see `compute_invoice_totals`); JSON-stored values are floats.
- New `{% trans %}` strings → run `makemessages -l en -l ar -l fr`, fill EN/AR,
  `compilemessages`, commit the `.mo` files.
- Do **not** put a model identifier in commits/PRs/code.
- Commit trailer: `Co-Authored-By: Claude <noreply@anthropic.com>`.

---

## 13. Common tasks

- **Create a staff account** → Super Admin dashboard → Users tab → Create user →
  pick role (`MEMBER` analyst, `FINANCE`, `PLATFORM_ADMIN`…). Persisted to Supabase.
- **Edit site text** → Super Admin → Content tab (FR/EN/AR). Changes appear within
  ~60s across all gunicorn workers (per-worker cache TTL).
- **Add a service** → Super Admin → Services tab (CRUD); pricing via tiers or
  `pricing_data`.
- **Add/redo translations** → edit `.po`, `compilemessages`, commit `.mo`.
- **Backup / restore DB** → `manage.py backup_db` / `restore_db`.

---

## 14. Security & secrets

- `.env*` is gitignored (except `.env.example`). Never commit real secrets.
- Rotate any exposed secret immediately (revoke token / reset password).
- Enable GitHub **secret scanning + push protection**.
- Report vulnerabilities privately (see `SECURITY.md`).

---

## 15. Status & roadmap

**Done & live:** deployment, media persistence, registration org-type + country,
full FR/EN/AR i18n, CMS Phase A (unified Content Manager), 49-test suite, working
CI, Dependabot/pip-audit/Sentry scaffolding.

**Pending (owner actions):** protect `main` + require CI; enable secret scanning;
verify Supabase backups; consider a paid Render tier for production.

**Optional / next:** CMS Phase B (admin-editable dropdown options), Phase C
(expand `{% cms %}` to public pages — low priority), deeper integration tests,
LibreOffice Dockerfile for server-side DOCX→PDF.

---

## 16. Collaborating with Claude (Opus)

When starting a new session, point Claude at this file plus `HANDOVER.md` and
`project_memory.md`. Good first prompt:

> "Read PROJECT_GUIDE.md, HANDOVER.md and project_memory.md, then we'll continue."

Working agreement that has worked well here:
- Branch is `claude/great-newton-6Ce7v` (Render deploys it); commit + push each
  change; update `project_memory.md` / `HANDOVER.md` when relevant.
- Verify with `manage.py check` + `manage.py test` before pushing.
- Don't change core business logic (pricing, workflow, invoicing) without tests
  and explicit confirmation.
- Pushing workflow files (`.github/workflows/`) needs a PAT with `workflow`
  scope; opening PRs / editing workflows may require GitHub App permissions.
