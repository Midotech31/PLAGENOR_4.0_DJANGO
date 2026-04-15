# PLAGENOR 4.0 — PROJECT HANDOVER DOCUMENT

> **CRITICAL**: This document is the single source of truth for continuing PLAGENOR 4.0 development.
> A new developer reading ONLY this file should understand the entire project state.

---

## 1. PROJECT OVERVIEW

### App Name & Purpose
**PLAGENOR 4.0** — Plateforme de Gestion des Analyses Biologiques / Biological Analysis Management Platform

A dual-channel platform serving:
- **IBTIKAR**: Academic/research channel (government-funded via IBTIKAR-DGRSDT)
- **GENOCLAB**: Commercial/clinic channel (direct payment)

### Tech Stack
- **Backend**: Django 5.1, Python 3.12
- **Database**: PostgreSQL
- **Frontend**: HTML/Tailwind CSS, Alpine.js, JavaScript
- **PDF Generation**: ReportLab, openpyxl
- **Email**: Django email backend (configurable)
- **Deployment**: Railway (primary), compatible with any Django host

---

## 2. CURRENT STATE — WORKING FEATURES

### Superadmin Dashboard
- [x] Service management with field editor
- [x] ServiceFormField CRUD
- [x] ServicePricing configuration
- [x] Conditional logic for form fields
- [x] User/member management

### Admin Ops Dashboard
- [x] Request list with filtering
- [x] Bulk assign, bulk transition
- [x] Performance metrics
- [x] Activity Dashboard with KPIs
- [x] Administrative close
- [x] Reassign request
- [x] Observer members
- [x] Poke system

### Member/Analyst Dashboard
- [x] **Fixed**: All tabs now display content (pending, progress, history, points, notifs)
- [x] **Fixed**: Observer access to request details
- [x] Badge Gallery with 10 levels
- [x] Points System
- [x] Reward Boxes
- [x] Smart reminders
- [x] Observed Requests

### Messaging System
- [x] Ephemeral messages
- [x] Smart reminders with escalation
- [x] File attachments
- [x] Observer read-only access

### Visual Design Standardization (2026-04-06 Session 2+)
- [x] `x-cloak` added to all Alpine.js tab containers
- [x] Message panel standardized to teal color scheme
- [x] Reminder cards standardized with NORMAL/URGENT/CRITICAL colors
- [x] Notification list standardized with unread indicators
- [x] Buttons standardized to Tailwind classes in:
  - `analyst/request_detail.html`
  - `admin_ops/request_detail.html`
  - `admin_ops/activity.html`

---

## 3. RECENT FIXES (2026-04-06)

### Member Dashboard Empty Content Fix
**Problem**: When clicking on menu tabs, content areas were empty.

**Root Causes**:
1. Missing `my_reminders` context variable
2. Missing "In Progress" tab content section
3. Missing Alpine.js `x-cloak` CSS rule

**Solution**:
| File | Change |
|------|--------|
| `dashboard/views/analyst.py` | Added Reminder import, query for my_reminders, added to context |
| `templates/dashboard/analyst/index.html` | Created separate "In Progress" tab section, added x-cloak to all tabs |
| `static/css/main.css` | Added `[x-cloak] { display: none !important; }` rule |

### Template Syntax Error Fix
**Problem**: `TemplateSyntaxError` - Invalid block tag: 'endif'

**Solution**: Removed 2 extra `{% endif %}` in `templates/dashboard/analyst/request_detail.html`

### URL Reversal Error Fix
**Problem**: `NoReverseMatch` for 'report_acknowledge' with `token=None`

**Solution**: Wrapped fetch URL in conditional `{% if req.report_token %}` check

### Observer Access Fix
**Problem**: Clicking on observed request gave 403 Forbidden

**Solution**: 
- Added observer access check in `dashboard/views/analyst.py`
- Uses correct field name: `informed_members` (not `observers`)
- Access condition: `if not was_assigned and not is_observer:`

---

## 4. DATABASE MODELS — KEY FIELDS

### Request (core)
| Field | Type | Purpose |
|-------|------|---------|
| `assigned_to` | ForeignKey | MemberProfile assigned |
| `informed_members` | ManyToManyField | **Observer members (read-only)** |
| `status` | CharField | Current workflow state |
| `report_token` | UUID | Can be None - check before using in URLs |

### MemberProfile (accounts)
| Field | Type | Purpose |
|-------|------|---------|
| `total_points` | IntegerField | Lifetime points |
| `milestone_level` | IntegerField | Current level (1-10) |

