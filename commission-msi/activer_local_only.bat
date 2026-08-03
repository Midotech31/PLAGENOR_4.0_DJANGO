@echo off
REM ===================================================================
REM  Commission MSI - Retour au mode LOCAL_ONLY
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Referme toute sortie externe. La cle API est EFFACEE des variables
REM  d'environnement de la session : la reactivation la redemandera.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Commission MSI - retour au mode LOCAL_ONLY ===
echo.
echo Plus rien ne quittera le poste. En contrepartie, la lecture semantique
echo assistee sera inactive : les informations redigees en prose ou en
echo tableau pourront rester non extraites, et seront alors signalees
echo "non verifiable" plutot que devinees.
echo.

choice /C ON /M "Revenir au mode LOCAL_ONLY (O) ou annuler (N)"
if errorlevel 2 (
  echo Annule. Aucune modification n'a ete faite.
  pause
  exit /b 1
)

setx ANALYSIS_MODE LOCAL_ONLY >nul
setx ALLOW_EXTERNAL_AI false >nul
setx WEB_SEARCH_ENABLED false >nul

REM La cle est retiree, pas seulement ignoree : une cle qui dort dans
REM l'environnement est une cle qui peut resservir sans qu'on le decide.
powershell -NoProfile -Command ^
  "[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $null, 'User');" ^
  "Write-Host 'Cle API effacee des variables d''environnement utilisateur.'"

set "ANALYSIS_MODE=LOCAL_ONLY"
set "ALLOW_EXTERNAL_AI=false"
set "ANTHROPIC_API_KEY="

echo.
call backend\.venv\Scripts\python.exe scripts\verifier_ia.py

echo.
echo === Mode LOCAL_ONLY actif ===
echo.
echo Fermez cette fenetre, puis lancez run_windows.bat.
echo.
echo Designed by Prof. Merzoug Mohamed
pause
endlocal
exit /b 0
