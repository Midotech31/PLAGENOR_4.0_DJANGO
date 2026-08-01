# Prompt maître V3 pour Claude Code — Application locale avec recherche Internet contrôlée et évaluation des manifestations scientifiques

## Contexte du kit fourni

Tu travailles dans un kit complet qui contient les cinq documents originaux transmis par l'utilisateur. Avant toute conception ou écriture de code :

1. lis `README.md` et `docs/CONTRAT_FAIL_SAFE.md` ;
2. vérifie les empreintes de `donnees/manifest_sources.json` ;
3. ouvre et examine tous les originaux de `references_officielles/originaux/`, page par page ;
4. utilise les extractions Markdown uniquement comme index de recherche ;
5. charge tous les JSON de `donnees/` ;
6. construis une matrice exigence -> source -> page -> test ;
7. n'active aucune règle issue d'une source absente, d'une proposition non adoptée ou d'une traduction non validée.

Les originaux prévalent sur le présent prompt. En cas de divergence, n'interprète pas : enregistre `CONTRADICTION_A_ARBITRER`, montre les deux passages et exige une validation humaine.

L'application doit être extrêmement sensible au contexte, mais son intelligence doit reposer d'abord sur des contrôles déterministes, des rapprochements explicables, des règles versionnées et des preuves. Les agents IA spécialisés connectés à Internet sont autorisés uniquement dans un module isolé de recherche publique, de vérification croisée et de classement indicatif. Ils doivent être clairement signalés, entièrement traçables et incapables de modifier seuls une conformité, une alerte confirmée, la grille scientifique officielle ou une conclusion.

Le « zéro erreur » absolu n'est pas une promesse acceptable. L'objectif obligatoire est : zéro erreur silencieuse, zéro affirmation orpheline de source, zéro décision automatique et arrêt sécurisé en cas d'incertitude.

## Mode d’emploi

1. Décompresser **tout le kit** dans un dossier de travail ; ne pas isoler le présent Markdown.
2. Ouvrir Claude Code à la racine du kit.
3. Lui demander d’exécuter intégralement `PROMPT_MAITRE_CLAUDE_CODE_V3.md` après avoir lu le `README.md`, les deux fichiers de `docs/`, tous les JSON de `donnees/` et les cinq originaux.
4. Autoriser Claude Code à créer le projet dans un nouveau sous-dossier `application/`, installer les dépendances locales et exécuter les tests.
5. Exiger une preuve de réussite des tests et une matrice exigence-source-page-test avant de considérer la livraison comme terminée.
6. Ne jamais lui fournir de vrais dossiers confidentiels pendant le développement : utiliser exclusivement des PDF fictifs et synthétiques.

Sources déjà incluses dans `references_officielles/originaux/` :

- `Envoi_218-DCEU-SDPUR_14-7-2026_الاجراءات_التظاهرات_العلمية.pdf` ;
- `Envoi_595-SG_19-5-2025_Organisation_manifestations_scientifiques.pdf` ;
- `Guide_Manifestations_internationales.doc` ;
- `Dossier_demande_organisation_manifestation_internationale.pdf` ;
- `Manuel_procedures_commission_manifestations_scientifiques_internationales.docx`.

Toute nouvelle instruction officielle doit être ajoutée au manifeste avec sa date, son autorité, son statut, son champ d’application et son empreinte SHA-256 avant activation d’une règle dérivée.

---

# PROMPT À DONNER INTÉGRALEMENT À CLAUDE CODE

Tu es architecte logiciel senior, ingénieur Python/TypeScript, expert en sécurité applicative locale, traitement documentaire, OCR, UX professionnelle et tests. Tu dois concevoir, développer, tester, documenter et livrer une application complète. Ne fournis pas seulement une analyse ou des extraits de code : crée réellement tous les fichiers du projet, exécute les tests, corrige les erreurs et prépare une archive installable pour Windows.

## 1. Contexte et finalité

L’application est destinée au Professeur Merzoug Mohamed, membre d’une commission régionale algérienne chargée d’examiner les demandes d’organisation de manifestations scientifiques internationales.

Elle doit accélérer et structurer l’examen des dossiers PDF sans remplacer l’évaluateur. Le principe impératif est :

> L’application extrait, vérifie, classe, compare, signale et prépare. L’évaluateur humain contrôle, interprète, apprécie et décide.

L’application ne doit jamais décider automatiquement d’un avis favorable, d’un rejet, d’une interdiction, d’une note scientifique ou de la validité juridique d’une pièce.

## 2. Règles absolues de fiabilité

Le système ne doit jamais :

- inventer un contenu absent du dossier ;
- compléter un texte illisible par supposition ;
- transformer une hypothèse en fait ;
- inventer une référence réglementaire ;
- conclure à partir d’un simple mot-clé, pays, nom, nationalité ou affiliation ;
- attribuer ou recommander automatiquement une note dans la grille scientifique officielle ;
- appliquer une règle non datée, non sourcée, non validée ou désactivée ;
- présenter l’absence d’alerte comme une garantie d’absence de risque ;
- envoyer le PDF, une pièce confidentielle, un document d’identité, une note interne ou une donnée personnelle non nécessaire à un service externe, une API d’IA ou un OCR en ligne ;
- traiter une rumeur, une accusation non étayée, une homonymie ou une simple appartenance déclarée comme une preuve ;
- inférer une incompatibilité à partir de la nationalité, de l’origine, de la religion, des opinions supposées ou de toute autre caractéristique sensible ;
- présenter un classement IA, un résultat de recherche Web ou une association détectée comme une décision juridique ou administrative.

En cas d’incertitude, afficher exactement :

> Contenu illisible ou insuffisamment fiable — vérification humaine obligatoire.

Chaque alerte doit préciser la source, la page, le contexte, la confiance, la raison, l’action recommandée et le statut humain. Une alerte reste une alerte et ne devient jamais automatiquement une décision.

## 3. Cible, fonctionnement et architecture retenue

Construire une application web locale moderne, prioritairement destinée à Windows 10/11 :

