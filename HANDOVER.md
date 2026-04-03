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

### Project Structure
```
PLAGENOR_4.0_DJANGO/
├── accounts/              # User accounts, MemberProfile, roles
│   ├── models.py          # User, MemberProfile, PointsHistory, Cheer
│   └── migrations/
├── api/                   # REST API endpoints
├── core/                  # Core business logic
│   ├── models.py          # Service, Request, ServiceFormField, ServicePricing
│   ├── workflow.py         # State machine, transitions, notifications
│   ├── state_machine.py    # IBTIKAR & GENOCLAB workflow states
│   ├── pricing.py          # Dynamic pricing calculation engine
│   ├── services/           # Service-specific submission logic
│   │   ├── ibtikar.py
│   │   └── genoclab.py
│   └── migrations/
├── dashboard/             # Django views by role
│   ├── views/
│   │   ├── admin_ops.py    # Admin operations, rewards, assignment
│   │   ├── analyst.py       # Member/analyst dashboard
│   │   ├── client.py        # GENOCLAB client views
│   │   ├── requester.py     # IBTIKAR requester views
│   │   ├── finance.py       # Finance validation
│   │   └── superadmin.py    # Super admin management
│   ├── urls.py
│   └── templates/
├── documents/             # PDF generation
│   ├── pdf_generator_ibtikar.py
│   ├── pdf_generator_platform_note.py
│   ├── pdf_generator_reception.py
│   └── pdf_generator_invoice.py
├── notifications/         # Notification system
│   ├── models.py          # Notification model with deep linking
│   ├── services.py        # Notification creation helpers
│   └── views.py           # Notification click handling
├── plagenor/              # Django project settings
├── templates/             # HTML templates
├── scripts/               # Utility scripts
└── requirements.txt
```

---

## 2. CURRENT STATE — WORKING FEATURES

### Superadmin Dashboard (`/dashboard/home/`)
- [x] Service management with field editor
- [x] ServiceFormField CRUD (parameters, sample table columns, additional info)
- [x] ServicePricing configuration (base price, per-sample, per-parameter, surcharges)
- [x] Conditional logic for form fields (show/hide based on other field values)
- [x] Option-level pricing for multi-select fields
- [x] User/member management
- [x] Payment method configuration
- [x] Budget override for requests
- [x] Force transition for stuck requests

### Admin Ops Dashboard (`/dashboard/ops/`)
- [x] Request list with filtering by channel, status, member
- [x] Request detail with workflow actions
- [x] Bulk assign, bulk transition
- [x] Manual points award to members
- [x] Performance metrics (`/dashboard/ops/performance/`)
- [x] Member points detail view (`/dashboard/ops/member/<id>/points/`)
- [x] Activity log
- [x] CSV export
- [x] Report review and validation
- [x] Cost adjustment

### Member/Analyst Dashboard (`/dashboard/analyst/`)
- [x] Assigned tasks view
- [x] In-progress requests
- [x] Completed history
- [x] **Badge Gallery** with 10 levels (Bronze → Legend)
- [x] **Points System** with milestone tracking
- [x] **Reward Boxes** (every 2000 points = 1 box)
- [x] 3D Gift box animation for unlocked rewards
- [x] Points history
- [x] Cheers system (messages from colleagues)
- [x] Gift collection mechanism
- [x] Productivity score calculation
- [x] Ranking position

### Client/Requester Views
- [x] Service catalog with dynamic forms
- [x] Dynamic cost estimation based on form parameters
- [x] Request submission (IBTIKAR or GENOCLAB)
- [x] Quote acceptance/rejection (GENOCLAB)
- [x] Purchase order upload (GENOCLAB)
- [x] Payment receipt upload
- [x] Appointment confirmation
- [x] Request tracking
- [x] Report download
- [x] Service rating

