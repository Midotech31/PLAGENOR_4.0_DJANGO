"""Score scientifique proposé et moteur d'avis déterministe.

Deux propriétés sont vérifiées sans relâche :

* le score est **recalculé** — plafonds respectés, additions exactes, aucun
  sous-critère non documenté ne reçoit de points ;
* l'avis est choisi dans la liste fermée, et un score élevé ne neutralise
  jamais une non-conformité réglementaire.
"""

from __future__ import annotations

from app.services import decision_engine, scientific_scoring
from app.services.regulatory_engine import CriterionResult, DossierFacts, Status

RICH_PAGE = """Programme scientifique et sessions thématiques
Axes thématiques : axe 1 matériaux, axe 2 énergie
Problématique : verrou scientifique du stockage
Objectifs spécifiques et résultats attendus, avec indicateurs de suivi
Priorité nationale : transition énergétique
Retombées et perspectives de recherche, réseau de recherche
Convention de coopération bilatérale signée avec l'Institut de Lyon
Hébergement, restauration et transport pris en charge
Proceedings et actes du colloque, ISBN à paraître
Textes intégraux sur le portail, résumé en arabe et en anglais
Dépôt DSpace avec métadonnées trilingues
Bilan final remis à la tutelle
Indexation Scopus et numéro spécial de revue
Plateforme de soumission en ligne : https://colloque.univ-oran.dz
Laboratoire des matériaux, unité de recherche du département
"""


def _facts(**kwargs) -> DossierFacts:
    base = {
        "values": {},
        "pages": {1: "Document de test."},
        "observations": {},
        "pieces": {},
        "findings": [],
        "evidence": {"page:1": "E-P001"},
    }
    base.update(kwargs)
    return DossierFacts(**base)


def _criterion(code: str, status: str, *, nature="OBLIGATOIRE", blocking=True, family="ADMINISTRATIF"):
    return CriterionResult(
        code=code,
        label=f"Critère {code}",
        family=family,
        order=1,
        status=status,
        finding="Constat de test.",
        exact_source="Guide du 14/07/2026",
        page="7",
        nature=nature,
        blocking=blocking,
    )


# --------------------------------------------------------------------------
# Score scientifique
# --------------------------------------------------------------------------


def test_the_grid_totals_exactly_one_hundred_points():
    grid = scientific_scoring.load_grid()
    assert grid["total"] == 100
    assert sum(family["max"] for family in grid["families"]) == 100
    for family in grid["families"]:
        assert sum(sub["max"] for sub in family["subcriteria"]) == family["max"]


def test_the_five_families_follow_the_official_weights():
    weights = {
        family["key"]: family["max"] for family in scientific_scoring.load_grid()["families"]
    }
    assert weights == {
        "pertinence_priorites": 30,
        "objectifs_resultats": 20,
        "valeur_internationale": 20,
        "faisabilite_gouvernance": 15,
        "valorisation_suivi": 15,
    }


def test_an_empty_dossier_scores_zero_everywhere_and_says_non_documente():
    result = scientific_scoring.score(_facts(pages={1: "Page vide de contenu utile."}))
    assert result.total == 0
    assert len(result.subscores) == 24
    for sub in result.subscores:
        assert sub.score == 0
        assert sub.justification.startswith(scientific_scoring.NOT_DOCUMENTED)
        # Un zéro pour absence de preuve ne préjuge jamais de l'organisateur.
        assert "ne préjuge" in sub.justification


def test_every_subscore_is_recomputed_and_never_exceeds_its_cap():
    result = scientific_scoring.score(
        _facts(
            pages={1: RICH_PAGE},
            values={
                "theme": "matériaux avancés",
                "objectifs": "structurer un réseau de recherche",
                "structure_porteuse": "Laboratoire des matériaux",
                "etablissement_organisateur": "Université d'Oran",
                "comite_scientifique": "Pr Jean Dubois ; Pr Karim Idrissi",
                "comite_organisation": "Dr Sofiane Merabet",
                "responsable_scientifique": "Pr Amina Belkacem",
                "intervenants": "Pr Zool Ismail",
                "partenaires": "Institut de Lyon",
                "financeurs": "Subvention de l'établissement",
                "modalites_publication": "actes indexés et numéro spécial",
                "format": "présentiel",
                "date_debut": "12/03/2027",
                "date_fin": "14/03/2027",
                "lieu": "Campus d'Oran",
            },
            observations={
                "countries": ["Algérie", "France", "Maroc"],
                "amounts": [
                    {"value": 1000000, "is_total": True},
                    {"value": 700000, "is_total": False},
                    {"value": 300000, "is_total": False},
                ],
                "urls": ["https://colloque.univ-oran.dz"],
                "intervenants_etrangers_presents": 2,
                "intervenants_total": 10,
            },
        )
    )
    assert result.total > 0
    for family in result.families:
        assert family.score == sum(sub.score for sub in family.subscores)
        assert family.score <= family.max
        for sub in family.subscores:
            assert 0 <= sub.score <= sub.max
    assert result.total == sum(family.score for family in result.families)
    assert result.total <= 100


def test_every_awarded_point_carries_a_justification():
    result = scientific_scoring.score(_facts(pages={1: RICH_PAGE}))
    for sub in result.subscores:
        if sub.score > 0:
            assert sub.justification.strip()
            # Un sous-critère noté n'est jamais marqué « non documenté ».
            assert not sub.justification.startswith(scientific_scoring.NOT_DOCUMENTED)


def test_scoring_is_deterministic():
    facts = _facts(pages={1: RICH_PAGE})
    assert scientific_scoring.score(facts).total == scientific_scoring.score(facts).total


