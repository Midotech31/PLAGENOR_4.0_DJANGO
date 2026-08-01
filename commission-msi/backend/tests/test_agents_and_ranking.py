"""Agents spécialisés, homonymies, désaccords et ranking externe indicatif."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agents import orchestrator
from app.agents.base import AgentInput
from app.agents.specialists import (
    AlgerianLawAgent,
    EventRankingAgent,
    IdentityAffiliationsAgent,
    PublicIntegrityAgent,
    ScientificReputationAgent,
    SourceVerifierAgent,
)
from app.core.vocabulary import (
    AGENT_DISAGREEMENT_MESSAGE,
    NOT_PROVIDED,
    AgentName,
    ClaimNature,
    EvidenceStatus,
    RankingGrade,
    SourceTier,
)
from app.ranking import service as ranking_service
from app.web_research.providers import SearchResult


def _result(url, title, tier, publisher=None, published_on="2026-02-01", snippet=None):
    return SearchResult(
        url=url,
        title=title,
        publisher=publisher,
        published_on=published_on,
        snippet=snippet or title,
        tier=tier,
        consulted_at=datetime.now(timezone.utc),
    )


def _input(results, *, label="Amina Belkacem", affiliation="Universite Fictive de Test", refs=None):
    return AgentInput(
        subject_kind="PERSONNE",
        subject_label=label,
        declared_affiliation=affiliation,
        results=results,
        algerian_references=refs or [],
    )


# --------------------------------------------------------------------------
# Agents pris isolément
# --------------------------------------------------------------------------


def test_identity_agent_confirms_matching_affiliation():
    results = [
        _result(
            "https://universite-fictive.test/a",
            "Amina Belkacem — Universite Fictive de Test",
            SourceTier.T2_INSTITUTION_ACADEMIQUE,
            publisher="Universite Fictive de Test",
        ),
        _result(
            "https://revue-fictive.test/b",
            "Amina Belkacem, Universite Fictive de Test",
            SourceTier.T3_PUBLICATION_SCIENTIFIQUE,
        ),
    ]
    claims = IdentityAffiliationsAgent().run(_input(results)).claims
    assert claims[0].status in {
        EvidenceStatus.SOURCES_CONCORDANTES,
        EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE,
    }


def test_identity_agent_flags_homonyms():
    """Homonymes portant le même nom avec des affiliations différentes."""
    results = [
        _result(
            "https://universite-a.test/x",
            "Amina Belkacem — Institut Fictif du Nord",
            SourceTier.T2_INSTITUTION_ACADEMIQUE,
            publisher="Institut Fictif du Nord",
        ),
        _result(
            "https://universite-b.test/y",
            "Amina Belkacem — Centre Fictif du Sud",
            SourceTier.T2_INSTITUTION_ACADEMIQUE,
            publisher="Centre Fictif du Sud",
        ),
    ]
    claim = IdentityAffiliationsAgent().run(_input(results)).claims[0]
    assert claim.status == EvidenceStatus.HOMONYMIE_POSSIBLE
    assert "interdit toute conclusion consolidée" in claim.notes


def test_agent_returns_absence_claim_when_no_result():
    claim = IdentityAffiliationsAgent().run(_input([])).claims[0]
    assert claim.nature == ClaimNature.ABSENCE_DE_PREUVE
    assert claim.status == EvidenceStatus.NON_ETABLI


def test_public_integrity_agent_never_concludes_incompatibility():
    results = [
        _result(
            "https://asso-fictive.test/membres",
            "Association fictive — conseil d'administration",
            SourceTier.T4_SITE_ORGANISATEUR,
            snippet="Amina Belkacem, membre du conseil d'administration de l'association fictive.",
        ),
        _result(
            "https://media-fictif.test/article",
            "Association fictive : nouveau board",
            SourceTier.T5_MEDIA_RECONNU,
            snippet="board de l'association fictive",
        ),
    ]
    claims = PublicIntegrityAgent().run(_input(results)).claims
    assert claims
    for claim in claims:
        assert "ne constituent pas une incompatibilité" in claim.notes
        assert "illégal" not in claim.statement.lower()


def test_algerian_law_agent_refuses_without_validated_reference():
    """Rapprochement avec un texte absent, abrogé ou non validé : impossible."""
    claim = AlgerianLawAgent().run(_input([])).claims[0]
    assert claim.status == EvidenceStatus.NON_ETABLI
    assert "jamais interprétée librement" in claim.notes

    unusable = [
        {"title": "Texte fictif", "status": "BROUILLON", "integrity_ok": True, "passages": [{"page_no": 1}]},
        {"title": "Texte abroge", "status": "ABROGE", "integrity_ok": True, "passages": [{"page_no": 2}]},
        {"title": "Texte altere", "status": "VALIDE", "integrity_ok": False, "passages": [{"page_no": 3}]},
        {"title": "Texte sans passage", "status": "VALIDE", "integrity_ok": True, "passages": []},
    ]
    claim = AlgerianLawAgent().run(_input([], refs=unusable)).claims[0]
    assert claim.status == EvidenceStatus.NON_ETABLI


def test_algerian_law_agent_only_points_to_passage():
    usable = [
        {
            "id": "reg-1",
            "title": "Texte officiel fictif",
            "reference": "FICTIF-001",
            "document_date": "2026-01-01",
            "status": "VALIDE",
            "integrity_ok": True,
            "passages": [{"id": "p1", "page_no": 4}],
        }
    ]
    claim = AlgerianLawAgent().run(_input([], refs=usable)).claims[0]
    assert claim.status == EvidenceStatus.A_VERIFIER
    assert "p. 4" in claim.statement
    assert "ne qualifie ni infraction" in claim.notes


def test_source_verifier_flags_weak_and_undated_sources():
    results = [
        _result("https://reseau-fictif.test/post", "Publication sans origine", SourceTier.T7_NON_ATTRIBUE, published_on=None),
        _result("https://social-fictif.test/compte", "Compte officiel fictif", SourceTier.T6_RESEAU_SOCIAL_OFFICIEL),
    ]
    claims = SourceVerifierAgent().run(_input(results)).claims
    natures = {claim.nature for claim in claims}
    assert ClaimNature.RUMEUR in natures
    assert any("aucune date de publication" in claim.statement for claim in claims)
    assert any("source non datée ne peut pas confirmer" in claim.notes for claim in claims)


def test_source_verifier_flags_official_vs_secondary_contradiction():
    results = [
        _result("https://officiel-fictif.test/decision", "Decision officielle fictive", SourceTier.T1_AUTORITE_OFFICIELLE),
        _result("https://media-a.test/1", "Article fictif A", SourceTier.T5_MEDIA_RECONNU),
        _result("https://media-b.test/2", "Article fictif B", SourceTier.T5_MEDIA_RECONNU),
    ]
    claims = SourceVerifierAgent().run(_input(results)).claims
    assert any(claim.status == EvidenceStatus.SOURCES_CONTRADICTOIRES for claim in claims)
    assert any("source officielle primaire prévaut" in claim.notes for claim in claims)


def test_reputation_agent_flags_predatory_signals():
    results = [
        _result(
            "https://revue-douteuse.test/appel",
            "Guaranteed publication for all submissions",
            SourceTier.T5_MEDIA_RECONNU,
            snippet="guaranteed publication within 48 hours",
        )
    ]
    claims = ScientificReputationAgent().run(_input(results)).claims
    assert any("pratique éditoriale douteuse" in claim.statement for claim in claims)
    assert all(claim.status != EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE for claim in claims)


def test_ranking_agent_returns_nr_when_evidence_is_insufficient():
    proposals = EventRankingAgent().run(_input([], label="Colloque fictif")).axis_proposals
    assert proposals
    assert all(proposal.proposed_score is None for proposal in proposals)
    assert all(not proposal.evidence_sufficient for proposal in proposals)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def test_agents_run_independently_on_isolated_input():
    """Un agent ne doit pas pouvoir modifier l'entrée vue par les autres."""
    results = [_result("https://a.test/1", "Source fictive", SourceTier.T2_INSTITUTION_ACADEMIQUE)]
    data = _input(results)
    outputs = orchestrator.run_agents(data)
    assert len(outputs) == 6
    assert {output.agent_name for output in outputs} == {item.value for item in AgentName}
    # L'entrée d'origine n'a pas été mutée.
    assert data.results == results