### System Features
- [x] **Server-side price validation** in `core/pricing.py`
- [x] **Role-aware notification links** - each notification type links to correct page
- [x] **Auto 50 points on service completion** - `core/workflow.py:_award_completion_points()`
- [x] **Badge/milestone/reward notifications** triggered automatically
- [x] **Bilingual emails** (FR/EN)
- [x] **PDF auto-generation** on key transitions
- [x] **State machine validation** for all workflow transitions
- [x] **Audit logging**

---

## 3. ARCHITECTURE DECISIONS

### Pricing: YAML → Database Migration
- **Old**: Pricing defined in YAML files in `services_registry/`
- **New**: Pricing stored in `ServicePricing` database model
- **Fallback**: Legacy `ibtikar_price`, `genoclab_price` fields kept on Service model

### ServiceFormField JSONField Extensions
```python
# Conditional logic - show/hide fields based on other field values
conditional_logic = [
    {
        "trigger_field": "service_type",
        "trigger_value": "urgent",
        "actions": ["show", "make_required"]
    }
]

# Option-level pricing for multi-select
option_pricing = {
    "premium_option": 500,
    "standard_option": 0
}
```

### Price Calculation Engine (`core/pricing.py`)
- `validate_and_calculate_price()` - validates client-submitted price against server-side calculation
- `calculate_price()` - main dispatcher based on ServicePricing configs
- Key features: per-sample, per-parameter, urgency surcharges, discounts

### Points System Architecture
```
award_points() in accounts/models.py:
├── Updates total_points
├── Checks milestone (every 1000 pts)
│   └── Creates milestone notification
├── Checks badge level (1=Bronze, 2=Silver, 3=Gold, 4=Platinum, 5=Diamond)
│   └── Creates badge notification
└── Checks reward boxes (every 2000 pts = 1 box)
    └── Creates reward notification
```

### Completion Points (`core/workflow.py`)
```python
_award_completion_points(request_obj, to_status, actor):
├── Trigger: IBTIKAR → CLOSED OR GENOCLAB → ARCHIVED
├── Check: completion_points_awarded flag (prevents double)
├── Award: 50 points to assigned_to member
├── Record: PointsHistory entry
└── Flag: Sets completion_points_awarded = True
```

### Role-Aware Notification Links
```python
# _get_request_link_url(request_obj, user)
- SUPER_ADMIN/PLATFORM_ADMIN → /dashboard/ops/request/{pk}/
- MEMBER → /dashboard/analyst/request/{pk}/
- FINANCE → /dashboard/ops/request/{pk}/
- CLIENT (GENOCLAB) → /dashboard/client/request/{pk}/
- REQUESTER (IBTIKAR) → /dashboard/requester/request/{pk}/
```

---

## 4. DATABASE MODELS — KEY FIELDS

### ServiceFormField (core)
| Field | Type | Purpose |
|-------|------|---------|
| `conditional_logic` | JSONField | Field visibility rules |
| `option_pricing` | JSONField | Per-option pricing |
| `affects_pricing` | BooleanField | Option affects total |
| `price_modifier_type` | CharField | add/set/multiply |
| `price_modifier_value` | DecimalField | Modifier amount |
| `channel` | CharField | IBTIKAR/GENOCLAB/BOTH |

### ServicePricing (core)
| Field | Type | Purpose |
|-------|------|---------|
| `pricing_type` | CharField | BASE/PER_SAMPLE/PER_PARAMETER/URGENCY_SURCHARGE/DISCOUNT |
| `channel` | CharField | IBTIKAR/GENOCLAB/BOTH |
| `amount` | DecimalField | Price amount |
| `unit` | CharField | Unit label |
| `min_quantity` | IntegerField | Minimum quantity |
| `max_quantity` | IntegerField | Maximum quantity |

