# PLAGENOR 4.0 — HANDOVER (cross-chat continuity)

> **Read this first when resuming in a new chat.** It is self-contained: it
> describes the project, the live deployment, what was done, what remains, and
> the operational gotchas (push path, signing, DB, secrets). Pair it with
> `project_memory.md` (per-feature changelog) for finer detail.

_Last updated: 2026-07-25._

> **État actuel en une ligne :** PR #1 fusionnée → **`main` est la branche de
> référence** (145 commits, CI verte, 102 tests). Cible d'hébergement :
> **Railway** (voir `deploy_railway.md`). Render reste l'ancien host.

---

## 1. What the project is

**PLAGENOR 4.0** — a Django platform for the **ESSBO** (École Supérieure en
Sciences Biologiques d'Oran), an **independent** institution (NOT affiliated
with "Université d'Oran" / "University of Oran" — that branding was scrubbed
everywhere, including a DB data migration).

Two operational channels:
- **IBTIKAR** — academic/DGRSDT (students & researchers, virtual budget).
- **GENOCLAB** — commercial (external clients, real invoicing).

Roles (`accounts.User.role`, table `users`):
`SUPER_ADMIN`, `PLATFORM_ADMIN`, `MEMBER` (analyst/operator), `FINANCE`,
`REQUESTER` (IBTIKAR), `CLIENT` (GENOCLAB).

Stack: **Django 5.1**, python-docx, openpyxl, dj-database-url, psycopg2-binary,
whitenoise, gunicorn. i18n FR/EN/AR (modeltranslation `_en`/`_ar` columns,
RTL via logical CSS properties). Emojis via **Twemoji 15.1** CDN.

---

## 2. Live deployment (current state)

### 2.a Cible actuelle — Railway (à déployer par l'utilisateur)

- Guide pas à pas : **`deploy_railway.md`** (à suivre tel quel).
- Branche à déployer : **`main`**. Config au repo : `railway.json`
  (build + `preDeployCommand` = migrate/seed/ensure_superuser + gunicorn +
  healthcheck `/healthz`) et `nixpacks.toml` (install + collectstatic).
- **Postgres géré par Railway** (add-on) référencé via `${{Postgres.DATABASE_URL}}` :
  c'est ce qui met fin définitivement aux comptes qui disparaissaient.
