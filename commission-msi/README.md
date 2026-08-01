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

## Installation rapide (Windows 10/11)

```bat
install_windows.bat
run_windows.bat
```

Détails complets : [`docs/GUIDE_INSTALLATION.md`](docs/GUIDE_INSTALLATION.md).

## Tests

```bat
run_tests.bat
```

131 tests backend (pytest) + 8 tests d'interface (Vitest) + vérification des
types TypeScript. Plan complet : [`docs/PLAN_TESTS.md`](docs/PLAN_TESTS.md).

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
