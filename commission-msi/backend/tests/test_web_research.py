"""Recherche Internet contrôlée : sortie réseau, redaction, agents, ranking.

Aucun test n'émet de requête réelle : un fournisseur fictif est enregistré.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from app.core.vocabulary import (
    AGENT_DISAGREEMENT_MESSAGE,
    WEB_UNAVAILABLE_MESSAGE,
    ClaimNature,
    DossierStatus,
    EvidenceStatus,
    InformationStatus,
    RankingGrade,
    SourceTier,
    WebRunStatus,
)
from app.web_research import egress, providers, redaction
from tests.fixtures import synthetic


# --------------------------------------------------------------------------
# Fournisseur fictif
# --------------------------------------------------------------------------


@dataclass
class FakeProvider:
    name: str = "fournisseur_fictif"
    tier: str = SourceTier.T2_INSTITUTION_ACADEMIQUE
    results: list = field(default_factory=list)
    error: Exception | None = None
    calls: list = field(default_factory=list)
    enabled: bool = True

    def is_configured(self) -> bool:
        return True

    def is_enabled(self) -> bool:
        return self.enabled

    def search(self, query: str, *, limit: int = 5):
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return list(self.results[:limit])


def _result(url: str, title: str, tier: str, *, publisher=None, published_on="2026-01-15", snippet=""):
    return providers.SearchResult(
        url=url,
        title=title,
        publisher=publisher,
        published_on=published_on,
        snippet=snippet or title,
        tier=tier,
        consulted_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch):
    provider = FakeProvider()
    providers.reset_registry()
    for existing in list(providers.provider_states()):
        providers.unregister(existing["name"])
    providers.register(provider)
    monkeypatch.setattr(
        providers,
        "check_connectivity",
        lambda timeout=5: {
            "online": True,
            "reason": "Fournisseur fictif joignable.",
            "checked_at": datetime.now(timezone.utc),
        },
    )
    return provider


def _prepare_dossier(client, dossier):
    """Renseigne des informations publiques fictives puis prépare une campagne."""
    client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("d.pdf", synthetic.make_pdf([synthetic.NATIVE_TEXT_FR]), "application/pdf")},
    )
    items = client.get(f"/api/v1/dossiers/{dossier['id']}/informations").json()["items"]
    for key, value in (
        ("intitule", "Colloque international fictif sur les materiaux durables"),
        ("responsable_scientifique", "Amina Belkacem"),
    ):
        item = next(item for item in items if item["key"] == key)
        response = client.post(
            f"/api/v1/dossiers/{dossier['id']}/informations/{item['id']}",
            json={
                "value": value,
                "status": InformationStatus.CONFIRME,
                "reason": "Confirme depuis la fiche technique fictive.",
                "page_no": 1,
                "source_excerpt": value,
            },
        )
        assert response.status_code == 200, response.text
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/recherche-web", json={"scope_note": "Test fictif."}
    )


# --------------------------------------------------------------------------
# Politique de sortie réseau
# --------------------------------------------------------------------------


def test_network_kill_switch_blocks_all_egress(monkeypatch):
    monkeypatch.setenv("MSI_NETWORK_DISABLED", "1")
    allowed, reason = egress.is_allowed("https://api.crossref.org/works")
    assert allowed is False
    assert "coupés" in reason
    with pytest.raises(egress.EgressRefused):
        egress.authorize("https://api.crossref.org/works")


def test_non_whitelisted_domain_is_refused(monkeypatch):
    monkeypatch.delenv("MSI_NETWORK_DISABLED", raising=False)
    with pytest.raises(egress.EgressRefused) as excinfo:
        egress.authorize("https://exemple.invalid/recherche")
    assert "liste blanche" in excinfo.value.message


def test_plain_http_is_refused(monkeypatch):
    monkeypatch.delenv("MSI_NETWORK_DISABLED", raising=False)
    with pytest.raises(egress.EgressRefused) as excinfo:
        egress.authorize("http://api.crossref.org/works")
    assert "TLS obligatoire" in excinfo.value.message


def test_allowed_domain_passes_and_is_logged(monkeypatch):
    monkeypatch.delenv("MSI_NETWORK_DISABLED", raising=False)
    egress.clear_egress_log()
    egress.authorize("https://api.crossref.org/works?query=test")
    entries = egress.egress_log()
    assert entries[-1].domain == "api.crossref.org"
    assert entries[-1].allowed is True


def test_egress_policy_is_exposed(client):
    state = client.get("/api/v1/recherche-web/fournisseurs").json()["egress"]
    assert state["tls_required"] is True
    assert state["inbound_listen"] == "127.0.0.1 uniquement"
    assert "Aucun PDF" in state["notice"]


# --------------------------------------------------------------------------
# Protection des données sortantes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, fragment",
    [
        ("%PDF-1.7 contenu", "PDF"),
        ("copie du passeport n 123456789", "identité"),
        ("contact prenom.nom@exemple.org", "courriel"),
        ("telephone +213 555 123 456", "téléphone"),
        ("date de naissance 1970", "état civil"),
        ("note interne du dossier", "document interne"),
    ],
)
def test_forbidden_payloads_never_leave_the_workstation(payload, fragment):
    with pytest.raises(redaction.PayloadRefused) as excinfo:
        redaction.assert_sendable(payload, subject_kind="PERSONNE")
    assert fragment in excinfo.value.message


def test_pdf_upload_to_provider_is_refused():
    with pytest.raises(redaction.PayloadRefused) as excinfo:
        redaction.assert_no_document(synthetic.make_pdf([synthetic.NATIVE_TEXT_FR]))
    assert "ne quitte jamais le poste" in excinfo.value.message


def test_minimal_public_query_is_allowed():
    report = redaction.assert_sendable(
        "Amina Belkacem Universite Fictive de Test", subject_kind="PERSONNE"
    )
    assert report["verdict"] == "AUTORISEE"


def test_overlong_or_multiline_query_is_refused():
    with pytest.raises(redaction.PayloadRefused):
        redaction.assert_sendable("a" * 400, subject_kind="PERSONNE")
    with pytest.raises(redaction.PayloadRefused):
        redaction.assert_sendable("ligne1\nligne2", subject_kind="PERSONNE")


def test_unknown_subject_kind_is_refused():
    with pytest.raises(redaction.PayloadRefused):
        redaction.assert_sendable("test", subject_kind="DOSSIER_COMPLET")


# --------------------------------------------------------------------------
# Cycle de vie d'une campagne
# --------------------------------------------------------------------------


def test_offline_run_fails_explicitly(client, dossier, monkeypatch):
    """Sans Internet, le cœur local reste utilisable et l'échec est explicite."""
    monkeypatch.setattr(
        providers,
        "check_connectivity",
        lambda timeout=5: {"online": False, "reason": "Hors ligne (test).", "checked_at": None},
    )
    prepared = _prepare_dossier(client, dossier)
    assert prepared.status_code == 201
    run = prepared.json()
    assert run["connectivity_ok"] is False

    query = run["queries"][0]
    client.post(
        f"/api/v1/recherche-web/{run['id']}/requetes/{query['id']}",
        json={"query_text": query["query_text"], "approved": True},
    )
    client.post(
        f"/api/v1/recherche-web/{run['id']}/approbation",
        json={"approved_by": "Prof. Merzoug Mohamed"},
    )
    executed = client.post(f"/api/v1/recherche-web/{run['id']}/execution").json()
    assert executed["online"] is False
    assert executed["status"] == WebRunStatus.ECHOUEE
    assert executed["message"] == WEB_UNAVAILABLE_MESSAGE

    # Le cœur documentaire reste pleinement utilisable.
    assert client.get(f"/api/v1/dossiers/{dossier['id']}/pages").status_code == 200


