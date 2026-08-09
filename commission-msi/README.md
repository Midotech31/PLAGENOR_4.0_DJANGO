# Commission MSI

**Application locale d'aide à l'examen des demandes d'organisation de
manifestations scientifiques internationales.**

*Designed by Prof. Merzoug Mohamed — Conçu par le Professeur Merzoug Mohamed.*

---

> **L'application extrait, vérifie, classe, compare, signale et prépare.
> L'évaluateur humain contrôle, interprète, apprécie et décide.**

Elle ne décide jamais automatiquement d'un avis favorable, d'un rejet, d'une
interdiction, d'une note scientifique ou de la validité juridique d'une pièce.

Le « zéro erreur » absolu n'est pas promis. L'objectif tenu est : **zéro erreur
silencieuse, zéro affirmation orpheline de source, zéro décision automatique,
arrêt sécurisé en cas d'incertitude.**

---

## Ce que fait l'application

- **Ingestion PDF** — validation stricte, empreinte SHA-256, stockage chiffré
  AES-256-GCM, original strictement inchangé.
- **Analyse page par page** — classification native / OCR / mixte / aucune,
  page blanche, difficile, doublon probable, rotation, images.
- **OCR local Tesseract** — à la demande uniquement, `fra+ara+eng`, confiance
  affichée, mots sous 65 % signalés, texte initial jamais écrasé.
- **Extraction prudente** — 29 champs structurés, contrôle renforcé sur les
  noms, dates, montants, pays, institutions, affiliations et références.
- **Catalogue de pièces** — 14 pièces sourcées + pièces complémentaires ; la
  détection d'un titre ne vaut jamais confirmation.
- **Moteur de vigilance déterministe** — 21 catégories multilingues
  (FR/EN/AR), section Maroc dédiée et contextualisée, indices secondaires
  exigeant un contexte institutionnel.
- **Recherche Internet contrôlée** — requêtes minimales relues et approuvées
  une par une, liste blanche TLS, interrupteur de coupure, aucun document ne
  quitte le poste.
- **Six agents spécialisés** — identité, intégrité publique, droit algérien,
  réputation scientifique, ranking, vérification des sources ; travail
  indépendant, désaccords bloquants.
- **Classement externe indicatif** — 7 axes, incertitudes, `NR` si preuves
  insuffisantes, **strictement séparé de la grille officielle**.
- **Grille scientifique** — 5 critères, total 100, saisie exclusivement
  humaine, total = simple somme.
- **Rapport DOCX/PDF** — 18 sections imposées + section ranking, contenus
  étiquetés, brouillon filigrané, export officiel derrière la porte G7.
- **Audit, sauvegarde, restauration** — journal par empreintes, manifeste
  SHA-256, restauration toujours sur copie vérifiée.

## Lancer l'application (Windows 10/11)

Une seule fois, pour installer :

```bat
install_windows.bat
```

Puis, à chaque usage :

```bat
run_windows.bat
```

Le lanceur ouvre le port, attend l'état « prêt », puis seulement ouvre le
navigateur sur `http://127.0.0.1:8731/`. Si le port est occupé :
`run_windows.bat --port 8732`. Pour arrêter : `Ctrl+C` dans la fenêtre.

L'application n'écoute que sur `127.0.0.1` et le refuse explicitement sur toute
autre adresse. Il n'y a ni compte, ni mot de passe, ni écran de connexion.

Détails complets : [`docs/GUIDE_INSTALLATION.md`](docs/GUIDE_INSTALLATION.md).

### Lecture sémantique — recommandée, sans clé et sans rien transmettre

```bat
installer_modele_local.bat
```

Installe un modèle de langage **qui tourne sur ce poste**. Aucune clé API,
aucun compte, aucun abonnement, aucune facture — et **aucune donnée ne quitte la
machine**, pas même un extrait.

Sans cette lecture, seules les informations écrites sous la forme
`Libellé : valeur` sont repérées. Mesure sur un dossier réel de 76 pages :
**4 champs sur 29, dont 2 faux**. Avec elle, le texte est lu.

Coût : environ 5 Go de disque, 8 Go de RAM, et 15 à 40 minutes par dossier sans
carte graphique. Le traitement tourne en arrière-plan et reprend où il s'est
arrêté.

Un modèle local lit moins bien qu'un modèle de service : il proposera **moins**
de valeurs, jamais des valeurs **moins vérifiées** — chacune doit citer sa page
et un extrait relu mot pour mot sur le texte local, sans quoi elle est rejetée.

