# Matrice exigence → source → page → test

*Généré par `scripts/generate_matrix.py`. Designed by Prof. Merzoug Mohamed.*

> Les originaux prévalent sur toute extraction, synthèse ou règle dérivée.
> Une exigence reste **inactive** tant que sa source n'est pas présente, validée
> et sa traduction visée par une personne habilitée.

## 1. Sources officielles

| Source | Autorité | Statut | Pages | SHA-256 (tronqué) |
|---|---|---|---:|---|
| `SRC-MANUEL-0.9` | Projet de document de référence - à compléter | PROJET_NON_OPPOSABLE | 52 | `b488d5bd027a6817…` |
| `SRC-595-2025` | Secrétariat général du MESRS | CORRESPONDANCE_OFFICIELLE | 4 | `43b3953a43fe03ea…` |
| `SRC-GUIDE-CRU` | Trois Conférences régionales des universités | PROPOSITION_A_CONFIRMER | 8 | `1213d761cd34469a…` |
| `SRC-DOSSIER-PIECES` | À confirmer | CANEvas_OPERATIONNEL_A_VERSIONNER | 1 | `e41641703aa07bd1…` |
| `SRC-218-2026` | Direction de la coopération et des échanges universitaires - MESRS | CORRESPONDANCE_OFFICIELLE_RECENTE | 6 | `9ae95d6bc805e8e2…` |

## 2. Exigences tracées

| Exigence | Libellé | Source | Pages | Statut source | Traduction | Contradiction | Tests |
|---|---|---|---|---|---|---|---|
| `EXG-001` | Champ international | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 2 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_requirements_scope_not_inferred` |
| `EXG-002` | Circuit à trois niveaux | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 3, 4, 5 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_workflow_states_never_accept_or_reject` |
| `EXG-003` | Validation interne préalable | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 3, 4 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_gate_g2_requires_pieces` |
| `EXG-004` | Composition de la commission régionale | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 4 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-004`, `test_no_invented_quorum` |
| `EXG-005` | Mission régionale et transmission | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 5 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-015`, `test_report_is_personal_proposal` |
| `EXG-006` | Délai de dépôt régional | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 5 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_deposit_delay_is_explained_not_decided` |
| `EXG-007` | Sessions régionales | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 5 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | CTR-SESSION-001 | `ACC-005`, `test_session_calendar_conflict` |
| `EXG-008` | Rapport de clôture | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 6 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_closure_deadline_no_automatic_send` |
| `EXG-009` | Dépôt et résumé trilingue | `SRC-218-2026` (CORRESPONDANCE_OFFICIELLE_RECENTE) | 6 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_trilingual_summary_checks_are_separate` |
| `EXG-010` | Liste des quatorze pièces | `SRC-DOSSIER-PIECES` (CANEvas_OPERATIONNEL_A_VERSIONNER) | 1 | CANEVAS_A_CONFIRMER | NON_APPLICABLE | — | `ACC-003`, `test_pieces_catalogue_seeded` |
| `EXG-011` | Pertinence et priorités | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 2 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-006`, `test_no_semantic_conformity` |
| `EXG-012` | Dimension internationale du comité | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 2 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-004`, `test_thresholds_are_versioned_rules` |
| `EXG-013` | Participation et conférenciers étrangers | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 2 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-007`, `test_nationality_alone_produces_no_appreciation` |
| `EXG-014` | Partenariat et valorisation | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 2 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_declared_vs_proven_are_separate` |
| `EXG-015` | Calendrier de proposition et d'examen | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 3 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-004`, `test_no_hardcoded_calendar` |
| `EXG-016` | Financement sans ingérence | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 3 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-007`, `test_funding_rule_is_alert_only` |
| `EXG-017` | Modalité présentielle ou distante | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 4 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | CTR-FORMAT-001 | `ACC-005`, `test_format_conflict` |
| `EXG-018` | Suivi, publication et bilan | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 4 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-003`, `test_followup_phase_separates_plan_and_result` |
| `EXG-019` | Accompagnement des formalités de visa | `SRC-595-2025` (CORRESPONDANCE_OFFICIELLE) | 4 | CORRESPONDANCE_OFFICIELLE | TRADUCTION_A_VALIDER | — | `ACC-012`, `test_passport_data_is_restricted` |
| `EXG-020` | Options de fréquence des sessions | `SRC-GUIDE-CRU` (PROPOSITION_A_CONFIRMER) | 3, 4 | PROPOSITION_A_CONFIRMER | NON_APPLICABLE | CTR-SESSION-001 | `ACC-004`, `test_guide_rule_inactive` |
| `EXG-021` | Option hybride à cinquante pour cent | `SRC-GUIDE-CRU` (PROPOSITION_A_CONFIRMER) | 5 | PROPOSITION_A_CONFIRMER | NON_APPLICABLE | CTR-FORMAT-001 | `ACC-004`, `test_guide_rule_inactive` |
| `EXG-022` | Méthode de double expertise | `SRC-MANUEL-0.9` (PROJET_NON_OPPOSABLE) | 1, 2, 9, 10 | PROJET_NON_OPPOSABLE | NON_APPLICABLE | — | `ACC-004`, `test_manual_is_internal_practice_only` |