---

## 5. KEY URLS

| URL | Purpose |
|-----|---------|
| `/dashboard/analyst/` | Member dashboard |
| `/dashboard/ops/activity/` | Activity Dashboard |
| `/messaging/reminders/` | AJAX endpoint for reminders |
| `python manage.py check_reminders` | Cron job |

---

## 6. FILES MODIFIED (2026-04-06 Sessions 2-5)

### Design Standardization — Session 5 (Final)
| File | Buttons | Changes |
|------|--------|---------|
| `templates/dashboard/superadmin/index.html` | Already OK | Verified all buttons standardized |
| `templates/dashboard/superadmin/field_templates_list.html` | 6 | Complete redesign with Tailwind cards/tables |
| `templates/dashboard/superadmin/service_edit.html` | 11 | All HTML + JS buttons standardized |
| `templates/dashboard/superadmin/request_detail.html` | 6 | Buttons + status badges + cards |
| `templates/dashboard/superadmin/audit_log.html` | 5 | Buttons + filter inputs + table |
| `templates/dashboard/admin_ops/performance_points.html` | 6 | Buttons + filter inputs + cards |
| `templates/dashboard/admin_ops/user_detail.html` | 6 | Buttons + info cards + badges |
| `templates/dashboard/admin_ops/users_list.html` | 7 | Buttons + filter inputs + table |
| `templates/dashboard/admin_ops/activity_log.html` | 6 | Buttons + filter inputs + table |
| `templates/dashboard/admin_ops/prepare_quote.html` | 4 | Buttons + form inputs + card layout |
| `templates/dashboard/admin_ops/report_review.html` | 4 | Buttons + cards |
| `templates/dashboard/error.html` | 2 | Complete redesign with centered content |

**Session 5 Total: 57 buttons standardized across 12 templates**

### Design Standardization — Sessions 2-4
| File | Changes |
|------|---------|
| `static/css/main.css` | x-cloak CSS rule |
| `messaging/templates/messaging/message_panel.html` | Complete redesign to teal scheme |
| `messaging/templates/messaging/reminder_card.html` | Complete redesign |
| `templates/includes/notification_list.html` | Complete redesign |
| `templates/dashboard/admin_ops/index.html` | Added x-cloak to 10 tabs |
| `templates/dashboard/client/index.html` | Added x-cloak to 6 tabs |
| `templates/dashboard/requester/index.html` | Added x-cloak to 5 tabs |
| `templates/dashboard/finance/index.html` | Added x-cloak to 6 tabs |
| `templates/dashboard/superadmin/index.html` | Added x-cloak to 13 tabs |
| `templates/dashboard/analyst/request_detail.html` | Buttons standardized to Tailwind |
| `templates/dashboard/admin_ops/request_detail.html` | Buttons standardized to Tailwind |
| `templates/dashboard/admin_ops/activity.html` | Buttons standardized to Tailwind |

### Bug Fixes (Session 2)
| File | Changes |
|------|---------|
| `dashboard/views/analyst.py` | Added my_reminders context, observer access fix |
| `templates/dashboard/analyst/index.html` | In Progress tab, x-cloak attributes |
| `templates/dashboard/analyst/request_detail.html` | Fixed extra endif, report_token check |

---

## 7. DESIGN STANDARDS (2026-04-06)

### Buttons
- Primary: `bg-teal-600 hover:bg-teal-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition`
- Secondary: `bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition`
- Danger: `bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 rounded-lg px-4 py-2 text-sm font-medium transition`
- Success: `bg-green-600 hover:bg-green-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition`

### Status Badge Colors
- COMPLETED, CLOSED, ARCHIVED, PAYMENT_CONFIRMED, REPORT_VALIDATED → `bg-green-50 text-green-700`
- ASSIGNED, ACCEPTED, ANALYSIS_STARTED, ANALYSIS_FINISHED, SAMPLE_RECEIVED → `bg-blue-50 text-blue-700`
- SUBMITTED, PENDING_ACCEPTANCE, PAYMENT_PENDING, APPOINTMENT_PROPOSED → `bg-amber-50 text-amber-700`
- VALIDATION_PEDAGOGIQUE, VALIDATION_FINANCE → `bg-purple-50 text-purple-700`
- REJECTED, EXPIRED, CANCELLED → `bg-red-50 text-red-700`

### Cards
- Standard: `bg-white rounded-xl shadow-sm border border-gray-100 p-6`
- Compact: `bg-white rounded-xl shadow-sm border border-gray-100 p-4`