### Request (core)
| Field | Type | Purpose |
|-------|------|---------|
| `channel` | CharField | IBTIKAR or GENOCLAB |
| `status` | CharField | Current workflow state |
| `assigned_to` | ForeignKey | MemberProfile |
| `ibtikar_id` | CharField | IBTIKAR-DGRSDT tracking |
| `tracking_number` | CharField | GENOCLAB tracking |
| `quote_amount` | DecimalField | Client quote |
| `admin_validated_price` | DecimalField | Final price |
| `completion_points_awarded` | BooleanField | Prevents double award |
| `generated_ibtikar_form` | FileField | Auto-generated PDF |
| `generated_platform_note` | FileField | Platform note PDF |
| `generated_reception_form` | FileField | Reception form PDF |
| `generated_invoice` | FileField | Excel invoice |

### MemberProfile (accounts)
| Field | Type | Purpose |
|-------|------|---------|
| `total_points` | IntegerField | Lifetime points |
| `milestone_count` | IntegerField | Number of 1000pt milestones |
| `milestone_level` | IntegerField | Current milestone level |
| `last_milestone_at` | DateTimeField | Last milestone timestamp |
| `milestone_history` | JSONField | List of milestone events |
| `badge_level` | IntegerField | 0=Newcomer, 1=Bronze...5=Diamond |
| `unlocked_reward_boxes` | IntegerField | Boxes available to collect |
| `collected_reward_boxes` | IntegerField | Boxes already collected |
| `reward_history` | JSONField | List of collected rewards |
| `gift_unlocked` | BooleanField | Current milestone gift available |
| `gift_collected` | BooleanField | Gift claimed |
| `reward_points` | IntegerField | Points in current cycle |

### Notification (notifications)
| Field | Type | Purpose |
|-------|------|---------|
| `notification_type` | CharField | WORKFLOW/POINTS/REWARD/etc. |
| `request` | ForeignKey | Linked request (optional) |
| `link_url` | CharField | Deep link URL |
| `action_url` | CharField | Action button URL |
| `read` | BooleanField | Read status |
| `read_at` | DateTimeField | Read timestamp |

---

## 5. PENDING TASKS

### All Visual Bugs Fixed (as of last session)
The following items from earlier sessions have been completed:
- [x] Badge gallery unlock colors - now correctly applies based on `milestone_level`
- [x] Badge shapes - 10 unique SVG shapes implemented
- [x] Current level highlight with "Actuel" label
- [x] Notification links - role-aware routing implemented

### Reward Box Collection UX (Completed)
- [x] AJAX collect for gift (milestone gift from admin)
- [x] AJAX collect for reward boxes (2000pt automated rewards)
- [x] Confirmation modal before opening
- [x] 3D animated reward box with floating animation
- [x] Confetti celebration animation on open
- [x] Collection history section with box details
- [x] Real-time toast notifications

### Test Coverage (Completed)
- [x] `tests/test_pricing.py` - Full coverage for pricing engine
  - Base price, per-sample, surcharges, discounts
  - validate_and_calculate_price() match vs mismatch
  - Field price modifiers (add/set/multiply)
  - Price propagation with multiple samples
  - Channel-specific pricing (IBTIKAR vs GENOCLAB)
  - Multiple discounts stacking
- [x] `tests/test_points.py` - Full coverage for points system
  - award_points() increments, milestones, badges, reward boxes
  - All 10 badge levels verified
  - Double award prevention
  - Reward box calculations
- [x] `tests/test_workflow.py` - Workflow transitions
  - Valid/invalid transitions for both channels
  - Auto 50pts on CLOSED/ARCHIVED
  - Double close prevention
  - No assigned member graceful skip
- [x] `tests/test_notifications.py` - Notification system
  - Notification creation, mark as read
  - All notification types
  - Role-aware links
- [x] `tests/test_conditional_logic.py` - Conditional pricing
  - Field show/hide logic
  - Price modifier activation/revert
  - Multi-select cumulative pricing

### Badge System Harmonisation (Completed)
- [x] Single source of truth: `BadgeConfig` DB model
- [x] All 10 badge levels (Bronze → Legend) configured
- [x] MemberProfile display properties query BadgeConfig
- [x] Removed deprecated `BADGE_TIERS` constant
- [x] `_calculate_badge_level()` uses BadgeConfig.get_badge_for_points()

