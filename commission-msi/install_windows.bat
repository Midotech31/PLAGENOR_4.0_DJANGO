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
  echo L'OCR local sera indisponible : les pages scannees resteront non extraites
  echo et explicitement marquees "verification humaine obligatoire".
  echo Installez Tesseract avec les paquets de langue fra, ara et eng.
) else (
  echo Tesseract detecte : OCR local disponible.
)

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
pause
endlocal