### Lecture par un modèle de service — si vous préférez la meilleure lecture

```bat
activer_hybrid_strict.bat
```

Exige une clé Anthropic (`platform.claude.com`) et transmet le texte des pages
ordinaires, expurgé. Environ 1 $ par dossier.

Sans elle, seules les informations écrites sous la forme `Libellé : valeur` sont
repérées. Mesure sur un dossier réel de 76 pages : **4 champs sur 29, dont
2 faux**. Avec elle, le texte est lu.

Le script demande la clé API sans jamais l'afficher ni l'écrire dans un fichier
du projet, puis effectue **un appel réel de contrôle** — une configuration
complète peut parfaitement accompagner une clé révoquée.

Le PDF original, les pièces d'identité, les numéros de passeport et les pages
classées `RESTREINT` ne sont jamais transmis : ces refus sont dans le code, pas
dans la configuration. Le modèle ne produit ni statut, ni note, ni avis — il
propose des valeurs, chacune devant citer sa page et un extrait relu mot pour
mot sur le texte local, sans quoi elle est rejetée.

Pour tout refermer et effacer la clé : `activer_local_only.bat`.

### Sous Linux ou macOS

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-ocr.txt
cd frontend && npm install && npm run build && cd ..
cd backend && .venv/bin/python -m alembic upgrade head && cd ..
backend/.venv/bin/python scripts/launcher.py
```

## Essayer l'application en cinq minutes

1. **Créer un dossier** — référence, intitulé, organisateur, puis « Créer ».
2. **Ouvrir le dossier** par le bouton « Actions » de sa ligne.
3. **Onglet « Document »** — verser le PDF de la demande.
4. **Onglet « Traitement du dossier »** — cliquer **une seule fois** sur
   « Traiter le dossier ». L'application lit le document, applique les 26
   critères, calcule le score sur 100, prépare les vérifications publiques, fait
   relire ses conclusions, propose un avis, **et produit le rapport harmonisé en
   Word et en PDF**.
5. **Télécharger** depuis la carte « Rapport harmonisé produit », qui apparaît à
   la fin du traitement.

Le traitement vit en base : fermer le navigateur ou l'application ne le perd
pas, il reprend là où il s'est arrêté.

Le rapport produit est un **brouillon filigrané**. L'export officiel reste un
acte distinct, dans l'onglet « Rapports », soumis à votre validation explicite.

## Si les pages arabes ne sont pas lues

**Double-cliquez sur `reparer_ocr_arabe.bat`**, à la racine du dossier de
l'application. Rien à taper, aucun dossier où se placer : le fichier se rend
lui-même au bon endroit avant de travailler.

Si Tesseract n'est pas encore installé, installez-le d'abord — une commande,
depuis n'importe quel dossier :

```bat
winget install --id UB-Mannheim.TesseractOCR
```

puis double-cliquez sur `reparer_ocr_arabe.bat`, qui posera le paquet arabe :
l'installation par winget ne pose que l'anglais.

Le script constate l'état réel, **pose le paquet arabe lui-même** si Tesseract
est présent sans lui, et vérifie le résultat en faisant lire une page arabe de
contrôle — il ne se contente pas de déposer un fichier. Si Tesseract est
entièrement absent, il donne la commande exacte pour l'installer.

Rappel de ce qui a coûté deux tentatives sur un poste réel : dans l'installateur
Windows de Tesseract, il faut **déplier « Additional language data »** et cocher
**Arabic**. RapidOCR ne comble pas ce manque — il ne lit pas l'arabe.

## Tests

```bat
run_tests.bat
```

Le script installe au besoin les dépendances de test
(`backend/requirements-dev.txt`), qui ne font délibérément pas partie de
l'installation : un poste d'évaluation n'a aucune raison d'embarquer un lanceur
de tests.

Sous Linux ou macOS :

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests -q
cd ../frontend && npm run test && npm run typecheck
```

292 tests backend (pytest) + 19 tests d'interface (Vitest) + vérification des
types TypeScript. Plan complet : [`docs/PLAN_TESTS.md`](docs/PLAN_TESTS.md).

## Construire l'archive de livraison

```bat
backend\.venv\Scripts\python.exe scripts\build_archive.py
```

