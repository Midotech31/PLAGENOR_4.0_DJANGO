@echo off
echo ============================================
echo   PLAGENOR 4.0 — Demarrage du serveur
echo   ESSBO — Universite d'Oran
echo ============================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo [ERREUR] Environnement virtuel introuvable.
    echo Executez: python -m venv venv
    pause
    exit /b 1
)

call venv\Scripts\activate

echo Verification de la base de donnees...
python manage.py migrate --run-syncdb

echo.
echo Demarrage du serveur sur http://0.0.0.0:8000
echo Appuyez sur Ctrl+C pour arreter.
echo.
python manage.py runserver 0.0.0.0:8000
