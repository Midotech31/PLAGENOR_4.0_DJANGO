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
