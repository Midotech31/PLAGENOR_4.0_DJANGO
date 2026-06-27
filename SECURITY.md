# Security Policy

## Secrets handling

- **Never** put secrets (PATs, database URLs/passwords, API keys, SMTP
  credentials) in commits, code, issues, pull requests, or chat. They belong
  only in the host's environment panel (Render → Environment, Supabase project
  settings).
- `.env*` files are gitignored (except `.env.example`, which holds placeholders
  only). Keep it that way.
- If a secret is ever exposed, **rotate it immediately** (revoke the token /
  reset the password) — rotation, not deletion, is what protects you.
- Enable **GitHub secret scanning + push protection** on this repo
  (Settings → Code security) so accidental leaks are blocked automatically.

## Production configuration

- `DEBUG=False` and a strong `SECRET_KEY` are required in production
  (`plagenor/settings.py` fails fast otherwise).
- `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` are auto-derived from the host.
- Uploaded media (reports, uploads) lives on Supabase Storage in a **private**
  bucket and is served through Django so the IBTIKAR citation gate stays
  effective — never make that bucket public.

## Reporting a vulnerability

Email the maintainer (see repository owner) with details. Please do not open a
public issue for security-sensitive reports.
