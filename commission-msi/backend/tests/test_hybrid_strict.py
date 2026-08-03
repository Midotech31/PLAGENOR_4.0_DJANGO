"""Mode `HYBRID_STRICT` : client réel, lecture assistée, garde-fous.

Le fil conducteur : **le modèle lit, il ne décide pas, et il ne fait entrer
aucune valeur dans le dossier sans montrer où elle est écrite.**

Aucun test ne sort du poste. Le client HTTP reçoit un ouvreur factice ; s'il
tentait un appel réel, l'assertion sur cet ouvreur le révélerait.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from app.core.config import reset_settings
from app.core.vocabulary import InformationStatus, JobState
from app.models import AiCall, ExtractedItem
from app.services import ai_client, ai_provider, ai_semantic_reading, job_service
from tests.fixtures import synthetic

PAGE_1 = """DEMANDE D'ORGANISATION D'UNE MANIFESTATION SCIENTIFIQUE INTERNATIONALE

Colloque international sur les materiaux durables et leurs applications

Universite Fictive de Test — Faculte des sciences
Campus fictif, Alger, du 12 au 14 mars 2027, en presentiel
"""


# --------------------------------------------------------------------------
# Ouvreurs factices
# --------------------------------------------------------------------------


class _Response:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class _Opener:
    """Ouvreur factice : enregistre la requête, rend une réponse programmée."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return _Response(self.payload)


class _FailingOpener:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def open(self, request, timeout=None):
        raise self.error


def _install_client(monkeypatch: pytest.MonkeyPatch, opener) -> None:
    """Fait construire au fournisseur un vrai client, branché sur un ouvreur factice.

    La vraie classe est capturée **avant** le remplacement : sans cela, la
    fabrique s'appellerait elle-même.
    """
    real = ai_client.AnthropicClient
    monkeypatch.setattr(ai_client, "AnthropicClient", lambda **kw: real(opener=opener))


def _text_payload(content: dict) -> dict:
    """Réponse de l'API Messages contenant `content` en JSON dans un bloc texte."""
    return {
        "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}],
        "model": "modele-fictif",
    }


@pytest.fixture
def hybrid(monkeypatch: pytest.MonkeyPatch):
    """Active le mode hybride avec une clé factice, jamais utilisée en ligne."""
    for name, value in (
        ("ANALYSIS_MODE", "HYBRID_STRICT"),
        ("ALLOW_EXTERNAL_AI", "1"),
        ("ANTHROPIC_API_KEY", "cle-de-test-jamais-reelle"),
        ("ANTHROPIC_MODEL_ANALYSIS", "modele-fictif"),
        ("MSI_PRIVACY_ACKNOWLEDGED", "1"),
    ):
        monkeypatch.setenv(name, value)
    reset_settings()
    yield
    reset_settings()


# --------------------------------------------------------------------------
# Le client
# --------------------------------------------------------------------------