- interface : React + TypeScript + Vite ;
- composants accessibles, icônes SVG locales et CSS moderne ;
- backend : Python 3.12 + FastAPI ;
- base : SQLite en mode WAL, SQLAlchemy 2 et migrations Alembic ;
- visualisation PDF : PDF.js dans le navigateur local ;
- extraction/rendu PDF : PyMuPDF ;
- OCR local : Tesseract avec `fra`, `ara` et `eng` ;
- prétraitement OCR : Pillow et OpenCV si disponible ;
- rapports : `python-docx` pour DOCX et ReportLab ou WeasyPrint pour PDF ;
- cryptographie : `cryptography`, AES-256-GCM ;
- tests backend : pytest ;
- tests frontend : Vitest + Testing Library ;
- tests de parcours : Playwright ;
- empaquetage Windows : script d’installation et lanceur local fiable, avec PyInstaller si pertinent.

Le backend doit écouter uniquement sur `127.0.0.1`. Aucune télémétrie, CDN, police distante ou ressource externe non maîtrisée ne doit être utilisée. Le frontend compilé doit être servi par le backend. Le cœur documentaire, l’OCR et la saisie doivent fonctionner hors ligne ; la recherche de profils, la vérification Web et le classement externe exigent une connexion Internet active et doivent passer exclusivement par le module en ligne contrôlé décrit ci-dessous.

Si une contrainte technique rend un choix impossible, explique brièvement le blocage dans `docs/DECISIONS_TECHNIQUES.md`, choisis l’alternative locale la plus simple et poursuis le développement sans réduire la sécurité ni la traçabilité.

## 4. Logique générale du workflow

Implémenter ce workflow :

1. ouverture directe et fiable du tableau de bord local, sans compte ni écran de connexion ;
2. création d’un dossier avec référence, intitulé et organisateur ;
3. import du PDF original ;
4. validation du fichier, empreinte SHA-256 et stockage chiffré sans modification ;
5. analyse structurelle page par page ;
6. extraction du texte natif ;
7. classification des pages : native, scannée, mixte, blanche, difficile, doublon probable ;
8. OCR local uniquement lorsque nécessaire ou demandé ;
9. extraction prudente des informations ;
10. propositions de pièces détectées ;
11. détection des incohérences objectives ;
12. moteur de vigilance déterministe ;
13. préparation et validation humaine des requêtes Web minimales ;
14. recherches publiques sur les intervenants, comités, organismes et points douteux ;
15. vérification croisée par agents spécialisés et traitement des homonymies ;
16. génération du ranking externe indicatif avec sources et incertitude ;
17. contrôle et qualification humaine ;
18. saisie de la grille scientifique officielle ;
19. notes, réserves et conclusion personnelle ;
20. génération d’un projet de rapport ;
21. export, audit et sauvegarde.

États recommandés du dossier :

`NOUVEAU`, `ANALYSE_EN_COURS`, `RECHERCHE_WEB_REQUISE`, `RECHERCHE_WEB_EN_COURS`, `A_CONTROLER`, `EN_EVALUATION`, `COMPLEMENT_REQUIS`, `ANALYSE_ENRICHIE_COMPLETE`, `PRET_POUR_RAPPORT`, `ARCHIVE`.

Ne jamais attribuer automatiquement un état équivalent à « accepté » ou « rejeté ».

## 5. Interface moderne exigée

Créer une interface claire, institutionnelle et contemporaine, sans surcharge visuelle.

Direction artistique :

- bleu nuit `#123342` ;
- vert profond `#176B5B` ;
- fond ivoire/gris très clair `#F5F7F6` ;
- ambre `#B97812` pour l’incertitude ;
- rouge sobre `#B33A3A` pour les alertes critiques ;
- cartes blanches, ombres très légères, rayons de 10 à 14 px ;
- police locale Inter ou système, et Noto Sans Arabic locale pour l’arabe ;
- contraste WCAG AA ;
- navigation clavier, focus visible et libellés accessibles ;
- prise en charge correcte du français, de l’anglais et de l’arabe RTL.

Écrans obligatoires :

### 5.1 Démarrage local

- aucune page de configuration de compte ;
- aucun écran de connexion, identifiant, mot de passe, cookie de session ou verrouillage après tentative ;
- ouverture directe du tableau de bord après vérification de santé du serveur ;
- message clair si le port local est occupé ou si le serveur ne peut pas démarrer ;
- avertissement sur `master.key`, le chiffrement du disque et le fait que le serveur local ne doit jamais être exposé au réseau ;
- indicateur séparé de connectivité Internet et d’état des fournisseurs de recherche, sans ouvrir le serveur local à une adresse distante.

### 5.2 Tableau de bord

- dossiers récents ;
- nombre d’alertes ouvertes ;
- pages nécessitant un OCR ;
- pièces manquantes ;
- rapports générés ;
- filtres par statut, organisateur, date et priorité ;
- recherche globale.

### 5.3 Espace dossier

En-tête permanent : référence, intitulé, organisateur, pages, état, score saisi et alertes ouvertes.

Onglets :

1. `Document` ;
2. `Pièces` ;
3. `Informations` ;
4. `Contrôle administratif` ;
5. `Évaluation scientifique` ;
6. `Alertes et points sensibles` ;
7. `Notes et conclusion` ;
8. `Rapports` ;
9. `Recherche Web et ranking` ;
10. `Historique`.

Dans `Document`, afficher en écran partagé :

- lecteur PDF et navigation page par page ;
- page originale ;
- image améliorée lorsque l’OCR est lancé ;
- texte extrait ;
- mode d’extraction ;
- confiance ;
- anomalies de page ;
- bouton OCR local ;
- corrections manuelles conservant toujours le texte initial ;
- recherche dans le texte avec retour direct à la page.

Tous les champs, pièces et alertes comportant une page doivent offrir un lien `Voir la source` qui ouvre la page concernée.

## 6. Analyse PDF et OCR

Conserver le PDF original chiffré et calculer son SHA-256. Refuser les faux PDF, fichiers vides, corrompus, trop volumineux ou protégés de manière incompatible.

Pour chaque page, enregistrer :

- numéro ;
- mode `NATIF`, `OCR`, `MIXTE`, `AUCUN` ;
- texte initial ;
- texte corrigé séparément ;
- confiance ;
- nombre de caractères ;
- nombre d’images ;
- dimensions et rotation ;
- blanche ou non ;
- doublon probable et page d’origine ;
- OCR requis ;
- date et version du moteur.

Pipeline OCR :

