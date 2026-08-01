# Analyse fonctionnelle

*Designed by Prof. Merzoug Mohamed.*

## 1. Besoin

Le Professeur Merzoug Mohamed, membre d'une commission régionale algérienne,
examine des demandes d'organisation de manifestations scientifiques
internationales transmises sous forme de dossiers PDF. L'application accélère
et structure cet examen **sans se substituer à l'évaluateur**.

## 2. Ce que l'application fait — et ne fait pas

| Elle fait | Elle ne fait jamais |
|---|---|
| Extraire, vérifier, classer, comparer, signaler, préparer | Décider d'un avis favorable ou d'un rejet |
| Calculer la somme des notes saisies | Proposer ou recommander une note |
| Signaler un point sensible à vérifier | Qualifier juridiquement un fait |
| Rapprocher un point d'un texte officiel validé | Inventer une règle ou une référence |
| Afficher une incertitude | Compléter un texte illisible par supposition |
| Consulter des sources publiques sur demande | Envoyer un document du dossier à l'extérieur |

## 3. Acteurs

Un seul acteur : **l'évaluateur**, seul utilisateur du poste. Aucun compte,
aucun rôle, aucune délégation. L'identité figurant dans les rapports et le
journal provient de `MSI_EVALUATOR`.

## 4. Exigences fonctionnelles principales

| Réf. | Exigence | Vérifiée par |
|---|---|---|
| EF-01 | Ouverture directe du tableau de bord, sans compte ni connexion | `test_dashboard_opens_directly_without_login` |
| EF-02 | Création d'un dossier (référence, intitulé, organisateur) | `test_...create_dossier` |
| EF-03 | Import PDF validé, empreinté, chiffré, inchangé | `test_native_pdf_is_stored_unchanged_and_fingerprinted` |
| EF-04 | Analyse structurelle et classification des pages | `test_page_classification_native_blank_mixed_and_duplicate` |
| EF-05 | OCR local à la demande, jamais systématique | `test_ocr_refused_when_native_text_is_sufficient` |
| EF-06 | Correction humaine conservant le texte initial | `test_page_correction_keeps_initial_text` |
| EF-07 | Provenance obligatoire de tout fait retenu | `test_fact_without_source_is_refused` |
| EF-08 | Catalogue de pièces, détection ≠ confirmation | `test_pieces...` |
| EF-09 | Contrôle administratif explicable | `test_...update_check` |
| EF-10 | Grille scientifique saisie, total = somme | `test_total_is_only_a_sum_of_entered_scores` |
| EF-11 | Moteur de vigilance déterministe et contextualisé | `test_vigilance_rules.py` |
| EF-12 | Section Maroc visible, contextualisée, non discriminatoire | `test_explicit_maroc_mention_creates_contextualised_alert` |
| EF-13 | Recherche Web contrôlée et approuvée requête par requête | `test_web_research.py` |
| EF-14 | Agents indépendants, désaccords bloquants | `test_agents_and_ranking.py` |
| EF-15 | Ranking externe séparé de la grille officielle | `test_ranking_never_touches_official_grid` |
| EF-16 | Conclusion en liste fermée, motivée | `test_conclusion_requires_closed_list_and_motivation` |
| EF-17 | Rapport DOCX/PDF étiqueté, porte G7 | `test_full_workflow_produces_valid_docx_and_pdf` |
| EF-18 | Journal d'audit sans valeur sensible en clair | `test_audit_never_stores_clear_sensitive_values` |
| EF-19 | Sauvegarde vérifiable, restauration sur copie | `test_backup_creates_verifiable_manifest` |

## 5. États du dossier

`NOUVEAU` → `ANALYSE_EN_COURS` → `RECHERCHE_WEB_REQUISE` →
`RECHERCHE_WEB_EN_COURS` → `A_CONTROLER` → `EN_EVALUATION` →
`COMPLEMENT_REQUIS` → `ANALYSE_ENRICHIE_COMPLETE` → `PRET_POUR_RAPPORT` →
`ARCHIVE`.

Aucun état équivalent à « accepté », « rejeté » ou « interdit » n'existe, et
toute tentative d'en forcer un est refusée.

## 6. Portes de validation

| Porte | Condition |
|---|---|
| `G0_SOURCE` | Empreintes des sources officielles cohérentes |
| `G1_EXTRACTION` | Pages lisibles ou explicitement marquées |
| `G2_ADMINISTRATIF` | Pièces qualifiées manuellement |
| `G3_ELIGIBILITE` | Informations retenues toutes sourcées |
| `G4_SCIENTIFIQUE` | Grille complète et justifiée |
| `G5_VIGILANCE` | Alertes qualifiées et motivées |
| `G6_RAPPORT` | Conclusion motivée, aucune affirmation orpheline |
| `G7_VALIDATION_HUMAINE` | Rapport explicitement validé |

Une porte non satisfaite bloque l'étape suivante ; elle ne transforme jamais le
dossier en rejet.

## 7. Exigences non fonctionnelles

- Fonctionnement hors ligne complet du cœur documentaire.
- Écoute exclusive sur `127.0.0.1`.
- Contraste WCAG AA, navigation clavier, focus visible, RTL arabe.
- Aucune ressource distante : polices système, icônes SVG locales.
- Interface responsive à partir de 900 px, tableaux défilables en dessous.
