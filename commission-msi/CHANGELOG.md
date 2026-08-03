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

### Rapport harmonisé — format de la commission

- Nouvelle mise en page **par défaut** (`layout=harmonise`), calquée sur le
  modèle fourni : huit sections, orientation technique transmise au ministère,
  fiche contrôlée en six rubriques, grille scientifique en cinq dimensions avec
  motif probant, matrice des 26 critères à cinq colonnes avec libellés communs
  courts et fondement exact.
- Section 4.1 dédiée aux éléments relatifs au Maroc et à Israël, signalés à
  titre strictement informatif : une nationalité, une formation ou un lien
  institutionnel antérieur ne constitue jamais une non-conformité.
- Encadrés de portée et principe probatoire repris du modèle ; la décision
  finale est rappelée comme relevant du ministère en tête, en section 7 et dans
  les encadrés.
- Trois pages atteintes sans retirer aucun des vingt-six constats.
- Les mises en page `compact` et `detaille` restent disponibles, et le choix est
  offert dans l'onglet Rapports.

### Échelle d'escalade OCR

- Nouveau module `ocr_engines` : texte natif → Tesseract multi-variantes →
  RapidOCR → modèle de vision → transcription humaine. La meilleure lecture
  mesurée est retenue ; aucune fusion entre moteurs.
- **RapidOCR** (modèles PP-OCR en ONNX, ~100 Mo, sans GPU) proposé en option
  via `backend/requirements-ocr.txt`. Mesuré meilleur sur la basse résolution,
  moins bon sur le flou : il supplée Tesseract sans le remplacer.
- **Correction d'un défaut réel** : sur une page illisible, un moteur pouvait
  renvoyer un texte faux avec une confiance élevée, présenté comme fiable.
  Trois doutes indépendants déclenchent désormais la relecture humaine —
  confiance basse, moins de 40 caractères utiles sur une page entière, ou
  désaccord entre deux moteurs.
- Une page qu'aucun moteur ne lit reste marquée à traiter, avec le motif nommé.
- Perdre Tesseract n'interrompt plus la lecture si un autre moteur est présent ;
  l'échec n'est explicite que si aucun moteur n'est disponible.
- Le barreau de vision refuse inconditionnellement les pages restreintes, et le
  fournisseur refuse tout bloc image sans classification — l'expurgation étant
  textuelle, elle ne peut rien voir dans une image.

### Corrections signalées à l'usage

- **« Requête refusée (422) »** à chaque qualification d'un critère : aucun
  gestionnaire n'existait pour les erreurs de schéma, et le motif réel était
  perdu. Les contraintes sont désormais traduites en phrases nommant le champ
  et la règle ; l'interface annonce l'exigence avant l'envoi et désactive
  l'enregistrement tant qu'elle n'est pas respectée.
- **Téléchargement du rapport introuvable** : deux boutons principaux, Word et
  PDF, lancent maintenant le téléchargement dès la génération. L'export
  officiel est replié avec l'énoncé de ses trois conditions. Le fichier porte
  la référence du dossier, sa version et son état au lieu d'un identifiant
  technique.

### Contrôle en ligne des profils des intervenants étrangers

- Nouvel agent `AGENT_SOUVERAINETE_NATIONALE` : pour chaque personne,
  institution, partenaire, sponsor ou financeur du dossier, il examine les
  sources publiques collectées et signale les **rattachements institutionnels**
  et **activités professionnelles publiquement documentés** relevant de l'une
  des douze catégories de vigilance nationale du référentiel (172 termes).
- Un terme n'est retenu que dans un **contexte institutionnel** — affiliation,
  programme, financement, partenariat. Une citation bibliographique ou une
  simple mention géographique ne déclenche rien.
- Deux sources indépendantes au minimum pour qu'un élément devienne un fait ;
  en deçà il reste une allégation à vérifier. L'absence d'élément trouvé est
  écrite comme telle et n'est jamais présentée comme une garantie.
- **Section 4.2 du rapport harmonisé** : personne, élément relevé, nombre de
  sources indépendantes, niveau de preuve. Aucun élément n'est qualifié par
  l'application.
- **Ce qui n'est jamais examiné**, et l'encadré de portée le dit au lecteur :
  la nationalité, l'origine ethnique, la religion, le lieu de naissance, la
  consonance d'un nom, une opinion supposée. Les trois catégories identitaires
  du référentiel sont exclues du champ, conformément au principe probatoire de
  l'application et à l'encadré de portée du modèle de la commission. Voir DT-23.

### Un seul clic produit le rapport final

- Nouvelle étape `REPORT_RENDERING` en fin de pipeline : le travail produit
  lui-même le **rapport harmonisé en Word et en PDF**, au format de la
  commission. Plus de seconde action, plus de mise en page à choisir.
- L'étape vient **après** le contrôle qualité : un rapport dont un contrôle
  bloquant échoue n'est jamais écrit sur le disque.
- Le brouillon est filigrané ; l'export officiel reste un acte humain distinct,
  soumis à la porte `G7_VALIDATION_HUMAINE`.
- Le nombre de pages est mesuré sur le PDF réellement écrit et conservé dans le
  point de reprise de l'étape.
- Interface : carte « Rapport harmonisé produit » en fin de traitement, avec les
  liens de téléchargement directs et aucun bouton « générer ». Une liste vide
  est expliquée au lieu d'être laissée en blanc. Voir DT-24.