1. rendu à 300 dpi ;
2. détection d’orientation ;
3. rotation sans perte ;
4. niveaux de gris ;
5. contraste automatique ;
6. réduction prudente du bruit ;
7. OCR `fra+ara+eng`, limité aux langues installées ;
8. récupération des mots et boîtes TSV ;
9. moyenne de confiance ;
10. surlignage des mots dont la confiance est inférieure à 65 % ;
11. affichage obligatoire de l’incertitude sous 65 % ou si le texte utile est trop court.

Ne jamais lancer automatiquement l’OCR sur toutes les pages si le texte natif est suffisant. Les noms propres, dates, montants, pays, institutions, affiliations et références réglementaires doivent porter un indicateur de contrôle renforcé.

## 7. Catalogue des pièces

Initialiser chaque dossier avec les pièces suivantes :

1. demande officielle ;
2. fiche technique ;
3. procès-verbal ou délibération ;
4. appel à communication ;
5. programme scientifique ;
6. comité scientifique ;
7. comité d’organisation ;
8. liste des intervenants ;
9. liste des participants ;
10. affiliations institutionnelles ;
11. justificatifs des partenaires ;
12. justificatifs des sponsors ;
13. budget ;
14. plan de financement ;
15. modalités de publication ;
16. modalités de valorisation ;
17. annexes administratives ;
18. documents d’identité, dans une section restreinte ;
19. autorisations, visas ou avis spécifiques ;
20. autres pièces exigées par un référentiel actif.

Statuts des pièces :

`ABSENTE`, `DETECTEE`, `CONFIRMEE`, `INCOMPLETE`, `ILLISIBLE`, `NON_CONFORME`, `A_VERIFIER`, `NON_APPLICABLE`.

La détection d’un titre ne vaut jamais confirmation de la validité de la pièce.

## 8. Informations structurées

Extraire prudemment ou permettre de saisir :

- intitulé ;
- type de manifestation ;
- thème ;
- objectifs ;
- dates de début et de fin ;
- lieu ;
- format présentiel, hybride ou à distance ;
- établissement organisateur ;
- structure porteuse ;
- responsable scientifique ;
- comité scientifique ;
- comité d’organisation ;
- intervenants ;
- participants ;
- pays représentés ;
- institutions représentées ;
- partenaires ;
- sponsors ;
- financeurs ;
- montants et devise ;
- budget total ;
- modalités de publication ;
- livrables ;
- résultats attendus ;
- retombées scientifiques ;
- retombées doctorales ;
- retombées socio-économiques ;
- références réglementaires citées.

Pour chaque information, conserver :

- valeur proposée ;
- valeur initiale ;
- valeur corrigée ;
- document et page ;
- extrait source ;
- coordonnées de zone si disponibles ;
- mode d’extraction ;
- confiance ;
- date ;
- auteur de la correction ;
- statut.

Statuts : `A_VERIFIER`, `CONFIRME`, `CORRIGE`, `REJETE`, `INCERTAIN`, `NON_APPLICABLE`.

## 9. Recherche Internet contrôlée sur les personnes, organismes et manifestation

Ajouter un module en ligne obligatoire pour toute **analyse enrichie**. Ce module doit vérifier la connectivité au démarrage et avant chaque campagne de recherche. En l’absence d’Internet, le cœur local reste utilisable, mais l’application affiche clairement :

> Recherche Web indisponible — analyse enrichie incomplète, vérification humaine externe obligatoire.

L’état d’un dossier ne peut pas être présenté comme `ANALYSE_ENRICHIE_COMPLETE` tant que les recherches en ligne requises ne sont pas terminées, échouées explicitement ou écartées avec une justification humaine.

### 9.1 Périmètre des recherches publiques

Pour chaque intervenant étranger, membre étranger du comité scientifique ou d’organisation, responsable, partenaire, sponsor, financeur et institution étrangère, rechercher uniquement des informations publiques nécessaires à l’évaluation :

- identité professionnelle et variantes du nom ;
- établissement et affiliations actuelles ou passées ;
- fonctions publiques, académiques, éditoriales ou associatives déclarées ;
- participation publique à des associations, organismes, réseaux, campagnes ou activités ;
- publications, conférences, projets, partenariats et conflits d’intérêts publics pertinents ;
- sanctions, interdictions, décisions judiciaires ou administratives uniquement lorsqu’elles proviennent d’une source officielle identifiable ;
- signaux d’usurpation d’identité, affiliation invérifiable, revue ou conférence prédatrice ;
- tout point du dossier suscitant un doute raisonnable et documentable.

Ne rechercher ni collecter les adresses privées, numéros personnels, données familiales, données de santé, identifiants privés, contenus derrière authentification, données obtenues illicitement ou informations sans rapport direct avec la mission de la commission.

### 9.2 Vérification d’une éventuelle incompatibilité avec les lois et principes applicables en Algérie

La notion de « principes de l’Algérie » ne doit jamais être laissée à l’interprétation libre d’un agent IA. Toute incompatibilité potentielle doit être comparée à un référentiel algérien officiel, daté, versionné, actif et validé dans l’application : Constitution, lois, règlements, instructions, décisions ou positions institutionnelles formellement intégrées au référentiel.

Pour chaque signalement :

1. identifier précisément la personne ou l’organisme et exclure les homonymes ;
2. citer la source Web, son éditeur, son URL canonique, sa date de publication et sa date de consultation ;
3. conserver un extrait bref ou une empreinte de la preuve publique, dans le respect des droits d’auteur ;
4. distinguer fait vérifié, déclaration de l’intéressé, allégation de tiers, opinion, rumeur et absence de preuve ;
5. exiger au moins deux sources indépendantes et fiables pour une conclusion sensible, sauf source officielle primaire suffisante ;
6. relier le point au texte algérien applicable, avec référence, article ou passage, statut et date ;
7. produire seulement un statut `A_VERIFIER`, `SOURCE_OFFICIELLE_TROUVEE`, `SOURCES_CONCORDANTES`, `SOURCES_CONTRADICTOIRES`, `HOMONYMIE_POSSIBLE`, `NON_ETABLI` ou `ECARTE_PAR_HUMAIN` ;
8. réserver toute qualification juridique, diplomatique ou administrative à l’évaluateur et aux autorités compétentes.

