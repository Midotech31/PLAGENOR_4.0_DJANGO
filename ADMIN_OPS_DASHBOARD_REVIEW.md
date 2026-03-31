# PLAGENOR 4.0 — admin_ops Dashboard End-to-End Review

**Review Date:** 2026-03-31  
**Reviewer:** Kilo Code  
**Role Tested:** PLATFORM_ADMIN / admin_ops  

---

## Executive Summary

The admin_ops dashboard provides operational oversight for platform administrators managing IBTIKAR (academic research) and GENOCLAB (commercial genomics) request lifecycles. The dashboard is **substantially functional** but has critical gaps in user oversight, activity logging, and some UI inconsistencies that should be addressed for production readiness.

---

## Feature-by-Feature Assessment

### 1. ✅ Request Management

**Status: FULLY FUNCTIONAL**

| Capability | Implementation | Status |
|------------|----------------|--------|
| View all requests | [`admin_ops.index()`](dashboard/views/admin_ops.py:28) with paginated lists | ✅ |
| Filter by channel | IBTIKAR / GENOCLAB filter via GET params | ✅ |
| Filter by status | Full status filter dropdown | ✅ |
| Search requests | `display_id` and `title` search | ✅ |
| Request lifecycle transitions | [`transition_request()`](dashboard/views/admin_ops.py:232) via state machine | ✅ |
| View request details | [`request_detail()`](dashboard/views/admin_ops.py:202) with full data display | ✅ |
| Assign to analysts | [`assign_request()`](dashboard/views/admin_ops.py:247) with load balancing | ✅ |
| Track appointment dates | [`modify_appointment()`](dashboard/views/admin_ops.py:346) | ✅ |

**Tabs Provided:**
- Pending (validation queue)
- All Requests (full list)
- Assignment panel
- Budget overview
- Performance/Points
- Ratings/Reviews
- Reports awaiting review

**Shallow Areas:**
- ❌ No bulk actions (e.g., bulk assign, bulk transition) — currently requires individual operations
- ❌ No export functionality for request lists (CSV/Excel)

---

### 2. ⚠️ User Oversight

**Status: PARTIAL — LIMITED SCOPE**

The admin_ops dashboard **does not have a dedicated user management interface**. User oversight is limited to:

| View | Location | Status |
|------|----------|--------|
| Requester profile | [`request_detail.html`](templates/dashboard/admin_ops/request_detail.html:474-484) (embedded in request) | ✅ |
| Requester submission history | **Not available** in request detail | ❌ |
| Account status (active/inactive) | Not visible in admin_ops | ❌ |
| List all students/clients | **Not available** | ❌ |
| Organization/lab details | ✅ Visible in request context | ✅ |

**Issues:**
- [`request_detail()`](dashboard/views/admin_ops.py:202) shows requester info but does NOT query their submission history
- No URL endpoint for `/ops/users/` or similar
- The [`MemberProfile`](accounts/models.py) data (analysts) is shown in Performance tab, but regular users are not

**Recommendation:** Add a user oversight tab with:
1. List of all registered users (requesters, clients)
2. Their submission counts and account status
3. Links to their request history
4. Ability to toggle account active/inactive status (delegates to superadmin)

---

### 3. ✅ Report Handling

**Status: FULLY FUNCTIONAL**

| Action | Implementation | Status |
|--------|----------------|--------|
| View reports awaiting review | `review_requests` queryset | ✅ |
| Download uploaded report | `report_file` link in template | ✅ |
| Validate report | [`transition(req, 'REPORT_VALIDATED')`](dashboard/views/admin_ops.py:369) | ✅ |
| Send back for revision | [`transition(req, 'ANALYSIS_STARTED')`](dashboard/views/admin_ops.py:378) with notes | ✅ |
| Add revision notes | `admin_revision_notes` field | ✅ |
| Notify analyst of revision | [`Notification`](notifications/services.py:105-120) creation | ✅ |

**Dedicated Review Page:** [`report_review.html`](templates/dashboard/admin_ops/report_review.html) provides focused interface for report validation.

**Issue:** No ability to **upload a report directly** from admin_ops — reports must be uploaded by the analyst. This may be intentional (separation of duties), but could be added for emergency cases.

---

### 4. ⚠️ Notifications

**Status: MOSTLY FUNCTIONAL — NO DEDICATED PANEL**

| Component | Implementation | Status |
|-----------|----------------|--------|
| Notifications created on actions | [`notifications/services.py`](notifications/services.py) | ✅ |
| Admin receives assignment notifications | ✅ Via `notify_workflow_transition()` | ✅ |
| Admin receives payment confirmations | ✅ | ✅ |
| Notification deep linking | [`link_url`, `action_url`](notifications/models.py:22-26) fields | ✅ |
| **Notification bell in UI** | **Not present in admin_ops templates** | ❌ |
| **Mark notifications read** | **Not accessible in admin_ops** | ❌ |