Le script procède **par liste blanche** : rien n'entre dans l'archive qui n'ait
été explicitement nommé. Il refuse de produire un fichier si un secret apparaît
dans un fichier texte, relit l'archive terminée pour vérifier qu'aucun chemin
interdit ne s'y est glissé, et affiche l'empreinte SHA-256 du résultat.

Ne sont jamais embarqués : `data/` (clé maîtresse, base, documents versés),
`references_officielles/originaux/`, `tests_private/`, `.venv`, `node_modules`,
`.git` et tout fichier `.key`, `.sqlite3` ou `.env`. L'interface compilée
(`frontend/dist`) l'est en revanche à dessein, pour qu'un poste sans Node.js
puisse lancer l'application.

## Sécurité en une page

- Aucun compte, aucun mot de passe, aucune session, aucune route `/login`.
- Écoute exclusive sur `127.0.0.1` ; `Host`, `Origin` et `Referer` non locaux
  refusés ; CSP restrictive.
- AES-256-GCM avec AAD liée à l'identifiant de chaque objet.
- Le cœur documentaire fonctionne **entièrement hors ligne**.
- Seul le module de recherche contrôlée sort du poste, sous liste blanche TLS,
  avec un garde-fou qui refuse tout PDF, document d'identité, courriel,
  téléphone ou donnée personnelle.
- **Ne perdez jamais `data/master.key`.** Activez BitLocker.

Détails : [`docs/SECURITE.md`](docs/SECURITE.md).

## Structure

```
commission-msi/
  backend/          FastAPI, SQLAlchemy 2, Alembic, services, agents, ranking
  frontend/         React + TypeScript + Vite (bundle local, FR/EN/AR RTL)
  rules/            référentiels versionnés (règles de vigilance, axes de ranking)
  references_officielles/  manifeste, données sourcées, extractions, originaux
  scripts/          lanceur local, matrice de traçabilité, contrôle d'intégrité
  docs/             13 documents de référence
  data/             base, master.key, documents chiffrés (jamais versionné)
```

## Documentation

| Document | Objet |
|---|---|
| [`ANALYSE_FONCTIONNELLE.md`](docs/ANALYSE_FONCTIONNELLE.md) | Besoin, exigences, états, portes |
| [`ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Couches, décisions structurantes, flux |
| [`MODELE_DONNEES.md`](docs/MODELE_DONNEES.md) | Entités et champs chiffrés |
| [`GUIDE_INSTALLATION.md`](docs/GUIDE_INSTALLATION.md) | Installation Windows reproductible |
| [`GUIDE_UTILISATEUR.md`](docs/GUIDE_UTILISATEUR.md) | Parcours complet, onglet par onglet |
| [`SECURITE.md`](docs/SECURITE.md) | Modèle de menace, chiffrement, politique de sortie |
| [`SAUVEGARDE_RESTAURATION.md`](docs/SAUVEGARDE_RESTAURATION.md) | Procédures vérifiées |
| [`MISE_A_JOUR.md`](docs/MISE_A_JOUR.md) | Migrations préservant les dossiers |
| [`INCIDENTS.md`](docs/INCIDENTS.md) | Symptômes, causes, conduite à tenir |
| [`PLAN_TESTS.md`](docs/PLAN_TESTS.md) | Couverture et correspondance ACC-001…016 |
| [`LIMITES.md`](docs/LIMITES.md) | 23 limites affichées dans l'application |
| [`DECISIONS_TECHNIQUES.md`](docs/DECISIONS_TECHNIQUES.md) | Écarts assumés et justifiés |
| [`MATRICE_TRACABILITE.md`](docs/MATRICE_TRACABILITE.md) | Exigence → source → page → test |

## Avant tout usage réel

1. Comparer le référentiel aux textes officiels en vigueur.
2. Désactiver toute règle non validée.
3. Faire tester l'application par un informaticien de confiance.
4. Effectuer une recette sur des PDF **fictifs**.
5. Activer BitLocker.
6. Tester sauvegarde **et** restauration sur copie.
7. Vérifier que le serveur écoute exclusivement sur `127.0.0.1`.
8. Conserver les dossiers réels hors de tout service cloud non autorisé.
9. Configurer la liste blanche des fournisseurs et vérifier leurs conditions.
10. Vérifier que seules des requêtes minimales et publiques quittent le poste.
11. Faire valider juridiquement le référentiel algérien utilisé.
12. Vérifier manuellement tout profil, homonymie, lien associatif et ranking
    avant usage dans un rapport.

---

*Designed by Prof. Merzoug Mohamed.*
