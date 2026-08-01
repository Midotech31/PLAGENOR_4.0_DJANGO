# Modèle de données

*Designed by Prof. Merzoug Mohamed.*

## Interdiction structurante

Aucune table `users`, `sessions`, `credentials` ou équivalente n'existe. Le test
`test_no_authentication_tables_exist` le vérifie à chaque exécution.

Les colonnes suffixées `_cipher` contiennent des blobs **AES-256-GCM** dont
l'AAD est liée à l'identifiant logique de l'objet.

## Cœur documentaire

| Table | Contenu |
|---|---|
| `dossiers` | id UUID, `reference` unique, title, organizer, status, priority, page_count, original_name, storage_path, sha256, size, champ international déclaré, validation G7, dates |
| `documents` | dossier_id, type, original_name, encrypted_path, sha256, size, version, `sensitivity` (`ORDINAIRE`/`RESTREINT`), page_count |
| `pages` | document_id, page_no, mode, `original_text_cipher`, `corrected_text_cipher`, confidence, char_count, image_count, width/height, rotation, needs_ocr, is_blank, is_difficult, duplicate_of, empreinte de texte, version du moteur |
| `ocr_runs` | page_id, engine, version, languages, parameters_json, confidence, mots sous seuil, `result_cipher`, `boxes_cipher`, succès, message |
| `extracted_items` | dossier_id, key, label, `initial_value_cipher`, `current_value_cipher`, page_id, page_no, `source_cipher`, bbox_json, extraction_mode, confidence, status, contrôle renforcé, saisie manuelle validée |
| `corrections` | entity_type, entity_id, field, `previous_hash`, `new_hash`, reason, evaluator_label — **la valeur initiale n'est jamais effacée** |

## Pièces, personnes, contrôles

`piece_definitions`, `piece_checks`, `persons`, `institutions`, `affiliations`,
`participations`, `administrative_checks`.

Les pièces sourcées (14, `SRC-DOSSIER-PIECES`) et les pièces complémentaires de
travail sont distinguées par leur `source_ref`.

## Appréciation humaine

| Table | Règle |
|---|---|
| `evaluation_criteria` | 5 critères, total 100 — issus de `grille_scientifique.json` |
| `evaluation_entries` | note saisie, `justification_cipher`, pages sources, auteur — **jamais alimentée par un agent** |
| `findings` | catégorie, code de règle, libellé, déclencheur et contexte chiffrés, page, priorité, confiance, explication, vérification recommandée, source, statut humain, signature de détection |
| `notes` | notes, réserves, questions et conclusion motivée (`body_cipher`) |
| `reports` | format, brouillon/officiel, chemin, sha256, version, évaluateur |

## Référentiel et traçabilité

`rules`, `rule_versions`, `regulations`, `regulation_passages`, `requirements`,
`source_documents`, `conflicts`.

Une règle `is_normative=true` ne peut être active que si elle est rattachée à
un texte `VALIDE`, présent, d'empreinte cohérente et porteur d'un passage
paginé.

## Module en ligne

| Table | Contenu |
|---|---|
| `web_research_runs` | campagne : statut, périmètre, connectivité, fournisseurs, approbation, échec explicite, justification de mise à l'écart |
| `web_queries` | requête minimale, objet, approbation, fournisseur, envoi, résultats, rapport de redaction |
| `web_sources` | URL canonique, domaine, éditeur, date de publication, **date de consultation**, palier de source, extrait chiffré, empreinte |
| `online_claims` | affirmation atomique chiffrée, nature, statut de preuve, confiance, sources, nombre de sources indépendantes, texte algérien lié, statut humain |
| `person_web_profiles` | profil public consolidé, variantes de noms, affiliations vérifiées |
| `association_links` | engagement public constaté, `legal_link_established` par défaut `false` |
| `identity_disambiguations` | candidats, discriminants, décision (`HOMONYMIE_POSSIBLE` par défaut) |
| `agent_assessments` | restitution par agent : axe, note proposée, intervalle d'incertitude, suffisance des preuves, justification chiffrée |
| `agent_disagreements` | sujet, axe, agents, dispersion, description — bloque toute conclusion consolidée |
| `event_rankings` / `event_ranking_axes` | classement externe indicatif, seuils, versions d'agents, décision humaine par axe |

## Exploitation

`audit_events` (empreintes uniquement), `backups` (manifeste SHA-256, présence
de `master.key`, vérification).

## Migrations

Alembic, `render_as_batch=True` (SQLite). Toute migration doit préserver les
dossiers existants ; aucune ne réinitialise une base contenant des données.
