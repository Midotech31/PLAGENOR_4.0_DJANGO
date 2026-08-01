# Plan de tests

*Designed by Prof. Merzoug Mohamed.*

## Principe

Aucun test réussi ne transforme l'application en autorité décisionnelle. Un
échec critique interdit l'usage réel jusqu'à correction et nouvelle validation.

**Tous les tests utilisent exclusivement des dossiers fictifs et synthétiques**
(`backend/tests/fixtures/synthetic.py`).

## Exécution

```bat
run_tests.bat
```

ou séparément :

```bat
cd backend && set PYTHONPATH=. && .venv\Scripts\python.exe -m pytest tests -q
cd frontend && npm run test && npm run typecheck
```

## Couverture par fichier

| Fichier | Portée |
|---|---|
| `test_ingestion_and_pages.py` | PDF natif, scanné, mixte, blanc, incliné, tableau, arabe, anglais, doublons, faux PDF, PDF vide/corrompu/chiffré/volumineux, OCR indisponible, corrections, recherche |
| `test_vigilance_rules.py` | Maroc explicite, institution indirecte, bibliographie, faux positif, absence de mention, Sahara occidental, page illisible, règles inactives, contradictions, frontières de mots, normalisation arabe |
| `test_evaluation_and_report.py` | Provenance obligatoire, notes hors bornes, justification, total bloqué, conclusion en liste fermée, brouillon filigrané, porte G7, fait orphelin, parcours complet DOCX/PDF |
| `test_security_and_backup.py` | Démarrage direct, absence de tables et routes d'authentification, port occupé, `Host`/`Origin`/`Referer` non locaux, en-têtes, traversée de chemin, AES-GCM, mauvaise clé, AAD, données restreintes, sauvegarde/restauration, intégrité des sources, transaction interrompue |
| `test_web_research.py` | Interrupteur réseau, liste blanche, TLS, redaction des requêtes, refus d'envoi de PDF, hors ligne, approbation, panne fournisseur, absence de résultat, pause/reprise/mise à l'écart, état enrichi, audit |
| `test_agents_and_ranking.py` | Agents isolés, homonymies, absence de preuve, texte algérien absent/abrogé/non validé, sources faibles et non datées, contradiction officielle/secondaire, signaux prédateurs, désaccords, ranking NR, séparation stricte de la grille officielle |
| `frontend/tests/ui.test.tsx` | Ouverture directe sans connexion, signature, limites, serveur non prêt, RTL arabe, lien d'évitement, statut jamais porté par la seule couleur, alertes annoncées |

## Correspondance avec les tests d'acceptation du kit

| Test | Couvert par |
|---|---|
| `ACC-001` ingestion | `test_native_pdf_is_stored_unchanged_and_fingerprinted`, `test_invalid_pdfs_are_refused_without_partial_result` |
| `ACC-002` OCR | `test_scanned_pdf_requires_ocr_and_is_marked_uncertain`, `test_ocr_unavailable_is_explicit` |
| `ACC-003` provenance | `test_fact_without_source_is_refused` |
| `ACC-004` règles | `test_normative_rules_are_inactive_without_validated_source`, `test_activating_normative_rule_without_regulation_is_refused` |
| `ACC-005` conflits | `test_conflicts_require_human_arbitration` |
| `ACC-006` notation | `test_score_out_of_bounds_is_refused`, `test_total_is_blocked_until_grid_is_complete` |
| `ACC-007` vigilance | `test_city_without_institutional_context_is_not_flagged`, `test_alert_never_changes_score_or_status` |
| `ACC-008` rapport | `test_orphan_fact_is_excluded_from_official_export` |
| `ACC-009` démarrage | `test_dashboard_opens_directly_without_login`, `test_port_probe_detects_occupied_port` |
| `ACC-010` base | `test_failed_write_keeps_previous_state` |
| `ACC-011` sauvegarde | `test_backup_creates_verifiable_manifest`, `test_restore_never_overwrites_existing_data` |
| `ACC-012` confidentialité | `test_restricted_document_access_is_audited`, `test_identity_piece_excerpt_is_masked` |
| `ACC-013` hors ligne | `test_offline_run_fails_explicitly`, `test_network_kill_switch_blocks_all_egress` |
| `ACC-014` accessibilité | `frontend/tests/ui.test.tsx` (RTL, lien d'évitement, couleur) |
| `ACC-015` validation humaine | `test_draft_report_is_watermarked_and_official_export_is_blocked` |
| `ACC-016` intégrité | `test_modified_regulation_suspends_linked_rules` |

## Tests métier : format exigé

Chaque test métier précise entrée, résultat attendu, résultat interdit,
confiance, contrôle humain et preuve conservée. Exemple type :

| Élément | Valeur |
|---|---|
| Entrée | PDF fictif mentionnant « Université Fictive de Rabat, Maroc » en affiliation |
| Résultat attendu | Une alerte `GEO-MAROC-001`, page 1, statut `A_VERIFIER`, contexte affiché |
| Résultat interdit | Rejet, interdiction, note, conclusion ou changement d'état du dossier |
| Confiance | 0,9 (terme principal) — qualifie la détection, jamais le risque |
| Contrôle humain | Qualification obligatoire de la relation + motivation ≥ 8 caractères |
| Preuve conservée | Déclencheur et contexte chiffrés, empreinte dans le journal d'audit |

## Preuves de livraison

- rapport de tests horodaté (sortie de `run_tests.bat`) ;
- versions des dépendances (`backend/requirements.txt`, `frontend/package.json`) ;
- empreinte du build (`sha256` de `frontend/dist`) ;
- matrice exigence-source-page-test (`docs/MATRICE_TRACABILITE.md`) ;
- journal des écarts connus (`docs/DECISIONS_TECHNIQUES.md`), à signer par le
  validateur.
