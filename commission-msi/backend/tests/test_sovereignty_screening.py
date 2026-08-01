"""Contrôle de souveraineté sur les profils publics.

Ce que ces tests protègent avant tout, c'est ce que l'agent **refuse** de faire.
Signaler un rattachement institutionnel documenté est légitime — la commission
le fait dans son propre modèle de rapport. Profiler une personne par sa
nationalité, son origine, sa religion ou la consonance de son nom ne l'est pas,
et le référentiel de l'application l'interdit explicitement.
"""

from __future__ import annotations

from app.agents.base import AgentInput
from app.agents.sovereignty import (
    INFORMATIVE_ONLY,
    MIN_INDEPENDENT_SOURCES,
    NEVER_SCREENED,
    SovereigntyScreeningAgent,
    screening_scope,
)
from app.core.vocabulary import AgentName, ClaimNature, EvidenceStatus, SourceTier
from app.web_research.providers import SearchResult

AGENT = SovereigntyScreeningAgent()


def _result(url: str, title: str, snippet: str) -> SearchResult:
    return SearchResult(
        url=url,
        title=title,
        publisher=None,
        published_on=None,
        snippet=snippet,
        tier=SourceTier.T2_INSTITUTION_ACADEMIQUE,
    )


def _run(results: list[SearchResult], label: str = "Pr Untel"):
    return AGENT.run(
        AgentInput(
            subject_kind="PERSONNE",
            subject_label=label,
            declared_affiliation=None,
            results=results,
        )
    )


# --------------------------------------------------------------------------
# Ce que l'agent refuse — le cœur du sujet
# --------------------------------------------------------------------------


def test_a_nationality_alone_never_produces_a_finding():
    """Une nationalité mentionnée n'est pas un rattachement institutionnel."""
    output = _run(
        [
            _result(
                "https://exemple.org/a",
                "Pr Untel",
                "Chercheur de nationalité marocaine, spécialiste des sols arides.",
            )
        ]
    )
    statements = " ".join(claim.statement for claim in output.claims)
    assert "Aucun rattachement institutionnel" in statements
    assert all(claim.nature == ClaimNature.ABSENCE_DE_PREUVE for claim in output.claims)


def test_a_bibliographic_mention_never_produces_a_finding():
    """Citer un travail mené au Maroc n'est pas y être rattaché."""
    output = _run(
        [
            _result(
                "https://revue.example/x",
                "Étude comparative",
                "L'auteur cite des travaux conduits au Maroc et en Tunisie.",
            )
        ]
    )
    assert all(claim.nature == ClaimNature.ABSENCE_DE_PREUVE for claim in output.claims)


def test_the_screening_scope_names_what_it_refuses_to_examine():
    scope = screening_scope()

    for forbidden in ("nationalité", "origine ethnique", "religion", "consonance du nom"):
        assert forbidden in scope["jamais_examine"]
    assert scope["jamais_examine"] == list(NEVER_SCREENED)
    assert "contexte institutionnel" in scope["exigence_de_contexte"]


def test_no_screened_category_targets_a_person_rather_than_an_activity():
    """Aucune catégorie examinée ne porte sur l'identité d'une personne."""
    identity_categories = {
        "IDENTITE_RELIGION_LANGUE",
        "DISCRIMINATION_HAINE",
        "MEMOIRE_NATIONALE",
    }
    assert not identity_categories & set(SovereigntyScreeningAgent.SCREENED_CATEGORIES)


# --------------------------------------------------------------------------
# Ce que l'agent signale, et comment
# --------------------------------------------------------------------------


def test_a_documented_institutional_affiliation_is_reported_with_its_sources():
    output = _run(
        [
            _result(
                "https://univ-a.example/profil",
                "Profil institutionnel",
                "Affiliated researcher, Bar-Ilan University, Israel — laboratory of soil science.",
            ),
            _result(
                "https://consortium-b.example/membres",
                "Consortium REACT4MED",
                "Partnership including the University of Haifa, Israel.",
            ),
        ]
    )
    findings = [claim for claim in output.claims if claim.nature != ClaimNature.ABSENCE_DE_PREUVE]
    assert findings, "un rattachement institutionnel documenté doit être signalé"
    claim = findings[0]
    assert claim.independent_source_count >= MIN_INDEPENDENT_SOURCES
    assert claim.nature == ClaimNature.FAIT_VERIFIE
    assert claim.status == EvidenceStatus.SOURCES_CONCORDANTES
    assert len(claim.source_urls) >= 2


