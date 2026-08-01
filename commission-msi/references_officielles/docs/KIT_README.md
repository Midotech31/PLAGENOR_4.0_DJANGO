# Kit complet de développement - Commission MSI

Ce kit doit être remis intégralement à Claude Code. Il contient les cinq documents sources fournis par l'utilisateur, leurs extractions de travail, les données structurées et le prompt maître.

## Ordre de lecture obligatoire

1. `docs/CONTRAT_FAIL_SAFE.md`
2. `donnees/manifest_sources.json`
3. tous les fichiers de `references_officielles/originaux/`
4. `docs/SYNTHESE_SOURCES_ET_CONTRADICTIONS.md`
5. les JSON de `donnees/`
6. `PROMPT_MAITRE_CLAUDE_CODE_V2.md`

Les originaux prévalent toujours sur les extractions et synthèses. Les extractions Markdown servent uniquement à la recherche et à l'indexation. Toute règle doit être reliée à un original, une page, une version et un statut de validation.

## Avertissement de fiabilité

Le « zéro erreur » absolu n'est pas techniquement démontrable. Le kit impose donc une politique plus sûre : aucune décision automatique, aucune affirmation sans source, suspension en cas de doute, original immuable, contrôles redondants et validation humaine obligatoire.

L'application demandée n'a aucun compte ni écran de connexion. Elle s'ouvre directement sur le tableau de bord et reste strictement liée à `127.0.0.1`. La protection d'accès repose donc sur le poste Windows, le chiffrement du disque, les permissions de fichiers et l'absence totale d'exposition réseau.

## Contenu

- `references_officielles/originaux/` : les cinq documents fournis, inchangés et contrôlés par empreinte ;
- `references_officielles/extractions/` : texte de travail du manuel et du guide pour recherche locale ; les scans officiels restent à lire sur l'image originale afin de ne pas figer un OCR arabe incertain ;
- `donnees/manifest_sources.json` : statut, autorité, pagination et SHA-256 de chaque source ;
- `donnees/exigences_sourcees.json` : exigences reliées aux sources et pages, traductions à valider et contradictions ;
- `donnees/catalogue_pieces.json` : les quatorze pièces et les champs de la fiche technique ;
- `donnees/grille_scientifique.json` : grille de saisie humaine, sans notation automatique ;
- `donnees/regles_vigilance_initiales.json` : règles d'alerte initiales explicables et non décisionnelles ;
- `donnees/sources_manquantes_a_valider.json` : références citées mais absentes, donc inactives ;
- `donnees/statuts_et_decisions.json` : vocabulaire contrôlé et sorties automatiques interdites ;
- `donnees/tests_acceptation.json` : tests critiques avec tolérance zéro pour la mise en service ;
- `docs/` : hiérarchie des sources, contradictions et contrat fail-safe ;
- `PROMPT_MAITRE_CLAUDE_CODE_V2.md` : instruction complète de construction.

Ne jamais utiliser de vrais dossiers confidentiels pendant le développement ou les tests.
