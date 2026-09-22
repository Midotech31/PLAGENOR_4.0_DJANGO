# Extension ERP PLAGENOR — architecture et audit initial

## Référence et périmètre

Base de travail : `82565afadc6e85760b924eb37ce105e37f8812a1` sur `main`.
La CI de cette base, run `35545126576`, a été relue : quatre jobs réussis.
L’extension est isolée sur `feature/erp-foundations-20260921`. Aucune fusion ni
modification de production ne fait partie de cette première tranche.

Le périmètre de cette tranche est le référentiel partagé : articles, catégories,
fournisseurs/fabricants, unités, conversions propres aux articles, emplacements,
délégations et historique. Il ne constitue pas encore le module ERP complet.
Les stocks, la biobanque et le CDC ne sont pas déclarés opérationnels par la
présence de ces référentiels.

## Architecture réellement présente dans PLAGENOR

| Domaine | État observé | Décision |
|---|---|---|
| Identité | `accounts.User`, six rôles existants | Réutilisation exclusive ; aucun second compte |
| Services | `core.Service` | Réutilisation pour les nomenclatures de consommation |
| Demandes | `core.Request`, canal et canal de facturation distincts | Conserver les workflows et les règles IBTIKAR/GENOCLAB/OHB |
| Échantillons | Listes JSON de `Request.sample_table` et des soumissions IBTIKAR | Ajouter ultérieurement un identifiant de spécimen lié à sa source et sa révision ; aucune migration déduite d’un intitulé |
| Organisations/laboratoires | Champs textuels des comptes, pas de modèle normalisé | Ne pas réécrire les profils ; emplacements structurés indépendants |
| Fournisseurs/catalogue de biens | Pas de référentiel métier équivalent | Créer un référentiel unique, réutilisable par les achats |
| Tâches | Affectations de demandes, pas de modèle générique de tâche | Ne pas prétendre réutiliser un modèle inexistant ; extension dédiée ultérieure |
| Audit | `RequestHistory` pour le workflow ; `core.audit` pour les logs | Historique ERP persistant avec acteurs existants et journalisation après commit |
| Notifications | `notifications.Notification`, lien configurable | Réutiliser pour les futures assignations et synthèses |
| Documents | Génération DOCX/PDF, conversion et archives existantes | Réutiliser ; ne pas déployer le serveur documentaire local CDC |

## Identification du CDC fourni

Archive : `CDC_Studio_ESSBO_1.2.3_LIVRAISON_DIRECTION.zip`.
SHA-256 : `ebc152e60f18f362842feee6d9333588646d3784131f879d00471fab118dce52`.
L’archive contient un installateur Windows, deux rapports de mise à niveau,
un fichier d’empreinte et une notice ; elle ne contient pas les sources Python.
L’installateur n’a pas été exécuté pendant cet audit.

SHA-256 de l’installateur :
`ce653c3e2da4ca93fe3ebd4ae7f91b632b7dcaa5fe1f4c8fc5e74bf9a4bd0c22`.
Un espace source local a été retrouvé avec un installateur de livraison ayant
exactement cette empreinte. Cet espace contient des modifications non commitées.
Une copie de travail et un inventaire d’empreintes ont été produits sans modifier
l’original. Cette association ne remplace pas une reconstruction reproductible
prouvant l’équivalence de chaque module source avec le binaire installé.

La suite du CDC a été exécutée sur cette copie, avec un profil de test isolé :
**71 tests réussis en 347,57 secondes**. Ce résultat concerne les tests disponibles,
pas une certification de l’installateur, de tous les parcours graphiques, ni une
validation juridique des modèles documentaires.

## Réutilisation native du CDC

| Composant CDC | Destination / traitement |
|---|---|
| `docengine`, édition OOXML conservatrice | Réutiliser le moteur après adaptation des chemins et tests Linux ; conserver les parties non modifiées |
| `catalog`, `consultation`, `institutional`, `common_data` | Reprendre les variables propres au dossier et la séparation des informations institutionnelles |
| `procurement`, `lot_catalog`, `schedule_adapter` | Adapter les lots d’achat, les articles et la synchronisation CPTC/BPU/DQE |
| `lot_workbook`, imports prévisualisés | Conserver le contrôle des cellules, l’identité signée, la révision et la confirmation atomique |
| `Dossier`, `Revision`, `Generation` | Modèles natifs liés à `AUTH_USER_MODEL`, versions immuables et générateur PLAGENOR |
| `CatalogItem`, `CatalogItemRevision` | Fusionner avec `erp.Article` et son historique, pas de deuxième catalogue |
| `SavedLot`, `SavedLotItem` | Gabarits de lots d’achat ; ne pas les confondre avec les lots physiques de réactifs |
| `EstimateEntry` | Estimation interne propre au dossier, séparée des prix historiques et des documents remis aux soumissionnaires |
| `AuditEvent` local | Adapter à PostgreSQL multiutilisateur ; ne pas reprendre une chaîne fondée sur une hypothèse de verrou SQLite global |
| Authentification locale, récupération locale, cookies CDC | Supprimer du périmètre d’intégration ; employer uniquement PLAGENOR |
| Lanceur Windows, verrou de processus local, profils SQLite, serveur local | Ne pas intégrer au serveur PLAGENOR |
| Conversion Word COM / worker CDC | Remplacer par la chaîne Linux/LibreOffice et le stockage PLAGENOR |