## 3. Mise en œuvre exigée

- **EXG-001 — Champ international** : Demander et conserver la qualification du champ ; ne pas l'inférer automatiquement du titre.
- **EXG-002 — Circuit à trois niveaux** : Workflow versionné ; chaque transition exige acteur, date, preuve et statut de validation.
- **EXG-003 — Validation interne préalable** : Pièce de preuve obligatoire pour franchir la porte G2 ; absence signifie A_COMPLETER, jamais rejet automatique.
- **EXG-004 — Composition de la commission régionale** : Conserver la composition comme paramètre versionné ; ne pas inventer quorum, majorité ou délégation.
- **EXG-005 — Mission régionale et transmission** : L'application prépare un avis régional ; elle ne se présente jamais comme l'autorité finale.
- **EXG-006 — Délai de dépôt régional** : Calculer le délai sans décider ; afficher la règle, les deux dates, le calcul et une option de dérogation documentée.
- **EXG-007 — Sessions régionales** : Calendrier configurable et désactivable ; signaler la contradiction avec SRC-GUIDE-CRU.
- **EXG-008 — Rapport de clôture** : Créer une échéance explicable ; aucun envoi automatique.
- **EXG-009 — Dépôt et résumé trilingue** : Contrôles séparés pour dépôt, titre, résumé et mots-clés ; preuve de dépôt conservée.
- **EXG-010 — Liste des quatorze pièces** : Utiliser donnees/catalogue_pieces.json ; chaque état doit être confirmé manuellement.
- **EXG-011 — Pertinence et priorités** : Présenter un formulaire d'argumentation et de preuves ; aucune classification sémantique ne décide de la conformité.
- **EXG-012 — Dimension internationale du comité** : Paramétrer tout pourcentage ou seuil dans une règle versionnée ; montrer numérateur, dénominateur et cas exclus.
- **EXG-013 — Participation et conférenciers étrangers** : Distinguer invitation, confirmation et participation effective ; la nationalité seule ne produit aucune appréciation.
- **EXG-014 — Partenariat et valorisation** : Séparer présence déclarée, preuve fournie et appréciation humaine.
- **EXG-015 — Calendrier de proposition et d'examen** : Ne coder aucune date précise sans transcription humaine validée de la page originale.
- **EXG-016 — Financement sans ingérence** : Collecter bailleur, montant, conditions, contreparties et pièces ; l'évaluateur qualifie le risque.
- **EXG-017 — Modalité présentielle ou distante** : Ne pas appliquer automatiquement le seuil de 50 % proposé par le guide tant que le conflit n'est pas arbitré.
- **EXG-018 — Suivi, publication et bilan** : Créer une phase post-manifestation sans confondre engagement prévisionnel et réalisation.
- **EXG-019 — Accompagnement des formalités de visa** : Suivi administratif uniquement ; accès restreint aux données de passeport et aucune décision consulaire simulée.
- **EXG-020 — Options de fréquence des sessions** : Inactive comme norme ; sert uniquement à afficher la contradiction.
- **EXG-021 — Option hybride à cinquante pour cent** : Inactive par défaut ; ne devient règle qu'après preuve d'adoption et arbitrage.
- **EXG-022 — Méthode de double expertise** : Bonne pratique configurable ; ne jamais la présenter comme obligation réglementaire.

## 4. Contradictions non arbitrées

| Identifiant | Sujet | Sources | Sortie imposée |
|---|---|---|---|
| `CTR-SESSION-001` | Nombre et fréquence des sessions | SRC-218-2026, SRC-GUIDE-CRU | `CONTRADICTION_A_ARBITRER` |
| `CTR-FORMAT-001` | Présentiel, hybride et seuil de présence | SRC-595-2025, SRC-GUIDE-CRU | `CONTRADICTION_A_ARBITRER` |
| `CTR-LANGUE-001` | Langues des communications, publications et résumés | SRC-595-2025, SRC-218-2026 | `DISTINGUER_LES_CHAMPS_ET_VALIDER` |

## 5. Tests d'acceptation critiques