---

## 8. IMPORTANT NOTES

### Field Names
- **Observers**: Use `informed_members` field on Request model
- **In Progress tab**: Uses `tab === 'progress'` (not 'in_progress')

### Testing Checklist
- [x] All dashboard tabs show content
- [x] Observer can view request details
- [x] Request detail page loads without errors
- [x] `manage.py check` passes

---

## 9. PREMIUM UI REDESIGN (2026-04-07) — COMPLETE

### Session 6 — Premium Design System

**Font Choice:** Inter (Google Fonts) with JetBrains Mono for codes/IDs

**Added comprehensive premium CSS design system with:**
- Teal-based color palette (`--primary: #0d9488`)
- Gradient buttons with glow effects and lift animations
- Premium cards with animated top borders on hover
- Modern badges with animated dots and gradient backgrounds
- Form inputs with focus glow states
- Sidebar active link with vertical indicator bar
- Modal overlays with backdrop blur and scale animations
- Chat bubbles with spring animations
- Progress bars with shimmer effects
- Premium empty states with dashed borders

**CSS Classes Available:**
| Class | Purpose |
|-------|---------|
| **Buttons** | |
| `btn btn-primary` | Gradient teal with glow |
| `btn btn-secondary` | Glass-like white with lift |
| `btn btn-danger` | Red gradient for critical actions |
| `btn btn-danger-soft` | Subtle red for less critical |
| `btn btn-success` | Green gradient |
| `btn btn-warning` | Amber gradient |
| `btn btn-info` | Blue gradient |
| `btn btn-purple` | Purple gradient |
| `btn btn-ghost` | Invisible until hovered |
| `btn btn-icon` | Icon-only buttons |
| `btn btn-sm/btn-lg/btn-xl/btn-xs` | Size variants |
| **Cards** | |
| `card` | Premium card with top border animation |
| `card card-hover` | Interactive cards with lift |
| `card card-interactive` | Cursor pointer cards |
| `card card-kpi` | KPI cards with animated top bar |
| `card card-flat` | Cards without shadow |
| `card card-glow` | Cards with primary glow |
| `card-header/card-body/card-footer` | Card sections |
| **Badges** | |
| `badge` | Premium badge base |
| `badge badge-success/info/warning/danger/purple/teal/cyan/neutral` | Status badges |
| `badge-dot` | Animated dot indicator |
| `badge-live` | Live status with pulse |
| **Forms** | |
| `input` | Premium form inputs with focus glow |
| `form-group/form-label/form-error` | Form structure |
| `form-check` | Checkbox/radio wrappers |
| **Tables** | |
| `table-container` | Premium tables with gradient headers |
| `table-compact` | Compact table variant |
| **Modals** | |
| `modal-overlay` | Blurred backdrop overlay |
| `modal modal-lg/modal-xl/modal-sm` | Size variants |
| `modal-header/modal-body/modal-footer` | Modal sections |
| **Utilities** | |
| `font-mono` | JetBrains Mono for IDs/codes |
| `request-id` | Styled request ID display |
| `price-tag` | Styled price display |
| `text-gradient` | Gradient text effect |
| `fade-in-up/scale-in` | Animation utilities |
| `skeleton` | Loading skeleton |
| `empty-state` | Premium empty states |
| `notification-dot` | Pulsing notification dot |
| `clickable-row` | Table row cursor pointer |
| `glass/glass-dark` | Glass morphism effect |
| `hover-lift` | Hover lift utility |

**Templates Updated:**
- `client/index.html`, `client/request_detail.html`, `client/archive_detail.html`
- `requester/index.html`, `requester/request_detail.html`, `requester/post_download.html`
- `analyst/index.html`, `analyst/request_detail.html`
- `finance/index.html`
- `superadmin/index.html`, `superadmin/service_edit.html`, `superadmin/request_detail.html`, `superadmin/audit_log.html`, `superadmin/field_templates_list.html`, `superadmin/field_template_create.html`, `superadmin/service_fields_reset.html`, `superadmin/payment_settings.html`, `superadmin/user_edit.html`, `superadmin/reset_account_confirm.html`, `superadmin/field_template_apply.html`, `superadmin/field_template_delete.html`, `superadmin/revenue_archives.html`
- `messaging/message_panel.html`, `messaging/reminder_card.html`
- `includes/notification_list.html`, `includes/sidebar.html`
- `admin_ops/index.html`, `admin_ops/report_review.html`, `admin_ops/prepare_quote.html`, `admin_ops/activity_log.html`, `admin_ops/users_list.html`, `admin_ops/performance_points.html`, `admin_ops/request_detail.html`, `admin_ops/member_points_detail.html`, `admin_ops/reassign_request.html`, `admin_ops/manage_observers.html`, `admin_ops/activity.html`, `admin_ops/user_detail.html`, `admin_ops/close_request.html`
- `error.html`
- `base.html` (added font preconnect)