- Médias : on garde **Supabase Storage** (gratuit) via les `SUPABASE_S3_*`.
- `PORT` et `RAILWAY_PUBLIC_DOMAIN` sont fournis par Railway ; `settings.py`
  en dérive seul `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
- Garde-fou : sans `DATABASE_URL` en prod, l'app **refuse de démarrer**
  (`ImproperlyConfigured`) au lieu de retomber sur un SQLite éphémère.

### 2.b Ancien host — Render (historique)

- **Host:** Render.com, **free** web service named `plagenor`, **region
  Frankfurt** (moved from Oregon to be near the DB). Blueprint = `render.yaml`.
- **URL:** https://plagenor.onrender.com
- **Database:** **Supabase Postgres** (free), via `DATABASE_URL` (pooler;
  recommended **session pooler port 5432**, password char `@` encoded as `%40`).
  Schema + migrations already applied (so `migrate` on deploy is a fast no-op).
- **Deploy pipeline:** push to branch `claude/great-newton-6Ce7v` → Render
  builds via `./build.sh` → `gunicorn plagenor.wsgi`.
- `build.sh` runs: `pip install` → `collectstatic` → `migrate` →
  `seed_services` → `seed_content` → `ensure_superuser` (all idempotent).
- **Render free tier has NO shell** (upgrade-gated) and **no persistent disk**
  (media is ephemeral — see Pending).

### Env vars on Render
- Set automatically by blueprint: `DEBUG=false`, `SECRET_KEY` (generated),
  `PYTHON_VERSION=3.11.9`.
- **You paste:** `DATABASE_URL` (Supabase string).
- Leave empty (auto-derived in `settings.py`): `ALLOWED_HOSTS`,
  `CSRF_TRUSTED_ORIGINS` (the `*.onrender.com` host + https origin are added
  automatically), `SMTP_*` (optional email).
- **To create the admin** (see §4): add `DJANGO_SUPERUSER_USERNAME`,
  `DJANGO_SUPERUSER_PASSWORD`, `DJANGO_SUPERUSER_EMAIL` → redeploy.

---

## 3. Git state & how to push (IMPORTANT operational gotchas)

- **Branche de référence : `main`** (PR #1 fusionnée le 2026-07-25, merge
  `6d041b3`, 145 commits). `claude/great-newton-6Ce7v` était la branche de
  travail ; elle est désormais **entièrement contenue dans `main`** (0 commit
  non fusionné). Le travail futur repart de `main` par PR relue + CI verte.
- **Repo:** `Midotech31/PLAGENOR_4.0_DJANGO` (was renamed from
  `midotech31/plagenor_4.0_django`; old name still redirects).
- Derniers travaux avant la fusion (du plus récent) :
  - `f89e763` docs: deploy from main on Railway
  - `e11c2c0` fix: **double débit budget IBTIKAR** + cap 2FA + fuite erreurs DB
  - `e651e9c` build: suppression de toute dépendance CDN externe
  - `b9aa3df` style: police arabe Tajawal
  - `1a70825` i18n: 172 chaînes non/mal traduites corrigées

### Création/fusion de PR : bloquée côté plateforme
- `create_pull_request` / `merge_pull_request` renvoient **403 « GitHub access
  is not enabled for this session »** : c'est une restriction de l'intégration,
  **pas** un problème de token. PR #1 a donc été créée et fusionnée
  **manuellement par l'utilisateur**. Prévoir la même chose la prochaine fois.

### PUSH BLOCKER (read before trying to push)
- The agent proxy push **and** the GitHub MCP `push_files`/tree both return
  **403** in this environment. They do NOT work.
- **Only working push path:** a one-shot HTTPS push with a user-provided PAT:
  ```
  git push "https://x-access-token:<PAT>@github.com/Midotech31/PLAGENOR_4.0_DJANGO.git" <branche>
  ```
  (Un PAT sans le scope `workflow` **ne peut pas** pousser un changement dans
  `.github/workflows/` — le push est rejeté entièrement.)
  Never store the token in `.git/config`; use it inline once, then ask the user
  to revoke it. (The local `origin` ref goes stale because direct-URL pushes
  don't update it — harmless; `git fetch <url> <branch>` to refresh if needed.)

### Commit-signing hook (expected, NOT actionable)
- A stop hook flags every commit as **Unverified**. The committer email is
  already correct (`Claude <noreply@anthropic.com>`); the only missing thing is
  a **GPG/SSH signature**. The configured SSH signing key
  `/home/claude/.ssh/commit_signing_key.pub` is an **empty 0-byte file with no
  private key**, so signing is **impossible** here. This is **cosmetic** (just
  GitHub's "Verified" badge) and has **zero functional impact**. Do not loop on
  it; do not rewrite history trying to fix it.

---

## 4. Creating the admin account (no shell available)

Because Render free has no shell, `createsuperuser` can't be run interactively.
Solution already shipped (commit `7fccc64`):

- `core/management/commands/ensure_superuser.py` — idempotent. Reads
  `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` /
  `DJANGO_SUPERUSER_EMAIL`. No-op if unset. Creates a `SUPER_ADMIN`; if the
  user exists it guarantees `is_superuser/is_staff/role=SUPER_ADMIN` and only
  resets the password when run with `--update-password`.
- Called from `build.sh` on every deploy.

**To create the admin:** add the 3 env vars on Render → redeploy → test
`https://plagenor.onrender.com/admin/`. Optionally remove
`DJANGO_SUPERUSER_PASSWORD` afterwards.

Alternative (no redeploy): insert directly via Supabase SQL Editor into table
`users` with a Django-hashed password (`make_password`).

---

## 5. Work completed in recent sessions (high-level)

