@echo off
REM ===================================================================
REM  Commission MSI - DESACTIVER la lecture semantique
REM  Designed by Prof. Merzoug Mohamed
REM
REM  ATTENTION : ce script RETIRE une capacite. Il ne l'active pas.
REM  Pour ACTIVER la lecture par un modele local : installer_modele_local.bat
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   ATTENTION - CE SCRIPT DESACTIVE LA LECTURE SEMANTIQUE
echo ============================================================
echo.
echo Vous cherchez peut-etre autre chose. Les trois modes :
echo.
echo   LOCAL_MODEL  Un modele installe SUR CE POSTE lit le dossier.
echo                Rien ne quitte la machine. Aucune cle, aucun compte.
echo                --^> pour l'activer : installer_modele_local.bat
echo.
echo   HYBRID_STRICT  Un modele de service lit le dossier. Meilleure
echo                lecture, mais exige une cle API et transmet le texte
echo                des pages ordinaires, expurge.
echo                --^> pour l'activer : activer_hybrid_strict.bat
echo.
echo   LOCAL_ONLY   AUCUNE lecture semantique. C'est ce que fait CE
echo                script. Le nom "LOCAL_ONLY" ne designe pas le modele
echo                local : il designe l'absence de lecture.
echo.
echo Etat actuel de votre poste :
echo.
if exist "backend\.venv\Scripts\python.exe" (
  backend\.venv\Scripts\python.exe scripts\verifier_ia.py 2>nul | findstr /C:"Mode d'analyse" /C:"Modele configure" /C:"Modèle configuré"
)
echo.
echo Ce que vous perdez en continuant : seules les informations ecrites
echo sous la forme "Libelle : valeur" seront extraites. Mesure sur un
echo dossier reel de 76 pages : 4 champs sur 29, dont 2 faux. Les autres
echo seront signalees "non verifiable" plutot que devinees.
echo.

choice /C ON /M "DESACTIVER la lecture semantique (O) ou annuler (N)"
if errorlevel 2 (
  echo.
  echo Annule. Aucune modification n'a ete faite.
  echo Pour ACTIVER la lecture par un modele local : installer_modele_local.bat
  pause
  exit /b 1
)

setx ANALYSIS_MODE LOCAL_ONLY >nul
setx ALLOW_EXTERNAL_AI false >nul
setx WEB_SEARCH_ENABLED false >nul

REM La cle d'un modele de service est retiree, pas seulement ignoree : une
REM cle qui dort dans l'environnement est une cle qui peut resservir sans
REM qu'on le decide. L'identifiant du modele LOCAL est conserve : il n'est
REM pas un secret, et le garder rend la reactivation immediate.
powershell -NoProfile -Command ^
  "[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $null, 'User');" ^
  "Write-Host 'Cle API de service effacee des variables d''environnement.'"

set "ANALYSIS_MODE=LOCAL_ONLY"
set "ALLOW_EXTERNAL_AI=false"
set "ANTHROPIC_API_KEY="

echo.
if exist "backend\.venv\Scripts\python.exe" (
  call backend\.venv\Scripts\python.exe scripts\verifier_ia.py
)

echo.
echo === Lecture semantique DESACTIVEE ===
echo.
echo Fermez cette fenetre, puis lancez run_windows.bat.
echo.
echo Pour la reactiver plus tard, sans rien retelecharger :
echo    setx ANALYSIS_MODE LOCAL_MODEL
echo puis fermez et relancez run_windows.bat.
echo Votre modele local est toujours installe.
echo.
echo Designed by Prof. Merzoug Mohamed
pause
endlocal
exit /b 0
