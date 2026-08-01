# Journal des versions

*Designed by Prof. Merzoug Mohamed.*

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [1.0.0] — 2026-08-01

Première livraison complète, conforme au prompt maître V3 et au contrat de
fiabilité du kit.

### Cœur documentaire

- Application locale FastAPI + React/TypeScript, servie par le backend,
  fonctionnant entièrement hors ligne.
- Aucun compte, aucun mot de passe, aucune session ; aucune table `users`,
  `sessions` ou `credentials` ; aucune route `/setup`, `/login` ou `/logout`.
- Ingestion PDF avec validation stricte, empreinte SHA-256 et chiffrement
  AES-256-GCM à AAD liée ; original strictement inchangé.
- Analyse structurelle page par page : native, OCR, mixte, aucune, blanche,
  difficile, doublon probable, rotation, images, dimensions.
- OCR local Tesseract à la demande (`fra+ara+eng`), confiance affichée, mots
  sous 65 % signalés, échec explicite si le moteur est absent.
- Corrections humaines historisées ne détruisant jamais la valeur initiale.
- 29 champs d'information structurés avec contrôle renforcé.
- 14 pièces sourcées (`SRC-DOSSIER-PIECES`) + 17 pièces complémentaires
  explicitement non opposables.
- Liste de contrôle administratif en 17 points.

### Vigilance

- Référentiel versionné `rules/default_rules.json` : 24 règles couvrant les
  21 catégories exigées, termes multilingues FR/EN/AR.
- Section Maroc dédiée, avec titre et avertissement imposés, qualification
  manuelle de la relation et indices secondaires exigeant un contexte
  institutionnel.
- Alerte de couverture pour toute page non extraite.
- Règles normatives inactives tant que leur source officielle n'est pas
  présente, validée, d'empreinte cohérente et rattachée à un passage paginé.
- Contradictions `CTR-SESSION-001`, `CTR-FORMAT-001`, `CTR-LANGUE-001`
  enregistrées et jamais arbitrées automatiquement.

### Module de recherche Internet contrôlée

- Politique de sortie : liste blanche de domaines, TLS obligatoire,
  interrupteur de coupure immédiate, journal des domaines appelés.
- Garde-fou de contenu refusant PDF, documents d'identité, courriels,
  téléphones, données d'état civil, coordonnées bancaires et notes internes.
- Requêtes minimales préparées, relues, modifiables et approuvées une par une
  avant tout envoi.
- Quatre fournisseurs publics sans clé (OpenAlex, Crossref, ROR, ORCID),
  désactivables indépendamment.
- Six agents spécialisés travaillant sur une entrée isolée, produisant des
  affirmations atomiques sourcées avec nature et niveau de preuve.
- Orchestrateur calculant médiane, dispersion et accord ; homonymie ou
  désaccord affiche `DESACCORD_AGENTS — ARBITRAGE_HUMAIN_OBLIGATOIRE` et
  bloque toute conclusion consolidée.
- États `RECHERCHE_WEB_REQUISE`, `RECHERCHE_WEB_EN_COURS` et
  `ANALYSE_ENRICHIE_COMPLETE`.

### Classement externe indicatif

- 7 axes totalisant 100, seuils `A+`/`A`/`B`/`C`/`D`/`NR` configurables et
  visibles.
- Intervalles d'incertitude, sources par axe, `NR — NON RENSEIGNE` si les
  preuves sont insuffisantes.
- Révision humaine par axe (accepter, corriger, écarter) avec justification.
- **Strictement séparé de la grille scientifique officielle**, qu'il ne
  modifie jamais.

### Appréciation et rapport

- Grille scientifique à 5 critères, saisie exclusivement humaine, total = somme.
- Conclusion en liste fermée de 8 valeurs, motivation obligatoire.
- Portes de validation `G0_SOURCE` à `G7_VALIDATION_HUMAINE`.
- Rapport DOCX et PDF : 18 sections imposées + section « Classement externe
  indicatif assisté par IA », contenus étiquetés, brouillon filigrané, export
  officiel bloqué en cas de fait orphelin ou d'alerte non qualifiée.

### Exploitation

- Journal d'audit exhaustif ne contenant que des empreintes SHA-256.
- Sauvegarde horodatée avec manifeste vérifiable ; restauration toujours sur
  copie vide, jamais en écrasant des données existantes.
- Lanceur Windows ouvrant le port, attendant l'état « prêt », puis seulement le
  navigateur ; un seul serveur, un seul onglet.
- Scripts `generate_matrix.py` et `verify_sources.py`.

### Tests

- 131 tests backend (pytest) couvrant `ACC-001` à `ACC-016`.
- 8 tests d'interface (Vitest) : démarrage direct, absence d'écran de
  connexion, RTL arabe, accessibilité, statut jamais porté par la seule
  couleur.
- Vérification des types TypeScript sans erreur.
- Toutes les fixtures sont fictives et synthétiques.

### Documentation

13 documents dans `docs/`, dont la matrice exigence → source → page → test et
le journal des écarts techniques assumés.
