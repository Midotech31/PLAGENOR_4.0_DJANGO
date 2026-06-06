@echo off
REM ===========================================================================
REM  PLAGENOR 4.0 — Windows one-time setup
REM
REM  Run this from cmd in the project root after `git clone` + `git checkout`.
REM  Idempotent: rerunning is safe — skips work that's already done.
REM
REM  What it does, in order:
REM   1. Verify Python is on PATH
REM   2. Create venv (skip if present)
REM   3. Install pip dependencies
REM   4. Write a .env with DEBUG=True + a generated SECRET_KEY (skip if exists)
REM   5. Run migrations
REM   6. Load the 9 production services from services_export.json
REM   7. Seed CMS content (156 rows across fr/en/ar)
REM   8. Compile translation catalogs (skipped silently on Windows if gettext
REM      is absent — the .mo files committed to git work without it)
REM   9. Prompt for a superuser account
REM
REM  When done, start the server with `run.bat`.
REM ===========================================================================

setlocal EnableDelayedExpansion

echo.
echo === PLAGENOR 4.0 setup ===
echo.

REM 1. Python check
python --version >nul 2>&1 || (
    echo [FAIL] Python is not on PATH. Install Python 3.11+ from python.org
    echo        and re-open cmd. Make sure "Add Python to PATH" was ticked.
    pause
    exit /b 1
)

REM 2. venv
if not exist venv\Scripts\activate.bat (
    echo [1/9] Creating virtual environment...
    python -m venv venv || goto :err
) else (
    echo [1/9] venv already present, skipping.
)
call venv\Scripts\activate.bat || goto :err

REM 3. Dependencies
echo [2/9] Installing dependencies (this takes a minute the first time)...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet || goto :err

REM 4. .env
if not exist .env (
    echo [3/9] Generating .env with a fresh SECRET_KEY...
    for /f "delims=" %%K in ('python -c "import secrets; print(secrets.token_urlsafe(50))"') do set SECRETKEY=%%K
    > .env echo DEBUG=True
    >> .env echo SECRET_KEY=!SECRETKEY!
    >> .env echo ALLOWED_HOSTS=localhost,127.0.0.1
    >> .env echo DOCUMENT_PDF_ENABLED=False
    >> .env echo SECURE_SSL_REDIRECT=False
    echo       .env written. Edit it later if you want PDF, SMTP, or PostgreSQL.
) else (
    echo [3/9] .env already exists, leaving it untouched.
)

REM 5. Migrations
echo [4/9] Running migrations...
python manage.py migrate --noinput || goto :err

REM 6. Services (from the version-controlled fixture)
echo [5/9] Loading services from services_export.json...
python manage.py loaddata services_export.json || (
    echo       services_export.json missing or invalid — try `seed_services` as fallback
    python manage.py seed_services
)

REM 7. CMS content
echo [6/9] Seeding CMS content ^(fr / en / ar^)...
python manage.py seed_content >nul || goto :err

REM 8. Translation catalogs — silent if gettext missing, .mo files are in git anyway
echo [7/9] Compiling translation catalogs ^(safe to fail on Windows^)...
python manage.py compilemessages >nul 2>&1

REM 9. Static files
echo [8/9] Collecting static files...
python manage.py collectstatic --noinput --clear >nul || goto :err

REM 10. Superuser
echo [9/9] Creating an admin account.
echo       Pick a username (e.g. ^"admin^") and a strong password.
echo       Press Ctrl+C to skip if you already have one.
python manage.py createsuperuser

echo.
echo === Setup complete ===
echo Run `run.bat` to start the server, then open http://localhost:8000/
echo.
pause
exit /b 0

:err
echo.
echo *** Setup failed. See the error above. ***
pause
exit /b 1
