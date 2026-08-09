@echo off
REM ===================================================================
REM  Commission MSI - Installation du modele de lecture LOCAL
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Installe un modele de langage qui tourne SUR CE POSTE.
REM  Aucune cle API, aucun compte, aucun abonnement, aucune facture.
REM  Aucune donnee ne quitte la machine.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM --- 0. L'application est-elle installee ? ---------------------------
REM Verifie AVANT tout : ce script se termine par une verification qui
REM utilise l'environnement Python de l'application. Sans lui, elle
REM echouerait sur un message de cmd incomprehensible, apres un
REM telechargement de plusieurs Go. Autant le dire tout de suite.
if not exist "backend\.venv\Scripts\python.exe" (
  echo.
  echo [ERREUR] L'application n'est pas encore installee.
  echo.
  echo Lancez d'abord install_windows.bat, puis revenez ici.
  echo L'ordre compte : ce script se termine par une verification qui a
  echo besoin de l'environnement Python cree par l'installation.
  echo.
  echo Rien n'a ete telecharge ni modifie.
  echo.
  pause
  exit /b 1
)

echo.
echo === Commission MSI - modele de lecture local ===
echo.
echo Ce que cela apporte :
echo   - le texte des pages est LU, ce qui permet d'extraire les
echo     informations redigees en prose ou en tableau, qu'aucune
echo     expression reguliere ne sait lire ;
echo   - chaque valeur proposee doit citer sa page et un extrait,
echo     verifie mot pour mot sur le texte local. Une valeur sans
echo     extrait verifiable est rejetee, jamais enregistree.
echo.
echo Ce que cela ne coute pas :
echo   - aucune cle API, aucun compte, aucun abonnement ;
echo   - AUCUNE donnee ne quitte ce poste, pas meme un extrait.
echo.
echo Ce que cela coute :
echo   - environ 5 Go de disque pour le modele ;
echo   - de la memoire vive : 8 Go minimum, 16 Go recommandes ;
echo   - du temps : sans carte graphique, comptez 15 a 40 minutes
echo     par dossier. Le traitement tourne en arriere-plan et vous
echo     pouvez fermer l'application : il reprend ou il s'est arrete.
echo.

choice /C ON /M "Installer le modele local (O) ou annuler (N)"
if errorlevel 2 (
  echo Annule. Aucune modification n'a ete faite.
  pause
  exit /b 1
)

REM --- 1. Ollama est-il present ? --------------------------------------
where ollama >nul 2>nul
if errorlevel 1 (
  echo.
  echo Ollama n'est pas installe. C'est le serveur qui fait tourner le
  echo modele sur ce poste. Il est libre et gratuit.
  echo.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ACTION REQUISE] Telechargez et installez Ollama :
    echo    https://ollama.com/download/windows
    echo Puis relancez ce script.
    pause
    exit /b 1
  )
  echo Installation d'Ollama via winget...
  winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
  where ollama >nul 2>nul
  if errorlevel 1 (
    echo.
    echo [ERREUR] Ollama reste introuvable apres installation.
    echo Fermez cette fenetre, ouvrez-en une NOUVELLE ^(le PATH doit etre
    echo relu^), puis relancez installer_modele_local.bat.
    pause
    exit /b 1
  )
)

echo Ollama detecte.

REM --- 2. Choix du modele ----------------------------------------------
REM qwen2.5 est retenu par defaut pour une raison mesurable sur ce travail :
REM c'est, parmi les modeles de cette taille, celui qui lit le mieux le
REM francais ET l'arabe, les deux langues des dossiers de la commission.
echo.
echo Choisissez la taille du modele :
echo.
echo   [1] qwen2.5:7b   - 5 Go, 8 Go de RAM.  Rapide, lecture correcte.
echo   [2] qwen2.5:14b  - 9 Go, 16 Go de RAM. Plus lent, lecture meilleure.
echo   [3] qwen2.5:3b   - 2 Go, 4 Go de RAM.  Poste modeste, lecture limitee.
echo.
choice /C 123 /M "Votre choix"
if errorlevel 3 set "MODELE=qwen2.5:3b"
if errorlevel 3 goto :CHOISI
if errorlevel 2 set "MODELE=qwen2.5:14b"
if errorlevel 2 goto :CHOISI
set "MODELE=qwen2.5:7b"
:CHOISI

echo.
echo Modele retenu : %MODELE%
echo Telechargement en cours. C'est long la premiere fois ^(plusieurs Go^).
echo.
ollama pull %MODELE%
if errorlevel 1 (
  echo.
  echo [ERREUR] Le telechargement du modele a echoue.
  echo Verifiez votre connexion, puis relancez ce script.
  echo Le telechargement reprend ou il s'est arrete.
  pause
  exit /b 1
)

REM --- 3. Reglages de l'application ------------------------------------
setx ANALYSIS_MODE LOCAL_MODEL >nul
setx MSI_LOCAL_MODEL "%MODELE%" >nul
setx MSI_LOCAL_MODEL_URL "http://127.0.0.1:11434" >nul

REM Rien ne sort : ces portes restent fermees et sont reecrites ici pour
REM qu'un reglage anterieur ne puisse pas les avoir laissees ouvertes.
setx ALLOW_EXTERNAL_AI false >nul
setx SEND_IDENTITY_DOCUMENTS false >nul
setx SEND_ORIGINAL_PDF false >nul

REM Valeurs posees aussi pour CETTE fenetre : setx ne vaut que pour les
REM processus a venir, et la verification ci-dessous tourne maintenant.
set "ANALYSIS_MODE=LOCAL_MODEL"
set "MSI_LOCAL_MODEL=%MODELE%"
set "MSI_LOCAL_MODEL_URL=http://127.0.0.1:11434"
set "ALLOW_EXTERNAL_AI=false"

REM --- 4. Verification --------------------------------------------------
echo.
echo === Verification ===
echo.
echo Un appel reel de controle va etre effectue sur ce poste.
echo.
call backend\.venv\Scripts\python.exe scripts\verifier_ia.py --appel
set VERDICT=%errorlevel%

echo.
if "%VERDICT%"=="0" (
  echo === Mode LOCAL_MODEL actif ===
  echo.
  echo Fermez cette fenetre, puis lancez run_windows.bat.
  echo L'etape "Lecture semantique assistee du dossier" apparaitra dans
  echo la progression du traitement.
  echo.
  echo Rappel : aucune donnee ne quitte ce poste.
) else (
  echo === Mode NON operationnel ===
  echo.
  echo Les reglages sont poses mais l'appel de controle a echoue.
  echo Le motif exact figure ci-dessus.
)
echo.
echo Pour revenir au mode sans lecture : activer_local_only.bat
echo.
echo Designed by Prof. Merzoug Mohamed
pause
endlocal
exit /b %VERDICT%
