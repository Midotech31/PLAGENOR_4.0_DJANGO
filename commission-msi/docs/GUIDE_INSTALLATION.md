# Guide d'installation (Windows 10/11)

*Designed by Prof. Merzoug Mohamed.*

## 1. Prérequis

| Composant | Version | Obligatoire | Remarque |
|---|---|---|---|
| Python | 3.12 (3.11 accepté) | oui | cocher « Add Python to PATH » |
| Node.js | 20 ou supérieur | pour recompiler l'interface | non requis si `frontend/dist` est fourni |
| Tesseract OCR | 5.x avec `fra`, `ara`, `eng` | non | sans lui, RapidOCR prend le relais |
| RapidOCR | installé par le script | non | second moteur, ~100 Mo, aucun GPU |
| BitLocker | — | fortement recommandé | chiffrement complet du disque |

Aucune connexion Internet n'est requise pour le cœur documentaire.

## 2. Installation

1. Décompressez l'archive dans un dossier **hors de tout service cloud non
   autorisé**, par exemple `C:\CommissionMSI`.
2. Double-cliquez sur `install_windows.bat`.

Le script crée l'environnement virtuel, installe les dépendances Python **et
le second moteur de lecture RapidOCR**, compile l'interface, applique les
migrations et signale l'absence éventuelle de Tesseract.

Les deux moteurs se complètent et l'application retient automatiquement la
meilleure des lectures : Tesseract est mesuré meilleur sur le flou et le bruit,
RapidOCR sur la basse résolution, et chacun supplée l'autre s'il manque.

3. Copiez `.env.example` en `.env` et adaptez-le si nécessaire.

## 3. Vérifications après installation

```bat
run_tests.bat
```

Le script installe au besoin `backend\requirements-dev.txt` : les outils de
test ne font pas partie de l'installation, un poste d'évaluation n'ayant aucune
raison d'embarquer un lanceur de tests.

Tous les tests doivent passer. Un seul échec critique interdit l'usage réel.

```bat
backend\.venv\Scripts\python.exe scripts\verify_sources.py
```

Ce contrôle compare les originaux déposés dans
`references_officielles\originaux\` au manifeste versionné (porte `G0_SOURCE`).
Une empreinte divergente suspend les règles liées.

## 4. Lancement

```bat
run_windows.bat
```

Le lanceur ouvre le port, attend l'état « prêt », **puis seulement** ouvre le
navigateur. Un second lancement ne démarre jamais un deuxième serveur.

Si le port est occupé :

```bat
run_windows.bat --port 8732
```

## 5. Installation manuelle (sans les scripts)

```bat
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend && npm install && npm run build && cd ..
cd backend && ..\backend\.venv\Scripts\python.exe -m alembic upgrade head && cd ..
backend\.venv\Scripts\python.exe scripts\launcher.py
```

## 6. Désinstallation

Supprimez le dossier de l'application. **Sauvegardez d'abord `data\` :** il
contient `master.key`, sans laquelle les données chiffrées sont définitivement
illisibles.

## 7. Rappels

- Ne perdez jamais `data\master.key`.
- Activez BitLocker.
- N'exposez jamais l'application au réseau.
- Utilisez exclusivement des PDF fictifs pendant la recette.
