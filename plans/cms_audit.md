# "Admin edits all app elements" — Audit & Build Plan

## What exists today

### Editable by admin now
- **`PlatformContent`** model `(key, lang, value)` — one row per key per
  language (FR/EN/AR). **158 keys seeded** (`seed_content.py`).
- Rendered via the **`{% cms 'key' 'default' %}`** template tag
  (`core/templatetags/cms.py`) with active-language lookup + fallback.
- **52 distinct `{% cms %}` keys** are actually wired into templates → those
  texts are already admin-editable.
- Content tab CRUD already works: `content_update` (create/update per lang) +
  `content_delete`. So the old audit note "no delete" is outdated.
- Other admin-managed data: **Services** (CRUD), **Techniques** (CRUD),
  **Payment methods**, **ServiceFormField** (per-service custom fields).

### NOT editable by admin (developer-only, via `.po` + redeploy)
- **~1931 `{% trans %}`** occurrences across templates — the bulk of UI
  labels, buttons, headings, help text. Editable only by changing the
  gettext catalogs and recompiling.
- The dropdown options just added — **org-type choices** and the **country
  list** — are Python constants (`accounts/countries.py`, model `choices`),
  not DB-backed.

## The core tension
A literal "edit **all** elements" means converting those ~1931 `{% trans %}`
strings into DB-backed `{% cms %}` keys. That is:
- **Enormous & risky** — touches every template, easy to introduce regressions.
- **Counterproductive** — it would dismantle the clean FR/EN/AR gettext
  workflow we just completed, and push translation work into the DB with no
  tooling.
**Recommendation: do NOT convert everything.** Instead make the
*content-bearing* surfaces fully editable and give admins a real manager.

## Known bug to fix along the way
`core/templatetags/cms.py` uses a module-level `_content_cache` dict that is
**never invalidated** → after an admin edits content, the change won't show
until the worker process restarts. Phase A must clear/scope this cache on save.

---

## Recommended phased plan

### Phase A — Unified Content Manager ✅ DONE (commit 4b51fa9)
Rebuild the Content tab into a proper editor:
- All keys listed with **FR / EN / AR side-by-side**, inline edit + save.
- **Search/filter** by key or text; flag "used" keys vs orphans.
- **Add new key**, **delete key (all langs)**, per-language edit.
- **Fix the cms cache** so edits appear immediately.
- Optional: "missing translation" highlighting per key.

### Phase B — Editable dropdown options (~0.5–1 session)
- Make **org-type** options admin-manageable (DB-backed list: label per lang,
  active flag, order). Registration/guest forms read from DB with the Python
  list as seed/fallback.
- **Country**: keep the 193-entry ISO list as a constant (stable data), but
  allow an admin "allowed countries" subset if desired.

### Phase C — Expand `{% cms %}` coverage on content pages (~1–2 sessions)
Convert remaining **hardcoded text on the public/informational surfaces** to
`{% cms %}` keys (seeded with current FR/EN/AR), so admins can edit them:
- `pages/` (home, about, services, help, contact, service_detail/landing),
  `accounts/login` + `register`, and the **email templates**.
- Explicitly **out of scope**: operational dashboard labels/buttons — those
  stay `{% trans %}` (developer-owned, fully translated already).

### Phase D — Inline click-to-edit overlay (optional, large)
Only if Phases A–C aren't enough. An "edit mode" that lets admins click any
`{% cms %}` element on a page and edit it in place (writes back by key). Large;
recommend deferring until the above is in use.

---

## Suggested order & deliverables
1. **Phase A** first — it's the backbone and immediately useful.
2. **Phase B** — unlocks the org-type request you just made, admin-side.
3. **Phase C** — broadens what "content" admins can actually reach.
4. **Phase D** — revisit only on demand.

Each phase ships independently (commit + push per step).