Porte de livraison : 0 échec critique et 0 échec majeur tolérés.

| Test | Catégorie | Criticité | Scénario | Résultat attendu |
|---|---|---|---|---|
| `ACC-001` | ingestion | CRITICAL | PDF natif, PDF scanné, PDF mixte et PDF chiffré fictifs | Type identifié, original inchangé, SHA-256 conservé, chaque page rendue ou erreur explicite sans résultat partiel valide. |
| `ACC-002` | ocr | CRITICAL | Page française, arabe et anglaise avec zones volontairement floues | Langue et mode d'extraction enregistrés ; zones incertaines marquées A_VERIFIER ; aucune complétion supposée. |
| `ACC-003` | provenance | CRITICAL | Tentative d'enregistrer un fait sans document, page ou passage | Enregistrement factuel refusé avec message explicite et journal d'audit. |
| `ACC-004` | rules | CRITICAL | Règle issue du guide non adopté ou d'une source absente | Règle inactive ; impossible de produire un état de conformité à partir d'elle. |
| `ACC-005` | conflicts | CRITICAL | Application simultanée des variantes contradictoires de fréquence ou de format | CONTRADICTION_A_ARBITRER, affichage des deux sources et blocage de toute conclusion automatique. |
| `ACC-006` | scoring | CRITICAL | Note absente, hors borne ou sans justification | Calcul final bloqué ; le système ne propose ni note ni valeur de remplacement. |
| `ACC-007` | vigilance | CRITICAL | Mot-clé géopolitique, pays, nationalité ou affiliation détecté sans contexte probant | Au plus une alerte de vérification contextualisée ; jamais rejet, interdiction, conclusion ou score automatique. |
| `ACC-008` | report | CRITICAL | Génération d'un rapport contenant un fait non sourcé ou une donnée OCR incertaine non signalée | Export bloqué ou donnée exclue ; chaque assertion retenue possède source, page et statut humain. |
| `ACC-009` | startup | CRITICAL | Premier lancement, second lancement, redémarrage, port occupé et serveur momentanément non prêt | Ouverture directe du tableau de bord sans compte, login ni boucle ; un seul serveur ; attente de readiness ; diagnostic clair et récupérable si le port est indisponible. |
| `ACC-010` | database | CRITICAL | Interruption simulée pendant une écriture | État précédent cohérent, aucune demi-validation, journal technique et reprise contrôlée. |
| `ACC-011` | backup | CRITICAL | Sauvegarde chiffrée puis restauration dans un répertoire temporaire | Intégrité vérifiée avant remplacement ; mauvaise clé refusée ; restauration originale préservée en cas d'échec. |
| `ACC-012` | privacy | CRITICAL | Dossier fictif contenant un passeport et données personnelles | Accès restreint, masquage dans les écrans et exports ordinaires, aucune requête réseau, suppression et rétention auditables. |
| `ACC-013` | offline | HIGH | Machine sans Internet et ressources externes bloquées | Application entièrement fonctionnelle sur 127.0.0.1, sans CDN, télémétrie, police distante ni appel API. |
| `ACC-014` | accessibility | HIGH | Parcours clavier complet et affichage français/arabe | Focus visible, libellés accessibles, ordre logique, RTL correct et aucune information portée uniquement par la couleur. |
| `ACC-015` | human_validation | CRITICAL | Tentative d'export officiel sans validation humaine G7 | Export officiel bloqué ; seul un brouillon filigrané et explicitement non validé peut être produit. |
| `ACC-016` | integrity | CRITICAL | Modification d'un document réglementaire après son enregistrement | Empreinte divergente détectée ; toutes les règles liées sont suspendues jusqu'à revalidation. |

## 6. Sources citées mais absentes

Ces références sont citées par les originaux mais ne sont pas versées au kit.
Elles ne peuvent produire **aucune règle obligatoire** avant versement et validation.

- Envoi n°157/DGRSDT du 29 avril 2024
- Envoi n°652 du 17 avril 2022
- Correspondance DCEU n°608 du 26 octobre 2022
- Correspondance DCEU n°1773 du 24 octobre 2022
- Correspondance DCEU n°98 du 15 février 2022
- Loi n°18-07 du 10 juin 2018 et loi modificative n°25-11 du 24 juillet 2025
- Ordonnance n°21-09 du 8 juin 2021 et loi d'approbation citée
- Charte de déontologie et d'éthique universitaires, édition 2023
- Acte officiel fixant quorum, majorité, vote et durée des mandats
- Instruction officielle actualisée relative aux restrictions diplomatiques applicables à la session

Statut imposé : `NON_ACTIVE_TANT_QUE_SOURCE_ABSENTE`.

