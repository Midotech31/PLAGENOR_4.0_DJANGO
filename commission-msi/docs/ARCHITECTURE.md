# Architecture

*Designed by Prof. Merzoug Mohamed.*

## Principe directeur

> L'application extrait, vérifie, classe, compare, signale et prépare.
> L'évaluateur humain contrôle, interprète, apprécie et décide.

Aucune décision automatique. Aucune affirmation sans source. Arrêt sécurisé en
cas d'incertitude.

## Vue d'ensemble

```
                   ┌──────────────────────────────────────────┐
   navigateur ────►│  Frontend React + TS (bundle local)      │
   127.0.0.1       │  10 onglets, FR / EN / AR RTL            │
                   └───────────────┬──────────────────────────┘
                                   │ /api/v1 (même origine)
                   ┌───────────────▼──────────────────────────┐
                   │  FastAPI — LocalOnlyMiddleware + CSP     │
                   ├──────────────────────────────────────────┤
                   │  api/v1  system · dossiers · web · réf.  │
                   ├──────────────────────────────────────────┤
                   │  services   pdf · ocr · rules · dossier  │
                   │             evaluation · report · backup │
                   │  web_research  egress · redaction ·      │
                   │                providers · service       │
                   │  agents     6 agents + orchestrateur     │
                   │  ranking    classement externe indicatif │
                   ├──────────────────────────────────────────┤
                   │  core   config · crypto · db · security  │
                   │         audit · text · vocabulary        │
                   ├──────────────────────────────────────────┤
                   │  SQLite WAL + AES-256-GCM (AAD liée)     │
                   └──────────────────────────────────────────┘
                                   │ (uniquement module en ligne)
                          liste blanche TLS ──► sources publiques
```

## Couches

### `app/core`

| Module | Rôle |
|---|---|
| `config.py` | Réglages locaux résolus une fois, chemins dérivés, signature |
| `crypto.py` | AES-256-GCM, AAD liée à l'identifiant, SHA-256, empreintes d'audit |
| `keyring.py` | Chargement de `master.key` — jamais régénérée si elle existe |
| `db.py` | SQLite WAL, `foreign_keys=ON`, `synchronous=FULL`, `session_scope` |
| `security.py` | `LocalOnlyMiddleware`, CSP, `safe_filename`, `resolve_within` |
| `errors.py` | Erreurs métier, réponses sans trace technique |
| `audit.py` | Journal d'audit — empreintes, jamais de valeur sensible en clair |
| `text.py` | Normalisation FR/EN/AR, frontières de mots, contenance explicable |
| `vocabulary.py` | Vocabulaire contrôlé, sorties automatiques interdites, limites |

### `app/services`

Ingestion PDF (`pdf_service`), OCR local (`ocr_service`), moteur de vigilance
déterministe (`rules_engine`), cycle de vie du dossier (`dossier_service`),
grille et portes (`evaluation_service`), référentiel réglementaire
(`regulation_service`), rapports (`report_service`), sauvegarde
(`backup_service`), référentiel versionné (`reference_data`, `seed`).

### `app/web_research`, `app/agents`, `app/ranking`

Module en ligne isolé, décrit en détail dans `SECURITE.md` §5. Il ne peut
modifier ni une conformité, ni une alerte confirmée, ni la grille scientifique
officielle, ni une conclusion.

## Décisions structurantes

1. **Aucune authentification.** Pas de table `users`, `sessions` ou
   `credentials` ; pas de route `/setup`, `/login`, `/logout`. La protection
   repose sur l'isolement local, le chiffrement du disque et les permissions
   de fichiers.
2. **Le PDF original est immuable.** Il est chiffré tel quel ; l'OCR travaille
   sur un rendu temporaire et n'écrase jamais le texte initial.
3. **Provenance obligatoire.** Un fait confirmé exige une page **et** un
   passage source, ou une saisie manuelle explicitement validée.
4. **Séparation stricte des couches d'appréciation.** Grille officielle
   (humaine, `evaluation_entries`) et classement externe indicatif
   (`event_rankings`) sont deux tables et deux écrans distincts.
5. **Portes de validation G0 → G7.** Une porte non satisfaite bloque l'étape
   suivante ; elle ne transforme jamais le dossier en rejet.

## Flux d'un dossier

1. `NOUVEAU` — création (référence, intitulé, organisateur).
2. Import PDF → validation, SHA-256, chiffrement, analyse page par page.
3. Classification : `NATIF`, `OCR`, `MIXTE`, `AUCUN`, blanche, difficile,
   doublon probable.
4. OCR local **à la demande** uniquement.
5. Extraction prudente, propositions de pièces, moteur de vigilance.
6. `RECHERCHE_WEB_REQUISE` → requêtes relues → `RECHERCHE_WEB_EN_COURS` →
   agents → ranking indicatif → `ANALYSE_ENRICHIE_COMPLETE`.
7. Qualification humaine des pièces, informations, contrôles et alertes.
8. Grille scientifique saisie ; total = simple somme.
9. Notes, réserves, conclusion personnelle motivée.
10. Rapport (brouillon filigrané, puis officiel après porte G7).
11. Export, audit, sauvegarde vérifiée.

Aucun état équivalent à « accepté » ou « rejeté » n'est jamais attribué.