L’absence de résultat ne signifie jamais absence d’implication. Une association, une présence à un événement, une signature collective ou un abonnement à un réseau ne prouvent pas à eux seuls une adhésion à toutes ses positions.

### 9.3 Hiérarchie et qualité des sources

Prioriser dans cet ordre :

1. sites officiels des autorités, juridictions, journaux officiels et registres publics ;
2. pages institutionnelles officielles, universités, organismes de recherche et identifiants scientifiques reconnus ;
3. publications scientifiques et bases bibliographiques reconnues ;
4. sites officiels des associations, conférences, éditeurs et organisateurs ;
5. médias reconnus et documents d’archives vérifiables ;
6. réseaux sociaux uniquement pour un compte officiel authentifié ou relié à une page institutionnelle, avec niveau de preuve faible.

Les agrégateurs anonymes, contenus générés automatiquement, captures sans origine, forums et publications non attribuées ne peuvent jamais suffire à confirmer un point sensible.

### 9.4 Agents IA spécialisés connectés à Internet

Mettre en œuvre une orchestration de plusieurs agents spécialisés, avec missions séparées :

- `AGENT_IDENTITE_AFFILIATIONS` : désambiguïsation des personnes, institutions et variantes de noms ;
- `AGENT_INTEGRITE_PUBLIQUE` : recherche d’engagements associatifs, fonctions, activités publiques et conflits d’intérêts pertinents ;
- `AGENT_DROIT_ALGERIEN` : rapprochement avec le seul référentiel algérien officiel validé ;
- `AGENT_REPUTATION_SCIENTIFIQUE` : réputation académique, publications, indexation, rétractations et signaux prédateurs ;
- `AGENT_RANKING_MANIFESTATION` : évaluation comparative de la manifestation ;
- `AGENT_VERIFICATEUR_SOURCES` : contrôle des citations, dates, homonymies, contradictions et niveau de preuve.

Chaque agent doit restituer des affirmations atomiques accompagnées de leurs sources. Un agent ne doit pas lire aveuglément la conclusion d’un autre avant sa propre analyse. L’orchestrateur compare ensuite les résultats, calcule les désaccords et soumet une synthèse à validation humaine. En cas de divergence importante, afficher `DESACCORD_AGENTS — ARBITRAGE_HUMAIN_OBLIGATOIRE` et ne pas produire de conclusion consolidée.

### 9.5 Protection des dossiers lors des recherches en ligne

- ne jamais téléverser le PDF original ni les pièces du dossier vers Internet ;
- ne transmettre aux moteurs ou agents que la requête minimale validée : nom public, affiliation, institution, intitulé de manifestation ou identifiant public ;
- permettre à l’évaluateur de relire et modifier chaque requête avant envoi ;
- masquer les données non nécessaires et interdire les documents d’identité ;
- chiffrer localement les résultats enregistrés ;
- utiliser TLS, délais d’expiration, quotas, liste de fournisseurs autorisés et journal d’audit ;
- stocker les clés API uniquement dans le coffre de secrets local ou les variables d’environnement, jamais dans le code, les journaux ou les sauvegardes non protégées ;
- permettre de désactiver un fournisseur sans désactiver le reste de l’application ;
- respecter les conditions d’utilisation, les licences, les droits d’auteur et la législation applicable à la protection des données.

## 10. Ranking indicatif de la manifestation par agents spécialisés

Créer un classement externe distinct de la grille scientifique officielle. Il sert d’aide à l’analyse et ne modifie jamais automatiquement la note saisie par l’évaluateur.

Axes indicatifs, configurables et totalisant 100 :

| Axe de ranking externe | Maximum |
|---|---:|
| Réputation et historique vérifiable de la manifestation | 20 |
| Crédibilité de l’organisateur et des institutions porteuses | 15 |
| Qualité et traçabilité du comité scientifique et des intervenants | 20 |
| Sélectivité, transparence de l’appel et qualité du programme | 15 |
| Publication, indexation, archivage et politiques éthiques | 15 |
| Portée internationale et diversité institutionnelle réelle | 10 |
| Transparence des partenaires, sponsors et conflits d’intérêts | 5 |

Règles du ranking :

- chaque axe reçoit une note proposée, un intervalle d’incertitude et une justification sourcée ;
- les agents travaillent indépendamment puis l’orchestrateur calcule médiane, dispersion et niveau d’accord ;
- aucune note n’est produite si les preuves sont insuffisantes ; utiliser `NR — NON RENSEIGNE` ;
- afficher séparément données observées, inférences, limites et avis des agents ;
- classification indicative : `A+`, `A`, `B`, `C`, `D` ou `NR`, avec seuils configurables et visibles ;
- comparer, lorsque possible, à des manifestations du même domaine, de même type et de portée comparable ;
- conserver la date du ranking, la version des agents, les requêtes, les sources et les paramètres ;
- permettre à l’évaluateur d’accepter, corriger ou écarter chaque axe avec justification ;
- ne jamais utiliser le ranking comme motif unique d’acceptation, de rejet, d’interdiction ou de transmission.

Le rapport doit intituler cette partie :

> Classement externe indicatif assisté par IA — non décisionnel, fondé sur des sources publiques consultées à la date indiquée.

## 11. Contrôle administratif déterministe

Créer une liste de contrôle éditable pour :

- pièces obligatoires ;
- signatures et tampons ;
- visas et autorisations ;
- cohérence des dates ;
- cohérence des noms et variantes orthographiques ;
- affiliations ;
- programme versus fiche technique ;
- programme versus thème et objectifs ;
- budget, sous-totaux, total et devise ;
- partenaires versus justificatifs ;
- sponsors versus justificatifs ;
- intervenants versus affiliations ;
- nombre de pays annoncé versus liste réelle ;
- format annoncé versus programme ;
- publication, valorisation, livrables et suivi ;
- expiration éventuelle de documents ;
- références réglementaires identifiables.

Statuts : `CONFIRME`, `NON_CONFIRME`, `INCOMPLET`, `INCOHERENT`, `ILLISIBLE`, `A_VERIFIER`, `NON_APPLICABLE`.

Les comparaisons automatiques doivent être explicables. En cas de rapprochement approximatif de noms, afficher les deux graphies, la métrique utilisée et demander une confirmation.

## 12. Grille scientifique

