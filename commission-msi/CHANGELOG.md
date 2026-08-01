# Journal des versions

*Designed by Prof. Merzoug Mohamed.*

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [2.0.0] — 2026-08-01

Alignement sur le prompt maître V4 : l'application **propose** désormais le
score scientifique et l'avis technique. Ce sont des propositions motivées,
rattachées à leurs preuves ; elles ne valent jamais décision.

### Évaluation automatique

- Référentiel versionné des **26 critères** (`rules/referentiel_26_criteres.json`)
  avec fondement exact, page, nature, caractère bloquant, exceptions et méthode
  de calcul. Corrections impératives encodées et testées : aucun délai universel
  de six mois, `A2` à 10 jours avant la session régionale, exception bilatérale
  sur `I2`, ratio exact sans tolérance inventée sur `I7`, `I9` conditionnel et
  non bloquant, passeports contrôlés en présence seule.
- Moteur réglementaire déterministe produisant `C/PC/NC/NV` pour chaque critère.
  Aucune cellule vide ; un calcul qui échoue devient `NV`, jamais une supposition.
- **Score scientifique sur 100** selon la grille détaillée (5 familles,
  24 sous-critères). Chaque sous-note porte une justification brève et ses
  preuves ; un élément non documenté vaut zéro avec la mention explicite, ce qui
  ne préjuge d'aucune incapacité réelle de l'organisateur.
- **Moteur d'avis** à liste fermée, enregistrant les règles déclenchées avec
  leurs critères et leurs preuves. Un score élevé ne neutralise jamais une
  non-conformité réglementaire.
- Les qualifications humaines — statut de critère, sous-note corrigée, avis
  retenu — priment toujours et ne sont jamais écrasées par une nouvelle analyse.

### Registre de preuves

- Table `evidence_items` : référence lisible et stable, origine, page,
  extrait chiffré et empreinte SHA-256. Le validateur refuse toute citation
  d'une preuve absente du registre.
- Les pièces d'identité y figurent en sensibilité `RESTREINT` : leur existence
  est traçable, leur contenu n'est ni affiché, ni transmis, ni reproduit.

### Traitement asynchrone durable

- Bouton **Traiter le dossier** créant un travail en base, exécuté par un worker
  distinct du serveur HTTP sous bail renouvelable avec battement.
- 13 états, points de reprise par étape indexés sur l'empreinte de leur entrée,
  boutons **Reprendre** et **Annuler** — l'annulation n'efface rien.
- Écran de progression : étape courante, pages traitées, recherches préparées,
  validations effectuées et estimation prudente.
- Les erreurs expliquent la cause et l'action possible, sans trace technique brute.

### Relecture indépendante et contrôle qualité

- `audit_service` recalcule les constats à partir des seuls faits, sans voir la
  rédaction du premier analyste. Tout désaccord non résolu classe le critère
  `NV` avec mention explicite — **aucune moyenne n'est jamais faite**.
- `report_qa_service` exécute le contrôle qualité §16 avant toute remise :
  présence et ordre des 26 critères, existence de chaque `evidence_id`,
  affirmations sans preuve, recalcul du score et des plafonds, avis dans la
  liste fermée, absence de délai de six mois vérifiée sur les calculs, absence
  de motif interdit. Un échec bloquant empêche la remise.

### Mode d'intelligence artificielle

- Abstraction `AIProvider` : `LOCAL_ONLY` par défaut, qui dit clairement ce
  qu'il ne peut pas faire, et `HYBRID_STRICT` configurable **uniquement** par
  variables d'environnement.
- Les pièces d'identité et numéros de passeport sont refusés et expurgés dans le
  code : `SEND_IDENTITY_DOCUMENTS=true` ne peut pas ouvrir cette porte.
- Un modèle indisponible lève `MODEL_UNAVAILABLE` sans basculement silencieux.
- Les appels sont journalisés par empreinte et catégorie de données, jamais par
  contenu ni raisonnement privé.

### Rapport

- Nouvelle mise en page **compacte** par défaut : page 1 informations et score,
  page 2 matrice réglementaire, page 3 vérifications et conclusion. Le nombre de
  pages est mesuré sur le fichier produit et renvoyé tel quel.
- Le rapport détaillé reste disponible (`layout=detaille`) quand les preuves ou
  les alertes exigent le détail intégral. Rien n'est jamais tronqué pour tenir
  dans un nombre de pages.

### Interface

- Deux nouveaux onglets : **Traitement du dossier** (bouton principal,
  progression, avis, score, matrice) et **Preuves et qualité** (registre,
  contrôle qualité, désaccords d'audit), traduits en français, anglais et arabe.

### OCR des images peu nettes

- Correction d'orientation par l'analyse `--psm 0` de Tesseract, puis jusqu'à
  cinq prétraitements essayés : standard, contraste fort, binarisation d'Otsu,
  agrandissement ×2, redressement par profil de projection.
- Le passage retenu est celui dont la note de qualité mesurée est la meilleure ;
  la recherche s'arrête dès qu'un résultat est franchement bon.
- Gains mesurés : flou fort 71,8 % → 92,8 % de confiance ; basse résolution
  30,4 % sur 25 caractères → 85,0 % sur 88 caractères.
- Les variantes essayées et leurs scores sont affichés : l'évaluateur voit ce
  qui a été tenté, pas seulement le résultat.

### Tests

- 229 tests backend et 15 tests d'interface au vert.

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