### Pricing Engine Bug Fix (Completed)
- [x] Fixed OVERRIDE pricing type not working correctly
- [x] Fixed BASE + DISCOUNT stacking
- [x] Fixed operator precedence issue in pricing logic

### Critical Fixes & Enhancements (Session 2026-04-03)
- [x] **core/views.py** - Deleted empty placeholder file
- [x] **api/views.py** - Not needed (views defined inline in api/urls.py)
- [x] **PointsHistory duplicate prevention** - Added `UniqueConstraint` on (member, reason, points)
- [x] **Soft delete on Service/Request/User** - Added `SoftDeleteModel` mixin with `is_deleted`, `deleted_at`, `deleted_by` fields
- [x] **OpenAPI documentation** - Configured at `/api/docs/` (Swagger) and `/api/redoc/`
- [x] **Request ID logging** - Already implemented in `plagenor/request_id.py`
- [x] **drf-spectacular** - Installed and configured for REST API docs

### Test Fixes (Session 2026-04-03 PM)
- [x] **Badge notification tests** - Fixed event index (milestone=0, badge_change=1, reward_box=2)
- [x] **reward_level_name test** - Fixed to use total_points instead of badge_level
- [x] **All 73 tests now pass** (100% pass rate)

### Soft Delete Integration
- Service/Request/User use `SoftDeleteManager` (excludes deleted by default)
- Use `model.soft_delete(deleted_by=user)` instead of `model.delete()`
- Use `model.all_objects` to query including deleted
- Use `model.hard_delete()` for permanent deletion (Superadmin only)
- Configuration models (ServiceFormField, ServicePricing, PlatformContent) use hard delete

### Pricing Security Fixes (Session 2026-04-03 Late)
- [x] **Server-side conditional logic evaluation** - `evaluate_conditional_logic_server_side()` mirrors JS logic
- [x] **Hidden field manipulation detection** - Rejects data for fields that should be hidden
- [x] **Hidden field logging** - Logs `HIDDEN_FIELD_MANIPULATION` events with severity HIGH
- [x] **max_selections field** - Added to `ServiceFormField` for multi-select security cap
- [x] **max_selections validation** - `validate_max_selections()` truncates excess selections
- [x] **11 new security tests** - Tests for conditional logic evaluation and max_selections

### Pricing Security Architecture
```
User submits form via curl (bypassing JS)
    ↓
validate_and_calculate_price()
    ↓
evaluate_conditional_logic_server_side()  ← NEW: evaluates visibility
    ↓
Only visible field values used for pricing calculation
    ↓
Hidden field data rejected + logged as SECURITY [HIDDEN_FIELD_MANIPULATION]
    ↓
validate_max_selections()  ← NEW: enforces selection limits
    ↓
calculate_cost_from_db() + apply_field_price_modifiers()
    ↓
Server price returned (authoritative)
```

### Potential Future Enhancements
1. **Milestone Celebration Animation**
   - When reaching 1000, 2000, etc. points
   - Currently: Notification only
   - Could add: Confetti animation on dashboard

2. **API Documentation**
   - REST API exists at `/api/`
   - No Swagger/OpenAPI documentation

---

## 6. FILES MODIFIED (ALL SESSIONS)

### Core App
| File | Changes | Session |
|------|---------|---------|
| `core/models.py` | Added ServiceFormField, ServicePricing, Request fields | Multiple |
| `core/workflow.py` | Added `_award_completion_points()`, role-aware notifications | Auto points |
| `core/pricing.py` | Dynamic pricing engine | Pricing migration |
| `core/services/ibtikar.py` | Service submission | Initial |
| `core/services/genoclab.py` | Service submission | Initial |
| `core/state_machine.py` | Workflow states | Initial |
| `core/pricing.py` | Fixed OVERRIDE pricing logic, discount stacking | Test coverage |
| `core/models.py` | Added SoftDeleteModel mixin for Service/Request | Soft delete |
| `core/models.py` | Added `max_selections` field to ServiceFormField | Pricing security |
| `core/pricing.py` | Added `evaluate_conditional_logic_server_side()`, `validate_max_selections()` | Pricing security |