## Points de vigilance établis

1. Le CDC utilise une identité locale automatique privilégiée. Elle est adaptée
   à son contexte local, pas à une intégration web multiutilisateur.
2. `finance.py` fixe une TVA de 19 %. Les achats devront porter leur propre
   configuration fiscale ; cette constante ne sera pas propagée à l’ERP.
3. Les unités et certaines quantités du catalogue CDC sont des chaînes. Leur
   migration nécessitera une correspondance explicite, sans conversion devinée.
4. Les révisions documentaires et les valeurs de catalogue actuelles doivent
   rester distinctes : modifier un article ne doit pas modifier un CDC finalisé.
5. Le worker local dépend d’un verrou de processus et de transactions SQLite
   `IMMEDIATE`. Ces hypothèses ne valent pas pour plusieurs workers PostgreSQL.
6. Le couple lecture-création des articles CDC n’a pas de contrainte unique sur
   son empreinte. La déduplication doit être renforcée au niveau transactionnel.
7. La lecture du code montre que `copied_item` produit un préfixe `reuse-`, alors
   que `validate_catalog` accepte `source-` et `new-`. Ce chemin doit être repris
   et testé explicitement lors du portage, malgré la réussite de la suite actuelle.
8. Certains tests CDC portent un chemin absolu vers leur interpréteur Windows.
   Ces chemins devront être supprimés des tests intégrés à la CI Linux.
9. Les rapports de génération CDC distinguent validation OOXML, validation Word
   non exécutée et validation juridique non acquise. Ces réserves sont conservées.

## Frontières de données

- `erp.Article` décrit un bien, pas une prestation ni un échantillon biologique.
- `erp.Party` représente un fournisseur, un fabricant ou les deux, sans créer de compte.
- Les prix sont des observations immuables et facultatives. Une absence de prix
  n’est pas convertie en zéro. Aucune TVA n’est appliquée par le référentiel.
- L’unité de gestion d’un article et la dimension d’une unité sont immuables
  après création. Les mouvements futurs conserveront leur unité et leur facteur.
- La fermeture transitive des emplacements autorise une hiérarchie configurable.
  Les réorganisations sont sérialisées et les identifiants des descendants restent stables.
- Les délégations ne créent pas de rôle global. Les capacités catalogue/coût sont
  limitées par catégorie exacte ; les capacités stockage par sous-arbre d’emplacement.
  Les vues comme les mutations contrôlent le périmètre côté serveur.
- Les métadonnées communes d’un catalogue ne représentent pas un droit de lecture
  des prix, des quantités d’un autre périmètre ou de données biologiques.

## Ordre de réalisation et conditions de passage

A. Audit et architecture — cette note et les preuves source/test.
B. Référentiels — application native, formulaires, délégations, versions et tests.
C. Lots, contenants, réceptions, ledger et balances — mouvements atomiques,
   idempotence et contre-passations ; aucune quantité libre utilisée comme stock.
D. Inventaires et alertes — ajustements approuvés, notifications regroupées.
E. Biobanque — pont depuis les JSON source, aliquots, positions uniques, chaîne de
   possession, freeze/thaw, températures et transferts d’urgence.
F. Prestations — nomenclatures, réservations et consommations réelles confirmées.
G. Prévisions — méthodes explicables, qualité des données, projets sans double
   comptage, stock utilisable, échéances et validation humaine.
H. CDC — reprise native du moteur et des révisions, rapprochement du catalogue,
   plan → lots d’achat → documents ; aucune seconde authentification.
I. Exports et tableaux de bord — contrôlés par périmètre et accès aux coûts.
J. Recette — PostgreSQL, concurrence, migrations depuis la production, sauvegarde
   et restauration, navigateurs, accessibilité et PDF inspectés page par page.

Une nouvelle application est ajoutée explicitement au périmètre de couverture
et au contrôle statique. Le seuil existant de 100 % n’est pas diminué. Un test
SQLite ne sert pas de preuve de verrouillage PostgreSQL. Les étapes non validées
restent ouvertes et ne sont pas fusionnées en production.

## Références techniques consultées

- Django 5.2, transactions et `select_for_update` :
  `https://docs.djangoproject.com/en/5.2/topics/db/transactions/`
  `https://docs.djangoproject.com/en/5.2/ref/models/querysets/`
- PostgreSQL, verrouillage explicite et ordre cohérent d’acquisition :
  `https://www.postgresql.org/docs/17/explicit-locking.html`
- OMS, LQSI, achats et inventaire ; registre des produits dangereux :
  `https://extranet.who.int/lqsi/activitiesqse/2/12`
  `https://extranet.who.int/lqsi/node/111`
- GS1, identifiants d’application pour lot et péremption :
  `https://ref.gs1.org/ai/10` et `https://ref.gs1.org/ai/17`.
- ISO 20387:2018, référence biobanque ; le projet de révision ne remplace pas une
  norme publiée. Aucune conformité ou accréditation n’est déclarée pour le logiciel.
  `https://www.iso.org/fr/standard/67888.html`