All shipped & pushed. See `project_memory.md` for the detailed per-feature log.

- **Deployment**: Render (Frankfurt) + Supabase fully wired. `render.yaml`,
  `build.sh`, `Procfile`, `runtime.txt`. `settings.py` auto-derives
  `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` (else prod login/registration = 403).
- **`ensure_superuser`** command (shell-less admin creation).
- **Smartphone responsiveness** (`45cb1a4`, CSS now `?v=8`):
  - Fixed `.main-content` keeping the desktop `max-width` at ≤768px (content
    was squeezed to ~500px with a dead side gap).
  - Global anti-horizontal-scroll guard (`overflow-x: clip` + `overflow-wrap`).
  - iOS no-zoom inputs (16px at ≤768px).
  - Topbar declutter, 44px tap targets, dropdown/modal width caps.
  - Tables: momentum scroll + wrapped the wide unwrapped ones.
  - Public nav links scroll horizontally instead of being hidden at 480px.
- **Public top-nav auth CTAs**: added **Sign in (ghost)** + **Sign up
  (solid)** pair, both always visible. Fixed a **specificity bug** where
  `.public-nav .nav-links a` (grey) overrode the solid button's white text
  (was grey-on-indigo / unreadable) — selectors now scoped through
  `.public-nav .nav-links a.nav-cta-*`.
- Earlier (prior sessions, all live): report **citation-clause gate** hardened
  (requester IBTIKAR must sign before download; client GENOCLAB downloads
  directly; analyst/admin exempt from clause AND rating; both land on a
  persuasive **rating page** after download that nudges 5★ implicitly);
  **anonymity** (requester/client never see analyst identity);
  **appointment-confirmation** idempotent flow; **document generators** audit
  fixes (French params, DA currency, sample summary, admin reprice note);
  **configurable bilan Excel** (12 dimensions + charts); **notification context
  icons**; **Twemoji**; **University-of-Oran branding scrub** (incl. DB
  migration `core/0021`).

---

## 6. Pending / next steps

**User actions (web UIs — agent cannot do these):**
1. **Finish admin creation**: add `DJANGO_SUPERUSER_*` env vars on Render →
   redeploy → verify `/admin/`.
2. **Verify the Sign up fix is live**: ensure Render deployed commit `e83c6ec`
   (CSS `?v=8`); hard-refresh (`Ctrl+Shift+R`). The screenshot bug (faint
   "Sign up" text) is fixed in code but needs the new build to be live.

**Security (user must do — flagged repeatedly):**
- 🔴 **Revoke the GitHub PAT** used for pushes (`ghp_aDMc…`).
- 🔴 **Rotate the Supabase DB password** (appeared in plaintext in chat).
- 🟠 Revoke older PATs exposed in earlier transcripts.
- (Earlier finding) `.env.supabase` had been tracked with a real cred — verify
  it's gitignored / history handled.

**Done — media persistence (Supabase Storage):**
- Uploaded media (report PDFs, order/payment files, avatars, gift/service
  images, DOCX templates) now persists on **Supabase Storage** (S3-compatible)
  instead of Render's ephemeral disk. Falls back to the local filesystem in dev
  when the `SUPABASE_S3_*` env vars are absent. See §9 for the one-time setup.
- Files are still served **through Django** (URLs stay `/media/<name>`), so the
  IBTIKAR citation gate keeps working and the bucket stays private. This also
  fixed a latent prod bug: non-report media (avatars, order/receipt files) was
  never web-served in production (the old `static()` media handler only ran
  under `DEBUG`).

**Registration enhancements (done):**
- `User.organization_type` (Académique/Entreprise/Laboratoire/Particulier/Autre)
  + `organization_type_other` free text + `country` (full ISO 3166 list,
  `accounts/countries.py`, default `DZ`). Added to the account registration
  form AND the public guest service form. Migration `accounts/0010`.

**i18n (done):** EN + AR catalogs fully translated (no empty `msgstr`); FR is
the source language. After adding UI strings, run
`python manage.py makemessages -l en -l ar -l fr --no-location`, fill the new
entries, then `compilemessages`. The `.mo` files are committed.

