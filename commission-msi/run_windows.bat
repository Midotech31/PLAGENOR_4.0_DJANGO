@echo off
REM ===================================================================
REM  Commission MSI - Lancement local
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Le lanceur ouvre d'abord le port, attend l'etat "pret", puis
REM  seulement ouvre le navigateur. Un seul serveur, un seul onglet.
REM ===================================================================
setlocal
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERREUR] L'application n'est pas installee.
  echo Executez d'abord install_windows.bat
  pause
  exit /b 1
)

echo Demarrage de Commission MSI en local (127.0.0.1)...
backend\.venv\Scripts\python.exe scripts\launcher.py %*

if errorlevel 1 (
  echo.
  echo Le demarrage a echoue. Consultez le message ci-dessus.
  echo Si le port est occupe, relancez avec : run_windows.bat --port 8732
  pause
)
endlocal