**Issue:** The admin_ops template does NOT include a notification bell/panel. Notifications are created in the backend but the admin has no UI to view or manage them.

**Recommendation:** Add notification bell in the topbar or as a sidebar widget:
```html
<a href="#" class="notification-bell" data-count="{{ unread_count }}">
    <svg>...</svg>
</a>
```

---

### 5. ✅ Performance and Points

**Status: FULLY FUNCTIONAL**

| Feature | Implementation | Status |
|---------|----------------|--------|
| View all member rankings | [`all_members_ranked`](dashboard/views/admin_ops.py:124) | ✅ |
| Productivity score display | `productivity_score` with progress bar | ✅ |
| Points balance display | `total_points` | ✅ |
| Award points to members | [`award_points()`](dashboard/views/admin_ops.py:277) | ✅ |
| Send cheers/encouragements | [`send_cheer()`](dashboard/views/admin_ops.py:330) | ✅ |
| Upload gift rewards | [`upload_gift()`](dashboard/views/admin_ops.py:307) | ✅ |
| Auto-unlock gift at 100 pts | [`gift_unlocked`](dashboard/views/admin_ops.py:288) logic | ✅ |
| Load balancing indicators | `current_load` / `max_load` | ✅ |

**Visual:** The performance tab includes rank badges (🥇🥈🥉), avatars, progress bars, and inline forms for awarding points/cheers.

**Issues:**
- Points awarding requires manual form submission — no AJAX
- No historical points chart or trends
- Gift upload only works if gift is already unlocked (100 pts threshold)

---

### 6. ❌ Activity Logs

**Status: MISSING — CRITICAL GAP**

The admin_ops dashboard **does not have a dedicated activity log/audit trail view**.

| Expected Feature | Status |
|------------------|--------|
| View all admin actions | ❌ Not available in admin_ops |
| Audit log of transitions | ⚠️ Only visible per-request in `RequestHistory` |
| Audit log of cost adjustments | ✅ Logged via [`log_action()`](core/audit.py:12) but not viewable |
| Global activity stream | ❌ Not available |

**Comparison with superadmin:**
- [`superadmin.audit_log()`](dashboard/views/superadmin.py:367) exists for SUPER_ADMIN role
- PLATFORM_ADMIN does **not** have access to this view (protected by `@superadmin_required`)

**Recommendation:** Either:
1. Create a simplified audit log view for PLATFORM_ADMIN showing only request-related actions
2. Or grant PLATFORM_ADMIN access to the existing `audit_log` view

```python
# In urls.py - add route accessible to admin_ops
path('ops/audit/', admin_ops.audit_log, name='admin_audit'),
```

---

### 7. ✅ Dashboard KPIs

**Status: FULLY FUNCTIONAL**

| KPI | Implementation | Status |
|-----|----------------|--------|
| Total requests | [`total_requests`](dashboard/views/admin_ops.py:33) | ✅ |
| Pending requests | [`pending_count`](dashboard/views/admin_ops.py:35) | ✅ |
| IBTIKAR count | [`ibtikar_count`](dashboard/views/admin_ops.py:39) | ✅ |
| GENOCLAB count | [`genoclab_count`](dashboard/views/admin_ops.py:40) | ✅ |
| Completed count | [`completed_count`](dashboard/views/admin_ops.py:41) | ✅ |
| Budget IBTIKAR (virtual) | [`ibtikar_budget`](dashboard/views/admin_ops.py:134) | ✅ |
| Revenue GENOCLAB (real) | [`genoclab_revenue`](dashboard/views/admin_ops.py:135) | ✅ |
| Average rating | [`avg_rating`](dashboard/views/admin_ops.py:140) | ✅ |
| Total ratings count | [`total_ratings`](dashboard/views/admin_ops.py:141) | ✅ |

**Real-time:** KPIs are calculated on each page load (no caching layer, but acceptable for admin use).

**Issues:**
- KPIs do not include **average turnaround time**
- No **overdue request alerts** (requests stuck in a status for too long)
- No **channel-specific pending counts**

---

### 8. ⚠️ Bilingual Support (FR/EN)

**Status: PARTIAL — INCONSISTENT**

| Area | French | English | Status |
|------|--------|---------|--------|
| Core labels | ✅ | ✅ | Working |
| Status transitions | ✅ | ⚠️ | Some `# fuzzy` entries |
| Error messages | ⚠️ | ❌ | Hardcoded in French |
| Button labels | ✅ | ✅ | Using `{% trans %}` |
| Flash messages | ⚠️ | ❌ | Hardcoded French |