def test_the_client_sends_the_key_in_the_header_and_never_in_the_body(hybrid):
    opener = _Opener(_text_payload({"champs": []}))
    client = ai_client.AnthropicClient(opener=opener)

    client.complete(
        model_id="modele-fictif",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    sent = opener.requests[0]
    assert sent.get_header("X-api-key") == "cle-de-test-jamais-reelle"
    assert sent.get_header("Anthropic-version") == ai_client.ANTHROPIC_API_VERSION
    assert "cle-de-test-jamais-reelle" not in sent.data.decode("utf-8")


def test_the_client_sends_no_sampling_parameter(hybrid):
    """`temperature`, `top_p` et `top_k` sont refusés par les modèles récents."""
    opener = _Opener(_text_payload({"champs": []}))
    ai_client.AnthropicClient(opener=opener).complete(
        model_id="claude-opus-5",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    body = json.loads(opener.requests[0].data.decode("utf-8"))
    for refuse in ("temperature", "top_p", "top_k"):
        assert refuse not in body, f"{refuse} ferait échouer l'appel"
    assert body["model"] == "claude-opus-5"
    # Le plafond couvre le raisonnement ET la réponse : trop bas, il tronque.
    assert body["max_tokens"] >= 16000


def test_a_repli_is_requested_only_where_the_api_accepts_it(hybrid):
    """L'envoyer à un modèle qui ne le connaît pas ferait échouer la requête."""
    capable = _Opener(_text_payload({"champs": []}))
    ai_client.AnthropicClient(opener=capable).complete(
        model_id="claude-opus-5",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )
    body = json.loads(capable.requests[0].data.decode("utf-8"))
    assert body["fallbacks"] == "default"
    assert capable.requests[0].get_header("Anthropic-beta") == ai_client.FALLBACK_BETA

    autre = _Opener(_text_payload({"champs": []}))
    ai_client.AnthropicClient(opener=autre).complete(
        model_id="claude-sonnet-5",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )
    body = json.loads(autre.requests[0].data.decode("utf-8"))
    assert "fallbacks" not in body
    assert autre.requests[0].get_header("Anthropic-beta") is None


def test_a_refusal_is_reported_as_such_not_as_a_breakdown(hybrid):
    """Un refus est une réponse valide : `content` peut être vide."""
    opener = _Opener({"stop_reason": "refusal", "content": []})

    with pytest.raises(RuntimeError, match="refusée par les filtres"):
        ai_client.AnthropicClient(opener=opener).complete(
            model_id="claude-opus-5",
            request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
        )


def test_the_client_never_returns_the_private_reasoning(hybrid):
    opener = _Opener(
        {
            "content": [
                {"type": "thinking", "thinking": "raisonnement privé à ne jamais conserver"},
                {"type": "text", "text": json.dumps({"champs": [], "remarques": []})},
            ]
        }
    )

    content = ai_client.AnthropicClient(opener=opener).complete(
        model_id="modele-fictif",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    assert content == {"champs": [], "remarques": []}
    assert "raisonnement" not in json.dumps(content, ensure_ascii=False)


def test_an_unknown_model_is_not_silently_replaced(hybrid):
    opener = _FailingOpener(
        urllib.error.HTTPError(
            ai_client.ANTHROPIC_ENDPOINT,
            404,
            "Not Found",
            {},
            io.BytesIO(json.dumps({"error": {"type": "not_found_error"}}).encode("utf-8")),
        )
    )
    provider = ai_provider.HybridStrictProvider(
        client=ai_client.AnthropicClient(opener=opener)
    )

    with pytest.raises(ai_provider.ModelUnavailable) as raised:
        provider.complete(ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]))

    assert raised.value.code == "MODEL_UNAVAILABLE"
    assert "basculement" in str(raised.value)


def test_an_answer_that_is_not_json_yields_no_value(hybrid):
    opener = _Opener({"content": [{"type": "text", "text": "je pense que oui"}]})

    with pytest.raises(RuntimeError, match="aucune valeur n'est retenue"):
        ai_client.AnthropicClient(opener=opener).complete(
            model_id="modele-fictif",
            request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
        )


def test_the_hybrid_provider_now_has_a_real_client(hybrid):
    """Le manque comblé : le mode était configurable mais jamais opérant."""
    provider = ai_provider.get_provider()

    assert provider.mode == ai_provider.HYBRID_STRICT
    assert isinstance(provider._client, ai_client.AnthropicClient)


def test_local_only_never_builds_anything_that_can_leave_the_machine(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "LOCAL_ONLY")
    reset_settings()
    try:
        provider = ai_provider.get_provider()
        assert provider.mode == ai_provider.LOCAL_ONLY
        assert not hasattr(provider, "_client")
    finally:
        reset_settings()


# --------------------------------------------------------------------------
# Vérification des propositions
# --------------------------------------------------------------------------


def test_a_value_without_a_verifiable_excerpt_is_refused():
    pages = {1: PAGE_1}
    kept, rejected = ai_semantic_reading.verify(
        [
            {
                "cle": "lieu",
                "valeur": "Campus fictif, Alger",
                "page": 1,
                "extrait": "Campus fictif, Alger, du 12 au 14 mars 2027",
            },
            {
                "cle": "budget_total",
                "valeur": "3 000 000 DA",
                "page": 1,
                "extrait": "Le budget previsionnel s'eleve a trois millions de dinars",
            },
        ],
        pages,
        {"lieu", "budget_total"},
    )

    assert [item.key for item in kept] == ["lieu"]
    assert len(rejected) == 1
    assert rejected[0]["cle"] == "budget_total"
    assert "introuvable" in rejected[0]["motif"]


def test_a_value_citing_a_page_that_was_not_sent_is_refused():
    _kept, rejected = ai_semantic_reading.verify(
        [{"cle": "lieu", "valeur": "Oran", "page": 42, "extrait": "le lieu retenu est Oran"}],
        {1: PAGE_1},
        {"lieu"},
    )
    assert rejected[0]["motif"].startswith("page 42 absente")


def test_a_field_outside_the_requested_list_is_refused():
    _kept, rejected = ai_semantic_reading.verify(
        [
            {
                "cle": "avis_du_rapporteur",
                "valeur": "FAVORABLE",
                "page": 1,
                "extrait": "Colloque international sur les materiaux durables",
            }
        ],
        {1: PAGE_1},
        {"lieu"},
    )
    # Le modèle ne peut pas glisser un avis dans le dossier par ce chemin.
    assert rejected[0]["motif"] == "champ hors de la liste demandée"


def test_a_too_short_excerpt_proves_nothing():
    _kept, rejected = ai_semantic_reading.verify(
        [{"cle": "format", "valeur": "présentiel", "page": 1, "extrait": "en"}],
        {1: PAGE_1},
        {"format"},
    )
    assert "trop court" in rejected[0]["motif"]


def test_pages_are_batched_within_the_character_budget():
    pages = {n: "x" * 20_000 for n in range(1, 8)}
    batches = ai_semantic_reading.build_batches(pages)

    assert sum(len(batch) for batch in batches) == 7
    for batch in batches:
        total = sum(len(pages[page_no]) for page_no in batch)
        assert total <= ai_semantic_reading.CHARS_PER_CALL or len(batch) == 1
    # Les pages restent entières et ordonnées : un extrait reste vérifiable.
    assert [page_no for batch in batches for page_no in batch] == list(range(1, 8))


# --------------------------------------------------------------------------
# Bout en bout, dans le pipeline
# --------------------------------------------------------------------------


def _import(client, dossier, pages: list[str]):
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", synthetic.make_pdf(pages), "application/pdf")},
    )


