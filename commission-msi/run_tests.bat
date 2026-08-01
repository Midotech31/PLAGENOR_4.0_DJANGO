@echo off
REM ===================================================================
REM  Commission MSI - Execution de tous les tests
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Les tests utilisent exclusivement des dossiers fictifs et
REM  synthetiques. Aucun dossier reel ne doit etre utilise.
REM ===================================================================
setlocal
cd /d "%~dp0"

set ECHEC=0

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERREUR] L'application n'est pas installee.
  echo Executez d'abord install_windows.bat
  pause
  exit /b 1
)

REM Les outils de test ne sont pas installes par install_windows.bat :
REM un poste d'evaluation n'a aucune raison d'embarquer un lanceur de tests.
backend\.venv\Scripts\python.exe -c "import pytest, httpx" >nul 2>nul
if errorlevel 1 (
  echo Installation des dependances de test...
  call backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
  if errorlevel 1 (
    echo [ERREUR] Installation des dependances de test echouee.
    pause
    exit /b 1
  )
)

echo === Tests backend (pytest) ===
pushd backend
set PYTHONPATH=.
call .venv\Scripts\python.exe -m pytest tests -q
if errorlevel 1 set ECHEC=1
popd

echo.
echo === Tests interface (Vitest) ===
pushd frontend
call npm run test
if errorlevel 1 set ECHEC=1
echo.
echo === Verification des types TypeScript ===
call npm run typecheck
if errorlevel 1 set ECHEC=1
popd

echo.
if "%ECHEC%"=="1" (
  echo [ECHEC] Au moins un test a echoue. La livraison n'est pas acceptable en l'etat.
) else (
  echo [SUCCES] Tous les tests sont passes.
)
pause
endlocal
exit /b %ECHEC%