**Translation Gaps Found:**

1. **`locale/en/LC_MESSAGES/django.po`** has several `# fuzzy` entries:
   - Line 393-395: `Validation Pédagogique` — fuzzy
   - Line 407-408: `Validation Finance` — fuzzy
   - Line 418-419: `Valider rapport` — fuzzy
   - Line 433-434: `Envoyer devis` — fuzzy

2. **Hardcoded French in views:**
   - [`dashboard/views/admin_ops.py:240`](dashboard/views/admin_ops.py:240): `"Demande {req.display_id} transférée vers {to_status}."`
   - [`dashboard/views/admin_ops.py:253`](dashboard/views/admin_ops.py:253): `"Veuillez sélectionner un analyste."`
   - [`dashboard/views/admin_ops.py:260-262`](dashboard/views/admin_ops.py:260): French error messages

**Recommendation:** 
- Replace hardcoded French strings with `gettext()` / `_()` and add EN translations
- Mark `.po` files as complete and run `compilemessages`

---

## Summary of Issues

### Critical (Must Fix)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 1 | **No activity log view** | admin_ops | No audit trail for PLATFORM_ADMIN |
| 2 | **Hardcoded French messages** | [`admin_ops.py`](dashboard/views/admin_ops.py) | Cannot switch to English |
| 3 | **No notification panel** | templates | Admins cannot see received notifications |

### High Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 4 | **No user oversight tab** | admin_ops | Cannot view registered users or their history |
| 5 | **No request history per user** | request_detail | Cannot see user's past submissions |
| 6 | **Fuzzy translations** | locale files | English may show untranslated strings |

### Medium Priority

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| 7 | **No bulk actions** | request lists | Time-consuming for large volumes |
| 8 | **No request export** | admin_ops | Cannot export data to CSV/Excel |
| 9 | **No overdue alerts** | KPIs | Stuck requests not highlighted |
| 10 | **No AJAX for point awards** | performance tab | Page reload required |

---

## Recommendations

### 1. Add Activity Log View for admin_ops

```python
# dashboard/views/admin_ops.py
@admin_required
def audit_log(request):
    """Paginated audit log for PLATFORM_ADMIN (request-scoped only)."""
    from core.models import RequestHistory
    from dashboard.utils import paginate_queryset
    
    qs = RequestHistory.objects.select_related('request', 'actor').order_by('-created_at')
    paginator, history, _ = paginate_queryset(qs, request, per_page=50)
    
    return render(request, 'dashboard/admin_ops/audit_log.html', {
        'history': history,
        'paginator': paginator,
    })
```

### 2. Add Notification Bell to Sidebar

In [`templates/includes/sidebar.html`](templates/includes/sidebar.html), add after the Ops nav items:
```html
{% if request.user.role in 'SUPER_ADMIN,PLATFORM_ADMIN' %}
<a href="{% url 'notifications:mark_all_read' %}" class="nav-item" title="{% trans 'Notifications' %}">
    <svg>...</svg>
    {% if unread_notifications > 0 %}
    <span class="badge">{{ unread_notifications }}</span>
    {% endif %}
</a>
{% endif %}
```

### 3. Add User Oversight Tab

Create a new view in [`admin_ops.py`](dashboard/views/admin_ops.py):
```python
@admin_required
def users(request):
    """List all users with their request counts."""
    from accounts.models import User
    users = User.objects.annotate(
        request_count=Count('requests')
    ).order_by('-request_count')
    return render(request, 'dashboard/admin_ops/users.html', {'users': users})
```

### 4. Fix Hardcoded French Messages

Replace all hardcoded strings with translations:
```python
from django.utils.translation import gettext_lazy as _

messages.success(request, _("Demande %(id)s transférée.") % {'id': req.display_id})
```

### 5. Add Bulk Actions

In the template, add checkbox selection and bulk action form:
```html
<form method="post" action="{% url 'dashboard:admin_bulk_assign' %}">
    {% csrf_token %}
    <button type="submit" class="btn btn-primary">{% trans "Assigner sélectionnés" %}</button>
</form>
```

---

## Conclusion

The admin_ops dashboard provides **strong operational functionality** for managing the request lifecycle, analyst assignments, and performance tracking. The main gaps are:

1. **Audit trail** — critical for accountability
2. **Notification visibility** — admins need to see what they've been told
3. **User oversight** — visibility into registered users and their activity
4. **English translations** — incomplete i18n implementation

These issues are addressable without major architecture changes and should be prioritized before production deployment.