def test_a_single_source_stays_an_allegation():
    output = _run(
        [
            _result(
                "https://univ-a.example/profil",
                "Profil",
                "Affiliated with a research institute in Morocco.",
            )
        ]
    )
    findings = [claim for claim in output.claims if claim.nature != ClaimNature.ABSENCE_DE_PREUVE]
    assert findings
    assert findings[0].nature == ClaimNature.ALLEGATION_TIERS
    assert findings[0].status == EvidenceStatus.A_VERIFIER


def test_every_finding_carries_the_informative_only_scope():
    output = _run(
        [
            _result(
                "https://univ-a.example/p",
                "Profil",
                "Affiliated researcher, institute in Morocco.",
            )
        ]
    )
    for claim in output.claims:
        if claim.nature != ClaimNature.ABSENCE_DE_PREUVE:
            assert claim.notes == INFORMATIVE_ONLY
            assert "ne constituent pas une non-conformité" in claim.notes
            assert "relèvent exclusivement du ministère" in claim.notes


def test_absence_of_result_is_not_a_clearance():
    output = _run([])

    assert output.claims
    for claim in output.claims:
        assert claim.status in {EvidenceStatus.NON_ETABLI, EvidenceStatus.A_VERIFIER}


def test_absence_of_finding_is_never_presented_as_a_guarantee():
    output = _run([_result("https://x.example/p", "Profil", "Professeur de biologie.")])

    note = " ".join(claim.notes or "" for claim in output.claims)
    assert "ni une garantie, ni une habilitation de sécurité" in note


# --------------------------------------------------------------------------
# Le vocabulaire vient du référentiel, pas du code
# --------------------------------------------------------------------------


def test_the_terms_come_from_the_validated_referential():
    scope = screening_scope()

    assert scope["categories_examinees"], "aucune catégorie chargée"
    assert sum(scope["termes_par_categorie"].values()) > 50
    # Toute catégorie examinée doit exister dans le référentiel de vigilance.
    from app.services import reference_data

    payload = reference_data.load_default_rules()
    rules = payload.get("rules", payload) if isinstance(payload, dict) else payload
    known = {rule["category"] for rule in rules}
    assert set(scope["categories_examinees"]) <= known


def test_the_agent_is_wired_into_the_pipeline():
    from app.agents.specialists import ALL_AGENTS

    assert any(isinstance(agent, SovereigntyScreeningAgent) for agent in ALL_AGENTS)


def test_the_agent_has_its_own_name_and_does_not_borrow_another():
    """Deux agents qui partagent un nom rendent leurs constats indiscernables."""
    from app.agents.specialists import PublicIntegrityAgent

    assert SovereigntyScreeningAgent.name == AgentName.SOUVERAINETE_NATIONALE
    assert SovereigntyScreeningAgent.name != PublicIntegrityAgent.name


def test_a_manifestation_is_not_a_subject_of_this_screening():
    """Une manifestation n'a ni rattachement ni activité propres."""
    output = AGENT.run(
        AgentInput(
            subject_kind="MANIFESTATION",
            subject_label="Colloque international 2027",
            declared_affiliation=None,
            results=[_result("https://x.example/p", "Colloque", "Affiliated institute, Morocco.")],
        )
    )
    assert output.claims == []


def test_an_organisation_is_screened_like_a_person():
    output = AGENT.run(
        AgentInput(
            subject_kind="INSTITUTION",
            subject_label="Institut X",
            declared_affiliation=None,
            results=[
                _result("https://a.example/p", "Institut X", "Partnership with an institute in Morocco."),
                _result("https://b.example/q", "Consortium", "Programme funded with an institute in Morocco."),
            ],
        )
    )
    findings = [claim for claim in output.claims if claim.nature != ClaimNature.ABSENCE_DE_PREUVE]
    assert findings
    assert findings[0].nature == ClaimNature.FAIT_VERIFIE
