@echo off
REM ===========================================================================
REM  PLAGENOR 4.0 — Windows dev-server launcher
REM
REM  Run this from cmd in the project root after `setup.bat` has been run once.
REM  Stops with Ctrl+C.
REM ===========================================================================

if not exist venv\Scripts\activate.bat (
    echo [FAIL] venv missing. Run `setup.bat` first.
    pause
    exit /b 1
)
if not exist .env (
    echo [FAIL] .env missing. Run `setup.bat` first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo.
echo Server starting at http://localhost:8000/   (Ctrl+C to stop)
echo.
python manage.py runserver
