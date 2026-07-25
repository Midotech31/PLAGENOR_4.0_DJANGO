# PLAGENOR 4.0 — Handover & Reproduction Guide

> A complete reference for re-creating PLAGENOR 4.0 from scratch. Built for another AI agent (or a new developer) so that, given this single document, the application can be reproduced feature-for-feature without going back to ask questions.
>
> Two complementary purposes:
>
> 1. **Reproduction** — describe every feature, model, role, flow, and business rule.
> 2. **Audit** — list every logic and objective in one place so the owner can spot-check for drift or mistakes.

---

## 1. Identity & objective

**PLAGENOR 4.0** (Plateforme de Gestion des Opérations Scientifiques) is a Django web application that manages scientific-analysis orders for **ESSBO** (École Supérieure en Sciences Biologiques d'Oran, Algeria). The platform runs **two parallel channels** in the same codebase:

| Channel | Audience | Pricing | Output |
|---|---|---|---|
| **IBTIKAR** | ESSBO students & researchers | Virtual budget cap **200 000 DA / student / year**, governed by DGRSDT | Platform note + DGRSDT submission code workflow |
| **GENOCLAB** | Companies, external labs, institutions | Commercial quote + invoice in DZD | Quote → PO → invoice → report |

**Designer / owner**: Prof. Mohamed Merzoug, ESSBO.

**Mission statement**: every scientific analysis request — academic or commercial — is captured online, priced consistently, routed through a single state machine, executed by an in-house analyst (MEMBER) under a load-balancing scheme, and delivered as a signed official PDF carrying the institutional banner.

**Non-goals**: PLAGENOR is **not** a generic LIMS, not a sample-storage system, not an inventory manager. It captures *requests* and *deliverables*, not bench data.

---

## 2. Top-level architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  PUBLIC SITE  (/, /services, /help, /track, /guest-submit, …)     │
│  base_public.html  ·  no auth required                              │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼   sign in / register
┌────────────────────────────────────────────────────────────────────┐
│  DASHBOARD  (/dashboard/…)                                         │
│  base.html with sidebar + topbar                                    │
│                                                                     │
│  ROUTER → role-specific view:                                       │
│   SUPER_ADMIN  → /home/  (services, users, content, audit, …)       │
│   PLATFORM_ADMIN → /ops/ (request lifecycle, assignments)           │
│   FINANCE     → /finance/ (budget validation, payment status)       │
│   MEMBER      → /analyst/ (assigned tasks, points, gift)            │
│   REQUESTER   → /requester/ (new IBTIKAR request, my requests)      │
│   CLIENT      → /client/ (new GENOCLAB request, my quotes)          │
│                                                                     │
│  All roles → /stats/, /notifications/, /accounts/profile/           │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼   transitions
┌────────────────────────────────────────────────────────────────────┐
│  STATE MACHINE  (core/state_machine.py + core/workflow.py)         │
│   IBTIKAR: 19 states / 24 edges     GENOCLAB: 21 states / 24 edges │
│   Every transition: role-permission check → audit history          │
│                   → in-app notification → e-mail → optional doc gen │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼   pricing
┌────────────────────────────────────────────────────────────────────┐
│  PRICING ENGINE (core/pricing.py)                                  │
│   Precedence: ServicePricing tiers > Service.pricing_data > YAML   │
│              > flat per-sample fallback                            │
│   Formula:    base_price × multiplier × N_samples                  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼   documents
┌────────────────────────────────────────────────────────────────────┐
│  DOCUMENT GENERATION (documents/generators.py)                     │
│   python-docx with .docx templates → LibreOffice headless → PDF    │
│   IBTIKAR form, platform note, quote, invoice, reception form,     │
│   stats report. Institutional banner on every page.                │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Web framework | Django 5.1 | `requirements.txt` pins |
| Language | Python 3.11+ | typing used loosely |
| DB (prod) | PostgreSQL | via `dj-database-url` env var |
| DB (dev) | SQLite | `data/plagenor.db` |
| ORM | Django ORM | `transaction.atomic()` + `select_for_update` |
| Templates | Django Templates | `{% icon %}` (Feather/Lucide SVG set), `{% cms %}` |
| HTMX | `django-htmx` | fragment endpoints for dynamic forms |
| i18n | gettext + `django-modeltranslation` | FR (source), EN, AR; RTL via CSS logical properties |
| Static | WhiteNoise | served at `/static/` |
| Documents | `python-docx` | + LibreOffice headless (`pdf_converter.py`) for PDF |
| Email | SMTP (prod) / console (dev) | console fallback if `SMTP_HOST` unset |
| Charts | Chart.js (CDN) | trend graphs on stats dashboard |
| Auth | Django built-in | custom `AbstractUser` + role field |
| Sessions | Django default | DB-backed |
| Signing | SSH-signed commits | hooks-friendly |

External tooling required only at build/deploy time:
- `gettext` (msgfmt, xgettext) for `python manage.py compilemessages`
- `libreoffice` headless (`soffice`) for DOCX→PDF conversion

---

## 4. Apps layout

```
plagenor/                # project settings, root URLs
  settings.py            # all config; reads .env for secrets
  urls.py                # mounts /admin/, /accounts/, /dashboard/, /documents/,
                         #         /notifications/, /i18n/, /report/<uuid>/,
                         #         and (catch-all) / → dashboard.urls_public
  wsgi.py / asgi.py

accounts/                # User + roles + member profile + gamification
core/                    # Service catalog, requests, pricing, state machine,
                         # sequences, CMS, payment methods, invoices
dashboard/               # All authenticated views (one module per role)
                         # + public site views (views_public.py)
documents/               # ServiceTemplate, DocumentBlock, generators,
                         # docx_helpers, pdf_converter
notifications/           # Notification model + emails.py (notify_* funcs)

services_registry/       # YAML service definitions (egtp_*.yaml)
documents/docx_templates/  # platform_note, quote, reception_form .docx
documents/assets/        # institutional_banner.png
templates/               # base.html, base_public.html, all UI
static/                  # css, js, icons, images
locale/                  # fr, en, ar .po + .mo catalogs
data/                    # plagenor.db (sqlite, dev), media/ (uploads)
```

Each app contributes its own `models.py`, `views.py` (or `views/` package), `urls.py`, `migrations/`, `templatetags/` (where applicable), and `admin.py`.

---

## 5. Data model — complete inventory

### 5.1 `accounts.User` (extends `AbstractUser`, db_table=`users`)

Custom user with role + organisation + an embedded profile. Email is required.

| Field | Type | Notes |
|---|---|---|
| role | CharField, choices=ROLE_CHOICES | see §6 |
| organization | CharField | free text |
| phone | CharField | |
| student_level | CharField | Master / PhD / etc. (REQUESTER only) |
| supervisor | CharField | (REQUESTER) |
| laboratory | CharField | |
| ibtikar_id | CharField | DGRSDT-issued ID (REQUESTER) |
| **gender** | CharField, choices=`[('M','Homme'),('F','Femme')]` | for stats; added in migration 0008 |
| **wilaya** | CharField(2), choices=58 official wilayas | added in migration 0008 |
| avatar | ImageField | |
| last_seen | DateTimeField | refreshed every 5 min by middleware |
| login_attempts | PositiveIntegerField | brute-force lockout |
| locked_until | DateTimeField | |
| must_change_password | BooleanField | enforced by middleware |
| preferred_language | CharField(2) | `'fr'`/`'en'`/`'ar'`/`''` (auto) |

### 5.2 `accounts.MemberProfile` (1-1 with User, MEMBER role only)

Tracks analyst availability, load, productivity, points (gamification).

Fields: `user`, `max_load` (int, default 5), `current_load`, `available` (bool), `techniques` (M2M→Technique), `productivity_score`, `productivity_status`, `total_points`, `gift_unlocked` (bool), `gift_image`, `gift_collected`.

Companion models: `Technique` (free name + category + active), `PointsHistory` (award log), `Cheer` (admin compliment message to member).

### 5.3 `core.Service`

The service catalog. UUID primary key. `code` is unique and matches a YAML file under `services_registry/`.

| Field | Type |
|---|---|
| id | UUIDField, primary_key |
| code | CharField, unique  (e.g. `EGTP-PCR`) |
| name / description | CharField / TextField — model-translated (FR/EN/AR) |
| channel_availability | choices: `BOTH` / `IBTIKAR` / `GENOCLAB` |
| service_type | choices: e.g. `analysis` / `sequencing` |
| ibtikar_price / genoclab_price | DecimalField — flat fallback price |
| turnaround_days | PositiveIntegerField |
| image | ImageField |
| active | BooleanField (default True) |
| **pricing_data** | JSONField (default `{}`) — SuperAdmin-authored base+multipliers (overrides YAML); migration 0019 |

Service definitions in YAML supply the *defaults* — DB pricing_data + ServicePricing tiers override YAML at runtime.

### 5.4 `core.ServiceFormField`

Dynamic form schema attached to a Service. Each row = one form field rendered on the New-Request page.

| Field | Type | Use |
|---|---|---|
| service | FK→Service | parent |
| name | CharField | param key (`pathogenic`, `analysis_mode`…) |
| label | CharField (model-translated) | UI label |
| field_type | choices: text / select / checkbox / number / date / table |
| **field_category** | choices: `parameter` / `sample_column` | added in 0018: distinguishes per-request params from sample-table columns |
| options | JSONField | for select/checkbox |
| required | BooleanField |
| sort_order | PositiveIntegerField |
| **affects_pricing** | BooleanField | gates the bridge to `option_pricing` |
| price_modifier_type | choices: `multiplier` / `surcharge` / `flat` |
| price_modifier_value | DecimalField | for legacy surcharge fields |
| condition_note_fr / _en | CharField | tooltip "this option includes extra charges" |
| **option_pricing** | JSONField | `{option_value: multiplier_or_amount}` — pricing per option |
| **conditional_logic** | JSONField | show/hide/required rules triggered by other fields |

### 5.5 `core.ServicePricing` (tier-based pricing)

Optional fine-grained pricing rules per service. Highest precedence in `resolve_cost`.

Fields: `service`, `pricing_type` (`base` / `per_parameter` / `urgency_surcharge` / `volume_discount` / `both`), `channel`, `name`, `description`, `amount`, `unit`, `min_quantity`, `max_quantity`, `min_amount`, `max_amount`, `is_active`, `priority` (lower = applied first), `updated_by`.

### 5.6 `core.Request` (the central object)

UUID primary key + human-readable `display_id` (e.g. `GCL-2026-0001`, `IBT-2026-0042`).

Key fields (grouped):

**Identity & ownership**
`display_id`, `title`, `description`, `channel` (`IBTIKAR`/`GENOCLAB`), `status` (state-machine state), `urgency` (`Normal`/`Urgent`/`Très urgent`), `service` (FK), `requester` (FK→User), `assigned_to` (FK→MemberProfile), `created_at`, `updated_at`, `archived` + `archived_at`.

**Pricing**
`budget_amount`, `declared_ibtikar_balance`, `quote_amount`, `admin_validated_price`, `quote_detail` (JSON), `pricing` (JSON breakdown), `service_params` (JSON), `sample_table` (JSON: list of rows).

**GENOCLAB lifecycle**
`order_file`, `order_uploaded_at`, `payment_receipt_file`, `payment_uploaded_at`.

**Scheduling**
`appointment_date`, `appointment_proposed_by`, `appointment_confirmed`, `appointment_confirmed_at`, `alt_date_proposed`, `alt_date_note`.

**Assignment dialog**
`assignment_accepted`, `assignment_accepted_at`, `assignment_declined`, `assignment_decline_reason`.

**Report delivery**
`report_file`, `report_token` (UUID, unique) — used for the public read-only viewer at `/report/<uuid>/`; `report_delivered`, `report_delivered_at`, `admin_revision_notes`.

**Feedback & receipt**
`service_rating` (1–5), `rating_comment`, `rated_at`, `receipt_confirmed`, `receipt_confirmed_at`, `citation_acknowledged`.

**Guest submission**
`submitted_as_guest` (bool), `guest_token` (UUID, unique), `guest_name`, `guest_email`, `guest_phone`. Public `/track/` looks up by `guest_token` ONLY (not display_id, to prevent enumeration).

**IBTIKAR-specific**
`ibtikar_external_code` — the DGRSDT-issued code that the requester pastes after platform-note delivery.

Indexes on `(channel, status)`, `(channel, archived)`, `status`, `requester`, `(assigned_to, status)`, `guest_token`, `report_token`.

### 5.7 `core.RequestHistory`

Audit log — one row per state transition: `request`, `from_status`, `to_status`, `actor` (nullable for system / guest), `notes`, `forced` (bool when SUPER_ADMIN used force-transition), `created_at`.

### 5.8 `core.RequestComment` and `core.Message`

`RequestComment`: per-step comments visible to admins. `Message`: direct messages between users tied to a request (`from_user` → `to_user`, `read` flag).

### 5.9 `core.Invoice`

GENOCLAB invoices. Sequentially numbered via `SequenceCounter`. Fields: `invoice_number` (unique), `request`, `client`, `line_items` (JSON), `subtotal_ht`, `vat_rate`, `vat_amount`, `total_ttc`, `payment_status` (`pending` / `paid` / `overdue` / `cancelled`), `locked` (bool — prevents edits once paid).

### 5.10 `core.PlatformContent` (CMS)

Editable site copy, addressed by `(key, lang)`. Used via `{% cms 'nav_brand' 'PLAGENOR 4.0' %}` — returns the active-language value, falling back to the literal default.

### 5.11 `core.PaymentMethod`

Simple list of payment options (`name`, `active`) — referenced when client uploads payment receipt.

### 5.12 `core.SequenceCounter` (atomic counter)

Single-row-per-scope counter. Scope examples: `IBT-2026`, `GCL-2026`, `INV-2026`. Row locked with `SELECT … FOR UPDATE` inside `transaction.atomic()` so concurrent submissions can't collide on `display_id` / `invoice_number`. See §10.

### 5.13 `core.RevenueArchive`

Monthly snapshot per channel for long-term reporting. Computed at month-end (or manually via SuperAdmin "Reset revenue" action).

### 5.14 `documents.ServiceTemplate`

Per-service .docx template. `template_type` ∈ {`ibtikar_form`, `platform_note`, `quote`, `reception_form`, `report_cover`}. Only one row can be active per `(service, template_type)`. Companion: `TemplatePlaceholder` (description of available `{{PLACEHOLDER}}` tokens for the editor).

### 5.15 `documents.DocumentBlock`

Injectable text blocks (legal notices, instructions, signature paragraphs) that get inserted into generated documents at a chosen `position`. Can be global or targeted at specific `services` (M2M). Multilingual via `language` field. Supports placeholders (`{{FULL_NAME}}`, `{{DISPLAY_ID}}`, `{{SERVICE_NAME}}`, `{{DATE}}`).

### 5.16 `notifications.Notification`

In-app notification (bell icon). Fields: `user`, `message`, `notification_type`, `request` (FK), `link_url`, `link_text`, `action_url`, `action_text`, `read`, `read_at`. Indexed on `(user, read)` + `created_at`.

---

## 6. Roles & permissions

**6 roles** (`accounts/models.py` `ROLE_CHOICES`):

| Code | French label | Responsibilities |
|---|---|---|
| `SUPER_ADMIN` | Super Administrateur | Services catalog, users, CMS, templates, audit log, force-transition, backup, **bypasses all permission checks** |
| `PLATFORM_ADMIN` | Administrateur Plateforme | Day-to-day request operations: validate, assign, prepare quote, generate invoice, confirm payment, modify appointment, review reports |
| `MEMBER` | Analyste / Opérateur | Receive assigned task, accept/decline, propose appointment, do analysis, upload report, earn points |
| `FINANCE` | Responsable Financier | Validate IBTIKAR budget consumption, update payment status |
| `REQUESTER` | Demandeur IBTIKAR | Create IBTIKAR requests, view own dashboard with budget panel, submit IBTIKAR code, confirm reception, rate service |
| `CLIENT` | Client GENOCLAB | Create GENOCLAB requests, accept/reject quote, upload PO + payment receipt, confirm reception, rate service |

Each role has its own router target (`dashboard.views.<role>.index`). The `dashboard_router` view in `dashboard/views/__init__.py` dispatches by `request.user.role`.

**Permission model**: `core/workflow.py` defines `ROLE_PERMISSIONS = {(from_status, to_status): [allowed_roles]}`. Every state-machine edge is in this map. `check_role_permission()` returns True when the actor's role is listed OR when actor is `SUPER_ADMIN`. Unknown edges deny by default. Force-transition (via SuperAdmin's `force_transition_view`) bypasses both the state-machine check and the role check but still validates that `to_status` is declared.

