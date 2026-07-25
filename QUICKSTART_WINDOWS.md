# PLAGENOR 4.0 — Windows quickstart

A zero-to-running guide for Windows operators. If you're on Linux/Mac,
see `deploy_guide.md` instead.

## Prerequisites (one-time)

Install these via their official installers, ticking "Add to PATH":

1. **Python 3.11 or newer** — https://www.python.org/downloads/
2. **Git** — https://git-scm.com/download/win
3. **LibreOffice** (optional, only if you want `.pdf` instead of `.docx` downloads) — https://www.libreoffice.org/download/

Verify in a fresh cmd window:

```cmd
python --version
git --version
```

Both should print versions, not "not recognized as ...".

## First-time setup

```cmd
cd %USERPROFILE%\Documents
git clone https://github.com/Midotech31/PLAGENOR_4.0_DJANGO.git
cd PLAGENOR_4.0_DJANGO
git checkout claude/loving-tesla-jfcNV
setup.bat
```

`setup.bat` is idempotent. It will:

1. Create a Python virtual environment (`venv\`)
2. Install all pip dependencies
3. Generate a `.env` with a fresh `SECRET_KEY` (only if missing)
4. Run database migrations
5. Load the 9 production services from `services_export.json`
6. Seed 156 CMS strings across French / English / Arabic
7. Collect static files
8. Prompt you to create a superuser admin

When it's done you'll see *"Setup complete"*.

## Running the server

```cmd
run.bat
```

Open **http://localhost:8000/** in your browser. Stop the server with `Ctrl+C` in the cmd window.

## After every `git pull`

```cmd
git pull
setup.bat
```

`setup.bat` notices what's already done and only re-runs the changed bits (migrations, new translations, new services).

## Recovering lost data

### Services disappeared

Your 9 services are version-controlled in `services_export.json`. To restore:

```cmd
call venv\Scripts\activate.bat
python manage.py loaddata services_export.json
```

You should see *"Installed 9 object(s) from 1 fixture(s)"*. They will reappear in the Services tab.

### Database completely wiped

If `data\plagenor.db` was deleted (never run `del data\plagenor.db`!), rebuild from scratch:

```cmd
setup.bat
```

It detects the missing DB, recreates it, reloads your 9 services from the export, reseeds CMS content, and prompts for a new admin. Past user accounts and submitted requests are NOT recoverable that way — they only exist in the SQLite file.

### Backing up before risky changes

```cmd
call venv\Scripts\activate.bat
copy data\plagenor.db data\plagenor.db.backup
python manage.py dumpdata core.Service --indent 2 -o services_export.json
```

Now if anything breaks: `copy data\plagenor.db.backup data\plagenor.db`

## Common errors

| Error | Fix |
|---|---|
| `python` not recognized | Reinstall Python with "Add Python to PATH" checked, or use `py` instead. |
| `ModuleNotFoundError: No module named 'modeltranslation'` | Run `pip install -r requirements.txt` inside the venv. |
| `no such column: services.name_fr` | Run `python manage.py migrate`. |
| `SECRET_KEY environment variable must be set when DEBUG is False` | Delete `.env` and rerun `setup.bat` — it'll regenerate one. |
| Language switcher only shows EN | Run `git pull` — the FR/EN/ع switcher landed in commit `e7d2f86`. |
| Menus still in French after switching | Translations are pre-compiled (`.mo`) and committed; if you edited `.po` files, run `python manage.py compilemessages` (needs GNU gettext — not required for stock translations). |
| GENOCLAB registration shows IBTIKAR student fields | Run `git pull` — fixed in commit `f6759ff`. |
| `gunicorn` fails with `No module named 'fcntl'` | Gunicorn is Linux-only. On Windows use `python manage.py runserver` for dev, or `pip install waitress` + `waitress-serve --listen=127.0.0.1:8000 plagenor.wsgi:application` for production-mode testing. |

## Going to production

Windows is for development only. Production deployment uses Linux + PostgreSQL + gunicorn + nginx — see `deploy_guide.md`.