### Accounts App
| File | Changes | Session |
|------|---------|---------|
| `accounts/models.py` | MemberProfile fields, `award_points()`, BadgeConfig integration | Rewards system |
| `accounts/models.py` | Removed BADGE_TIERS, display properties use BadgeConfig | Badge harmonisation |
| `accounts/models.py` | Added SoftDeleteUserManager, soft delete on User | Soft delete |
| `accounts/models.py` | Added PointsHistory unique constraint | Duplicate prevention |

### Tests App
| File | Purpose |
|------|---------|
| `tests/conftest.py` | pytest fixtures (UserFactory, MemberProfileFactory, etc.) |
| `tests/test_pricing.py` | Pricing engine tests (30 tests) - Including security tests |
| `tests/test_points.py` | Points & rewards tests (27 tests) - Fixed badge notification tests |
| `tests/test_workflow.py` | Workflow transitions tests (7 tests) |
| `tests/test_notifications.py` | Notification system tests (6 tests) |
| `tests/test_conditional_logic.py` | Conditional pricing tests (11 tests) |
| **Total: 84 tests** | All passing (100%) |

### Notifications App
| File | Changes | Session |
|------|---------|---------|
| `notifications/models.py` | `get_absolute_url()`, role-aware routing | Notification links |
| `notifications/services.py` | `_get_request_link_url()`, role-aware links | Notification links |

### Dashboard App
| File | Changes | Session |
|------|---------|---------|
| `dashboard/views/admin_ops.py` | Bulk actions, performance, CSV export | Admin ops |
| `dashboard/views/analyst.py` | Badge gallery, reward boxes, AJAX collect | Rewards UX |
| `dashboard/urls.py` | New routes for reward box collection | Various |

### Templates
| File | Changes | Session |
|------|---------|---------|
| `templates/dashboard/analyst/index.html` | Badge gallery, reward boxes, AJAX collect, history | Rewards UX |
| `templates/dashboard/admin_ops/index.html` | Activity log, performance | Admin ops |
| `templates/includes/notification_list.html` | SVG icons | Notifications |

### Documents App
| File | Changes | Session |
|------|---------|---------|
| `documents/pdf_generator_ibtikar.py` | PDF generation | Initial |
| `documents/pdf_generator_platform_note.py` | Platform note | Initial |
| `documents/pdf_generator_reception.py` | Reception form | Initial |
| `documents/pdf_generator_invoice.py` | Invoice | Initial |

---

## 7. MIGRATIONS

### Applied Migrations (in order)
```
accounts:
  0001_initial
  0002_alter_user_managers
  0003_user_ibtikar_id
  0004_user_avatar_user_last_seen
  0005_must_change_password
  0006_add_student_level_other
  0007_add_milestone_tracking
  0008_add_user_position
  0009_alter_user_laboratory_alter_user_position
  0010_update_position_choices
  0011_add_reward_fields_to_memberprofile
  0012_user_address_user_country_user_faculty_and_more
  0013_add_badge_and_reward_tracking
  0014_add_soft_delete_and_points_constraint  # Soft delete fields, unique constraint

core:
  0001_initial
  0002_revenuearchive_message
  0003_invoice_payment_status_alter_request_status_and_more
  0004_quote_detail_field
  0005_alt_date_fields
  0006_ibtikar_workflow_states
  0007_add_service_pricing
  0008_request_order_file_request_order_uploaded_at_and_more
  0009_citation_acknowledged
  0010_add_performance_indexes
  0011_remove_invoice_invoice_paystat_idx_and_more
  0012_add_generated_ibtikar_form
  0013_add_report_version
  0014_citation_accepted_fields
  0015_add_generated_pdfs
  0016_add_hidden_from_archive
  0017_add_invoice_fields_and_payment_settings
  0018_add_pdf_form_fields
  0019_populate_service_form_fields
  0020_alter_service_options_alter_serviceformfield_options_and_more
  0021_add_pi_fields
  0022_extend_serviceformfield
  0023_add_field_channel_to_serviceformfield
  0024_add_pricing_fields_to_serviceformfield
  0025_request_ibtikar_id_request_tracking_number_and_more
  0026_add_accepted_declined_statuses
  0027_serviceformfield_conditional_logic
  0028_serviceformfield_option_pricing
  0029_add_completion_points_awarded
  0030_add_soft_delete  # Soft delete on Service and Request
  0031_add_max_selections_field  # max_selections for multi-select security

notifications:
  0001_initial
  0002_add_notification_deep_linking
  0003_add_document_ready_type
  0004_alter_notification_notification_type  # Notification type field update
```