**In progress — admin "edit all app elements" (Full visual CMS):**
- User wants admins to edit every text/label/option app-wide. A
  `PlatformContent` key-value CMS already exists (Content tab). This is a large,
  multi-step effort — being built incrementally.

**Offered, not started (optional improvements):**
- Expose `organization_type` / `country` in the profile editor (the profile
  view currently only updates `organization`).
- **PDF generation**: a Dockerfile with **LibreOffice** headless if server-side
  DOCX→PDF is needed in prod.
- On-demand generated docs (devis/facture/note/bilan) still write to the local
  ephemeral disk and are streamed once — fine, they are regenerated on demand.

---

## 7. Conventions & verify commands

- French UI everywhere. No emojis in code/commits. No gratuitous refactors.
- Do NOT put the model identifier in commits/PRs/code (chat only).
- Multi-line `{# #}` Django comments render as literal text — keep template
  comments **single-line**.
- After CSS/template changes, **bump the cache-buster** `?v=N` in `base.html`
  AND `base_public.html` (currently `v=8`).
- **Verify before pushing:**
  ```
  SECRET_KEY=dummy DEBUG=true python manage.py check
  ```
  Template compile check: load via `django.template.loader.get_template`.
  CSS sanity: brace count balanced.
- Default dev DB is `data/plagenor.db` (gitignored), **not** `db.sqlite3`.

---

## 8. Key files map

- Deploy: `render.yaml`, `build.sh`, `Procfile`, `runtime.txt`,
  `plagenor/settings.py` (ALLOWED_HOSTS / CSRF auto-derivation).
- Admin bootstrap: `core/management/commands/ensure_superuser.py`.
- Styles: `static/css/main.css` (single 2200-line stylesheet; responsive block
  near the `@media` queries ~line 1790+; nav CTAs near `.public-nav`).
- Public shell: `templates/base_public.html` (nav with Sign in/Sign up).
  App shell: `templates/base.html` (sidebar + topbar).
- Reports gating + media serving: `dashboard/views/report.py`
  (`_is_internal_staff`, `protected_report_media`, `serve_media`).
- Media storage backend: `plagenor/storages.py` (`SupabaseMediaStorage`);
  config in `plagenor/settings.py` (`STORAGES` / `USE_SUPABASE_STORAGE`).
- Appointment flow: `dashboard/utils.py` (`confirm_appointment_flow`).
- Bilan: `core/bilan.py` + `documents/stats_excel.py`.
- Generators: `documents/generators.py`.
- Per-feature changelog: `project_memory.md`.

---

## 9. Supabase Storage setup (one-time, for persistent media)

Without this, `SUPABASE_S3_*` is unset → the app uses the local disk (fine for
dev, ephemeral on Render so reports/uploads vanish on restart).

1. **Supabase dashboard → Storage → New bucket**: name it `media`, keep it
   **Private** (do NOT make it public — the citation gate relies on Django
   serving the files, and the bucket should not be world-readable).
2. **Project Settings → Storage → S3 connection**: copy the **endpoint URL**
   (`https://<project-ref>.supabase.co/storage/v1/s3`) and **region**, then
   **generate an S3 access key** (gives an access key id + secret).
3. **On Render → Environment**, add:
   - `SUPABASE_S3_ENDPOINT` = the endpoint URL above
   - `SUPABASE_S3_REGION` = the region (e.g. `eu-central-1`)
   - `SUPABASE_S3_ACCESS_KEY_ID` = the generated key id
   - `SUPABASE_S3_SECRET_ACCESS_KEY` = the generated secret
   - `SUPABASE_S3_BUCKET` = `media` (optional; defaults to `media`)
4. Redeploy. New uploads land in Supabase Storage. **Existing files already on
   the ephemeral disk are not migrated** — re-upload any that must persist
   (reports are regenerated/re-uploaded by analysts anyway).

Deps added: `django-storages==1.14.4` + `boto3` (in `requirements.txt`).
