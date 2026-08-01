# Incidents et conduite à tenir

*Designed by Prof. Merzoug Mohamed.*

## Principe

Une erreur technique interrompt l'action et conserve l'état précédent. Elle ne
produit jamais de résultat partiel présenté comme valide.

## Tableau des incidents

| Symptôme | Cause probable | Conduite à tenir |
|---|---|---|
| `Le port local 8731 est occupé` | Autre programme, ou serveur déjà lancé | Relancer avec `run_windows.bat --port 8732` |
| Le navigateur s'ouvre sur une page vide | Interface non compilée | `cd frontend && npm run build` |
| `Serveur non prêt` persistant | Base ou référentiel non initialisés | `alembic upgrade head`, puis consulter `GET /api/v1/readiness` |
| `ORIGINE_NON_LOCALE` | Accès depuis une autre machine | Comportement attendu : l'application ne doit jamais être exposée au réseau |
| `Déchiffrement impossible` | `master.key` absente, remplacée ou corrompue | Restaurer une sauvegarde. **Sans la clé d'origine, les données sont irrécupérables** |
| `OCR local introuvable` | Tesseract non installé | Installer Tesseract avec `fra`, `ara`, `eng`. Les pages restent marquées « vérification humaine obligatoire » |
| `PDF illisible ou corrompu` | Fichier invalide ou tronqué | Refus volontaire. Obtenir une version lisible ; aucune analyse partielle n'est produite |
| `PDF protégé par mot de passe` | Chiffrement incompatible | Refus volontaire : l'application ne contourne jamais une protection |
| `PROVENANCE_REQUISE` | Fait sans page ni passage source | Renseigner la page et l'extrait, ou cocher « saisie manuelle validée » |
| `PORTE_NON_SATISFAITE` | Porte G4/G5/G6/G7 non satisfaite | Compléter la grille, qualifier les alertes, motiver la conclusion |
| Export officiel bloqué | Fait orphelin ou alerte non qualifiée | Le message liste les éléments concernés |
| `CONTRADICTION_A_ARBITRER` | Sources divergentes | Arbitrage humain écrit et motivé requis |
| `Recherche Web indisponible` | Hors ligne, coupure ou domaine hors liste blanche | Le cœur local reste utilisable. Vérifier `MSI_NETWORK_DISABLED` et `MSI_ALLOWED_DOMAINS` |
| `ENVOI_REFUSE` | Requête contenant une donnée personnelle ou un document | Comportement attendu : reformuler en requête publique minimale |
| `SORTIE_RESEAU_REFUSEE` | Domaine hors liste blanche, ou HTTP non TLS | Vérifier les conditions d'utilisation avant tout ajout à la liste blanche |
| `DESACCORD_AGENTS` | Agents divergents ou homonymie | Arbitrage humain obligatoire ; aucune conclusion consolidée |
| `EMPREINTE DIVERGENTE` sur une source | Original modifié après enregistrement | Toutes les règles liées sont suspendues ; revalidation humaine obligatoire |
| Sauvegarde refusée à la restauration | Archive altérée ou destination non vide | L'installation d'origine reste intacte |

## Escalade

1. Consulter `GET /api/v1/diagnostic` et l'onglet **Historique**.
2. Créer une sauvegarde avant toute manipulation corrective.
3. Consigner l'incident : date, action, message exact, dossier concerné.
4. En cas de doute sur l'intégrité des données, **cesser l'usage réel** et
   restaurer une sauvegarde vérifiée sur copie.
