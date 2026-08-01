# Mise à jour

*Designed by Prof. Merzoug Mohamed.*

## Règle absolue

Une mise à jour **ne réinitialise jamais** une base contenant des données et
**préserve toujours** les dossiers existants.

## Procédure

1. **Sauvegardez** (`POST /api/v1/sauvegardes`) et vérifiez l'archive.
2. Arrêtez l'application.
3. Remplacez le code, en conservant `data/` et `.env`.
4. Réinstallez les dépendances :
   `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`
5. Appliquez les migrations : `cd backend && alembic upgrade head`
6. Recompilez l'interface : `cd frontend && npm install && npm run build`
7. Exécutez `run_tests.bat`. Un échec critique interdit la remise en service.
8. Relancez et contrôlez `GET /api/v1/readiness` et `GET /api/v1/diagnostic`.

## Mise à jour du référentiel de règles

`rules/default_rules.json` est versionné. Au démarrage :

- une règle **nouvelle** est créée ;
- une règle dont la `version` a changé est remplacée, **l'ancienne définition
  étant historisée** dans `rule_versions` ;
- une règle dont la version est identique n'est pas écrasée : les décisions
  humaines (activation, suspension) sont conservées.

Une règle `is_normative` reste inactive tant que son texte officiel n'est pas
présent, validé, d'empreinte cohérente et rattaché à un passage paginé.

## Ajout d'une source officielle

1. Déposez l'original dans `references_officielles/originaux/`.
2. Ajoutez son entrée au manifeste : date, autorité, statut, champ
   d'application, pagination et empreinte SHA-256.
3. Lancez `scripts/verify_sources.py`.
4. Importez le texte, rattachez le passage exact **et sa page**, puis validez-le.
5. Alors seulement, la règle dérivée peut être activée.

## Après mise à jour

Régénérez la matrice de traçabilité :

```
backend\.venv\Scripts\python.exe scripts\generate_matrix.py
```