def test_assisted_reading_fills_a_field_that_no_label_announces(
    hybrid, client, dossier, session, monkeypatch
):
    """Le cas réel : la page dit tout, mais pas sous la forme « Libellé : valeur »."""
    assert _import(client, dossier, [PAGE_1]).status_code == 201

    opener = _Opener(
        _text_payload(
            {
                "champs": [
                    {
                        "cle": "etablissement_organisateur",
                        "valeur": "Universite Fictive de Test",
                        "page": 1,
                        "extrait": "Universite Fictive de Test — Faculte des sciences",
                    }
                ],
                "non_trouves": ["sponsors"],
                "remarques": [],
            }
        )
    )
    _install_client(monkeypatch, opener)

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    assert job_service.work_once() == created["id"]

    state = client.get(f"/api/v1/dossiers/{dossier['id']}/traitement").json()["job"]
    assert state["state"] == JobState.COMPLETED, state["error_message"]

    item = session.scalars(
        session.query(ExtractedItem)
        .filter(
            ExtractedItem.dossier_id == dossier["id"],
            ExtractedItem.key == "etablissement_organisateur",
        )
        .statement
    ).first()
    session.refresh(item)
    assert item.page_no == 1
    # Proposée, jamais confirmée : la confirmation appartient à l'évaluateur.
    assert item.status == InformationStatus.A_VERIFIER
    assert item.confidence == ai_semantic_reading.CONFIDENCE_READING


def test_the_call_is_journalled_without_its_content(hybrid, client, dossier, session, monkeypatch):
    assert _import(client, dossier, [PAGE_1]).status_code == 201
    opener = _Opener(_text_payload({"champs": [], "non_trouves": [], "remarques": []}))
    _install_client(monkeypatch, opener)

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    job_service.work_once()

    calls = session.scalars(
        session.query(AiCall).filter(AiCall.dossier_id == dossier["id"]).statement
    ).all()
    assert calls, "l'appel doit laisser une trace auditables"
    call = calls[0]
    assert call.role == ai_semantic_reading.ROLE
    assert call.job_id == created["id"]
    assert call.model_id == "modele-fictif"
    # Empreintes et catégories, jamais le contenu en clair.
    assert len(call.input_sha256) == 64
    assert "EXTRAIT_TEXTE" in call.data_categories
    for column in (call.input_sha256, call.output_sha256, call.data_categories):
        assert "Universite Fictive" not in (column or "")


def test_local_only_says_the_reading_was_not_active(client, dossier, session, monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "LOCAL_ONLY")
    reset_settings()
    assert _import(client, dossier, [PAGE_1]).status_code == 201

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    assert job_service.work_once() == created["id"]

    state = client.get(f"/api/v1/dossiers/{dossier['id']}/traitement").json()["job"]
    assert JobState.SEMANTIC_READING in state["steps_done"]

    checkpoint = job_service.checkpoint_for(session, created["id"], JobState.SEMANTIC_READING)
    result = json.loads(checkpoint.result_json)
    # L'étape ne bascule pas silencieusement : elle écrit qu'elle n'a pas eu lieu.
    assert result["active"] is False
    assert "inactive" in result["constat"]


def test_a_failed_call_does_not_produce_a_report_built_on_nothing(
    hybrid, client, dossier, monkeypatch
):
    """Absorber la panne donnerait un rapport d'apparence normale. Elle remonte."""
    assert _import(client, dossier, [PAGE_1]).status_code == 201
    opener = _FailingOpener(urllib.error.URLError("réseau indisponible"))
    _install_client(monkeypatch, opener)

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    job_service.work_once()

    state = client.get(f"/api/v1/dossiers/{dossier['id']}/traitement").json()["job"]
    assert state["state"] in {JobState.QUEUED, JobState.FAILED}
    assert state["error_message"]
    assert "Reprendre" in state["error_message"]


def test_a_restricted_document_is_never_read_by_the_model(hybrid, client, dossier, session):
    from app.models import Document

    assert _import(client, dossier, [PAGE_1]).status_code == 201
    document = session.scalars(
        session.query(Document).filter(Document.dossier_id == dossier["id"]).statement
    ).first()
    document.sensitivity = "RESTREINT"
    session.commit()

    pages, withheld = ai_semantic_reading.readable_pages(session, dossier["id"])

    assert pages == {}
    assert withheld >= 1