**All templates converted to premium CSS button classes. Zero old flat button patterns (bg-teal-600, bg-green-600, bg-amber-500, bg-red-600, bg-violet-600) remaining.**

---

## 10. PREMIUM BUTTON MAPPING

### Primary Button
```
inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg px-4 py-2 text-sm font-medium transition
```

### Secondary Button
```
inline-flex items-center gap-2 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 rounded-lg px-4 py-2 text-sm font-medium transition
```

### Danger Button
```
inline-flex items-center gap-2 bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 rounded-lg px-4 py-2 text-sm font-medium transition
```

### Warning Button
```
inline-flex items-center gap-2 bg-amber-50 text-amber-600 hover:bg-amber-100 border border-amber-200 rounded-lg px-4 py-2 text-sm font-medium transition
```

### Ghost Button (icon-only)
```
p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition
```

### Button Type Mapping
| Action | Style |
|--------|-------|
| Save, Submit, Create, Add, Approve, Assign, Confirm | Primary (teal) |
| Cancel, Back, Close modal, Export, Filter, Reset | Secondary (white) |
| Delete, Remove, Reject, Close request, Revoke | Danger (red) |
| Override, Force, Escalate, Poke | Warning (amber) |
| Small icon-only actions in tables (edit, view, copy) | Ghost |

---

---

## 11. ISO/IEC 17025:2017 GAP ANALYSIS AUDIT (2026-04-08)

### Overview
Conducted comprehensive code audit against ISO/IEC 17025:2017 requirements. Full report: **`PLAGENOR_4.0_ISO17025_AUDIT_REPORT.md`**

### Verdict: ⚠️ PARTIALLY COMPLIANT (50% overall)

| Category | Score | Notes |
|----------|-------|-------|
| Software Compliance | 65% | Solid foundations, gaps documented |
| Operational Compliance | 40% | Relies on manual procedures |
| Accreditation Evidence | 50% | Foundations present, formal proofs insufficient |

### Critical Gaps (Must Fix for Accreditation)

| Clause | Gap | Priority |
|--------|-----|----------|
| 6.4 Equipment | No Equipment/Calibration models | 🔴 CRITICAL |
| 6.5 Metrology | No ReferenceMaterial/CalibrationCertificate | 🔴 CRITICAL |
| 7.10 Non-Conformities | No NonConformance/RootCause models | 🔴 CRITICAL |
| 8.3 Document Control | No Document/Approval workflow models | 🔴 CRITICAL |
| 8.5 Corrective Actions | No CorrectiveAction/CAPA models | 🔴 CRITICAL |
| 8.8 Internal Audits | No InternalAudit/AuditFinding models | 🔴 CRITICAL |
| 7.8 Reports | PDFs missing uncertainty statements | 🔴 CRITICAL |
| 7.4 Samples | No ChainOfCustody model | 🔴 CRITICAL |
| 6.2 Personnel | No TrainingRecord/CompetencyAssessment | ⚠️ HIGH |

### Strengths Found
- ✅ RBAC with ROLE_PERMISSIONS dict (workflow.py)
- ✅ RequestHistory audit trail on every transition
- ✅ Server-side pricing validation (core/pricing.py)
- ✅ SoftDeleteModel with deleted_by tracking
- ✅ UUID PKs + database indexes on Request
- ✅ 4 complete PDF generators (IBTIKAR, Platform Note, Reception, Invoice)
- ✅ ReportVersion model for document archives
- ✅ Security: HTTPS, CSRF, CSP, HSTS, rate limiting
- ✅ Role-aware email notifications (bilingual FR/EN)

### Phased Action Plan

**Phase 1 (0-3 months): Prerequisites**
1. Create Equipment + EquipmentCalibration models
2. Create ReferenceMaterial + MeasurementUncertaintyRecord models
3. Create NonConformance + RootCause + CorrectiveAction models (CAPA)
4. Create QualityDocument + DocumentApproval models

**Phase 2 (3-6 months): Completeness**
5. Create TrainingRecord + CompetencyAssessment models
6. Create InternalAudit + AuditFinding models
7. Create ManagementReview model
8. Update PDF generators with uncertainty statements + conformity declarations