---

## 8. HOW TO RUN

### Prerequisites
- Python 3.12+
- PostgreSQL database (or SQLite for local dev)
- `.env` file with database credentials

### Setup Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Verify system
python manage.py check

# Create superuser (if needed)
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Environment Variables (`.env`)
```env
DEBUG=True
SECRET_KEY=your-secret-key
DATABASE_URL=postgres://user:password@host:5432/plagenor
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=user@example.com
EMAIL_HOST_PASSWORD=password
DEFAULT_FROM_EMAIL=PLAGENOR <noreply@plagenor.essbo.dz>
BASE_URL=http://localhost:8000
SUPPORT_EMAIL=contact@plagenor.essbo.dz
```

### Key URLs
| URL | Purpose |
|-----|---------|
| `/admin/` | Django admin |
| `/dashboard/home/` | Superadmin dashboard |
| `/dashboard/ops/` | Admin Ops |
| `/dashboard/analyst/` | Member dashboard |
| `/dashboard/requester/` | IBTIKAR requester |
| `/dashboard/client/` | GENOCLAB client |
| `/api/v1/services/` | REST API - Services list |
| `/api/v1/requests/` | REST API - Requests list |
| `/api/docs/` | Swagger/OpenAPI documentation |
| `/api/redoc/` | ReDoc API documentation |

---

## 9. TESTING CHECKLIST

### Core Functionality
- [ ] Create a new service with form fields
- [ ] Add pricing configuration
- [ ] Test conditional logic (show field based on another)
- [ ] Submit IBTIKAR request → check workflow
- [ ] Submit GENOCLAB request → check workflow

### Points & Rewards System
- [ ] Award points to member → verify total increases
- [ ] Close IBTIKAR request → verify +50 pts awarded
- [ ] Archive GENOCLAB request → verify +50 pts awarded
- [ ] Close already-closed request → verify no double award
- [ ] Reach 1000 pts → verify milestone notification
- [ ] Reach 2000 pts → verify reward box unlocked
- [ ] Collect reward box → verify counter updates

### Badge Gallery
- [ ] View member with 1500 pts → Bronze greyed, Silver colored
- [ ] View member with 3500 pts → Bronze, Silver, Gold colored; Platinum greyed
- [ ] Current level badge has "Actuel" label
- [ ] All 10 badge shapes are visually distinct

### Notifications
- [ ] Workflow transition → notification created
- [ ] Click notification → lands on correct page
- [ ] Role-based routing works (admin vs member vs client)

### PDF Generation
- [ ] Submit IBTIKAR request → form generated
- [ ] Appointment confirmed → reception form generated
- [ ] Close IBTIKAR → platform note generated

### Admin Operations
- [ ] Bulk assign requests to member
- [ ] Bulk transition requests
- [ ] CSV export works
- [ ] Activity log shows entries

---

## 10. WARNINGS / GOTCHAS

### Legacy Fields (DO NOT DELETE)
- `Service.ibtikar_price` — fallback price, still referenced in some templates
- `Service.genoclab_price` — fallback price, still referenced
- `services_registry/*.yaml` — YAML archives kept for reference, not used in code