Créer exactement ces critères :

| Critère | Maximum |
|---|---:|
| Pertinence scientifique et adéquation aux priorités nationales | 30 |
| Clarté des objectifs, résultats attendus et retombées | 20 |
| Valeur ajoutée de la coopération internationale | 20 |
| Faisabilité organisationnelle, gouvernance et financement | 15 |
| Valorisation, publications, livrables et suivi | 15 |

Règles :

- l’utilisateur saisit chaque note ;
- aucune proposition automatique dans la grille scientifique officielle ; les propositions du ranking externe restent dans un module séparé et non décisionnel ;
- pas de note hors limites ;
- justification obligatoire pour toute note ;
- calcul automatique du total uniquement ;
- historique de toutes les modifications ;
- passages sources affichables à côté de chaque critère ;
- avertissement si la justification est vide ou trop courte, sans interprétation automatique de sa qualité.

## 13. Moteur d’alertes et incohérences

Chaque résultat doit avoir :

- identifiant ;
- catégorie ;
- code de règle ;
- libellé ;
- terme ou comparaison déclencheuse ;
- contexte ;
- page ;
- coordonnées si disponibles ;
- priorité `FAIBLE`, `MOYEN`, `ELEVE`, `CRITIQUE` ;
- confiance ;
- explication ;
- vérification recommandée ;
- source réglementaire éventuelle ;
- statut humain ;
- commentaire ;
- dates de création et modification.

Statuts humains : `A_VERIFIER`, `CONFIRME`, `ECARTE`, `INCERTAIN`, `NON_APPLICABLE`, `TRANSMIS`.

Une motivation d’au moins huit caractères est obligatoire pour `CONFIRME`, `ECARTE` et `TRANSMIS`.

## 14. Référentiel initial des points sensibles

Créer un fichier versionné `rules/default_rules.json`. Chaque règle contient :

`code`, `category`, `label`, `priority`, `terms`, `context_terms`, `guidance`, `source_ref`, `source_date`, `authority`, `scope`, `version`, `validated_at`, `active`.

Une règle sans source officielle validée peut exister comme règle de vigilance, mais son `source_ref` doit être `À confirmer par le Professeur Merzoug Mohamed ou par la commission` et elle ne doit jamais être présentée comme une interdiction.

### 12.1 Maroc — section spécifique obligatoire

Catégorie : `MENTIONS_MAROC`.

Termes principaux :

`Maroc`, `Morocco`, `Royaume du Maroc`, `Kingdom of Morocco`, `Moroccan`, `marocain`, `marocaine`, `marocains`, `marocaines`, `المغرب`, `المملكة المغربية`.

Indices secondaires à utiliser seulement avec un contexte institutionnel ou d’affiliation : domaine `.ma`, indicatif `+212`, Rabat, Casablanca, Marrakech/Marrakesh, Fès/Fez, Tanger/Tangier, Agadir, Oujda, Meknès, Tétouan.

Afficher le titre exact :

> Mentions relatives au Maroc — vérification institutionnelle obligatoire

Afficher aussi :

> Point de vigilance institutionnelle — vérifier les instructions officielles applicables à la session avant toute conclusion.

Classifier manuellement ou par proposition prudente la relation :

`MENTION_GEOGRAPHIQUE`, `REFERENCE_BIBLIOGRAPHIQUE`, `AFFILIATION`, `NATIONALITE_DECLAREE`, `INTERVENANT`, `PARTICIPANT`, `PARTENAIRE`, `SPONSOR`, `FINANCEUR`, `COMITE`, `ORGANISATEUR`, `COOPERATION_ENVISAGEE`, `AUTRE`.

Une ville, un domaine, un indicatif ou un nom ne suffit jamais à établir une collaboration. La nationalité d’une personne ne doit jamais produire automatiquement un avis défavorable.

### 12.2 Autres catégories de vigilance

Créer au minimum les catégories et termes indicatifs suivants, toujours comme alertes à vérifier :

1. `INTEGRITE_TERRITORIALE` : Sahara occidental, Western Sahara, RASD, SADR, République arabe sahraouie démocratique, الصحراء الغربية, frontières contestées, cartes politiques, dénominations territoriales.
2. `RELATIONS_DIPLOMATIQUES` : Palestine, Israël, normalisation, ambassade, consulat, mission diplomatique, visa, protocole officiel.
3. `CARTES_SYMBOLES` : carte, frontière, drapeau, emblème, hymne, logo officiel, dénomination d’une institution ou d’un territoire.
4. `COMMUNICATION_INSTITUTIONNELLE` : position officielle, au nom du gouvernement, communiqué officiel, diffusion en direct, porte-parole, représentation officielle.
5. `MEMOIRE_NATIONALE` : Révolution algérienne, guerre de libération, martyrs, colonialisme, colonisation française, archives mémorielles.
6. `IDENTITE_RELIGION_LANGUE` : formulations susceptibles de stigmatiser une religion, une langue, une origine, une région ou une communauté. Distinguer impérativement étude scientifique et promotion.
7. `DISCRIMINATION_HAINE` : incitation à la haine, supériorité raciale, discrimination, stigmatisation.
8. `ORDRE_PUBLIC_VIOLENCE` : appel à la violence, émeute, mobilisation violente, extrémisme, contenu pouvant provoquer une panique. Distinguer analyse scientifique et incitation.
9. `DEFENSE_SECURITE` : secret défense, base militaire, capacité militaire, renseignement, système d’armes, informations opérationnelles.
10. `INFRASTRUCTURES_CRITIQUES` : énergie, eau, télécommunications, transport, plans, coordonnées, vulnérabilités ou cartographies sensibles.
11. `CYBER_DUAL_USE` : malware, ransomware, zero-day, exploit, intrusion offensive, contournement d’authentification, phishing, outils à double usage.
12. `IA_DESINFORMATION` : deepfake, médias synthétiques, désinformation, propagande automatisée, manipulation de l’opinion.
13. `BIOSECURITE_DUAL_USE` : gain de fonction, pathogène virulent, toxine biologique, synthèse de pathogène, protocoles à potentiel de mésusage.
14. `SANTE_PUBLIQUE` : essai clinique, données de patients, allégation de guérison, épidémie, communication pouvant provoquer panique ou fausse assurance.
15. `DONNEES_GENETIQUES_BIOMETRIQUES` : génome humain, génomique des populations, base biométrique, réidentification, données génétiques.
16. `RESSOURCES_BIOLOGIQUES` : ressources génétiques, export d’échantillons, connaissances traditionnelles, accord de transfert de matériel, partage des avantages.
17. `PATRIMOINE_ARCHIVES` : fouilles archéologiques, manuscrits, archives nationales, patrimoine culturel, reproduction, numérisation ou déplacement.
18. `FINANCEMENT_INFLUENCE` : financement étranger, sponsor étranger, donateur anonyme, contrepartie éditoriale, conflits d’intérêts.
19. `SOUVERAINETE_DONNEES` : transfert international, cloud étranger, transfert de technologie, données sensibles, échantillons ou logiciels stratégiques.
20. `REPUTATION_SCIENTIFIQUE` : revue prédatrice, éditeur prédateur, publication garantie, affiliation non vérifiable, identité douteuse, conflit d’intérêts.
21. `ETHIQUE_RECHERCHE` : sujets humains, consentement, comité d’éthique, mineurs, populations vulnérables, prélèvements et données personnelles.