**Phase 3 (6-12 months): Optimization**
9. Create SampleCondition + ChainOfCustody models
10. Implement automated backups + data retention policy

### Django Models to Create

```python
# Phase 1 (Priority)
class Equipment(models.Model): ...
class EquipmentCalibration(models.Model): ...
class ReferenceMaterial(models.Model): ...
class MeasurementUncertaintyRecord(models.Model): ...
class NonConformance(models.Model): ...
class RootCauseAnalysis(models.Model): ...
class CorrectiveAction(models.Model): ...
class QualityDocument(models.Model): ...
class DocumentApproval(models.Model): ...

# Phase 2
class TrainingRecord(models.Model): ...
class CompetencyAssessment(models.Model): ...
class InternalAudit(models.Model): ...
class AuditFinding(models.Model): ...
class AuditResponse(models.Model): ...
class ManagementReview(models.Model): ...
class ManagementReviewAction(models.Model): ...

# Phase 3
class SampleCondition(models.Model): ...
class ChainOfCustody(models.Model): ...
```

### Quick Reference Matrix

| ✅ Conform | ⚠️ Partial | ❌ Absent |
|------------|------------|-----------|
| 7.1 Requests review | 4.1 Impartiality | 6.4 Equipment |
| 7.5 Tech records | 4.2 Confidentiality | 6.5 Metrology |
| (RBAC foundations) | 6.2 Personnel | 7.10 NC |
| | 7.4 Samples | 8.3 Documents |
| | 7.8 Reports | 8.5 Corrective |
| | 7.11 Data/IT | 8.8 Audits |
| | | 8.9 Mgmt Review |

---

*Last Updated: 2026-04-15*
*Status: ✅ ISO 17025 GAP ANALYSIS COMPLETE — Full report in PLAGENOR_4.0_ISO17025_AUDIT_REPORT.md*

---

## 14. SESSION QA FINALE PRÉ-DÉPLOIEMENT (2026-04-15)

### Parcours audités (manuel simulé)
- Public/Landing: homepage CMS + fallback, services/partners, track/guest-submit.
- Auth/Accounts: login, register, redirections et liens publics.
- Requester/Client: détail demande, pipeline, documents/rapport, sections de notation.
- Analyst/Admin Ops/Superadmin: vérification logique d’actions conditionnelles et liens critiques.
- Notifications/PDF UX: cohérence de navigation et états de téléchargement.

### Correctifs appliqués pendant la passe QA
- `templates/accounts/login.html`
  - Lien “Soumettre en tant qu’invité” corrigé vers `guest_submit` (au lieu de `track`) pour éviter un parcours trompeur.
- `templates/pages/track.html`
  - Condition de téléchargement rapport guest sécurisée avec une logique explicite: le bouton n’apparaît que si un `report_file` existe ET statut dans `SENT_TO_REQUESTER|SENT_TO_CLIENT|COMPLETED`.
- `templates/dashboard/admin_ops/request_detail.html`
  - Condition “Préparer / Modifier le devis” refactorisée avec parenthésage implicite explicite (if imbriqués) pour fiabiliser l’affichage action GENOCLAB selon statut.
- `templates/dashboard/client/request_detail.html`
  - Bloc “Votre évaluation” corrigé: n’apparaît plus hors état `COMPLETED` (évite affichage vide/incohérent quand la demande n’est pas clôturée).

### Ambiguïté métier maintenue stable (TODO)
- `dashboard/views/requester.py`
  - TODO conservé sur la reprogrammation IBTIKAR (introduire ou non un statut dédié `APPOINTMENT_RESCHEDULING_REQUESTED`).
  - Comportement actuel volontairement conservé pour éviter régression workflow.

### Validation technique post-QA
- `python manage.py check` → OK (0 issue)
- `python manage.py test -v2 --keepdb` → OK (84/84)
- Note: le run de tests signale des changements de modèles non migrés déjà présents dans l’état courant du repo (`core`, `notifications`), non introduits par cette passe QA.

---

## 13. SESSION 9 (2026-04-15) — FINAL STABILIZATION PASS

### What was finalized
- Fixed critical template logic using invalid membership checks (`value in 'A,B,C'`) in dashboard pipelines by switching to the safe `|in_list` filter:
  - `templates/dashboard/client/index.html`
  - `templates/dashboard/requester/index.html`
- Fixed broken requester receipt block in dashboard index:
  - Replaced invalid form action variable (`requester_confirm_url2`) with valid URLs
  - Restored expected actions: report download + receipt confirmation
