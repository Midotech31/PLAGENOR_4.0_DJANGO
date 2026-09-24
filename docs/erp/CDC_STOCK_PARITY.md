# Intégration CDC Studio et gestion des stocks

Référence de comparaison : conversation CDC ESSBO Tool fournie par l’utilisateur
(https://chatgpt.com/share/6ab46c21-a698-83ea-b19e-34c507c5a542), archive
CDC Studio 1.2.3 et cahier des charges ERP du 20 septembre 2026.

## Fonctions métier et parcours natifs

| Fonction | Parcours PLAGENOR |
|---|---|
| Trois familles institutionnelles | ERP → Cahiers des charges → Créer : équipements, réactifs, travaux |
| Variables propres au dossier | Informations : référence, objets FR/AR, exercice, financement, délais, horaires, retrait |
| Lots et articles | Édition technique, rattachement au catalogue commun, quantités et unités explicites |
| Lots réutilisables | Ajouter ou réutiliser un lot existant de même famille, avec nouvelles identités ; prix à reconfirmer |
| Retrait et réintégration | Retrait logique, données et anciennes révisions conservées |
| Échanges Excel | Classeur rempli/vide, feuille par lot, identité signée, aperçu persistant, confirmation atomique |
| Modes d’import | Mise à jour/ajout conserve les absents ; remplacement les désactive sans supprimer leur historique |
| Estimations | Accès séparé, export DZD explicite, import facultatif, source obligatoire, pas de conversion implicite |
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

## Adaptations et limites explicites

L’authentification locale, le lanceur EXE, les profils SQLite et le fonctionnement
hors ligne de CDC Studio ne sont pas dupliqués dans ce serveur web. Les comptes,
PostgreSQL, sauvegardes et conversions Linux sont ceux de PLAGENOR.
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

Tests métier et HTTP : `erp/test_cdc_exchange.py` ; régressions existantes :
`erp/test_cdc_workflow.py`, `erp/test_operations.py`, `erp/test_procurement.py`,
`erp/test_imports.py`, `erp/test_consumption.py`, `erp/test_biobank.py`.
Parcours navigateur bureau/mobile : `e2e/cdc-exchange.spec.js`.
Les résultats exécutés et le commit final sont rapportés dans la PR et la CI.