Les termes doivent être multilingues lorsque pertinent : français, anglais et arabe. Les règles doivent produire un extrait de contexte et non une simple liste de mots.

## 15. Référentiel réglementaire personnel

Créer un module permettant d’importer les textes, notes, guides, instructions, décisions, listes de pièces et modèles d’avis.

Métadonnées :

- titre ;
- référence ;
- date ;
- version ;
- autorité émettrice ;
- date d’entrée en vigueur ;
- date de fin éventuelle ;
- champ d’application ;
- statut `BROUILLON`, `A_VERIFIER`, `VALIDE`, `ABROGE`, `SUSPENDU` ;
- empreinte du fichier ;
- fichier source chiffré ;
- validateur et date de validation.

Seules les règles `VALIDE` et `active=true` peuvent être appliquées. En cas de chevauchement ou contradiction, afficher :

> Contradiction réglementaire détectée — interprétation humaine obligatoire.

Ne jamais inventer une règle à partir du titre d’un document. Conserver le passage exact et la page du texte officiel lorsqu’une disposition est liée à une règle.

## 16. Conclusions possibles

Proposer une liste fermée, choisie uniquement par l’évaluateur :

- `AVIS_FAVORABLE` ;
- `AVIS_FAVORABLE_SOUS_RESERVES` ;
- `AJOURNEMENT_COMPLEMENT_INFORMATION` ;
- `NON_ELIGIBILITE_QUALIFICATION_INTERNATIONALE` ;
- `POSSIBILITE_REQUALIFICATION` ;
- `TRANSMISSION_COMMISSION_AVEC_VIGILANCE` ;
- `TRANSMISSION_TUTELLE_ALERTE_MOTIVEE` ;
- `NON_DETERMINABLE_INFORMATION_INSUFFISANTE`.

La motivation est obligatoire. Afficher clairement : « Proposition personnelle de l’évaluateur — ne vaut pas décision de la commission ».

## 17. Rapport personnel

Générer un DOCX et un PDF comprenant :

1. identification du dossier ;
2. synthèse factuelle ;
3. inventaire des pièces ;
4. pages illisibles ou incertaines ;
5. informations manquantes ;
6. incohérences ;
7. contrôle administratif ;
8. éligibilité internationale à apprécier ;
9. grille scientifique saisie ;
10. conformité réglementaire à vérifier ;
11. risques institutionnels ;
12. mentions relatives au Maroc ;
13. autres points sensibles ;
14. questions à la commission ;
15. réserves ;
16. conclusion personnelle motivée ;
17. références aux pages ;
18. identité de l’évaluateur, date, version et empreinte du rapport.

Distinguer visuellement : `FAIT_EXTRAIT`, `CALCUL`, `ALERTE_SYSTEME`, `COMMENTAIRE_EVALUATEUR`, `CONCLUSION_EVALUATEUR`, `A_VERIFIER`.

Chaque fait doit être relié à une page ou être explicitement indiqué comme saisie manuelle validée. Le document doit porter en première page : « Projet de rapport — validation humaine obligatoire ».

## 18. Modèle de données minimal

Créer des migrations pour les entités suivantes :

- ne créer aucune table `users`, `sessions`, `credentials` ou équivalente ;
- `dossiers` : id UUID, reference unique, title, organizer, status, page_count, original_name, storage_path, sha256, size, created_at, updated_at ;
- `documents` : id, dossier_id, type, encrypted_path, sha256, version, sensitivity, created_at ;
- `pages` : id, document_id, page_no, mode, original_text_cipher, corrected_text_cipher, confidence, char_count, image_count, rotation, needs_ocr, is_blank, duplicate_of, created_at ;
- `ocr_runs` : id, page_id, engine, version, languages, parameters_json, confidence, result_cipher, boxes_cipher, created_at ;
- `extracted_items` : id, dossier_id, key, label, initial_value_cipher, current_value_cipher, page_id, source_cipher, bbox_json, extraction_mode, confidence, status, updated_by, updated_at ;
- `corrections` : id, entity_type, entity_id, previous_hash, new_hash, reason, evaluator_label, created_at ;
- `piece_definitions` et `piece_checks` ;
- `persons`, `institutions`, `affiliations`, `participations` ;
- `web_research_runs`, `web_queries`, `web_sources`, `online_claims` ;
- `person_web_profiles`, `association_links`, `identity_disambiguations` ;
- `agent_assessments`, `agent_disagreements`, `event_rankings`, `event_ranking_axes` ;
- `administrative_checks` ;
- `evaluation_criteria` et `evaluation_entries` ;
- `findings` ;
- `rules` et `rule_versions` ;
- `regulations` et `regulation_passages` ;
- `notes` ;
- `reports` ;
- `audit_events` ;
- `backups`.

Chiffrer les documents, textes, extraits, commentaires, corrections, notes et justifications. Les métadonnées minimales nécessaires à la recherche locale peuvent rester en clair, mais documenter cette limite.

## 19. API locale

Créer des routes versionnées `/api/v1` :