- Hardened PDF file existence checks (removed ineffective `hasattr(..., 'exists')` on string paths):
  - `documents/pdf_generator_platform_note.py`
  - `documents/pdf_generator_reception.py`
- Improved Platform Note turnaround rendering to respect channel-aware service configuration:
  - Uses `turnaround_ibtikar` + `turnaround_unit` (business/calendar/weeks)
- Simplified unstable User Oversight annotation in Admin Ops (invalid ORM aggregation removed):
  - `dashboard/views/admin_ops.py`

### Product quality impact
- Pipeline progress indicators now evaluate statuses correctly (no false positives from substring checks).
- Requester dashboard “report ready” action is operational again (no broken submit target).
- PDF generators are more resilient against missing/partial files and display more accurate turnaround metadata.
- Admin users list is stable and maintainable with a clean request-count aggregation.

### Validation executed
- `python manage.py check` → OK
- `python manage.py test -v2 --keepdb` → 84/84 OK

---

## 12. SESSION 8 (2026-04-10)

### Delivery Summary
- Homepage CMS completed and validated (editable sections/blocks workflow active)
- Service image ratios fixed across homepage cards, services catalogue, and service detail (no cropping)
- PDF logo ratio protection implemented through shared logo dimension helper
- Service form field ordering improved with reliable up/down swap controls
- New `PDFFormField` architecture delivered (separated from `ServiceFormField`)
- Notification link/action fixes applied for broken analyst acceptance URLs
- Forms audit executed (CSRF/method/action review, no critical POST+CSRF regressions)
- Pre-deployment hardening pass executed (security settings, static pipeline, checks)

### Implemented Work
- **Homepage CMS**
  - Superadmin homepage manager and sections/blocks ordering/editing/toggling flow validated
- **Image Ratios**
  - Service image containers standardized with fixed aspect ratio + `object-fit: contain`
  - Removed service-image clipping patterns (`object-fit: cover`/hidden crop contexts)
- **PDF Logo Ratios**
  - `documents/pdf_styles.py` now computes logo height from actual source image ratio
  - Affects IBTIKAR/Platform Note/Reception generators via shared helper
- **Field Ordering (Service Edit)**
  - Added per-field position visibility and ↑↓ move actions with neighbor swap
  - Ordering persisted by category and service
- **PDF Dynamic Fields (Tâche 3)**
  - Added `PDFFormField` model + migration (`core.0041_pdfformfield`)
  - Added `documents/pdf_dynamic_fields.py` (`get_pdf_fields`, `render_pdf_fields`)
  - Integrated dynamic fields in 3 PDF generators before signature blocks
  - Added superadmin UI + routes for PDF fields CRUD, toggle, and ↑↓ ordering
  - Added sidebar entry: “Champs PDF”
- **Notifications**
  - Fixed broken action links from `/dashboard/ops/request/<pk>/accept/` to valid analyst route `/dashboard/analyst/accept/<pk>/`
- **Forms Audit**
  - Global scan done on templates/forms for method/csrf/action consistency
  - No critical missing-CSRF POST templates found in server-rendered forms

### Pre-Deployment Audit (Session 8)
- `plagenor/settings.py`
  - WhiteNoise middleware placed directly after `SecurityMiddleware`
  - `STATICFILES_STORAGE` set to `whitenoise.storage.CompressedManifestStaticFilesStorage`
  - Production hardening block appended (as requested) for SSL/HSTS/secure cookies/CSRF trusted origins
  - Base defaults tightened (`DEBUG=False` by default; hardened fallback `SECRET_KEY`)
- Debug prints removed from targeted app code paths
- `.env.example` replaced with minimal production-oriented keys:
  - `DEBUG`, `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`, `BASE_URL`, `SUPPORT_EMAIL`

### Command Outputs (Session 8)
- `python manage.py check --deploy`
  - Current output still includes environment-driven warnings when running with non-production env values in local shell (not code regressions)
- `python manage.py makemigrations --check --dry-run`
  - Clean after applying pending migration updates
- `python manage.py collectstatic --noinput --dry-run`
  - Successful dry-run
- `python manage.py test -v2`
  - Aborted in this environment due to existing PostgreSQL test DB requiring interactive confirmation (`test_postgres` already exists)

### Notes
- For fully clean `check --deploy` output, run with production-grade environment variables set in runtime shell (`DEBUG=False`, strong `SECRET_KEY`, and HTTPS deployment context).