def test_a_subcriterion_failure_scores_zero_and_never_invents(monkeypatch):
    def explode(sub, family, facts):
        raise RuntimeError("panne simulée")

    monkeypatch.setitem(scientific_scoring.METHODS, "GOVERNANCE", explode)
    result = scientific_scoring.score(_facts(pages={1: RICH_PAGE}))
    governance = next(sub for sub in result.subscores if sub.key == "gouvernance")
    assert governance.score == 0
    assert governance.justification.startswith(scientific_scoring.NOT_DOCUMENTED)


# --------------------------------------------------------------------------
# Moteur d'avis
# --------------------------------------------------------------------------


def test_the_avis_always_belongs_to_the_closed_list():
    decision = decision_engine.propose([_criterion("A1", Status.C)])
    assert decision.avis in decision_engine.CLOSED_LIST
    assert "ne valant pas décision officielle" in decision.disclaimer


def test_all_mandatory_criteria_satisfied_gives_favorable():
    results = [_criterion(f"A{i}", Status.C) for i in range(1, 5)]
    decision = decision_engine.propose(results, scientific_total=90)
    assert decision.avis == decision_engine.FAVORABLE
    assert decision.reserves == []
    assert "R4_TOUTES_EXIGENCES_DEMONTREES" in {r.rule for r in decision.triggered_rules}


def test_a_mandatory_criterion_nc_gives_ajournement():
    results = [_criterion("A1", Status.C), _criterion("A2", Status.NC)]
    decision = decision_engine.propose(results)
    assert decision.avis == decision_engine.AJOURNEMENT_POUR_COMPLEMENTS
    assert decision.required_complements
    assert "A2" in decision.blocking_criteria


def test_a_high_score_never_neutralises_a_regulatory_non_conformity():
    """Règle 2 : le score n'entre pas dans le choix de l'avis."""
    results = [_criterion("A1", Status.C), _criterion("A2", Status.NC)]
    low = decision_engine.propose(results, scientific_total=5)
    high = decision_engine.propose(results, scientific_total=100)
    assert low.avis == high.avis == decision_engine.AJOURNEMENT_POUR_COMPLEMENTS
    trace = next(r for r in high.triggered_rules if r.rule == "R2_SCORE_NON_NEUTRALISANT")
    assert "ne neutralise aucune non-conformité" in trace.explanation


def test_only_international_conditions_missing_gives_requalification():
    results = [
        _criterion("A1", Status.C),
        _criterion("A2", Status.C),
        _criterion("I2", Status.NC, family="INTERNATIONAL"),
        _criterion("I3", Status.NC, family="INTERNATIONAL"),
    ]
    decision = decision_engine.propose(results)
    assert decision.avis == decision_engine.REQUALIFICATION_NATIONALE_A_EXAMINER
    assert "sans préjuger de la décision" in decision.motivation


def test_partial_conformities_alone_give_favorable_with_reserves():
    results = [_criterion("A1", Status.C), _criterion("A2", Status.PC)]
    decision = decision_engine.propose(results)
    assert decision.avis == decision_engine.FAVORABLE_SOUS_RESERVES
    assert len(decision.reserves) == 1
    assert decision.blocking_criteria == []


def test_a_mostly_unverifiable_dossier_is_not_determinable():
    results = [_criterion(f"A{i}", Status.NV) for i in range(1, 5)]
    decision = decision_engine.propose(results)
    assert decision.avis == decision_engine.NON_DETERMINABLE_INFORMATION_INSUFFISANTE
    assert "n'est pas un motif de rejet" in decision.motivation


def test_only_a_human_qualified_severe_alert_triggers_transmission():
    results = [_criterion("A1", Status.C)]
    # Une alerte encore à vérifier ne déclenche rien : le moteur n'anticipe pas.
    unqualified = decision_engine.propose(
        results, findings=[{"status": "A_VERIFIER", "priority": "CRITIQUE", "rule_code": "R-01"}]
    )
    assert unqualified.avis == decision_engine.FAVORABLE

    qualified = decision_engine.propose(
        results, findings=[{"status": "CONFIRME", "priority": "CRITIQUE", "rule_code": "R-01"}]
    )
    assert qualified.avis == decision_engine.TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE
    trace = next(r for r in qualified.triggered_rules if r.rule == "R6_ALERTE_GRAVE_PROUVEE")
    # Une transmission n'est ni une culpabilité, ni un rejet.
    assert "ni une culpabilité, ni un rejet" in trace.explanation


def test_an_unresolved_audit_disagreement_is_recorded_without_averaging():
    decision = decision_engine.propose(
        [_criterion("A1", Status.C)],
        unresolved_disagreements=[{"criterion_code": "A1", "reason": "constats divergents"}],
    )
    trace = next(r for r in decision.triggered_rules if r.rule == "R8_DESACCORD_AUDIT_NON_RESOLU")
    assert "aucune moyenne" in trace.explanation


def test_every_decision_records_its_triggering_criteria_and_evidence():
    results = [_criterion("A1", Status.C), _criterion("A2", Status.NC)]
    decision = decision_engine.propose(results, scientific_total=42)
    main = next(r for r in decision.triggered_rules if r.rule.startswith("R1_"))
    assert main.criteria == ["A2"]
    assert decision_engine.to_dict(decision)["triggered_rules"]


def test_an_avis_outside_the_closed_list_is_refused():
    import pytest

    with pytest.raises(ValueError, match="hors de la liste fermée"):
        decision_engine.ProposedDecision(
            avis="ACCEPTE",
            label="Accepté",
            motivation="—",
            triggered_rules=[],
            blocking_criteria=[],
            reserves=[],
            required_complements=[],
        )