### Known Limitations
1. **IBTIKAR budget**: Budget validation happens client-side in forms; server-side validation exists but may need enhancement
2. **YAML pricing**: Old YAML-based pricing is NOT used; all pricing comes from ServicePricing model
3. **Email**: Requires external SMTP server; dev mode uses console backend
4. **Guest tracking**: Guest token-based tracking exists but limited functionality

### Important Code Locations
| Feature | File | Key Function |
|---------|------|--------------|
| Workflow transitions | `core/workflow.py` | `transition()` |
| Price calculation | `core/pricing.py` | `calculate_price()` |
| Award points | `accounts/models.py` | `award_points()` |
| Auto completion pts | `core/workflow.py` | `_award_completion_points()` |
| Notification routing | `notifications/models.py` | `get_absolute_url()` |
| Badge calculation | `accounts/models.py` | `_calculate_badge_level()` |
| State machine | `core/state_machine.py` | `validate_transition()` |

### Database Considerations
- PostgreSQL recommended for production
- SQLite works for development
- Large file uploads stored in `media/` directory
- PDFs generated dynamically, not stored (except explicit saves)

### Git History
Latest commits:
```
358b295 fix: Badge gallery unlock colors and unique shapes
1aae35c feat: Auto 50 points on service completion + notification links fix
4372b49 PLAGENOR 4.0: Complete implementation - Notifications, Rewards UX...
```

---

## APPENDIX: BADGE LEVEL REFERENCE

| Level | Badge Name | Points Required | Threshold Check |
|-------|------------|-----------------|-----------------|
| 1 | Bronze | 0 pts | `milestone_level >= 1` |
| 2 | Silver | 1,000 pts | `milestone_level >= 2` |
| 3 | Gold | 2,000 pts | `milestone_level >= 3` |
| 4 | Platinum | 3,000 pts | `milestone_level >= 4` |
| 5 | Diamond | 4,000 pts | `milestone_level >= 5` |
| 6 | Master | 5,000 pts | `milestone_level >= 6` |
| 7 | Grand Master | 6,000 pts | `milestone_level >= 7` |
| 8 | Elite | 7,000 pts | `milestone_level >= 8` |
| 9 | Champion | 8,000 pts | `milestone_level >= 9` |
| 10 | Legend | 9,000 pts | `milestone_level >= 10` |

> **Note**: Badge level calculation in `_calculate_badge_level()` only goes to 5 (Diamond).
> The 10-level gallery uses `milestone_level` instead.

---

## APPENDIX: WORKFLOW STATES

### IBTIKAR Channel
```
DRAFT → SUBMITTED → VALIDATION_PEDAGOGIQUE → VALIDATION_FINANCE →
PLATFORM_NOTE_GENERATED → IBTIKAR_SUBMISSION_PENDING → IBTIKAR_CODE_SUBMITTED →
ASSIGNED → PENDING_ACCEPTANCE → ACCEPTED → APPOINTMENT_PROPOSED →
APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED → ANALYSIS_STARTED →
ANALYSIS_FINISHED → REPORT_UPLOADED → REPORT_VALIDATED →
SENT_TO_REQUESTER → COMPLETED → CLOSED
```

### GENOCLAB Channel
```
REQUEST_CREATED → QUOTE_DRAFT → QUOTE_SENT → QUOTE_VALIDATED_BY_CLIENT →
ORDER_UPLOADED → ASSIGNED → PENDING_ACCEPTANCE → ACCEPTED →
APPOINTMENT_PROPOSED → APPOINTMENT_CONFIRMED → SAMPLE_RECEIVED →
ANALYSIS_STARTED → ANALYSIS_FINISHED → PAYMENT_PENDING → PAYMENT_UPLOADED →
PAYMENT_CONFIRMED → REPORT_UPLOADED → REPORT_VALIDATED →
SENT_TO_CLIENT → COMPLETED → ARCHIVED
```

---

*Last Updated: 2026-04-03*
*Maintained by: Kilo AI (final session)*