### OCR — un défaut d'installation n'est plus imputé au document

- **Mesuré : RapidOCR ne lit pas l'arabe.** Sur une page arabe nette, Tesseract
  avec son paquet `ara` lit 3 lignes sur 3 à 89 % ; RapidOCR renvoie « rmg » à
  62 %. Ses modèles PP-OCR couvrent le latin, pas l'arabe.
- Conséquence corrigée : RapidOCR se déclarait disponible et son bruit suffisait
  à faire afficher « contenu illisible » sur une page parfaitement lisible. Le
  soupçon portait sur le document alors que le manque était celui du poste.
- Chaque moteur déclare désormais les **écritures** qu'il sait lire. Le message
  d'échec nomme l'installation manquante — Tesseract absent, paquet `ara`
  absent, ou mode `LOCAL_ONLY` — et ne propose jamais RapidOCR pour l'arabe.
- Nouveau `GET /api/v1/diagnostic-ocr` et bloc dépliant dans l'onglet
  « Document » : moteurs présents, langues Tesseract installées, arabe lisible
  ou non, sans ouvrir de terminal.
- `install_windows.bat` vérifie la présence du paquet `ara` et donne le lien de
  `ara.traineddata`. Voir DT-25.

### Installation — un verdict de lecture, pas un simple « terminé »

- **Limite des 260 caractères de Windows détectée avant l'installation.** Un
  poste réel a vu RapidOCR échouer sur un chemin de 262 caractères — dossier
  d'installation de 133, dépendance la plus profonde de 129. Le contrôle est
  désormais fait d'emblée, avec les deux remèdes : chemin court, ou
  `LongPathsEnabled`.
- Nouveau `scripts/verify_install.py` : il **fait lire deux images de contrôle**,
  une latine et une arabe, et rend trois verdicts distincts — tout est lu,
  seul le latin est lu, ou rien n'est lu. Relançable à tout moment.
- `install_windows.bat` l'exécute et rappelle son résultat : « Installation
  terminée » ne veut rien dire si aucune page ne peut être lue.
- L'échec de RapidOCR précise désormais qu'il n'empêche pas la lecture de
  l'arabe, dont Tesseract seul se charge. Voir DT-26.

### Tesseract trouvé même hors du PATH

- L'installateur Windows d'UB-Mannheim **n'ajoute pas Tesseract au PATH** par
  défaut. L'application le déclarait donc absent alors qu'il était installé.
- La recherche essaie désormais, dans l'ordre : le chemin configuré, le PATH,
  puis les emplacements d'installation standard — y compris une installation
  utilisateur sans droits administrateur. Voir DT-27.

### Rapport conforme aux douze rapports de la commission

- **Sept sections, plus huit.** Les douze rapports « réexaminés » du CRU Ouest
  ne portent ni section « Sources et traçabilité », ni tableau des règles de
  décision, ni sous-section de contrôle en ligne. Le rapport produit s'y
  conforme.
- **Titre de la section 6 conditionnel**, comme dans les douze modèles :
  « Réserves maintenues et conditions préalables à la tenue » sous avis
  favorable, « Compléments indispensables avant appréciation ministérielle » en
  ajournement.
- Fiche de six lignes sans ligne de titre ; légende de la matrice avant le
  tableau ; en-tête dans l'ordre intitulé, lieu et dates, pièce évaluée ;
  libellés de dimensions alignés ; étiquettes `[FAIT EXTRAIT]` et `[CALCUL]`
  retirées du format harmonisé.
- La provenance descend en **pied de page** : absente des modèles, mais un
  document officiel ne peut pas se passer de sa référence et de sa date.
- **Les détails retirés passent à l'interface** : nouveau
  `GET /dossiers/{id}/rapport-details` et carte « Traçabilité du rapport » —
  sources, versions, preuves citables, contrôle en ligne des profils et sa
  portée, contradictions connues, légendes, principe probatoire. Voir DT-28.

### Le paquet arabe s'installe tout seul

- Nouveau `scripts/installer_arabe.py` : quand Tesseract est présent sans son
  modèle arabe, **le script pose le paquet lui-même** puis vérifie le résultat
  en faisant lire une page arabe de contrôle. Répéter la consigne n'avait pas
  suffi sur un poste réel.
- Le dossier `tessdata` est lu dans la sortie de `tesseract --list-langs`, et
  non déduit du chemin du binaire — ce qui serait faux dès qu'un
  `TESSDATA_PREFIX` est défini.
- Plusieurs adresses de téléchargement, sur des hôtes différents : la forme
  `github.com/.../raw/...` a été mesurée renvoyant 403 derrière un mandataire,
  là où `raw.githubusercontent.com` passe.
- `install_windows.bat` l'exécute. Voir DT-29.

### Un raccourci double-cliquable pour réparer la lecture arabe

- Nouveau **`reparer_ocr_arabe.bat`** à la racine. La consigne précédente,
  relative, échouait sur « Le chemin d'accès spécifié est introuvable » dès
  qu'elle était tapée depuis un autre dossier — le script ne démarrait même pas.
- L'identifiant winget est désormais inscrit, **relevé** sur un poste réel :
  `UB-Mannheim.TesseractOCR`. L'installation par winget ne pose que l'anglais,
  d'où l'étape suivante qui pose l'arabe. Voir DT-30.

### Tests

- 322 tests backend et 22 tests d'interface au vert.

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
