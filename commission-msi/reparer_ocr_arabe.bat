@echo off
REM ===================================================================
REM  Commission MSI - Rendre l'arabe lisible
REM  Designed by Prof. Merzoug Mohamed
REM
REM  A DOUBLE-CLIQUER. Aucune commande a taper, aucun dossier ou se
REM  placer : ce fichier se rend lui-meme dans le dossier de
REM  l'application avant de travailler.
REM
REM  Il existe parce qu'une commande relative tapee depuis un autre
REM  dossier ne produit qu'un "Le chemin d'acces specifie est
REM  introuvable", qui n'apprend rien.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Commission MSI - reparation de la lecture arabe ===
echo.
echo Dossier de l'application : %CD%
echo.

if not exist "backend\.venv\Scripts\python.exe" (
  echo [ERREUR] L'application n'est pas installee dans ce dossier.
  echo.
  echo Ce fichier doit rester a la racine du dossier Commission_MSI,
  echo a cote de install_windows.bat et de run_windows.bat.
  echo Executez d'abord install_windows.bat.
  echo.
  pause
  exit /b 1
)

where tesseract >nul 2>nul
if errorlevel 1 (
  echo [INFO] Tesseract n'est pas dans le PATH. Recherche aux emplacements
  echo        d'installation standard par l'application...
  echo.
)

call backend\.venv\Scripts\python.exe scripts\installer_arabe.py
set RESULTAT=%errorlevel%

echo.
if "%RESULTAT%"=="0" (
  echo === Termine : l'arabe est lisible ===
  echo.
  echo Relancez run_windows.bat, ouvrez le dossier, puis cliquez sur
  echo "Traiter le dossier". Les pages arabes seront lues.
) else (
  echo === La lecture arabe n'est pas encore operationnelle ===
  echo.
  echo Suivez l'indication affichee ci-dessus, puis relancez ce fichier.
)
echo.
pause
endlocal
exit /b %RESULTAT%