def test_execution_without_approval_is_refused(client, dossier, fake_provider):
    run = _prepare_dossier(client, dossier).json()
    response = client.post(f"/api/v1/recherche-web/{run['id']}/execution")
    assert response.status_code == 422
    assert "non approuvée" in response.json()["error"]["message"]
    assert fake_provider.calls == []


def test_approval_requires_at_least_one_approved_query(client, dossier, fake_provider):
    run = _prepare_dossier(client, dossier).json()
    response = client.post(
        f"/api/v1/recherche-web/{run['id']}/approbation",
        json={"approved_by": "Prof. Merzoug Mohamed"},
    )
    assert response.status_code == 422
    assert "rien ne peut quitter le poste" in response.json()["error"]["message"]


def test_query_can_be_edited_before_sending(client, dossier, fake_provider):
    run = _prepare_dossier(client, dossier).json()
    query = run["queries"][0]
    response = client.post(
        f"/api/v1/recherche-web/{run['id']}/requetes/{query['id']}",
        json={"query_text": "Requete relue par l evaluateur", "approved": True},
    )
    assert response.status_code == 200
    assert response.json()["query_text"] == "Requete relue par l evaluateur"


def test_editing_query_with_personal_data_is_refused(client, dossier, fake_provider):
    run = _prepare_dossier(client, dossier).json()
    query = run["queries"][0]
    response = client.post(
        f"/api/v1/recherche-web/{run['id']}/requetes/{query['id']}",
        json={"query_text": "Amina Belkacem passeport 123456789", "approved": True},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ENVOI_REFUSE"


def _approve_and_run(client, dossier, run):
    for query in run["queries"]:
        client.post(
            f"/api/v1/recherche-web/{run['id']}/requetes/{query['id']}",
            json={"query_text": query["query_text"], "approved": True},
        )
    client.post(
        f"/api/v1/recherche-web/{run['id']}/approbation",
        json={"approved_by": "Prof. Merzoug Mohamed"},
    )
    return client.post(f"/api/v1/recherche-web/{run['id']}/execution").json()


def test_successful_run_records_sources_and_claims(client, dossier, fake_provider):
    fake_provider.results = [
        _result(
            "https://universite-fictive.test/equipe",
            "Amina Belkacem — Universite Fictive de Test",
            SourceTier.T2_INSTITUTION_ACADEMIQUE,
            publisher="Universite Fictive de Test",
        ),
        _result(
            "https://revue-fictive.test/article",
            "Publication fictive sur les materiaux durables",
            SourceTier.T3_PUBLICATION_SCIENTIFIQUE,
            publisher="Revue Fictive",
        ),
    ]
    run = _prepare_dossier(client, dossier).json()
    executed = _approve_and_run(client, dossier, run)
    assert executed["online"] is True
    assert executed["sources"] > 0
    assert executed["claims"] > 0

    detail = client.get(f"/api/v1/recherche-web/{run['id']}").json()
    assert detail["sources"]
    for source in detail["sources"]:
        assert source["url"].startswith("https://")
        assert source["consulted_at"] is not None
        assert source["tier"] in {item.value for item in SourceTier}
    for claim in detail["claims"]:
        assert claim["human_status"] == EvidenceStatus.A_VERIFIER
        assert claim["nature"] in {item.value for item in ClaimNature}
    assert "Aucun document du dossier n'a été transmis" in detail["notice"]


def test_provider_failure_is_explicit_and_not_silent(client, dossier, fake_provider):
    import urllib.error

    fake_provider.error = urllib.error.URLError("delai depasse")
    run = _prepare_dossier(client, dossier).json()
    executed = _approve_and_run(client, dossier, run)
    assert executed["provider_errors"]
    assert any("injoignable" in error for error in executed["provider_errors"])


def test_no_result_is_never_proof_of_absence(client, dossier, fake_provider):
    fake_provider.results = []
    run = _prepare_dossier(client, dossier).json()
    _approve_and_run(client, dossier, run)
    detail = client.get(f"/api/v1/recherche-web/{run['id']}").json()
    statements = " ".join(claim["statement"] for claim in detail["claims"])
    assert "ne prouve ni l'absence d'activité, ni l'absence de risque" in statements


def test_run_can_be_paused_resumed_and_dismissed(client, dossier, fake_provider):
    run = _prepare_dossier(client, dossier).json()
    assert (
        client.post(
            f"/api/v1/recherche-web/{run['id']}/etat", json={"status": WebRunStatus.EN_PAUSE}
        ).json()["status"]
        == WebRunStatus.EN_PAUSE
    )
    short = client.post(
        f"/api/v1/recherche-web/{run['id']}/etat",
        json={"status": WebRunStatus.ECARTEE_PAR_HUMAIN, "justification": "court"},
    )
    assert short.status_code == 422
    dismissed = client.post(
        f"/api/v1/recherche-web/{run['id']}/etat",
        json={
            "status": WebRunStatus.ECARTEE_PAR_HUMAIN,
            "justification": "Recherche ecartee : information deja verifiee hors application.",
        },
    )
    assert dismissed.json()["status"] == WebRunStatus.ECARTEE_PAR_HUMAIN


def test_enriched_state_requires_terminal_run(client, dossier, fake_provider):
    before = client.get(f"/api/v1/dossiers/{dossier['id']}/recherche-web").json()["enriched_state"]
    assert before["complete"] is False
    assert before["message"] == WEB_UNAVAILABLE_MESSAGE

    refused = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-enrichie")
    assert refused.status_code == 422

    run = _prepare_dossier(client, dossier).json()
    _approve_and_run(client, dossier, run)
    accepted = client.post(f"/api/v1/dossiers/{dossier['id']}/analyse-enrichie")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == DossierStatus.ANALYSE_ENRICHIE_COMPLETE


def test_dossier_status_moves_through_web_states(client, dossier, fake_provider):
    _prepare_dossier(client, dossier)
    assert (
        client.get(f"/api/v1/dossiers/{dossier['id']}").json()["status"]
        == DossierStatus.RECHERCHE_WEB_REQUISE
    )


def test_web_audit_trail_is_complete(client, dossier, fake_provider):
    fake_provider.results = [
        _result("https://a.test/x", "Source fictive A", SourceTier.T2_INSTITUTION_ACADEMIQUE)
    ]
    run = _prepare_dossier(client, dossier).json()
    _approve_and_run(client, dossier, run)
    actions = {event["action"] for event in client.get("/api/v1/audit", params={"limit": 500}).json()["items"]}
    for expected in (
        "WEB_RUN_PREPARE",
        "WEB_QUERY_EDIT",
        "WEB_RUN_APPROVE",
        "WEB_RUN_START",
        "WEB_QUERY_SENT",
        "AGENT_RUN",
        "RANKING_BUILD",
    ):
        assert expected in actions, f"action {expected} absente du journal"
