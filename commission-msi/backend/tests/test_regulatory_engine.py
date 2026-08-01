"""Les 26 critères réglementaires : statut obligatoire, corrections impératives.

Ces tests vérifient point par point les consignes du référentiel :

* aucun délai universel de six mois n'est appliqué ;
* `A2` compare au délai de 10 jours avant la session régionale ;
* `I2` comporte une exception bilatérale ;
* `I7` affiche le ratio exact sans marge de tolérance inventée ;
* `I9` porte « si possible » et ne devient jamais bloquant ;
* les passeports ne sont contrôlés qu'en présence, jamais en contenu ;
* une information absente produit `NV`, jamais une supposition ;
* aucune cellule n'est laissée vide.
"""

from __future__ import annotations

import json

from app.services import regulatory_engine
from app.services.regulatory_engine import DossierFacts, Status, evaluate, summarize


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


def _by_code(results) -> dict:
    return {result.code: result for result in results}


# --------------------------------------------------------------------------
# Couverture et complétude
# --------------------------------------------------------------------------


def test_the_twenty_six_criteria_are_all_evaluated_once_and_in_order():
    results = evaluate(_facts())
    assert len(results) == 26
    codes = [result.code for result in results]
    assert len(set(codes)) == 26
    assert [result.order for result in results] == sorted(result.order for result in results)


def test_no_cell_is_ever_left_empty():
    """Chaque critère porte un statut, un constat et un fondement exact."""
    for result in evaluate(_facts()):
        assert result.status in {Status.C, Status.PC, Status.NC, Status.NV}
        assert result.finding.strip(), f"{result.code} sans constat"
        assert result.exact_source.strip(), f"{result.code} sans fondement"
        assert result.page.strip(), f"{result.code} sans page de référence"
        assert result.nature in {"OBLIGATOIRE", "RECOMMANDE"}


def test_an_empty_dossier_produces_nv_not_non_conformity_by_default():
    """L'absence d'information ne se transforme jamais en supposition."""
    results = _by_code(evaluate(_facts()))
    assert results["A2"].status == Status.NV
    assert results["A3"].status == Status.NV
    assert results["I2"].status == Status.NV
    assert results["I3"].status == Status.NV


# --------------------------------------------------------------------------
# Corrections impératives du référentiel
# --------------------------------------------------------------------------


def test_no_six_month_deadline_is_carried_by_any_criterion():
    """Aucun critère ne porte de délai de six mois — seule l'interdiction le nomme."""
    referential = regulatory_engine.load_referential()
    for criterion in referential["criteria"]:
        # Les champs opérants — conditions appliquées et paramètres de calcul —
        # ne doivent contenir aucune trace d'un délai de six mois.
        operative = json.dumps(
            {
                "conditions": criterion["conditions"],
                "calculation_params": criterion["calculation_params"],
            },
            ensure_ascii=False,
        ).lower()
        assert "six mois" not in operative, criterion["code"]
        assert "180" not in operative, criterion["code"]
    # L'interdiction, elle, est écrite noir sur blanc dans les corrections.
    corrections = " ".join(referential["corrections_imperatives"]).lower()
    assert "six mois" in corrections and "jamais être appliqué" in corrections


def test_a2_uses_ten_days_before_the_regional_session():
    results = _by_code(
        evaluate(_facts(values={"date_debut": "20/05/2027", "date_depot": "01/05/2027"}))
    )
    a2 = results["A2"]
    assert a2.status == Status.C
    assert a2.calculation["minimum_jours"] == 10
    assert a2.calculation["ecart_jours"] == 19
    # La règle des six mois n'est jamais appliquée, et le dit explicitement.
    assert a2.calculation["delai_six_mois_applique"] is False


def test_a2_deadline_not_met_is_non_conformity_with_the_exact_gap():
    results = _by_code(
        evaluate(_facts(values={"date_debut": "10/05/2027", "date_depot": "06/05/2027"}))
    )
    assert results["A2"].status == Status.NC
    assert results["A2"].calculation["ecart_jours"] == 4


def test_i2_bilateral_exception_prevents_a_mechanical_non_conformity():
    """Une coopération bilatérale rend le seuil 3 pays / 2 continents inopposable."""
    facts = _facts(
        pages={1: "Le projet s'inscrit dans une coopération bilatérale algéro-française."},
        observations={"countries": ["Algérie", "France"]},
    )
    i2 = _by_code(evaluate(facts))["I2"]
    assert i2.status == Status.PC
    assert "exception_bilaterale" in i2.calculation
    assert "bilatérale" in i2.finding


def test_i2_without_bilateral_mention_applies_the_threshold():
    facts = _facts(observations={"countries": ["Algérie", "France", "Maroc"]})
    i2 = _by_code(evaluate(facts))["I2"]
    assert i2.status == Status.C
    assert i2.calculation["nombre_pays"] == 3
    assert i2.calculation["nombre_continents"] == 2


def test_i7_shows_the_exact_ratio_and_invents_no_tolerance():
    facts = _facts(
        observations={"intervenants_etrangers_presents": 2, "intervenants_total": 25}
    )
    i7 = _by_code(evaluate(facts))["I7"]
    assert i7.status == Status.PC
    assert i7.calculation["ratio"] == 0.08
    assert i7.calculation["tolerance"] is None
    assert "environ 10 %" in i7.finding
    assert "8.0%" in i7.finding


def test_i9_is_conditional_and_never_becomes_blocking():
    i9 = _by_code(evaluate(_facts()))["I9"]
    assert i9.blocking is False
    assert i9.nature == "RECOMMANDE"
    assert i9.status != Status.NC


def test_passports_are_checked_for_presence_only():
    a4 = _by_code(evaluate(_facts(pieces={"conferenciers_etrangers_passports": "CONFIRMEE"})))["A4"]
    assert a4.status == Status.C
    assert "aucune donnée de passeport n'est reproduite" in a4.calculation["confidentialite"].lower()
    # Aucun numéro, aucune donnée personnelle ne transite par le constat.
    assert "passeport" in a4.finding.lower()
    assert not any(char.isdigit() for char in a4.finding)


# --------------------------------------------------------------------------
# Robustesse
# --------------------------------------------------------------------------


def test_a_calculation_failure_becomes_nv_and_never_an_invention(monkeypatch):
    def explode(criterion, facts):
        raise RuntimeError("panne simulée")

    monkeypatch.setitem(regulatory_engine.CALCULATORS, "PIECES_PRESENCE", explode)
    a1 = _by_code(evaluate(_facts()))["A1"]
    assert a1.status == Status.NV
    assert "non déterminable" in a1.finding


def test_summary_counts_and_lists_blocking_issues():
    summary = summarize(evaluate(_facts()))
    assert sum(summary["counts"].values()) == 26
    assert summary["referential_version"]
    for issue in summary["blocking_issues"]:
        assert issue["status"] in {Status.NC, Status.NV}
