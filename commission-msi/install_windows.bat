@echo off
REM ===================================================================
REM  Commission MSI - Installation locale Windows 10/11
REM  Designed by Prof. Merzoug Mohamed
REM
REM  Ce script installe l'application entierement en local.
REM  Aucun compte, aucun mot de passe, aucune donnee envoyee en ligne
REM  pour le coeur documentaire.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo === Commission MSI - installation locale ===
echo.

REM --- 1. Python -----------------------------------------------------
where python >nul 2>nul
if errorlevel 1 (
  echo [ERREUR] Python est introuvable.
  echo Installez Python 3.12 depuis python.org en cochant "Add Python to PATH".
  pause
  exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo Python detecte : !PYVER!

REM --- 1b. Longueur du chemin d'installation --------------------------
REM Windows refuse tout fichier de plus de 260 caracteres. Les dependances
REM ajoutent jusqu'a 129 caracteres apres ce dossier : un chemin trop long
REM fait echouer l'installation EN COURS DE ROUTE, apres plusieurs minutes
REM de telechargement. Mieux vaut le dire avant.
set "ICI=%CD%"
REM Valeur de repli : si la mesure echoue, on n'ecrit pas une comparaison
REM avec une variable vide, qui ferait planter le script sur une erreur de
REM syntaxe au lieu d'installer.
set "TAILLE=0"
REM Python est deja verifie present : lui demander la longueur evite une
REM sous-routine batch fragile, qui devrait manipuler setlocal pour rien.
for /f %%L in ('python -c "import os;print(len(os.getcwd()))"') do set TAILLE=%%L
if !TAILLE! GTR 101 (
  echo.
  echo [ERREUR] Le chemin d'installation fait !TAILLE! caracteres, maximum conseille 101.
  echo   %ICI%
  echo.
  echo Windows refuse tout fichier depassant 260 caracteres au total, et les
  echo dependances ajoutent jusqu'a 129 caracteres apres ce dossier.
  echo L'installation echouerait en cours de route.
  echo.
  echo Deux remedes, l'un ou l'autre suffit :
  echo   1. deplacez ce dossier vers un chemin court, par exemple C:\CommissionMSI,
  echo      puis relancez install_windows.bat ;
  echo   2. ou activez les chemins longs, en PowerShell ADMINISTRATEUR, sur une
  echo      seule ligne, puis redemarrez le poste et relancez install_windows.bat :
  echo      New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force
  echo.
  choice /C ON /M "Continuer malgre tout (O) ou arreter (N)"
  if errorlevel 2 exit /b 1
)

REM --- 2. Environnement virtuel --------------------------------------
if not exist "backend\.venv" (
  echo Creation de l'environnement virtuel local...
  python -m venv backend\.venv
  if errorlevel 1 (
    echo [ERREUR] Creation de l'environnement virtuel impossible.
    pause
    exit /b 1
  )
)

echo Installation des dependances Python locales...
call backend\.venv\Scripts\python.exe -m pip install --upgrade pip
call backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  echo [ERREUR] Installation des dependances Python echouee.
  pause
  exit /b 1
)

REM --- 2b. Second moteur OCR (optionnel mais recommande) ---------------
REM RapidOCR tire onnxruntime, dont un fichier depasse la limite des 260
REM caracteres sur un chemin long. Le telecharger 70 Mo pour echouer a
REM l'ecriture, puis afficher un mur de rouge, n'apprend rien a personne :
REM quand le chemin est trop long, l'etape est annoncee comme sautee.
REM Ce moteur ne lit pas l'arabe : son absence ne coute que la lecture des
REM pages latines a basse resolution.
if !TAILLE! GTR 101 (
  echo.
  echo [IGNORE] Second moteur RapidOCR : installation sautee.
  echo Le chemin de ce dossier fait !TAILLE! caracteres et son installation
  echo echouerait a l'ecriture, sans rien apprendre d'utile.
  echo Ce moteur ne lit PAS l'arabe : son absence n'est pas la cause d'une
  echo page arabe illisible. Seul Tesseract lit l'arabe.
  echo Pour l'obtenir : deplacez le dossier vers un chemin court, ou activez
  echo les chemins longs, puis relancez install_windows.bat.
  goto :APRES_OCR
)