---

## 7. The two channels

### 7.1 IBTIKAR (academic)

- **Eligibility**: ESSBO students/researchers registered on the platform.
- **Budget**: each requester has a **virtual annual budget capped at 200 000 DA** (configurable per user via SUPER_ADMIN's `budget_override` view; otherwise a uniform cap). Budget is tracked by **declared_ibtikar_balance** the requester self-reports at submission *or* the carried-forward remaining balance from the year-to-date.
- **Display ID format**: `IBT-YYYY-NNNN` (e.g. `IBT-2026-0042`). Allocated atomically via `SequenceCounter`.
- **Submission gate** (`dashboard/views/requester.py`): before the request is created, `resolve_cost()` is computed; if the new cost would push the year-to-date over the cap, the form refuses with a clear message and shows the remaining balance.
- **Workflow** (§8.1): the request goes through pedagogical validation → finance validation → a **platform note** is generated → the requester gets an external code from DGRSDT and submits it back via `submit_ibtikar_code` → request is assigned to a MEMBER → analysis runs → report delivered.
- **No invoicing** — IBTIKAR consumes the virtual budget, no money changes hands inside the app.

### 7.2 GENOCLAB (commercial)

- **Eligibility**: external clients (companies, labs, institutions). Self-register as CLIENT.
- **Pricing**: real DZD pricing via the same engine; resulting amount is the basis of a **quote**.
- **Display ID format**: `GCL-YYYY-NNNN`.
- **Workflow** (§8.2): the admin prepares a quote → client accepts (or rejects, restarting the loop) → uploads PO → invoice generated → client uploads payment receipt → assigned to MEMBER → analysis → report.
- **Invoicing**: sequential `invoice_number`, locked once paid, archived in `RevenueArchive` monthly.

### 7.3 Cross-channel concepts

| Concept | Shared? | Notes |
|---|---|---|
| Service catalog | Yes | each Service has a `channel_availability` flag |
| Pricing formula | Yes | same engine for both |
| MEMBER assignment | Yes | same load-balancing logic |
| Report delivery + viewer | Yes | `/report/<uuid>/` |
| Notifications + e-mail | Yes | role + transition routing |
| Statistics | Yes | filtered by channel |

---

## 8. State machine

### 8.1 IBTIKAR (19 states, see `core/state_machine.py:16`)

```
DRAFT → SUBMITTED → VALIDATION_PEDAGOGIQUE → VALIDATION_FINANCE
                                          ↘ REJECTED (terminal)
VALIDATION_FINANCE → PLATFORM_NOTE_GENERATED → IBTIKAR_SUBMISSION_PENDING
                                            → IBTIKAR_CODE_SUBMITTED
                                            → ASSIGNED
ASSIGNED → APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED
       → ANALYSIS_STARTED → ANALYSIS_FINISHED → REPORT_UPLOADED
                                              ↘ ANALYSIS_STARTED (retry)
REPORT_UPLOADED → REPORT_VALIDATED → SENT_TO_REQUESTER → COMPLETED → CLOSED
```

`REJECTED` and `CLOSED` are terminal.

### 8.2 GENOCLAB (21 states, see `core/state_machine.py:51`)

```
REQUEST_CREATED → QUOTE_DRAFT → QUOTE_SENT → QUOTE_VALIDATED_BY_CLIENT
              ↘ REJECTED                  ↘ QUOTE_REJECTED_BY_CLIENT → QUOTE_DRAFT
QUOTE_VALIDATED_BY_CLIENT → ORDER_UPLOADED → INVOICE_GENERATED → ASSIGNED
                                          ↘ ASSIGNED (direct, no invoice yet)
ASSIGNED → APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED
       → ANALYSIS_STARTED → ANALYSIS_FINISHED → PAYMENT_PENDING
       → PAYMENT_CONFIRMED → REPORT_UPLOADED → REPORT_VALIDATED
       → SENT_TO_CLIENT → COMPLETED → ARCHIVED
```

`REJECTED` and `ARCHIVED` are terminal.

### 8.3 Transition rules (`core/workflow.py`)

`transition(request_obj, to_status, actor, notes='', force=False)` does:

1. Validate `(current_status, to_status)` is in the channel's allowed map (state machine).
2. Validate `actor.role` is in `ROLE_PERMISSIONS[(current_status, to_status)]` (or actor is `SUPER_ADMIN`, or `force=True`).
3. `transaction.atomic()`:
   - Update `request.status = to_status`.
   - Persist any side-effect fields (e.g. `appointment_confirmed=True` when moving to `APPOINTMENT_CONFIRMED`).
   - Create `RequestHistory(request, from_status, to_status, actor, notes, forced)`.
4. `_create_notifications()` — fires in-app `Notification` rows for the relevant audience (assignee + requester + ops admins).
5. `_send_transition_emails()` — routes to the right `notify_*` function (see §13). Failures are logged but **never** block the transition.
6. `_auto_generate_documents()` — stub for future automatic generation.

Calling code must use `transition()`. Never set `request.status = ...` directly — you'd skip history, notifications, and emails.

---

## 9. Service catalog

### 9.1 YAML registry (`services_registry/*.yaml`)

8 canonical services as of this handover (each `egtp_*.yaml`):

| Code | Service | Notes |
|---|---|---|
| `EGTP-IMT` | Identification microbienne par MALDI-TOF | base_price varies by pathogenic |
| `EGTP-PCR` | PCR (gene-specific) | multipliers per analysis_mode |
| `EGTP-CAN` | Capillary sequencing (Sanger) | multipliers per primer_type |
| `EGTP-SEQS` | Sanger sequencing service | |
| `EGTP-LYOPH` | Lyophilisation | multipliers per drying_level |
| `EGTP-ILLUMINA_WGS` | Illumina whole-genome sequencing | multipliers per sequencing_mode |
| `EGTP-SEQ02` | Second-line sequencing | |
| `EGTP-PS` | Antibiogramme / phenotypic susceptibility | |

Each YAML defines (top-level keys observed):

```yaml
service_code: EGTP-PCR
service_name: …
category: microbiology
type: analysis
version: 1.0
description: …
parameters:           # form schema → seeded into ServiceFormField
  - name: pathogenic
    type: checkbox
  - name: analysis_mode
    type: select
    options: [Simple, Duplicate, Triplicate]
    affects_pricing: true
pricing:              # baseline; overridden by DB pricing_data + ServicePricing
  pricing_model: per_sample_table_row_with_multiplier
  currency: DZD
  base_price:
    pathogenic: 2500
    non_pathogenic: 400
  multipliers:
    Simple: 1
    Duplicate: 2
    Triplicate: 2.6
sample_table:         # column schema
  columns:
    - name: sample_id
    - name: source
deliverables: [report_pdf, raw_data_zip]
compliance: { … }
turnaround_time: { days: 7 }
override_policy: { … }
```

### 9.2 Service registry loader (`core/registry.py`)

`load_service_registry(force_reload=False)` reads every `*.yaml` from `BASE_DIR / 'services_registry'` and returns `{service_code: definition}`. Cached with `@lru_cache(maxsize=1)`. `get_service_def(code)` returns one definition. `get_all_service_codes()` lists them.

### 9.3 SuperAdmin can create new services

Via `superadmin.service_create` and `service_edit`. New services live in DB only (no YAML). They use the same unified "Prix de base & multiplicateurs" editor that writes to `Service.pricing_data` — same formula, same precedence.

---

## 10. Pricing engine

### 10.1 The protected formula (`core/pricing.py:88`)

This formula is the explicit logic of the platform owner. **It must be preserved exactly** when reproducing — the entire pricing UI, the DB tier overrides, and the YAML defaults all feed into this single function:

```python
def _price_per_row_with_multiplier(pricing, params, samples, currency):
    n = len(samples)
    if n <= 0:
        raise ValueError("At least one sample is required")

    params = _normalize_params(params)

    base_prices = pricing.get('base_price', {})
    multipliers = pricing.get('multipliers', {})

    pathogenic = bool(params.get('pathogenic', False))
    base_key = 'pathogenic' if pathogenic else 'non_pathogenic'
    base_price = _coerce_int(
        base_prices.get(base_key, base_prices.get('default', 0)),
        default=0, key=f"base_price/{base_key}",
    )

    mult_key = (
        params.get('analysis_mode') or params.get('qc_level')
        or params.get('sequencing_mode') or params.get('drying_level')
        or params.get('primer_type')
    )
    if not mult_key and multipliers:
        mult_key = list(multipliers.keys())[0]

    multiplier = (
        _coerce_float(multipliers.get(mult_key, 1), default=1.0,
                      key=f"multiplier/{mult_key}")
        if mult_key else 1.0
    )
    unit_price = int(base_price * multiplier)
    total = unit_price * n

    return {
        'pricing_model': 'per_sample_table_row_with_multiplier',
        'number_of_units': n,
        'unit_price': unit_price,
        'total': total,
        'currency': currency,
        'breakdown': {
            'base_price': base_price,
            'multiplier_key': mult_key,
            'multiplier': multiplier,
            'pathogenic': pathogenic,
            'rows_billed': n,
        },
    }
```

In English: **cost = base_price × multiplier × N_samples**, where:
- `base_price` depends on whether the sample is *pathogenic* (higher) or *non-pathogenic*.
- `multiplier` is selected from `params.analysis_mode / qc_level / sequencing_mode / drying_level / primer_type` — whichever the chosen service defines.
- `N_samples` is the row count in the sample-table.

`unit_price` is `int(base_price × multiplier)` — coercion to int is **intentional** (whole DA only).

### 10.2 `resolve_cost(service, channel, sample_table, service_params, urgency)`

Walks **four precedence steps** in order, returning at the first that yields a price:

1. **ServicePricing tiers (DB)** — if any active `ServicePricing` rows exist for `(service, channel)`, `calculate_cost_from_db()` evaluates them by `priority` (lower first), summing base + matching tier modifiers + urgency surcharge. Returns `source='service_pricing_db'`.
2. **`Service.pricing_data` (DB JSON)** — if non-empty, build a synthetic YAML-shape def and call the YAML pricing path. Returns `source='service_pricing_data'`. This is the slot the SuperAdmin's "Prix de base & multiplicateurs" editor writes to.
3. **YAML registry** — call `calculate_price(yaml_def, params, samples)`. Returns `source='yaml'`.
4. **Flat fallback** — `Service.ibtikar_price` or `Service.genoclab_price` × max(1, sample_count). Returns `source='flat'`.

All four paths return the SAME shape: `{'total': <int>, 'source': <str>, 'breakdown': [...], …}`. Callers can rely on `result['total']`.

### 10.3 Where pricing is consumed

| Consumer | Behaviour |
|---|---|
| Requester / Client form (frontend) | `cost-calculator.js` reads `data-pricing-config` + `data-option-pricing` attributes; same formula in JS so the estimate updates **live** as fields change |
| `requester.create_request` | Re-runs `resolve_cost` server-side; rejects if IBTIKAR cap exceeded |
| `client.create_request` | Calls `resolve_cost` and stores as initial `quote_amount` |
| Guest submission | Same `resolve_cost` call so anonymous quotes match registered ones |
| Admin `admin_ops.prepare_quote` | Re-prices and lets admin override into `admin_validated_price` |

### 10.4 Front-end ↔ back-end pricing bridge

Because YAML can declare multipliers under arbitrary param keys (`analysis_mode`, `drying_level`, etc.) but the form fields are stored in `ServiceFormField`, `dashboard/views/service_form_api.py::service_form_fragment` does a **bridge step** when rendering: if a YAML `multipliers` block exists for a param that has options, inject the multipliers as `option_pricing` on that ServiceFormField at render time. This keeps the JS calculator perfectly in sync with the server. Keys are compared as **strings** (so YAML `Lyoph: 1.4` reaches the field whose option text is `'Lyoph'` — historic int/str mismatch bug fixed in commit `62e151f`).

### 10.5 IBTIKAR cap enforcement

Always uses the **resolved cost** (`_price_result['total']`), never the flat fallback — guards in `requester.create_request` compute resolve_cost *before* checking the cap (commit `2e5ec46` moved this guard below resolve_cost). The remaining balance is sourced from `budget_context.budget_remaining` (computed by `dashboard/utils.py`) — never hard-coded.

---

## 11. Dynamic forms

The New-Request form is **service-driven**. Selecting a service issues an HTMX request to `/dashboard/api/service-form/<service_code>/` which returns a server-rendered form fragment built from:

1. The Service's `ServiceFormField` rows where `field_category='parameter'` → standard inputs.
2. The Service's `ServiceFormField` rows where `field_category='sample_column'` → columns of the sample-table widget (`sample_id`, `source`, …).
3. The Service's YAML `parameters` → seeded into `ServiceFormField` at first edit if no rows exist.
4. The `option_pricing` bridge (§10.4) so the JS calculator can compute the live estimate.

Frontend validation in `static/js/form-validation.js`. Live cost in `static/js/cost-calculator.js`.

`conditional_logic` (JSON on ServiceFormField) declares show/hide/required rules triggered by other fields, evaluated client-side.

---

## 12. Document generation

### 12.1 Document types

| Type | When generated | Template file |
|---|---|---|
| `ibtikar_form` | After IBTIKAR `VALIDATION_FINANCE` → `PLATFORM_NOTE_GENERATED` | per-Service ServiceTemplate (DB) |
| `platform_note` | Same | `documents/docx_templates/platform_note_template.docx` |
| `quote` | GENOCLAB `QUOTE_DRAFT` → `QUOTE_SENT` | `documents/docx_templates/quote_template.docx` |
| `reception_form` | When admin marks `SAMPLE_RECEIVED` | `documents/docx_templates/reception_form_template.docx` |
| `report_cover` | When MEMBER uploads report | optional cover; analyst attaches the actual report PDF |
| `stats_report` | SuperAdmin / PLATFORM_ADMIN clicks "Exporter" on `/stats/` | built dynamically by `documents.generators.generate_stats_report` |

### 12.2 Pipeline

```
fields + sample_table → populate_legacy_param_questions() and
                        populate_legacy_sample_table()  (label-based matching)
                     → fill the .docx template (python-docx)
                     → inject any DocumentBlock entries that target this template
                     → save .docx → LibreOffice headless → PDF
                     → attach to Request.report_file / quote PDF / etc.
```

`documents/generators.py` exposes `generate_<type>(request)` functions. Each:
1. Renders the .docx via python-docx, using `_field_label_map` to translate field names to user-friendly labels.
2. Calls `_render_service_params` and `_render_sample_table` (label-aware).
3. Passes the .docx to `documents/pdf_converter.py::convert_to_pdf` which spawns `soffice --headless --convert-to pdf`.
4. (Optional UNO backend daemon for higher throughput on Linux.)
5. The institutional banner (`documents/assets/institutional_banner.png`) and header text are inserted from a single helper so all docs share the same official look.

### 12.3 Template cache invalidation

`documents/generators.py` keeps a cache keyed by `_service_fields_signature(service)` (a hash of the field rows). When the SuperAdmin edits a ServiceFormField, the signature changes → cache key changes → next generation re-renders fresh.

---

## 13. Notifications

### 13.1 In-app

`notifications.Notification` rows are created by `_create_notifications` in `core/workflow.py` on every transition. The bell icon (in `templates/includes/topbar.html`) shows unread count + a dropdown of latest items. Each notification has `link_url` (deep link to the request) and optional `action_url` (e.g. "Confirm receipt").

### 13.2 E-mail (`notifications/emails.py`)

| Function | Triggered by |
|---|---|
| `notify_submission_confirmation(req)` | Every new submission (incl. guest) |
| `notify_guest_tracking_code(req)` | Guest submission — sends the UUID tracking link |
| `notify_assignment(req)` | Transition to `ASSIGNED` |
| `notify_appointment(req)` | `APPOINTMENT_PROPOSED` or `APPOINTMENT_CONFIRMED` |
| `notify_report_delivery(req)` | `SENT_TO_REQUESTER` / `SENT_TO_CLIENT` (carries the unguessable `report_token` URL) |
| `notify_status_change(req, old, new)` | Generic fallback for any other transition |

All `notify_*` functions go through `_email_ctx(request_obj, **extra)` which exposes `request_obj` as BOTH `'request'` and `'request_obj'` in the template context (templates historically use `{{ request }}` — see fix commit `e7ccd87`).

### 13.3 SMTP config

In `plagenor/settings.py` (env-driven). If `SMTP_HOST` is unset, falls back to the console backend (printed in dev console). The owner has reserved a Gmail address `genomicsplatform.essbo@gmail.com` for outbound notifications — App-Password is set in `.env` (`.env` is gitignored).

---

## 14. Internationalization (FR / EN / AR)

### 14.1 Settings

- `LANGUAGE_CODE = 'fr'`, `LANGUAGES = [('fr','Français'),('en','English'),('ar','العربية')]`.
- Source strings in **French**, EN/AR `.po` translations under `locale/`. The `fr.po` has all empty msgstrs by design (msgid is the source). `.mo` files **are committed** intentionally (project policy in `.gitignore`) so Windows operators without GNU gettext can deploy straight from `git pull`.
- `django-modeltranslation` provides per-language fields on Service, Technique, PlatformContent, etc. (migrations 0007, 0014, 0015, 0016).

### 14.2 RTL

`base.html` and `base_public.html` set `<html lang="{{ LANGUAGE_CODE }}" dir="rtl|ltr">` based on language. CSS uses **logical properties** (`inset-inline-start`, `padding-inline-end`, `margin-block-start`, etc.) so the same stylesheet works for LTR (fr/en) and RTL (ar) without duplicate rules. The icons templatetag supports `flip_rtl=True` for direction-aware glyphs (arrows, send).

### 14.3 Language switching

- `PreferredLanguageMiddleware` (in `dashboard/middleware.py`) — for authenticated users, honours `request.user.preferred_language` over cookie / Accept-Language; runs after AuthenticationMiddleware and LocaleMiddleware.
- For anonymous users, the regular `LocaleMiddleware` reads the `django_language` cookie (set by `dashboard.views_public.switch_language`, which validates `next` against the request host to prevent open-redirect).
- Top-right selector in `templates/includes/language_switcher.html` (compact mode in public nav, full mode in profile dropdown).

### 14.4 msgctxt collision pattern

Some French words (e.g. `Démarrer`, `Centre d'aide`) are reused with different meanings in the dashboard and on the help page. Without disambiguation, `makemessages` marks the second occurrence `fuzzy` and `msgfmt` skips it, so the .mo falls back to French. Solution: use `{% trans "..." context "help" %}` (or `pgettext('help', '…')`) on the help-page-specific occurrences. This gives them their own catalog slot without touching the dashboard's translations. Applied to 9 strings on the help page.

### 14.5 Help center

Public page at `/help/`, route name `help`. Implemented in `dashboard/views_public.py::help_center` (passes `user_role` so the relevant section can be highlighted). Template `templates/pages/help.html`:

- Hero with live filter (matches against section text)
- Quick-nav grid of 6 cards using `{% icon %}` (rocket, graduation-cap, building, search, file-text, help-circle)
- Five guided sections: Getting started, IBTIKAR requester, GENOCLAB client, Tracking & reports, Generated documents
- FAQ accordion with 6 entries (language switch, IBTIKAR budget, cost formula, guest submission, missing e-mails, password)
- Contact CTA

Linked from: public nav, public footer, authenticated sidebar (Profile area).

---

## 15. Statistics

### 15.1 Engine (`core/stats.py`)

Single centralised aggregation module. Public functions:

- `headline_kpis(qs)` — total, completed %, rejected %, average duration, etc.
- `breakdown_by_status(qs)`, `breakdown_by_service(qs)`, `breakdown_by_wilaya(qs)`, `breakdown_by_organization(qs)`, `breakdown_by_gender(qs)`, `breakdown_by_analysis_frame(qs)`
- `monthly_trend(qs, months=12)` → list of `(YYYY-MM, count, revenue)` for Chart.js
- `stats_for_user(user, **filters)` — **role-aware scoping**:
  - `REQUESTER` / `CLIENT` → only their own requests (personal KPIs)
  - `MEMBER` → only requests where they are `assigned_to`
  - `FINANCE` → finance-relevant slice
  - `SUPER_ADMIN` / `PLATFORM_ADMIN` → full institutional view

`_apply_filters(qs, channel, service_code, status, wilaya, organization, gender, analysis_frame, date_from, date_to, requester_id, client_id, assigned_member_id)` is the single filter applicator used by every breakdown.

Two state-set constants: `REJECTED_STATES`, `COMPLETED_STATES` — used to compute headline rates.

### 15.2 UI (`dashboard/views/stats.py`, `templates/dashboard/stats.html`)

- `/stats/` (auth-required) — KPI grid, breakdown tables, monthly trend graph (Chart.js).
- Filter bar visible only to admin roles; non-admins see their scoped view.
- "Exporter" button → `/stats/export/` (admin-only) → official DOCX-then-PDF via `documents.generators.generate_stats_report` (full breakdown + institutional header).

---

## 16. Content management (CMS)

### 16.1 `{% cms 'key' 'default' %}` template tag

Resolves `(key, current_language)` in `PlatformContent`, falling back to the literal default. Editable by SUPER_ADMIN on `/dashboard/home/content/update/`. Used throughout `base_public.html` for the brand name, footer description, contact lines, etc.

### 16.2 DocumentBlock editor

`/dashboard/home/` includes a "Document Blocks" panel. SuperAdmin authors paragraphs to be injected into generated documents (legal notices, signature lines, instructions). Each block has:
- `template_type` — which document(s) to target
- `services` (M2M) — empty = global, else specific services only
- `position` — top / before-body / after-body / bottom
- `language`
- `title` (rendered bold above the body)
- `priority` (lower = inserted first)

Placeholders (`{{FULL_NAME}}`, `{{DISPLAY_ID}}`, `{{SERVICE_NAME}}`, `{{DATE}}`) are resolved at generation time.

---

## 17. Authentication & profile

- Custom `accounts.User(AbstractUser)`. Registration via `accounts.views.register`. Role chosen at registration: `REQUESTER` or `CLIENT` (other roles are admin-provisioned).
- Wilaya + gender are collected at registration (used by stats).
- `must_change_password` enforced by `ForcePasswordChangeMiddleware` — newly-provisioned accounts are redirected to the change-password page.
- `UpdateLastSeenMiddleware` updates `User.last_seen` at most every 5 minutes.
- Brute-force protection: `login_attempts` + `locked_until` fields, checked in the login view.
- Profile page (`/accounts/profile/`) lets the user update info + preferred language; SuperAdmin can edit any user via `superadmin_user_edit`.

---

## 18. Public pages

| URL | Name | Purpose |
|---|---|---|
| `/` | home | Landing, latest active services preview |
| `/services/` | services | Full catalog with cards |
| `/service/<code>/` | service_landing | Pre-submission CTA per service |
| `/service/<code>/detail/` | service_detail | Full YAML view (debug/transparent) |
| `/about/` | about | Static institutional page |
| `/contact/` | contact | Contact form / info |
| `/help/` | help | Help center §14.5 |
| `/track/?q=<UUID>` | track | Public guest tracking by `guest_token` UUID |
| `/track/ibtikar-code/<uuid:pk>/` | guest_ibtikar_code | Guest submits DGRSDT code post-platform-note |
| `/guest-submit/` | guest_submit | Anonymous request submission |
| `/switch-language/` (POST) | switch_language | Validated `next=` URL switch |

Guest submission supports both channels. Quoted via the same `resolve_cost` so anonymous prices equal registered prices.

---

## 19. URL structure (full)

See `plagenor/urls.py`. Mount points:
- `/admin/` — Django admin (SuperAdmin only)
- `/accounts/` — registration, login, profile
- `/dashboard/` — all authenticated dashboards (one URL conf per role section, see `dashboard/urls.py`)
- `/documents/` — uploads & template assets
- `/notifications/` — bell endpoints (HTMX)
- `/i18n/` — Django's set-language
- `/jsi18n/` — JavaScript translation catalog
- `/report/<uuid>/` — read-only report viewer (anonymous-accessible via report_token)
- `/` — fall-through to `dashboard.urls_public` (the public site)

Authenticated dashboard URLs total **~70**, grouped by role module (`requester`, `client`, `member`/analyst, `finance`, `admin_ops`, `superadmin`) plus API fragments (`/api/service-form/…`, `/api/service/…/pricing/…`).

---

## 20. Settings & middleware

### 20.1 Critical settings

```python
LANGUAGE_CODE = 'fr'
LANGUAGES     = [('fr','Français'), ('en','English'), ('ar','العربية')]
USE_I18N      = True
USE_TZ        = True
TIME_ZONE     = 'Africa/Algiers'
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL     = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'
SESSION_COOKIE_AGE  = 60 * 60 * 24 * 7   # 1 week
```

Secrets from `.env` (gitignored): `SECRET_KEY`, `DATABASE_URL` (optional, defaults to SQLite), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM`.

### 20.2 Middleware stack (in order)

1. `SecurityMiddleware`
2. `WhiteNoiseMiddleware` — serves static in prod
3. `SessionMiddleware`
4. `LocaleMiddleware` — picks language from cookie / Accept-Language
5. `CommonMiddleware`
6. `CsrfViewMiddleware`
7. `AuthenticationMiddleware`
8. **`PreferredLanguageMiddleware`** (custom) — overrides language with `user.preferred_language` for authenticated users
9. `MessageMiddleware`
10. `XFrameOptionsMiddleware`
11. **`UpdateLastSeenMiddleware`** (custom) — touches `user.last_seen` every 5 min
12. **`ForcePasswordChangeMiddleware`** (custom) — redirects to password change if `user.must_change_password`
13. `HtmxMiddleware` (django-htmx)

---

## 21. Sequence counter (atomic display IDs)

```python
def next_display_id(prefix, year, initial_value_fn=None) -> str:
    scope = f"{prefix}-{year}"
    with transaction.atomic():
        counter, _ = SequenceCounter.objects.select_for_update().get_or_create(
            scope=scope, defaults={'value': (initial_value_fn() if initial_value_fn else 0)},
        )
        counter.value += 1
        counter.save(update_fields=['value', 'updated_at'])
    return f"{prefix}-{year}-{counter.value:04d}"
```

- `SELECT … FOR UPDATE` locks the row (true row-lock on PostgreSQL; SQLite uses transaction serialization).
- `initial_value_fn` lets a first-call seed the counter to match existing records (used when migrating legacy data).
- Retries up to 3× on IntegrityError to handle concurrent first-creates.
- **Use for**: `IBT-YYYY`, `GCL-YYYY`, `INV-YYYY`. **Never** compute display IDs with `.count() + 1` — that's racy.

---

## 22. Deployment

### 22.1 Local dev (Linux/macOS/WSL)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit SECRET_KEY etc.
python manage.py migrate
python manage.py compilemessages
python manage.py seed_accounts   # one demo user per role (DEV ONLY)
python manage.py runserver
```

### 22.2 Windows (the owner's workstation)

`setup.bat` automates the steps above (venv, pip, migrate, compilemessages, seed_accounts). Documented in `QUICKSTART_WINDOWS.md`. Demo passwords are local-only.

### 22.3 Production

- PostgreSQL DB via `DATABASE_URL` env var.
- `DEBUG=False` requires `SECRET_KEY` env var (enforced by `settings.py`).
- `python manage.py collectstatic --noinput` then WhiteNoise serves at `/static/`.
- `python manage.py compilemessages` on the deploy host (or rely on the committed .mo files).
- LibreOffice headless installed for DOCX→PDF.

### 22.4 Git workflow (this codebase)

- Main branch: `main` (or `master`).
- Feature branches per session (e.g. `claude/loving-tesla-jfcNV`).
- Commits SSH-signed (env-managed signing key). `gpg.ssh.allowedSignersFile` is needed for local verification; signing always works.
- `.mo` files committed intentionally (project policy in `.gitignore` header).

---

## 23. Migrations (chronological)

### accounts/
1. `0001_initial` — User
2. `0002_alter_user_managers`
3. `0003_user_ibtikar_id`
4. `0004_user_avatar_user_last_seen`
5. `0005_must_change_password`
6. `0006_user_preferred_language`
7. `0007_technique_category_ar_…` — modeltranslation fields on Technique
8. **`0008_user_gender_user_wilaya`** — gender + wilaya for stats

### core/
1. `0001_initial`
2. `0002_revenuearchive_message`
3. `0003_invoice_payment_status_alter_request_status…`
4. `0004_quote_detail_field`
5. `0005_alt_date_fields`
6. `0006_ibtikar_workflow_states`
7. `0007_add_service_pricing` — ServicePricing model
8. `0008_request_order_file_…`
9. `0009_citation_acknowledged`
10. `0010_alter_request_service_rating_alter_request_status…`
11. `0011_backfill_member_load`
12. `0012_sequencecounter`
13. `0013_seed_sequence_counters`
14. `0014_service_description_ar_…` — modeltranslation
15. `0015_backfill_translation_fields`
16. `0016_platformcontent_multilingual`
17. `0017_serviceformfield_affects_pricing_and_more`
18. `0018_serviceformfield_field_category` — separates parameter vs sample_column
19. **`0019_service_pricing_data`** — `Service.pricing_data` JSONField

### documents/
1. `0001_initial` — ServiceTemplate, TemplatePlaceholder
2. `0002_documentblock`
3. `0003_documentblock_services_m2m`

### notifications/
1. `0001_initial` — Notification
2. `0002_add_notification_deep_linking` — link_url, link_text, action_url, action_text
3. `0003_alter_notification_notification_type`

---

## 24. Invariants & business rules (the audit checklist)

> Use this list to spot drift. Each line is a rule that must hold true.

### Pricing
- [ ] The formula `unit_price = int(base_price × multiplier); total = unit_price × N_samples` must remain in `_price_per_row_with_multiplier`.
- [ ] `base_price` is selected by `pathogenic` boolean: `pathogenic` (higher) vs `non_pathogenic` (lower). Never average, never sum.
- [ ] `multiplier` candidate keys are read **in order**: `analysis_mode`, `qc_level`, `sequencing_mode`, `drying_level`, `primer_type`. First non-empty wins; default `1.0` if none.
- [ ] `resolve_cost` precedence is `ServicePricing tiers > Service.pricing_data > YAML > flat`. Adding a new override layer goes ABOVE flat.
- [ ] Live JS calculator and server `resolve_cost` must produce the same total for the same inputs.
- [ ] Option keys compared as strings (handles YAML's int `1` vs select `'Simple'` etc.).

### IBTIKAR budget
- [ ] Cap is **200 000 DA / requester / year**; SuperAdmin override per-user is allowed.
- [ ] Cap check uses **resolved cost**, not flat `Service.ibtikar_price`.
- [ ] Remaining balance shown to the user is sourced from `budget_context.budget_remaining` — **no hard-coded `200000`** in templates or JS.
- [ ] Display ID format `IBT-YYYY-NNNN`, allocated via `SequenceCounter`. Never `Request.count() + 1`.

### State machine
- [ ] `transition()` is the only entry point. Never set `request.status = …` directly.
- [ ] Every edge in the state machine has a row in `ROLE_PERMISSIONS`. Missing → denied by default.
- [ ] `SUPER_ADMIN` bypasses checks; `force_transition` bypasses both state-machine and role validation (still records `forced=True` in history).
- [ ] Email failures inside `_send_transition_emails` must NEVER block the transition.

### Documents
- [ ] Every official document carries the institutional header (`institutional_banner.png`).
- [ ] All fields filled from online form + registration data (the user's "Tous les champs sans exception" rule).
- [ ] Fields shown on form must be present on the document, and vice versa (bidirectional parity).
- [ ] `_service_fields_signature` cache invalidates when ServiceFormField edits change the schema.

### i18n
- [ ] All user-visible strings use `{% trans %}` / `{% blocktrans %}`. French is source.
- [ ] EN/AR `.po` translated; `.mo` committed.
- [ ] Page-specific strings that share a French source with unrelated dashboard strings use `context="..."` to avoid collisions.
- [ ] `<html dir>` flips to `rtl` for Arabic.
- [ ] CSS uses logical properties (`inset-inline-start`, etc.) — no `left`/`right` hardcoded.

### Stats
- [ ] `stats_for_user` scoping: REQUESTER/CLIENT personal, MEMBER assigned, FINANCE finance, ADMIN full.
- [ ] Wilaya/Gender/Établissement/Cadre breakdowns visible to ADMIN only.
- [ ] Stats export uses the same generator pipeline (DOCX → PDF, banner).

### Sequences & uniqueness
- [ ] `display_id` and `invoice_number` allocated atomically via `SequenceCounter`.
- [ ] `guest_token` and `report_token` are unguessable UUIDv4 — public lookups use only these (never sequential IDs).

### Permissions
- [ ] Public `/track/` accepts only `guest_token` UUID — `display_id` rejected (anti-enumeration).
- [ ] `switch_language`'s `next=` validated against the request host (`url_has_allowed_host_and_scheme`).
- [ ] Login brute-force lockout via `login_attempts` + `locked_until`.

### Notifications
- [ ] `_email_ctx` passes the request object under BOTH `'request'` and `'request_obj'` (template legacy compatibility).
- [ ] `_send_transition_emails` routes to the right `notify_*` function per transition. Generic `notify_status_change` is the fallback.

---

## 25. Pitfalls / gotchas observed in real session work

1. **`makemessages` fuzzy matches** can leak the wrong translation through `msgfmt` (because fuzzy entries are skipped → fallback to French). Disambiguate with `msgctxt`.
2. **`gpg.ssh.allowedSignersFile`** must be configured for local commit verification (`%G?` reports `N` otherwise even when commits are signed). The signing wrapper `/tmp/code-sign` only supports `-Y sign`; route `verify` / `find-principals` / `check-novalidate` to the real `ssh-keygen` via a shim.
3. **`cost-calculator.js`** previously always returned the `non_pathogenic` base; the pathogenic checkbox must be read from the DOM (fixed in `2ab04ed`).
4. **Section-4 ServiceFormField questions** hidden when a sample_table is also defined — `column_names` array must be computed in `service_form_fragment` so the param-vs-column distinction works (fixed in `66adfe7`).
5. **Comment leaks**: multi-line `{# … #}` Django comments leaked as visible text on some pages — compress to single-line (fixed in `804ea8e`).
6. **`_send_transition_emails`** used to be `pass`. If you re-introduce it, wire it explicitly to the `notify_*` map.
7. **YAML int vs string keys** for multipliers — compare as strings. The `Lyoph` multiplier bug (`1` vs `'1'`) is a classic.
8. **Hard-coded `200000`** in three places once leaked back the IBTIKAR cap when SuperAdmin had overridden. Always read `budget_remaining` from context.
9. **`.env` is gitignored** — never commit secrets. Demo accounts seeded by `seed_accounts` are local-dev only.
10. **Bundle delivery**: when the push proxy is down, `git bundle create` from `origin/<branch>..HEAD` → user `git fetch bundle <branch>:<branch>` → push from their workstation.

---

## 26. Reproduction checklist (for an AI reading this fresh)

Build PLAGENOR 4.0 from scratch by executing this list in order:

1. `django-admin startproject plagenor .` + `python manage.py startapp accounts core dashboard documents notifications`.
2. Configure `settings.py` per §20.1, declare custom `AUTH_USER_MODEL='accounts.User'`, install `django-modeltranslation` and `django-htmx`, register the 3 custom middlewares.
3. Implement `accounts.User` with the role + organization + wilaya/gender fields (§5.1). Create `MemberProfile`, `Technique`, `PointsHistory`, `Cheer` companions.
4. Implement core models: `Service` (with `pricing_data` JSONField), `ServiceFormField` (with `field_category`, `affects_pricing`, `option_pricing`, `conditional_logic`), `ServicePricing`, `Request` (full field list §5.6), `RequestHistory`, `RequestComment`, `Invoice` (with sequential `invoice_number`), `PlatformContent`, `PaymentMethod`, `Message`, `SequenceCounter`, `RevenueArchive`.
5. Implement `SequenceCounter`-based ID allocation in `core/sequences.py` (§21). Use it for `display_id` and `invoice_number`.
6. Implement the state machine in `core/state_machine.py` (§8.1 and §8.2). Implement `core/workflow.py::transition` with `ROLE_PERMISSIONS` (every edge listed), history record, in-app notifications, email routing, `force=True` bypass.
7. Implement `core/pricing.py`:
   - `_price_per_row_with_multiplier` exactly as §10.1.
   - `calculate_price` dispatcher.
   - `calculate_cost_from_db` for `ServicePricing` tiers.
   - `resolve_cost` with the four-tier precedence (§10.2).
8. Build the YAML registry (`services_registry/egtp_*.yaml`) and loader (`core/registry.py`).
9. Implement `dashboard.urls`, `dashboard.urls_public`, and the role-routing in `dashboard.views.__init__::dashboard_router`. Implement one view module per role (§19).
10. Implement the dynamic form fragment API (`/api/service-form/<code>/`) with the option_pricing bridge (§10.4).
11. Implement `dashboard/views_public.py` for home/services/about/contact/help/track/guest_submit/switch_language.
12. Implement `static/js/cost-calculator.js` — same formula as `_price_per_row_with_multiplier`, reads `data-pricing-config` + `data-option-pricing` attributes.
13. Implement `documents/generators.py` — one `generate_<type>` function per document type (§12.1), pipeline §12.2. Implement `documents/pdf_converter.py` (LibreOffice headless).
14. Implement `notifications/emails.py` with the six `notify_*` functions (§13.2) and `_email_ctx` shim.
15. Implement statistics: `core/stats.py` (engine, role-aware `stats_for_user`) + `dashboard/views/stats.py` + `templates/dashboard/stats.html` (KPI grid + Chart.js trend + admin filter bar). `documents.generators.generate_stats_report` for the export.
16. Implement CMS: `PlatformContent` + `{% cms %}` templatetag. `DocumentBlock` for document injection.
17. Implement `core/templatetags/icons.py` (Feather/Lucide SVG set). Use `{% icon %}` everywhere — no emoji.
18. Implement help center (`/help/`) per §14.5. Use `msgctxt "help"` for collision-prone French strings.
19. Set up locale: `python manage.py makemessages -l en -l ar`, translate, `compilemessages`, commit the `.mo`.
20. Seed demo data: `core/management/commands/seed_accounts.py` (one user per role).
21. Verify: `python manage.py check`, navigate `/`, `/help/` in fr/en/ar, submit a guest request, walk it through the IBTIKAR and GENOCLAB flows in a test session.

---

## 27. Where to start reading the codebase

If your goal is to extend, not to reproduce, start here in this order:

1. `core/models.py` — the request object and its lifecycle fields.
2. `core/state_machine.py` + `core/workflow.py` — what can happen to a request and who can do it.
3. `core/pricing.py` — how cost is determined; protect `_price_per_row_with_multiplier`.
4. `dashboard/views/requester.py` and `dashboard/views/client.py` — entry-side flows.
5. `dashboard/views/admin_ops.py` and `dashboard/views/analyst.py` — operator-side flows.
6. `documents/generators.py` — output side.
7. `templates/base.html` (auth) and `templates/base_public.html` (public) — UI shell.
8. `static/js/cost-calculator.js` — frontend mirror of the pricing formula.

---

*End of handover. This document is meant to be self-contained — if a reader cannot reproduce a feature from the description above, that's a gap in this document, not in the codebase.*
