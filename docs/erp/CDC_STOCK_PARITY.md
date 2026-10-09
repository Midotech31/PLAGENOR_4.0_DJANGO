# Intégration CDC Studio et gestion des stocks

Référence de comparaison : conversation CDC ESSBO Tool fournie par l’utilisateur
(https://chatgpt.com/share/6ab46c21-a698-83ea-b19e-34c507c5a542), archive
CDC Studio 1.2.3 et cahier des charges ERP du 20 septembre 2026.
Le handover `HANDOVER_CDC_Studio_ESSBO_GPT_Work_20261009(1).md` fourni le
9 octobre 2026 précise les parcours de la version 1.2.3. Les sources complètes
non commitées sur le lecteur E: ne sont pas disponibles dans ce dépôt ; ce lecteur
ne doit pas être utilisé pour PLAGENOR.

## Fonctions métier et parcours natifs

| Fonction | Parcours PLAGENOR |
|---|---|
| Trois familles institutionnelles | ERP → Cahiers des charges → Créer : équipements, réactifs, travaux |
| Variables propres au dossier | Informations : référence, objets FR/AR, exercice, financement, délais, horaires, retrait |
| Lots et articles | Édition technique, rattachement au catalogue commun, quantités et unités explicites |
| Édition des articles | Recherche, duplication technique, déplacement et réordonnancement, retrait/réintégration et révisions |
| Lots réutilisables | Ajouter ou réutiliser un lot existant de même famille, avec nouvelles identités ; prix à reconfirmer |
| Articles historiques sélectionnés | Équipements/réactifs : révision source autorisée, recherche, sélection multiple, aperçu éditable, exclusion et confirmation ; identités indépendantes, exigences reprises, estimations exclues. Travaux : postes existants modifiables et duplication complète du dossier, ajout sélectif refusé avant création d’une révision incompatible |
| Retrait et réintégration | Retrait logique, données et anciennes révisions conservées |
| Échanges Excel | Classeur rempli/vide, feuille par lot, identité signée, aperçu persistant, confirmation atomique |
| Grille d’évaluation Excel | Gouvernance → Exporter la grille Excel : critères, exigences et traçabilité de la révision courante |
| Modes d’import | Mise à jour/ajout conserve les absents ; remplacement les désactive sans supprimer leur historique |
| Estimations | Accès séparé, export DZD explicite, import facultatif, source obligatoire, pas de conversion implicite |
| Budget HT/TVA/TTC | Estimations et totaux financiers : calcul decimal commun par article, lot et dossier ; taux proposé de 19 % pour les nouveaux articles, taux existants conservés |
| Classeur financier | Trois feuilles lisibles et identité masquée signée ; quantités/prix/taux importables, totaux recalculés côté serveur, cellules vides explicitement effacées, ancien export périmé refusé |
| Import général | Centre d’import CDC : classeur technique, classeur financier, pièces jointes et imports du référentiel commun selon les permissions |
| Tableaux du modèle | Consultation paginée/recherche, paragraphes autorisés, ajout/retrait versionné de lignes simples ; tableaux gérés et structures incompatibles protégés |
| Guide | Neuf étapes du dossier, aide sur droits, aperçus périmés, génération, revues, historique et archivage ; FR/EN/AR |
| Historique | Révisions immuables ; reprise administrative créant une nouvelle révision |
| Contrôles et documents | Références FR/AR, nettoyage ciblé, OOXML, normalisation, conversion PDF réelle, contrôle des pages et approbation |
| Délégation | Comptes et permissions PLAGENOR, retrait immédiat des droits lors d’une réaffectation |
| Catalogue stock | Articles, catégories, fabricants/fournisseurs, unités et conversions, criticité et seuils |
| Flux physiques | Réception, quarantaine/contrôle, consommation, réservation/libération, transfert, retours et contre-passations |
| Lots physiques | Identité fabricant, dates, stabilité après ouverture, FEFO, traçabilité des analyses |
| Inventaire | Campagne déléguée, comptage, écarts/recomptage, approbation et écritures de correction |
| Stockage/biobanque | Hiérarchie, grilles, positions, aliquots, cycles froid, températures, incidents et transfert de masse |
| Préparations internes | Produits sources, lots, quantités, protocole et traçabilité |
| Sécurité chimique | FDS et pièces, dangers renseignés, incompatibilités configurées |
| Approvisionnement | Prévisions explicables, décisions humaines, plan approuvé, CDC, commandes, réceptions partielles et stock |
| Imports stock | Catalogue, stock initial, réceptions, emplacements, échantillons, prix, plan et températures : aperçu/confirmation/rapport |
| Pilotage | Alertes regroupées, rapports filtrés, exports, identification/étiquettes, recherche par fournisseur et emplacement |

## Garanties du parcours Excel

- Le classeur est lié au dossier, à sa révision et au contenu exporté.
- Formules, macros, connexions externes, doublons et identités déplacées sont rejetés.
- Le serveur conserve l’aperçu pendant 24 heures ; aucune donnée métier ne change avant confirmation.
- La confirmation reverrouille la tâche, le dossier et l’aperçu, puis revérifie droits et version.
- Un double envoi du même aperçu ne crée pas deux révisions.
- Un changement de dossier, de délégation, de version ou de droit financier empêche une application indue.
- Liens catalogue, facteurs d’unité et snapshots sont préservés. Une unité structurée ne peut pas être remplacée librement dans Excel.
- Les prix internes ne remplissent jamais les cases réservées aux soumissionnaires.

La grille d’évaluation est un export de lecture distinct du classeur d’import des
lots. Elle reprend les critères et exigences retenus, les libellés des lots et
articles enregistrés dans la révision, ainsi que sa référence, son numéro, son
identifiant et son empreinte SHA-256. Les estimations financières restent exclues,
y compris pour un relecteur technique délégué. Les nombres restent numériques et
les textes sont des cellules littérales, même lorsqu’ils commencent par `=`.
Les en-têtes suivent la langue de l’interface ; les feuilles arabes utilisent la
lecture de droite à gauche. Les libellés métier restent ceux de la révision.
Un critère rattaché à un lot retiré conserve l’identifiant du lot lorsqu’aucun
libellé n’est présent dans le catalogue de cette révision.

## Adaptations et limites explicites

L’authentification locale, le lanceur EXE, les profils SQLite et le fonctionnement
hors ligne de CDC Studio ne sont pas dupliqués dans ce serveur web. Les comptes,
PostgreSQL, sauvegardes et conversions Linux sont ceux de PLAGENOR.
Les formulaires web enregistrent explicitement les modifications validées ; ils ne reproduisent pas la sauvegarde à chaque frappe de certaines versions du client local.
La reprise d’une révision documentaire n’est pas une restauration globale de base.

Les modèles complets restent soumis à leurs correspondances documentaires :
les équipements et réactifs nécessitent le rattachement de chaque lot à son
emplacement institutionnel ; le modèle Travaux conserve son lot et ses postes
qualifiés. Un changement incompatible d’allotissement est signalé et bloque la
génération au lieu de produire des annexes incohérentes. Cette limite existait
dans le moteur repris ; elle ne doit pas être présentée comme une génération
universelle de modèles arbitraires.

L’archive installable ne contient pas les sources complètes du binaire. La
comparaison établit les parcours identifiés dans les références et le code,
pas une équivalence binaire certifiée ni une validation juridique automatique.

## Vérification

Tests métier et HTTP : `erp/test_cdc_exchange.py`, `erp/test_cdc_exports.py` ; régressions existantes :
`erp/test_cdc_workflow.py`, `erp/test_operations.py`, `erp/test_procurement.py`,
`erp/test_imports.py`, `erp/test_consumption.py`, `erp/test_biobank.py`.
Parcours navigateur bureau/mobile : `e2e/cdc-exchange.spec.js`.
Les résultats exécutés et le commit final sont rapportés dans la PR et la CI.

La finalisation du 9 octobre est vérifiée par `erp/test_cdc_completion.py` et
`e2e/cdc-completion.spec.js` : copie sélective, confirmation, refus atomiques,
révocation des droits, documents XLSX altérés, dates/formules/macros/liens externes,
reprise des anciennes révisions sans clé d’article explicite, et flux financiers.
Les dossiers de 57 et 74 articles sont des jeux **synthétiques**, avec reprise,
retrait de lot, conservation des révisions et DOCX rendus en PDF par la CI.
Ils ne sont pas les deux dossiers réels conservés dans CDC Studio.
Les imports et copies utilisent des écritures groupées ; les tests mesurent la
croissance bornée des requêtes. Le stock conserve ses calculs Decimal exacts avec
une lecture groupée des contenants, sans une requête par article.

La CI impose cinq validations (SQLite, PostgreSQL, navigateurs, sécurité,
conteneur), avec 100 % des instructions applicatives mesurées. Les preuves de
restauration PostgreSQL produites par cette CI concernent sa base synthétique.
Le contrôle `scripts/qualify_cdc_restore.py` est limité aux deux bases locales
nommées de la CI. Il compare les empreintes et effectifs des données CDC après
`pg_restore`, puis confirme les aperçus restaurés et vérifie leur idempotence,
les exigences copiées et les totaux financiers. Il refuse une base de production.
Une restauration d’une sauvegarde réelle de production en environnement isolé
et la recette connectée des dossiers institutionnels nécessitent leurs accès et
leurs données ; elles doivent être consignées séparément avant de revendiquer
une qualification opérationnelle intégrale.
