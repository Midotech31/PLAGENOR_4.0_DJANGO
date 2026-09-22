# Audit de persistance du CMS PLAGENOR 4.0

Date : 22 septembre 2026. Base : `e830a94a7898c24083e10463c7eaedbf89cd0b96`.

## Périmètre et méthode

L'audit porte sur le CMS réellement présent dans PLAGENOR, indépendamment de l'extension ERP non publiée. Les essais utilisent une base SQLite et des médias synthétiques isolés. Aucun tarif, compte, dossier ou document métier réel n'a été modifié pour les essais.

Les contrôles combinent parcours dans un navigateur, requêtes HTTP, lectures par une connexion indépendante à la base, rechargement, réouverture et nouvelle session. Les tests Python et les scénarios Playwright sont conservés dans le dépôt ; les journaux et captures détaillés sont conservés hors du dépôt.

## Anomalies reproduites et corrections

| Anomalie | Cause et correction |
|---|---|
| Tarifs enregistrés mais champs vides à la réouverture | Des valeurs localisées comme `2345,67` étaient injectées dans des contrôles HTML numériques. Les contrôles concernés utilisent désormais un format numérique non localisé ; l'affichage destiné à la lecture reste localisé. |
| Configuration tarifaire perdue lors d'une sauvegarde partielle | Les champs absents étaient interprétés comme des effacements. Les groupes non transmis sont préservés ; un marqueur explicite distingue le retrait de tous les champs personnalisés. |
| Traductions non transmises effacées | Une mise à jour partielle du contenu ne remplace plus les autres langues par des chaînes vides. Une valeur vide explicitement transmise conserve son sens d'effacement. |
| Multiplicateurs supprimés réapparaissant | Une table vide explicitement enregistrée remplace l'ancienne configuration et ne réintroduit pas silencieusement les valeurs du catalogue. |
| Données CMS périmées selon le processus serveur | Le cache partagé uniquement à l'intérieur d'un processus a été remplacé par une lecture cohérente avec la base, mutualisée pendant une requête. |
| Montants acceptés avec une précision incompatible | Les tarifs passent désormais la validation complète du modèle avant écriture. Les réponses de succès suivent une écriture atomique et une relecture. |
| Perte des saisies lors du refus d'un service | Le formulaire est réaffiché avec les données transmises et un statut d'erreur explicite. Les fichiers doivent être sélectionnés à nouveau, sans message de sauvegarde réussie. |
| Moyens de paiement dupliqués | L'ajout répété ne provoque plus une erreur d'unicité ; l'entrée existante est signalée. |
| Troisième version d'un modèle impossible | L'unicité porte désormais sur le seul modèle actif ; plusieurs versions inactives peuvent être conservées. Une migration dédiée est fournie. |
| Service/type d'un modèle modifiés à l'écran mais inchangés en base | Les champs éditables sont effectivement appliqués, validés et relus. |
| Faux fichiers DOCX acceptés | Le contenu du fichier est validé, pas uniquement son extension. Un rejet conserve le modèle actif précédent et les champs saisis. |
| Modèles stockés à distance ignorés | La génération lit le stockage configuré et prépare une copie locale vérifiée ; un modèle enregistré mais introuvable n'est plus remplacé silencieusement. |
| Blocs documentaires vides dans leur formulaire | Le nom de contexte `block` entrait en collision avec le mécanisme d'héritage des pages. Les données sont maintenant exposées sous un nom distinct. |
| Ancien document conservé après modification d'un modèle ou d'un bloc | Les signatures du cache incluent les versions et le contenu pertinents, y compris la suppression d'un bloc ancien et la modification d'un champ sans changement d'identifiant. |
| Blocs et relations partiellement enregistrés | La sauvegarde du bloc et de ses services associés est atomique. Les valeurs invalides sont refusées et restent disponibles pour correction. |
| Type tarifaire ou options altérés à la réouverture | Le type de forfait total est présent dans le sélecteur ; les options existantes sont sérialisées sans perdre les virgules contenues dans une option. |

## Vérifications réalisées

Les nouveaux tests contrôlent notamment les tarifs des quatre canaux administratifs, les limites numériques, les mises à jour partielles, les traductions, la visibilité du contenu public, les nouvelles sessions, les techniques, les comptes et profils membres, les annonces, les moyens de paiement, les versions de modèles, leur stockage et les relations des blocs documentaires. Les suppressions logiques sont distinguées des suppressions physiques.

Le parcours navigateur principal a validé quinze points de contrôle distincts, avec relecture des données synthétiques par un autre processus. Il inclut les sauvegardes refusées sans perte de saisie, les tarifs, les contenus trilingues, trois versions successives d'un modèle, sa modification, sa suppression et une déconnexion/reconnexion réelle. Des tests Playwright supplémentaires reproduisent la persistance des décimales et la conservation des saisies refusées sur ordinateur et mobile.

Les contrôles Django, migrations, compilation des pages, syntaxe JavaScript et analyse statique ont été exécutés. Le seuil de couverture global de 100 % n'a pas été abaissé. Les totaux exacts de chaque passe sont consignés dans les journaux et dans la demande de fusion ; un succès fonctionnel ne doit pas être confondu avec le franchissement du seuil de couverture.

## Rubriques demandées mais absentes comme modules autonomes

Cette application ne dispose pas de modèles CRUD autonomes pour les enseignants, programmes pédagogiques, formations, structures institutionnelles, conférences, colloques, événements, galeries, menus/sous-menus ou gestion avancée du référencement. Des informations institutionnelles et de page d'accueil sont gérées par `PlatformContent` ; cela ne constitue pas un CMS universitaire complet pour ces autres domaines. Ces rubriques ne sont pas déclarées validées.

## Limites avant clôture de l'audit global

La présente correction n'est pas une certification exhaustive de tous les chemins d'administration. Restent à qualifier séparément :

- le téléversement historique des modèles globaux, qui utilise encore un emplacement dans l'arborescence applicative, ainsi que son effet réel pour chaque générateur documentaire ;
- les scénarios d'échec et de conservation des saisies de tous les autres formulaires d'administration, au-delà des parcours ciblés et des tests de non-régression exécutés ;
- la parité avec le stockage et la configuration de production, la qualification PostgreSQL de la migration et les conflits multi-utilisateurs réels ;
- la couverture des écrans Django Admin et les rubriques institutionnelles non implémentées dans PLAGENOR.

Aucun résultat de test sur une base isolée n'est présenté comme un essai d'écriture sur la production. Les anciens essais et leurs échecs sont conservés dans le dossier de preuves, sans être réétiquetés comme réussis.

## Reprise et preuves

Worktree de vérification : `E:\PLAGENOR_CMS_VERIFY_20260922`.
Branche : `audit/cms-verification-20260922`.
Preuves : `E:\PLAGENOR_ERP_20260921_EVIDENCE\CMS_VERIFICATION_20260922T131536Z`.
Le worktree d'audit initial et celui de l'ERP ont été préservés séparément.
