# Déploiement sur Railway — guide pas à pas

Railway héberge **l'application + la base PostgreSQL** au même endroit. On garde
**Supabase Storage** (gratuit, déjà configuré) pour les médias/rapports.

Config déjà dans le repo : `railway.json` (build + preDeploy migrate/seeds +
start gunicorn + healthcheck `/healthz`) et `nixpacks.toml` (install +
collectstatic). Tu n'as rien à coder — juste à cliquer et coller des variables.

---

## 1. Créer le projet

1. Va sur https://railway.app → connecte-toi avec GitHub.
2. **New Project → Deploy from GitHub repo** → choisis `Midotech31/PLAGENOR_4.0_DJANGO`.
3. Dans le service, **Settings → Branch** → sélectionne **`main`** (une fois la
   PR #1 fusionnée, `main` contient tout ; c'est la branche à déployer
   désormais, et le travail futur y arrive par PR relue + CI verte).
   (Le 1er build va probablement échouer : normal, on n'a pas encore mis les
   variables. On corrige aux étapes 2–3.)

## 2. Ajouter la base PostgreSQL

1. Dans le projet Railway : **New → Database → Add PostgreSQL**.
2. Railway crée une base et une variable **`DATABASE_URL`**.
3. Sur ton **service applicatif** → **Variables → New Variable → Add Reference**
   → choisis `DATABASE_URL` du Postgres (Railway propose `${{Postgres.DATABASE_URL}}`).
   Ainsi l'app pointe automatiquement vers la base Railway.

## 3. Variables d'environnement du service

Service applicatif → **Variables** → ajoute (RAW editor, une par ligne) :

```
SECRET_KEY=<génère une chaîne aléatoire de 50+ caractères>
DEBUG=false
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=<mot de passe admin fort>
DJANGO_SUPERUSER_EMAIL=mohamedmerzoug459@gmail.com

# Médias sur Supabase Storage (identiques à Render)
SUPABASE_S3_ENDPOINT=https://afqehtcjvvdreqmqryoe.storage.supabase.co/storage/v1/s3
SUPABASE_S3_REGION=eu-west-1
SUPABASE_S3_ACCESS_KEY_ID=<ta clé S3 Supabase>
SUPABASE_S3_SECRET_ACCESS_KEY=<ton secret S3 Supabase>
SUPABASE_S3_BUCKET=media

# Optionnel — monitoring
# SENTRY_DSN=<ton DSN Sentry>
```

- `DATABASE_URL` est déjà là via la référence (étape 2) — **ne le recolle pas**.
- Railway fournit `PORT` et `RAILWAY_PUBLIC_DOMAIN` automatiquement (le code les
  gère : `ALLOWED_HOSTS` / CSRF s'auto-configurent).

## 4. Générer le domaine public

Service → **Settings → Networking → Generate Domain**. Tu obtiens une URL
`https://<ton-app>.up.railway.app`. (Le code l'ajoute seul à ALLOWED_HOSTS.)

## 5. Déployer

Clique **Deploy** (ou pousse un commit). Le pipeline :
1. **Build** : pip install + `collectstatic`.
2. **preDeploy** : `migrate` (crée le schéma dans le Postgres Railway) +
   `seed_services` + `seed_content` + `ensure_superuser` (crée l'admin).
3. **Start** : `gunicorn` + healthcheck sur `/healthz`.

Vérifie les logs : pas d'erreur `ImproperlyConfigured: DATABASE_URL` (sinon la
référence de l'étape 2 manque), et `ensure_superuser` doit créer l'admin.

## 6. Vérifier

- Ouvre `https://<ton-app>.up.railway.app/` → la page charge.
- `/admin/` → connexion avec `admin` + ton mot de passe.
- `/healthz` → `{"status":"ok"}` ; `/readyz` → `{"database":"ok"}`.
- Crée un compte staff → redéploie (ou redémarre) → il est **toujours là**
  (persistance Postgres confirmée).

---

## Migration des données depuis Supabase (optionnel)

Si tu avais déjà des données utiles dans le Postgres Supabase et veux les
reprendre sur Railway :

```bash
# 1) Dump depuis Supabase (connexion directe, PG 16)
pg_dump "postgresql://postgres.<ref>:<mdp>@<host>:5432/postgres" \
  --no-owner --no-privileges -Fc -f plagenor.dump

# 2) Restore dans le Postgres Railway (URL visible dans l'onglet Postgres → Connect)
pg_restore --no-owner --no-privileges -d "<DATABASE_URL Railway>" plagenor.dump
```

Sinon (recommandé vu l'historique SQLite éphémère) : pars d'une base neuve —
`migrate` crée le schéma, `ensure_superuser` l'admin, tu recrées le staff une
fois. Tout persiste ensuite.

---

## Notes
- **Sauvegardes** : le workflow GitHub `db-backup.yml` fonctionne aussi avec
  Railway — mets le secret `DATABASE_URL` (celui de Railway) dans GitHub
  Actions.
- **Coût** : facturation à l'usage (~5–10 $/mo pour ce profil). Surveille
  l'onglet **Usage**.
- **Région** : choisis une région Europe (proche Algérie) dans les settings du
  service si disponible.
- On peut plus tard migrer aussi les médias sur un volume Railway, mais garder
  Supabase Storage (gratuit) est parfaitement valable.
