# PLAGENOR 4.0 — Project Memory

## Current Objective
- Déploiement Render (région Frankfurt) + Supabase. App = https://plagenor.onrender.com.
- RESTE (action user, UI Render): ajouter DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL dans Environment -> redeploy cree l'admin via ensure_superuser. Puis tester /admin/.

## Phase 3 (fait, 87 tests, couverture 24%->34%)
- Tests vues: routeur + 6 dashboards par role (rendu 200 pour le bon role, 403 autres, redirect anon). Exerce toutes les vues d'atterrissage. 24%->27%.
- Tests generateurs DOCX: generate_invoice_document + generate_ibtikar_form rouverts avec python-docx (valide) + assertions valeurs (num facture, ligne, display_id); build_field_map. 27%->34%. Plancher CI remonte 22->30.
- Conformite donnees: page /confidentialite/ (textes editables CMS privacy_*), export /mes-donnees/export/ (JSON des donnees perso + demandes de l'utilisateur, login requis, ne renvoie QUE ses donnees). Lien footer. Suppression = via admin (note sur la page, pas de self-service destructif par design). 3 tests.
- NON FAIT volontairement (risque/stabilite): refactoring CSS/vues massif (touche du code qui marche, faible ROI). A faire progressivement si besoin.

## Phase 2 (fait, 77 tests)
- Tests E2E: parcours COMPLETS des 2 canaux via transition() avec acteurs role-appropries. IBTIKAR DRAFT->CLOSED (16 transitions) + assertion deduction budget une seule fois sur COMPLETED + 16 lignes RequestHistory. GENOCLAB REQUEST_CREATED->ARCHIVED (18). + test negatif (CLIENT ne peut pas faire l'etape finance).
- Couverture: coverage.py en CI, .coveragerc (omit migrations/tests/wsgi/settings), plancher fail_under=22 (actuel 24% du code non-test). A remonter au fil des tests, jamais baisser.
- Accessibilite (WCAG additif): skip-link + <main role=main> sur les 2 shells, :focus-visible global, .sr-only, nav aria-label. lang/dir deja dynamiques (RTL arabe). CSS ?v=9.
- 2FA TOTP OPT-IN (pyotp==2.10.0): champs User.totp_secret/totp_enabled (migration 0011). Login inchange pour non-inscrits; si totp_enabled -> gate verify apres mot de passe (session pending_2fa_user, pas de login tant que code non valide). Enrolement dans profil (QR via qrcode lib, secret en session jusqu'a confirmation). Desactivation self-service. RESET par Super Admin (users tab, pas de codes de secours par design). Vues: two_factor_verify/setup/disable + superadmin.reset_2fa. 7 tests.
- RESTE Phase 2 possible: remonter la couverture (tests generateurs docs, vues), audit accessibilite navigateur (axe/Lighthouse).

## Phase 1 durcissement production (fait, 67 tests)
- Mot de passe oublie: flux Django natif (token signe/expirable/usage unique) + templates FR styles + emails HTML/txt + lien sur login. Ne revele pas l'existence d'un email. Reset efface le verrou brute-force. Vues: ForgotPassword{,Done,Confirm,Complete}View. 3 tests.
- Healthchecks: /healthz (liveness, sans DB) + /readyz (readiness, SELECT 1 -> 503 si DB down), non-caches, sans auth. Pour monitoring uptime externe (UptimeRobot) + Render health check. plagenor/health.py. 2 tests.
- Rate limiting: core/ratelimit.py (sans dependance, fail-open, cache Django, par IP). Applique: login 20/5min, password-reset 5/h (anti email-bomb), guest_submit 10/h (anti spam). GET passent. Defense en profondeur sur le lockout par compte. 2 tests. NB: LocMemCache par worker -> limite effective xN workers (OK pour ralentir; Redis pour exactitude).
- Sauvegarde DB planifiee: .github/workflows/db-backup.yml (cron hebdo lundi 03h UTC + manuel). pg_dump 16 -> gzip -> artifact retenu 90j. Skip propre si secret DATABASE_URL absent. ACTION USER: ajouter le secret DATABASE_URL dans repo Settings -> Secrets Actions.
- RESTE Phase 1 (actions user): DATABASE_URL sur Render (bloquant deploiement), Render Starter, DSN Sentry, rotation PAT.

## Audit securite complet (fait, 60 tests)
- Couverture auth verifiee sur TOUTES les vues (decorateurs OK; non-decores = helpers prives ou fragment public voulu). Sequences atomiques OK, CSRF OK (1 exemption justifiee token), pas de SQL brut/eval.
- FIX HAUTE 1: serve_media servait orders/, payments/, documents/ (devis/factures generes a noms PREVISIBLES, IDs sequentiels) SANS authentification (regression de la route media/<path>). Nouvelle politique _may_access_media: avatars/+service_images/ publics; orders/+payments/ = staff OU proprietaire (Request.requester); tout le reste = staff uniquement. Refus = 404 (pas de fuite d'existence). 7 tests.
- FIX HAUTE 2: brute-force login inexistant — login_attempts/locked_until JAMAIS utilises. CustomLoginView: 5 echecs -> verrou 15 min; mot de passe correct pendant verrou refuse SANS compter comme echec; succes reinitialise compteurs. 5 tests (+override STORAGES en test car manifest whitenoise).
- FIX MOY: upload_report analyste sans validation d'extension -> whitelist .pdf/.doc/.docx (sinon .html stocke = XSS via protected_report_media inline). + download_report garde la vraie extension (nommait tout .pdf).
- FIX MIN: guest_submit whitelist serveur organization_type + country contre les choices du modele.
- NOTES (LOW, non corriges volontairement): as_json mark_safe + pricing_json|safe (donnees admin/YAML uniquement — surveiller si jamais exposees a saisie utilisateur); template_detail description|safe (page admin); check_email = enumeration d'emails (necessaire UX inscription); report_token sans expiration (capability link par design); HSTS_PRELOAD off.

## CRITICAL — disappearing accounts = ephemeral SQLite (fixed guard + user action)
- SYMPTOME: compte cree par superadmin -> disparait apres redeploy/restart/spin-down.
- CAUSE: settings.py tombait en fallback SQLite (disque Render EPHEMERE) quand DATABASE_URL absent -> toutes les donnees effacees a chaque restart. build.sh n'est PAS destructif (seeds idempotents); le probleme = DATABASE_URL non defini en prod.
- FIX CODE: settings.py refuse desormais de demarrer en prod (DEBUG=False) sans DATABASE_URL -> raise ImproperlyConfigured (comme SECRET_KEY). DEBUG=true garde SQLite local. Verifie: DEBUG=true sans URL=OK SQLite; DEBUG=false sans URL=raise; URL defini=Postgres. 49 tests OK.
- ACTION USER (resolution reelle): Render -> Environment -> definir DATABASE_URL = chaine Supabase (Session pooler port 5432, encoder @ -> %40) -> redeploy. Apres ca les comptes persistent. NB: les donnees SQLite ephemeres sont perdues; le schema Supabase sera (re)cree par migrate au deploy, admin recree par ensure_superuser.
- DIAGNOSTIC BONUS: avec ce guard, si le prochain deploy CRASH avec "DATABASE_URL is not set", la cause est confirmee; s'il deploie OK, DATABASE_URL etait deja defini et chercher ailleurs.

## Hardening round 2 — deferred items (done, user-authorized, 49 tests)
- Decimal money: compute_invoice_totals utilise Decimal + ROUND_HALF_UP (au lieu de float + round() banquier). Retourne des floats (JSON-safe pour quote_detail + DecimalField). Valeurs identiques sur les cas normaux; +tests (arrondi half-up 0.125->0.13, json-safe).
- Tests integration: deduct_ibtikar_balance (reduit le solde, plancher 0, skip si non-declare) + bout-en-bout: transition IBTIKAR SENT_TO_REQUESTER->COMPLETED deduit budget_amount du solde declare. Suite = 49 tests OK.
- Requirements epingles: dj-database-url==3.1.2, psycopg2-binary==2.9.10, boto3==1.43.36, sentry-sdk==2.63.0 (versions verifiees en local py3.11; psycopg2 = Postgres prod uniquement).
- Sentry: init garde dans settings.py, NO-OP sauf si SENTRY_DSN present (try/except, ne casse jamais le boot). Vars .env.example: SENTRY_DSN/ENVIRONMENT/TRACES_SAMPLE_RATE.
- Verifie: check OK (avec et sans DSN), 49 tests OK.

## Best-practices hardening (safe subset, done)
- CI reparee + VERTE: .github/workflows/django.yml (py3.11, trigger main+claude/**+PR, SECRET_KEY) -> run #9 success sur fc0a0d1. Tourne check + 43 tests a chaque push.
- Dependabot: .github/dependabot.yml (pip + github-actions, hebdo) -> PRs de MAJ deps/securite reviewables.
- pip-audit en CI: etape NON-bloquante (continue-on-error) -> visibilite CVE sans casser le build.
- SECURITY.md: politique secrets (jamais en commit/chat, rotation, push protection), config prod, bucket prive.
- PR ouverte great-newton -> main pour instaurer le flux review/CI-gate.
- VOLONTAIREMENT NON FAIT (risque core-logic / destabilisation, demande user): refactor Decimal des montants (compute_invoice_totals utilise float comme l'original) ; gating lint/pin requirements (risque CI rouge / build deploy) ; Sentry (dep runtime). A faire avec validation explicite + tests.
- ACTIONS USER (settings only): activer branch protection sur main (require Django CI), activer secret scanning+push protection, revoquer les PAT exposes, upgrade Render (cold start), upgrade hosting.

## Tests — first real coverage (done, 43 passing)
- Avant: 0 test. Maintenant 43 tests sur les chemins critiques (argent + securite). `python manage.py test` = 43 OK.
- core/tests.py: calculate_price (multiplier/pathogene/fixed + cas d'erreur), resolve_cost (fallback flat, normalisation canal), check_ibtikar_budget (non-declare bloque, dans/au-dessus du solde, cap depuis settings).
- core/tests.py (workflow): get_allowed_next_states, check_role_permission (super-admin bypass, mauvais role refuse, edge inconnu fail-closed), transition (succes maj statut+historique, cible invalide -> InvalidTransitionError, mauvais role -> AuthorizationError), force_transition (bypass graph, statut inconnu raise).
- core/tests.py (invoice): compute_invoice_totals (VAT 19%, lignes+frais, VAT 0, arrondi 2dp, vide). NOUVEAU helper core/financial.compute_invoice_totals extrait du calcul inline du devis (admin_ops.py) -> DRY + testable, math identique.
- dashboard/tests.py: gate rapport — IBTIKAR non-acquitte bloque, acquitte servi, GENOCLAB exempt; serve_media stream + 404.
- accounts/tests.py: inscription type "autre" exige detail, pays sauve, email duplique rejete.
- CI: .github/workflows/django.yml etait MORT (Python 3.7-3.9 vs Django 5.1 besoin 3.10+, trigger main seulement, pas de SECRET_KEY). Fix pret LOCALEMENT (py3.11, trigger claude/** + main + PR, SECRET_KEY CI) mais NON poussable: PAT sans scope `workflow` ET MCP app token 403. ACTION USER: appliquer le YAML via l'editeur web GitHub OU fournir un PAT avec scope workflow.

## CMS Phase A — Unified Content Manager (done, verified)
- Onglet Contenu superadmin refondu: 1 ligne par cle avec FR/EN/AR cote a cote, edites/enregistres ensemble. Formulaire "nouvelle entree" 3 langues, suppression par cle (toutes langues), recherche cle+valeurs, badge "langues manquantes".
- Backend: vue index groupe le contenu par cle (content_rows). Nouvelles vues content_save (upsert toutes langues) + content_delete_key. URLs content/save/ + content/delete-key/.
- BUG corrige: core/templatetags/cms.py avait un cache module jamais invalide -> edits invisibles jusqu'au restart worker. Maintenant TTL 60s + clear_cms_cache() appele sur chaque ecriture (update/save/delete).
- Verifie: check OK, template compile, test fonctionnel (cache stale->fresh apres clear; save-all ecrit 3 langues; delete-key supprime tout).
- Plan complet: plans/cms_audit.md. Reste: Phase B (options dropdown editables), Phase C (etendre {% cms %} aux pages contenu), Phase D (overlay click-to-edit, optionnel).

## Registration: organization type + country (done, verified)
- GENOCLAB clients sont surtout entreprises/labos. Ajout User.organization_type (academique/entreprise/laboratoire/particulier/autre) + organization_type_other (texte libre si "autre") + country (liste ISO 3166 complete, accounts/countries.py, defaut DZ Algerie).
- RegistrationForm: 3 nouveaux champs + clean() exige le detail si "autre". register.html: selects + boite "autre" conditionnelle + JS toggle. Formulaire service invite (guest_submit) idem: vue stocke dans requester_data, country_choices passe au contexte.
- Migration accounts/0010. Verifie: check OK, templates compilent, 193 pays, 6 choix type.
- RESTE possible: exposer organization_type/country dans l'edition de profil (profile view ne MAJ que organization actuellement).

## i18n: EN + AR completes (done, verified)
- makemessages rafraichi (gettext installe). Comble TOUS les msgstr vides: 56 EN + 56 AR (observateurs/lecture seule, reassignation, nudges de notation, consignes solde IBTIKAR, configurateur bilan Excel, bannieres RDV, aide invite-vs-compte, + nouveaux champs type orga/pays).
- HTML (<strong>), placeholders %(name)s et %% preserves; compilemessages sans erreur de format. FR = langue source (msgstr vides = fallback msgid FR, normal).
- Fix: apostrophe echappee dans un {% trans %} cassait l'extraction -> passe au pattern {% trans "..." as var %}.
- Script de remplissage: scratchpad/fill_po.py + fill_po2.py (polib).

## Media persistence -> Supabase Storage (done, verified)
- Probleme: disque Render free = ephemere -> rapports/uploads (report_file, order_file, payment_receipt_file, avatars, gift/service images, templates DOCX) perdus a chaque restart/redeploy.
- Fix: STORAGES['default'] = plagenor/storages.SupabaseMediaStorage (S3-compatible, django-storages + boto3) quand SUPABASE_S3_ENDPOINT/ACCESS_KEY_ID/SECRET_ACCESS_KEY presents; sinon FileSystemStorage (dev). Bucket prive.
- SupabaseMediaStorage.url() force le retour vers /media/<name> -> tous les fichiers restent servis PAR Django (jamais d'URL S3 directe/signee exposee). Garde la clause de citation IBTIKAR effective + bucket prive.
- report.py: protected_report_media sert via default_storage.open (au lieu de open(MEDIA_ROOT/...)); nouvelle vue serve_media pour le reste du media (avatars/orders/receipts/images/templates) -> route media/<path> apres media/reports/<path>.
- BONUS: corrige un bug latent prod -> l'ancien static(MEDIA_URL) ne tournait que sous DEBUG, donc le media non-rapport ne se servait pas en prod. serve_media le sert maintenant dans tous les envs.
- Docs generes a la demande (devis/facture/note/bilan) restent en ecriture disque locale + stream immediat (regenerables) -> hors scope, OK.
- Env vars (Render): SUPABASE_S3_ENDPOINT, SUPABASE_S3_REGION, SUPABASE_S3_ACCESS_KEY_ID, SUPABASE_S3_SECRET_ACCESS_KEY, SUPABASE_S3_BUCKET(=media). Voir HANDOVER §9.
- Verifie: manage.py check (mode FS + mode Supabase) OK; backend Supabase instancie (bucket/endpoint/path-style/prive) + url()->/media/; routing reports->gate, autres->serve_media; serve_media 200/404; clause IBTIKAR non-acquittee=403, acquittee=200 (octets corrects streames depuis le storage).

## Responsive / smartphone (done, verified check+compile)
- Bug majeur corrige: .main-content gardait max-width:calc(100vw - sidebar) a <=768px -> contenu ecrase ~500px avec vide lateral. Fix: max-width:100% en mobile.
- Garde anti-scroll horizontal global: html,body overflow-x:clip (pas hidden -> sticky topbar OK) + overflow-wrap:break-word.
- iOS no-zoom: inputs/.form-control = 16px a <=768px.
- Topbar mobile: search + bouton logout redondant masques, titre ellipsis, dropdowns largeur min(320px, 100vw-24px), tap targets 44px.
- Tables: .table-wrapper momentum scroll + overscroll contain. 3 tables larges non-wrappees corrigees (service_form_fields sample table overflow:auto, documents/template_list + template_detail wrap .table-wrapper).
- Public nav: liens ne sont plus caches a 480px -> scroll horizontal (tous accessibles).
- Header/btn rows flex-wrap; boutons form pleine largeur mobile; modals max-width:100vw-24px.
- Cache-buster CSS v5->v6 dans base.html + base_public.html.

## Création admin sans shell (done, pushed 7fccc64)
- Render free tier = pas de Shell (upgrade payant). Donc createsuperuser interactif impossible.
- Ajout core/management/commands/ensure_superuser.py: cree un SUPER_ADMIN depuis DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL. Idempotent (no-op si vars absentes; si user existe -> garantit is_superuser/is_staff/role=SUPER_ADMIN; mot de passe reecrit seulement avec --update-password).
- build.sh appelle `python manage.py ensure_superuser || true` apres les seeds.
- Table users (db_table='users'). Alternative SQL direct possible via Supabase SQL Editor si besoin immediat (INSERT avec make_password hash).

## Deploiement gratuit (prepare)
- Stack reco: app sur Render (free web service) + DB Supabase (Postgres gratuit persistant, multi-comptes) + media -> Supabase Storage (TODO, disque Render ephemere).
- Fichiers ajoutes: render.yaml (blueprint), build.sh (pip+collectstatic+migrate+seed), Procfile (gunicorn), runtime.txt (py3.11.9).
- settings.py: ALLOWED_HOSTS auto-ajoute RENDER_EXTERNAL_HOSTNAME; CSRF_TRUSTED_ORIGINS depuis env ou derive des hosts https (sinon login/inscription = 403 en prod).

## Graphiques bilan Excel (done)
- documents/stats_excel.py: chart par feuille de dimension (BarChart horizontal des effectifs, top 15) + PieChart "Répartition par canal" sur la Synthèse. Vérifié: 13 chart parts embarqués, classeur valide.

## Audit documents + corrections (done, verified)
- Audit des 6 documents générés. GENOCLAB devis/facture = irréprochables (totaux, montant en lettres). Corrections appliquées:
- Note de plateforme: params en FR (Oui/Non, labels FR via _PARAM_LABELS/_fr_param_value), échantillons = résumé (nouveau {{SAMPLE_SUMMARY}} + _format_sample_summary), multiplicateur défaut ×1, note "réajustement administratif" quand admin override (ne prétend plus une formule fausse).
- Monnaie uniformisée DA + séparateur espace partout: _money/_money_2dp (default DA + replace ','->' '), stats report, templates (platform_note_template.docx, build_default_templates.py). Plus aucun DZD.
- Formulaire IBTIKAR: fuite "Renseignements_Inventeurs.docx" retirée du template egtp_imt.docx. Colonnes Code/Conditions se remplissent avec les vraies clés registre (sample_code/culture_conditions) — l'audit initial utilisait de mauvaises clés de test.
- Fiche réception: liste échantillons en labels FR (détail conservé, {{SAMPLE_TABLE}} inchangé).
- Reste possible: graphiques dans bilan/stats (aucune figure actuellement).

## Staff exempt from report clause + rating (done, verified)
- Analyst(MEMBER)/admins(SUPER_ADMIN,PLATFORM_ADMIN,FINANCE) download reports from history anytime: no citation clause, no rating.
- report.py: _is_internal_staff(user) helper. download_report + protected_report_media skip the IBTIKAR gate for staff. report_viewer passes is_staff_viewer -> rating block hidden for staff in report_viewer.html.
- Verified (test client): requester rating=shown/download=302; analyst+admin rating=hidden/download=200; anon=302.

## Notification context icons restored (done, verified)
- Notifications showed text only (no per-type icon). Added Notification.icon + Notification.accent properties (map notification_type -> icon name from core icons + accent colour). No migration (properties only).
- Rendered an accent-tinted icon badge in topbar dropdown + includes/notification_list.html via {% icon notif.icon %}.
- Types->icons: INFO message-square, WORKFLOW flag, SYSTEM zap, ASSIGNMENT clipboard, STATUS_CHANGE send, APPOINTMENT clock, REPORT file-text, PAYMENT dollar-sign, REWARD award.

## Modern emoji rendering (Twemoji) — done, verified
- All emojis render via Twemoji 15.1 (latest colour SVG set) for a consistent modern look on every OS/browser, never the basic native glyphs.
- CDN twemoji.min.js + static/js/twemoji-init.js loaded in base.html + base_public.html. init parses document.body on load, re-parses on htmx:afterSwap, exposes window.twemojiParse(node).
- img.emoji CSS in main.css (inline, 1em). report_viewer rating re-parses its dynamic emoji via window.twemojiParse.
- Dependency: jsdelivr CDN at runtime (falls back to native glyphs if blocked).

## Rating-after-download nudge (done, verified live)
- Both requester(IBTIKAR) + client(GENOCLAB) now land on the rating step right after downloading (report_viewer.html).
- Download via hidden iframe (no navigation) -> revealRating() scrolls + spotlight pulse. IBTIKAR: clause modal first; GENOCLAB: directDownload (no clause).
- Persuasive rating (implicit, never asks for 5★ in words): 5★ pre-selected by default, dynamic emoji (😞→🤩) + reaction text happiest at 5, comment placeholder primes positives. Low scores get empathetic copy.
- Client GENOCLAB confirmed = direct download, no clause (per user).

## Report citation-clause gate hardened (done, verified live)
- Bug: requester could download report without signing clause via direct report_file.url links AND raw /media/reports/<file> URL.
- Fixed template bypasses: requester index (window.open report_file.url), requester request_detail (report_file.url fallback), client index (report_file.url) -> all route through report_view (gated).
- NEW: protected_report_media view + url 'media/reports/<path>' (declared before static()): IBTIKAR + not citation_acknowledged -> redirect to report_view; else serve. Closes raw /media/ bypass.
- Verified: unsigned IBTIKAR raw media + download = 302 blocked; after acknowledge = 200. GENOCLAB exempt (serves).

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