def test_homonymy_blocks_consolidated_conclusion():
    results = [
        _result("https://a.test/x", "Amina Belkacem — Institut Fictif du Nord", SourceTier.T2_INSTITUTION_ACADEMIQUE, publisher="Institut Fictif du Nord"),
        _result("https://b.test/y", "Amina Belkacem — Centre Fictif du Sud", SourceTier.T2_INSTITUTION_ACADEMIQUE, publisher="Centre Fictif du Sud"),
    ]
    result = orchestrator.orchestrate(_input(results))
    assert result.blocked is True
    assert result.message == AGENT_DISAGREEMENT_MESSAGE


def test_no_disagreement_when_evidence_is_consistent():
    results = [
        _result(
            "https://universite-fictive.test/equipe",
            "Amina Belkacem — Universite Fictive de Test",
            SourceTier.T2_INSTITUTION_ACADEMIQUE,
            publisher="Universite Fictive de Test",
        )
    ]
    result = orchestrator.orchestrate(_input(results))
    assert result.blocked is False
    assert "validation humaine" in result.message


# --------------------------------------------------------------------------
# Ranking externe
# --------------------------------------------------------------------------


def test_ranking_axes_configuration_totals_100(client):
    config = client.get("/api/v1/ranking/axes").json()
    assert sum(axis["max"] for axis in config["axes"]) == 100
    assert len(config["axes"]) == 7
    assert "non décisionnel" in config["title"]
    assert "jamais une note saisie" in config["warning"]