- santé et démarrage : health, readiness et diagnostic local ;
- dossiers : créer, lister, filtrer, consulter, archiver ;
- documents : importer, télécharger l’original, afficher une page ;
- pages : texte, OCR, correction, recherche ;
- pièces : lister et mettre à jour ;
- informations : confirmer, corriger, rejeter, ajouter ;
- contrôle administratif ;
- évaluation ;
- alertes ;
- recherche Web : connectivité, préparation de requêtes, lancement, pause, reprise, annulation, sources et validation ;
- profils publics, affiliations, liens associatifs et désambiguïsation ;
- agents IA, désaccords et ranking externe ;
- notes et conclusion ;
- rapports ;
- référentiels et règles ;
- audit ;
- sauvegardes et vérification de restauration.

Valider toutes les entrées avec Pydantic. Utiliser des réponses d’erreur claires, sans exposer de trace technique ou de secret dans l’interface.

## 20. Sécurité obligatoire

- écoute uniquement sur `127.0.0.1` ;
- refus d’une adresse distante sans option explicite et avertissement ;
- aucune ressource Internet non autorisée ; seuls les appels sortants du module de recherche contrôlée sont permis ;
- aucune écoute réseau entrante autre que `127.0.0.1` ;
- politique de sortie réseau en liste blanche, TLS obligatoire, journalisation des domaines et possibilité de couper immédiatement les accès externes ;
- aucune transmission de PDF, pièce confidentielle, document d’identité, note interne ou donnée non nécessaire à un fournisseur externe ;
- aucun compte, aucun écran de connexion, aucun mot de passe applicatif et aucune session d'authentification ;
- aucune route `/setup`, `/login` ou `/logout` ;
- origine locale stricte, en-têtes `Host` validés et méthodes mutantes refusées depuis une origine non locale ;
- CSP restrictive ;
- validation MIME, en-tête et structure PDF ;
- limite de taille configurable ;
- protection contre traversée de chemin et noms dangereux ;
- AES-256-GCM avec AAD liée aux identifiants ;
- fichiers temporaires dans un dossier dédié, supprimé après usage ;
- journal d’audit ne contenant pas les valeurs sensibles en clair ;
- sauvegarde cohérente de la base, des documents, rapports et clé ;
- avertissement : ne jamais perdre `master.key` ;
- recommandation BitLocker ;
- séparation des documents d’identité avec niveau `RESTREINT`.

Point technique impératif : toute écriture SQLite doit être explicitement validée par `commit()` avant d'afficher un succès ou d'envoyer une redirection. En cas d'échec, exécuter `rollback()` et conserver l'état précédent.

Le lanceur Windows doit d’abord ouvrir le port, puis seulement ouvrir le navigateur. Il ne doit pas créer plusieurs onglets ni lancer silencieusement deux serveurs.

## 21. Journal d’audit

Journaliser :

- démarrage et arrêt de l'application ;
- résultat des contrôles de santé locaux ;
- import ;
- empreinte et analyse ;
- consultation d’un original ;
- OCR et confiance ;
- corrections ;
- confirmations et rejets ;
- modifications des pièces ;
- notes et justifications ;
- qualification d’alertes ;
- vérification de connectivité, requêtes Web, fournisseurs appelés et erreurs réseau ;
- sources consultées, affirmations extraites, homonymies, validations et rejets humains ;
- exécutions des agents, versions, désaccords et ranking externe ;
- conclusion ;
- génération et téléchargement de rapports ;
- sauvegarde/restauration ;
- import, activation et désactivation des règles ;
- archivage ou suppression contrôlée.

Une correction ne doit jamais effacer la valeur initiale. Utiliser des empreintes pour tracer les valeurs sensibles sans les exposer dans l’audit.

## 22. Sauvegarde et restauration

Créer depuis l’interface une sauvegarde horodatée comprenant :

- copie cohérente SQLite via l’API backup ;
- documents chiffrés ;
- rapports chiffrés ;
- `master.key` ;
- référentiel actif ;
- manifeste avec SHA-256.

Afficher que cette sauvegarde contient la clé et doit être stockée sur un support chiffré. Fournir une commande de vérification et une procédure de restauration sur copie. Ne jamais écraser automatiquement des données existantes pendant une restauration.

## 23. Tests obligatoires

Créer des fixtures fictives et tester :

- PDF natif ;
- PDF scanné ;
- PDF mixte ;
- page blanche ;
- page inclinée ;
- image sombre ;
- faible résolution ;
- tableau ;
- signature et tampon ;
- français, arabe et anglais ;
- noms propres, dates et montants ;
- dates contradictoires ;
- budget incohérent ;
- pages ou pièces manquantes ;
- doublons ;
- mention explicite du Maroc ;
- institution marocaine indirecte ;
- simple bibliographie concernant le Maroc ;
- faux positif ;
- page illisible pouvant contenir un terme sensible ;
- absence de mention marocaine ;
- Sahara occidental et cartographie ;
- conflit entre règles ;
- règle inactive ;
- texte officiel sans page identifiable ;
- PDF invalide, vide, énorme ou chiffré ;
- chiffrement et mauvaise clé ;
- démarrage direct sur le tableau de bord sans `/setup` ni `/login` ;
- rafraîchissement et redémarrage sans boucle de redirection ;
- port occupé, second lancement et serveur non prêt ;
- requête mutante provenant d'une origine ou d'un `Host` non local ;
- traversée de chemin ;
- absence d’Internet pendant une recherche et reprise contrôlée ;
- fournisseur externe indisponible, réponse incomplète ou délai dépassé ;
- tentative d’envoyer un PDF ou une donnée personnelle à un fournisseur externe ;
- homonymes portant le même nom avec affiliations différentes ;
- source officielle contredisant une source secondaire ;
- rumeur non sourcée, capture sans origine et faux profil social ;
- implication associative publique réelle mais sans lien démontré avec une incompatibilité juridique ;
- rapprochement avec un texte algérien absent, abrogé ou non validé ;
- désaccord entre agents spécialisés ;
- ranking avec preuves suffisantes, insuffisantes et contradictoires ;
- vérification que le ranking externe ne modifie pas la grille scientifique officielle ;
- rapport DOCX/PDF valide ;
- sauvegarde puis restauration sur copie.

Pour chaque test métier, préciser entrée, résultat attendu, résultat interdit, confiance, contrôle humain et preuve conservée.

## 24. Critères d’acceptation