echo Installation du second moteur de lecture (RapidOCR)...
call backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-ocr.txt
if errorlevel 1 (
  echo [AVERTISSEMENT] RapidOCR n'a pas pu etre installe.
  echo.
  echo Si l'erreur ci-dessus mentionne "No such file or directory" avec un
  echo chemin tres long, la cause est la limite des 260 caracteres de Windows,
  echo et non un probleme de reseau. Voir les deux remedes indiques plus haut.
  echo.
  echo Si l'erreur mentionne "Could not find a version that satisfies" avec
  echo une longue liste de versions "Requires-Python", la cause est que
  echo RapidOCR ne prend pas encore en charge la version de Python installee
  echo ^(mesure : aucune version de rapidocr-onnxruntime ne prend en charge
  echo Python 3.13 au moment de l'ecriture^). Ni un chemin ni une connexion n'y
  echo changeraient rien : il faut attendre une version compatible de
  echo RapidOCR, ou installer Python 3.12 a cote pour ce seul composant.
  echo.
  echo Dans les deux cas, l'application fonctionnera avec Tesseract seul : les
  echo pages a basse resolution seront moins bien lues, et aucune lecture de
  echo secours ne sera disponible si Tesseract manque.
  echo RapidOCR ne lit de toute facon pas l'arabe : son absence n'empeche
  echo pas la lecture des pages arabes, c'est Tesseract qui s'en charge.
)
:APRES_OCR

REM --- 3. Interface --------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
  echo [AVERTISSEMENT] npm est introuvable : l'interface compilee ne sera pas reconstruite.
  echo Installez Node.js 20 ou superieur si vous souhaitez recompiler l'interface.
) else (
  echo Compilation de l'interface locale...
  pushd frontend
  call npm install --no-audit --no-fund
  call npm run build
  popd
  if errorlevel 1 (
    echo [ERREUR] Compilation de l'interface echouee.
    pause
    exit /b 1
  )
)

REM --- 4. Base de donnees et referentiel ------------------------------
echo Initialisation de la base locale et du referentiel versionne...
pushd backend
call .venv\Scripts\python.exe -m alembic upgrade head
popd
if errorlevel 1 (
  echo [ERREUR] Migration de la base echouee. Aucune donnee existante n'a ete modifiee.
  pause
  exit /b 1
)

REM --- 5. OCR --------------------------------------------------------
where tesseract >nul 2>nul
if errorlevel 1 (
  echo [AVERTISSEMENT] Tesseract est introuvable.
  echo Les pages scannees resteront non extraites et explicitement marquees
  echo "verification humaine obligatoire".
  echo.
  echo   Telechargez : https://github.com/UB-Mannheim/tesseract/wiki
  echo   COCHEZ, dans l'installateur, "Additional language data" puis
  echo   Arabic, French et English. Sans le paquet arabe, aucune page
  echo   arabe ne pourra etre lue : RapidOCR ne lit que le latin.
) else (
  echo Tesseract detecte. Verification des paquets de langue...
  tesseract --list-langs 2>nul | findstr /B /C:"ara" >nul
  if errorlevel 1 (
    echo [AVERTISSEMENT] Le paquet de langue ARABE est absent.
    echo Aucune page arabe ne pourra etre lue. RapidOCR ne comble pas ce
    echo manque : ses modeles couvrent le latin, pas l'arabe.
    echo.
    echo   Reexecutez l'installateur Tesseract et cochez
    echo   "Additional language data" ^> Arabic,
    echo   ou copiez ara.traineddata dans le dossier tessdata de Tesseract.
    echo   Fichier : https://github.com/tesseract-ocr/tessdata/raw/main/ara.traineddata
  ) else (
    echo Paquet arabe present : les pages arabes sont lisibles.
  )
)

REM --- 5b. Pose automatique du paquet arabe ---------------------------
REM Repeter la consigne n'a pas suffi sur un poste reel : l'arabe se cache
REM derriere une case a cocher que personne ne deplie. Le script le pose
REM lui-meme quand Tesseract est la sans son modele arabe.
call backend\.venv\Scripts\python.exe scripts\installer_arabe.py

echo.
echo === Verification de l'installation ===
echo.
REM "Installation terminee" ne veut rien dire si aucune page ne peut etre lue.
REM Le script fait lire deux images de controle et rend un verdict.
call backend\.venv\Scripts\python.exe scripts\verify_install.py
set VERDICT=%errorlevel%

echo.
echo === Installation terminee ===
echo.
echo IMPORTANT
echo  - Ne perdez jamais le fichier data\master.key : sans lui, les donnees
echo    chiffrees sont definitivement illisibles.
echo  - Activez BitLocker : le chiffrement applicatif ne remplace pas le
echo    chiffrement complet du disque.
echo  - N'exposez jamais cette application au reseau.
echo.
echo Lancez maintenant run_windows.bat
echo.
echo Designed by Prof. Merzoug Mohamed
if not "%VERDICT%"=="0" (
  echo.
  echo [RAPPEL] La verification ci-dessus a signale un point bloquant pour la
  echo lecture des pages. Relancez-la a tout moment avec :
  echo    backend\.venv\Scripts\python.exe scripts\verify_install.py
)
pause
endlocal
exit /b 0