def test_ranking_with_insufficient_evidence_is_nr(session, dossier=None):
    from app.models import Dossier
    from app.services import dossier_service

    record = dossier_service.create_dossier(
        session, reference="MSI-RANK-1", title="Colloque fictif", organizer="Organisateur fictif"
    )
    result = orchestrator.orchestrate(
        AgentInput(
            subject_kind="MANIFESTATION",
            subject_label="Colloque fictif",
            declared_affiliation=None,
            results=[],
        )
    )
    ranking = ranking_service.build_ranking(
        session, record.id, run_id=None, orchestration=result
    )
    assert ranking.grade == RankingGrade.NR
    view = ranking_service.ranking_view(session, record.id)
    assert all(axis["display_score"] == NOT_PROVIDED for axis in view["axes"])
    assert isinstance(session.get(Dossier, record.id), Dossier)


def test_ranking_never_touches_official_grid(client, dossier):
    """Le ranking externe ne modifie jamais la grille scientifique officielle."""
    from app.core.db import get_session_factory

    before = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    with get_session_factory()() as db_session:
        result = orchestrator.orchestrate(
            AgentInput(
                subject_kind="MANIFESTATION",
                subject_label="Colloque fictif",
                declared_affiliation=None,
                results=[
                    _result(
                        "https://a.test/1",
                        "Colloque fictif — international proceedings indexed",
                        SourceTier.T3_PUBLICATION_SCIENTIFIQUE,
                    ),
                    _result(
                        "https://b.test/2",
                        "Colloque fictif — call for papers peer review",
                        SourceTier.T4_SITE_ORGANISATEUR,
                    ),
                ],
            )
        )
        ranking_service.build_ranking(db_session, dossier["id"], run_id=None, orchestration=result)

    after = client.get(f"/api/v1/dossiers/{dossier['id']}/evaluation").json()
    assert after["total"] == before["total"] is None
    assert after["criteria"] == before["criteria"]

    ranking = client.get(f"/api/v1/dossiers/{dossier['id']}/ranking").json()["ranking"]
    assert ranking is not None
    assert "strictement séparé" in ranking["separation_notice"]


def test_evaluator_can_review_a_ranking_axis(client, dossier):
    from app.core.db import get_session_factory

    with get_session_factory()() as db_session:
        result = orchestrator.orchestrate(
            AgentInput(
                subject_kind="MANIFESTATION",
                subject_label="Colloque fictif",
                declared_affiliation=None,
                results=[
                    _result("https://a.test/1", "Colloque fictif international proceedings", SourceTier.T3_PUBLICATION_SCIENTIFIQUE),
                    _result("https://b.test/2", "Colloque fictif call for papers", SourceTier.T4_SITE_ORGANISATEUR),
                ],
            )
        )
        ranking_service.build_ranking(db_session, dossier["id"], run_id=None, orchestration=result)

    axis = client.get(f"/api/v1/dossiers/{dossier['id']}/ranking").json()["ranking"]["axes"][0]

    short = client.post(
        f"/api/v1/ranking/axes/{axis['id']}", json={"decision": "ACCEPTE", "justification": "ok"}
    )
    assert short.status_code == 422

    accepted = client.post(
        f"/api/v1/ranking/axes/{axis['id']}",
        json={
            "decision": "ECARTE",
            "justification": "Axe ecarte : sources publiques insuffisantes pour ce dossier fictif.",
        },
    )
    assert accepted.status_code == 200
    assert "grille scientifique officielle n'est pas modifiée" in accepted.json()["notice"]


def test_ranking_axis_correction_is_bounded(client, dossier):
    from app.core.db import get_session_factory

    with get_session_factory()() as db_session:
        result = orchestrator.orchestrate(
            AgentInput(
                subject_kind="MANIFESTATION",
                subject_label="Colloque fictif",
                declared_affiliation=None,
                results=[_result("https://a.test/1", "Colloque fictif international", SourceTier.T4_SITE_ORGANISATEUR)],
            )
        )
        ranking_service.build_ranking(db_session, dossier["id"], run_id=None, orchestration=result)

    axis = client.get(f"/api/v1/dossiers/{dossier['id']}/ranking").json()["ranking"]["axes"][0]
    response = client.post(
        f"/api/v1/ranking/axes/{axis['id']}",
        json={
            "decision": "CORRIGE",
            "score": axis["max"] + 5,
            "justification": "Tentative de correction hors bornes pour le test fictif.",
        },
    )
    assert response.status_code == 422
    assert "hors bornes" in response.json()["error"]["message"]
