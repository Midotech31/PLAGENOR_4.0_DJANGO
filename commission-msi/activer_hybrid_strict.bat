@echo off
REM ===================================================================
REM  Commission MSI - Activation du mode HYBRID_STRICT
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Ce script active la lecture semantique assistee du dossier.
REM  La cle API n'est JAMAIS ecrite dans un fichier du projet : elle est
REM  posee dans les variables d'environnement de VOTRE session Windows,
REM  et saisie sans jamais s'afficher a l'ecran.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Commission MSI - activation du mode HYBRID_STRICT ===
echo.
echo Ce que ce mode change :
echo   - le texte des pages est lu par un modele, ce qui permet d'extraire
echo     les informations redigees en prose ou en tableau, qu'aucune
echo     expression reguliere ne sait lire ;
echo   - chaque valeur proposee doit citer sa page et un extrait, verifie
echo     mot pour mot sur le texte local. Une valeur sans extrait
echo     verifiable est rejetee, jamais enregistree ;
echo   - toutes les valeurs restent au statut A_VERIFIER. Le modele ne
echo     produit ni statut, ni note, ni avis : ceux-ci restent calcules
echo     par les moteurs deterministes.
echo.
echo Ce qui ne quitte JAMAIS le poste, quelle que soit la configuration :
echo   - le PDF original ;
echo   - les pieces d'identite et les numeros de passeport ;
echo   - les pages d'un document classe RESTREINT.
echo.
echo Ce qui est transmis : le texte des pages ordinaires, expurge.
echo.

choice /C ON /M "Activer le mode HYBRID_STRICT (O) ou annuler (N)"
if errorlevel 2 (
  echo Annule. Aucune modification n'a ete faite.
  pause
  exit /b 1
)

REM --- 1. Identifiant du modele --------------------------------------
echo.
echo Identifiant EXACT du modele a utiliser.
echo N'utilisez pas d'alias "latest" : l'identifiant exact doit apparaitre
echo dans le journal d'audit, sans quoi deux analyses ne sont pas comparables.
echo.
set "MODELE="
set /p MODELE="Identifiant du modele : "
if "%MODELE%"=="" (
  echo [ERREUR] Aucun identifiant saisi. Rien n'a ete modifie.
  pause
  exit /b 1
)

REM --- 2. Cle API, saisie sans echo ------------------------------------
REM La saisie passe par PowerShell en mode masque : la cle n'apparait ni a
REM l'ecran, ni dans l'historique de commandes, ni dans un fichier du projet.
echo.
echo Cle API. La saisie est masquee : rien ne s'affiche pendant la frappe.
echo.
powershell -NoProfile -Command ^
  "$s = Read-Host 'Cle API' -AsSecureString;" ^
  "$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);" ^
  "$k = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b);" ^
  "[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b);" ^
  "if ([string]::IsNullOrWhiteSpace($k)) { Write-Host '[ERREUR] Cle vide.'; exit 1 };" ^
  "[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', $k, 'User');" ^
  "Write-Host 'Cle enregistree dans les variables d''environnement utilisateur.'"
if errorlevel 1 (
  echo [ERREUR] La cle n'a pas ete enregistree. Rien d'autre n'a ete modifie.
  pause
  exit /b 1
)

REM --- 3. Reglages du mode --------------------------------------------
setx ANALYSIS_MODE HYBRID_STRICT >nul
setx ALLOW_EXTERNAL_AI true >nul
setx MSI_PRIVACY_ACKNOWLEDGED true >nul
setx ANTHROPIC_MODEL_ANALYSIS "%MODELE%" >nul

REM Les pieces d'identite et le PDF original restent fermes. Ces deux
REM lignes sont ecrites explicitement pour qu'un reglage anterieur ne
REM puisse pas les avoir laisses ouverts.
setx SEND_IDENTITY_DOCUMENTS false >nul
setx SEND_ORIGINAL_PDF false >nul

REM Valeurs posees aussi pour CETTE fenetre, sinon la verification ci-dessous
REM lirait l'ancienne configuration : setx ne vaut que pour les processus a venir.
set "ANALYSIS_MODE=HYBRID_STRICT"
set "ALLOW_EXTERNAL_AI=true"
set "MSI_PRIVACY_ACKNOWLEDGED=true"
set "ANTHROPIC_MODEL_ANALYSIS=%MODELE%"
set "SEND_IDENTITY_DOCUMENTS=false"
set "SEND_ORIGINAL_PDF=false"
for /f "usebackq delims=" %%K in (`powershell -NoProfile -Command ^
  "[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')"`) do set "ANTHROPIC_API_KEY=%%K"

REM --- 4. Verification -------------------------------------------------
echo.
echo === Verification ===
echo.
echo Un appel reel de controle va etre effectue. Il transmet une phrase de
echo test, jamais un dossier. C'est le seul moyen de savoir si la cle et
echo l'identifiant du modele fonctionnent vraiment.
echo.
call backend\.venv\Scripts\python.exe scripts\verifier_ia.py --appel
set VERDICT=%errorlevel%

echo.
if "%VERDICT%"=="0" (
  echo === Mode HYBRID_STRICT actif ===
  echo.
  echo Fermez cette fenetre, puis lancez run_windows.bat.
  echo L'etape "Lecture semantique assistee du dossier" apparaitra dans la
  echo progression du traitement.
) else (
  echo === Mode NON operationnel ===
  echo.
  echo Les reglages sont poses mais l'appel de controle a echoue. Relisez le
  echo motif ci-dessus : il indique s'il s'agit de la cle, de l'identifiant
  echo du modele, ou du reseau. Relancez ce script apres correction.
)
echo.
echo Pour revenir au mode local : activer_local_only.bat
echo.
echo Designed by Prof. Merzoug Mohamed
pause
endlocal
exit /b %VERDICT%