La livraison n’est acceptable que si :

1. l’installation Windows est documentée et reproductible ;
2. le serveur écoute seulement en local ;
3. aucun écran, route, table ou mécanisme de connexion ne subsiste ;
4. le tableau de bord s'ouvre directement, sans boucle de redirection ;
5. le PDF original reste inchangé et chiffré ;
6. chaque information possède une source ou le statut `A_VERIFIER` ;
7. l’OCR affiche sa confiance ;
8. une alerte ne peut produire ni note ni décision ;
9. la section Maroc est visible, contextualisée et non discriminatoire ;
10. une règle non validée ne peut être présentée comme interdiction ;
11. les corrections sont historisées ;
12. le rapport distingue faits, alertes et appréciation humaine ;
13. la sauvegarde contient un manifeste vérifiable ;
14. tous les tests automatisés passent ;
15. le cœur local reste utilisable sans Internet et les fonctions en ligne signalent explicitement leur indisponibilité ;
16. la recherche Web ne transmet aucun document confidentiel et chaque affirmation possède URL, date, type de source et niveau de preuve ;
17. les homonymies et contradictions bloquent toute conclusion consolidée ;
18. le ranking externe est sourcé, daté, révisable et strictement séparé de la grille officielle ;
19. les agents IA ne peuvent produire seuls ni décision, ni qualification juridique définitive, ni avis favorable ou défavorable ;
20. aucun `TODO`, secret codé en dur, mot de passe par défaut ou fonction fictive ne subsiste dans la livraison.

## 25. Arborescence attendue

Créer au minimum :

```text
commission-msi/
  backend/
    app/
      api/
      core/
      models/
      schemas/
      services/
      rules/
      web_research/
      agents/
      ranking/
      reports/
      main.py
    migrations/
    tests/
    requirements.txt ou pyproject.toml
  frontend/
    src/
      components/
      pages/
      features/
      services/
      styles/
      i18n/
    tests/
    package.json
  rules/default_rules.json
  references_officielles/
  scripts/
  docs/
    ARCHITECTURE.md
    MODELE_DONNEES.md
    GUIDE_INSTALLATION.md
    GUIDE_UTILISATEUR.md
    SECURITE.md
    SAUVEGARDE_RESTAURATION.md
    MISE_A_JOUR.md
    INCIDENTS.md
    PLAN_TESTS.md
    LIMITES.md
    DECISIONS_TECHNIQUES.md
  data/.gitkeep
  install_windows.bat
  run_windows.bat
  run_tests.bat
  .env.example
  README.md
  CHANGELOG.md
  VERSION
```

## 26. Méthode de travail imposée à Claude Code

Procède dans cet ordre et ne t’arrête pas après le plan :

1. inspecter le dossier et les références fournies ;
2. rédiger `docs/ANALYSE_FONCTIONNELLE.md` et `docs/ARCHITECTURE.md` ;
3. créer l’arborescence ;
4. définir les migrations et modèles ;
5. développer le backend ;
6. développer l’interface ;
7. intégrer PDF.js, PyMuPDF et OCR ;
8. intégrer règles, contrôles et traçabilité ;
9. intégrer le module de recherche Internet contrôlée, les fournisseurs configurables et la protection des requêtes ;
10. intégrer les agents spécialisés, la vérification croisée et le ranking externe ;
11. intégrer rapports, audit et sauvegarde ;
12. créer les scripts Windows ;
13. créer les tests ;
14. installer les dépendances ;
15. exécuter formatage, vérification des types et tests ;
16. corriger jusqu’à réussite ;
17. exécuter un scénario de bout en bout local puis un scénario en ligne avec données fictives ;
18. créer une archive ZIP finale sans données réelles, sans `.venv`, sans secrets et sans cache ;
19. afficher un bilan concis : fonctions réalisées, tests réussis, limites résiduelles et chemin de l’archive.

Utilise des données de démonstration entièrement fictives. Ne supprime aucun fichier utilisateur préexistant. Ne réinitialise jamais une base contenant des données. Toute migration doit préserver les dossiers existants.

## 27. Limites à afficher dans l’application

- aucune garantie d’exhaustivité ou de zéro erreur ;
- OCR particulièrement fragile pour noms, dates, montants et arabe ;
- absence d’alerte ne prouve pas absence de risque ;
- détection textuelle insuffisante pour drapeaux, cartes, logos, tampons et signatures ;
- règles officielles susceptibles d’évoluer ;
- qualification juridique et diplomatique réservée aux autorités compétentes ;
- appréciation scientifique réservée à l’évaluateur ;
- résultats Web dépendants de la disponibilité, de l’indexation, de la langue et de la date de consultation ;
- absence de résultat Web ne prouvant ni l’absence d’activité ni l’absence de risque ;
- risque d’homonymie, de contenu obsolète, de désinformation et de biais des moteurs ou agents ;
- ranking IA indicatif, non homologué et non substitutif à l’évaluation réglementaire ou scientifique humaine ;
- qualification d’une activité comme contraire à la loi réservée aux autorités compétentes et fondée uniquement sur un texte algérien officiel validé ;
- prototype local non équivalent à une plateforme institutionnelle homologuée ;
- chiffrement applicatif ne remplaçant pas le chiffrement complet du disque.

Commence maintenant. Crée l’application complète dans le dossier courant, exécute les tests et ne te limite pas à me donner des instructions.

---

## Conseils après génération

Avant d’utiliser l’application produite par Claude Code avec des dossiers réels :

1. comparer le référentiel avec les textes officiels en vigueur ;
2. désactiver toute règle non validée ;
3. faire tester l’application par un informaticien de confiance ;
4. effectuer une recette sur des PDF fictifs ;
5. activer BitLocker ;
6. tester sauvegarde et restauration ;
7. vérifier que le serveur écoute exclusivement sur `127.0.0.1` ;
8. conserver les vrais dossiers hors de tout service cloud non autorisé ;
9. configurer une liste blanche de fournisseurs de recherche et vérifier leurs conditions de traitement des données ;
10. tester que seules des requêtes minimales et publiques quittent le poste ;
11. faire valider juridiquement le référentiel algérien utilisé pour qualifier les points sensibles ;
12. vérifier manuellement tout profil, homonymie, implication associative et ranking avant usage dans un rapport.
