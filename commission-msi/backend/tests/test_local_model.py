"""Mode `LOCAL_MODEL` : lecture sémantique par un modèle installé sur le poste.

Le fil conducteur : **la lecture devient possible sans que rien ne sorte.**

C'est la garantie de souveraineté du mode local, avec la lecture en plus — et
non un mode dégradé du mode hybride. Un modèle local lit moins bien ; il ne lit
pas moins sûrement, parce que le contrôle des extraits est le même.

Aucun test ne sort du poste : le client reçoit un ouvreur factice.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from app.core.config import get_settings, reset_settings
from app.core.vocabulary import InformationStatus, JobState
from app.services import ai_provider, ai_semantic_reading, job_service, local_model_client
from tests.fixtures import synthetic

PAGE_1 = """DEMANDE D'ORGANISATION D'UNE MANIFESTATION SCIENTIFIQUE INTERNATIONALE

Colloque international sur les materiaux durables et leurs applications

Universite Fictive de Test — Faculte des sciences
Campus fictif, Alger, du 12 au 14 mars 2027, en presentiel
"""


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


def _chat_payload(content: dict) -> dict:
    """Réponse d'Ollama : le JSON produit est dans `message.content`."""
    return {
        "model": "qwen2.5:7b",
        "message": {"role": "assistant", "content": json.dumps(content, ensure_ascii=False)},
        "done": True,
    }


@pytest.fixture
def local_mode(monkeypatch: pytest.MonkeyPatch):
    for name, value in (
        ("ANALYSIS_MODE", "LOCAL_MODEL"),
        ("MSI_LOCAL_MODEL", "qwen2.5:7b"),
    ):
        monkeypatch.setenv(name, value)
    reset_settings()
    yield
    reset_settings()


# --------------------------------------------------------------------------
# La garantie de souveraineté
# --------------------------------------------------------------------------


def test_nothing_leaves_the_machine_in_this_mode(local_mode):
    """L'intérêt central : lire sans transmettre."""
    state = ai_provider.status()

    assert state["mode"] == ai_provider.LOCAL_MODEL
    assert state["external_transmission"] is False
    assert state["identity_documents_transmitted"] is False
    assert state["original_pdf_transmitted"] is False
    assert "Rien ne quitte la machine" in state["notice"]


def test_the_recommended_mode_needs_neither_key_nor_subscription(local_mode):
    """Recommander un mode payant à une commission publique serait discutable."""
    assert ai_provider.status()["recommended"] == ai_provider.LOCAL_MODEL


def test_the_local_provider_never_builds_an_external_client(local_mode):
    provider = ai_provider.get_provider()

    assert provider.mode == ai_provider.LOCAL_MODEL
    assert provider.available()
    # Aucun client Anthropic n'est construit : le mode ne peut pas sortir.
    assert provider._client is None


def test_an_unconfigured_local_model_says_what_is_missing(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "LOCAL_MODEL")
    monkeypatch.delenv("MSI_LOCAL_MODEL", raising=False)
    reset_settings()
    try:
        described = ai_provider.get_provider().describe()
        assert described["available"] is False
        assert any("MSI_LOCAL_MODEL" in item for item in described["missing"])
    finally:
        reset_settings()


# --------------------------------------------------------------------------
# Le client
# --------------------------------------------------------------------------


def test_the_context_window_is_always_stated(local_mode):
    """La valeur par défaut d'Ollama tronquerait les pages en silence."""
    opener = _Opener(_chat_payload({"champs": []}))
    local_model_client.LocalModelClient(opener=opener).complete(
        model_id="qwen2.5:7b",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    body = json.loads(opener.requests[0].data.decode("utf-8"))
    assert body["options"]["num_ctx"] == get_settings().local_model_context
    # Sortie contrainte : un petit modèle rendrait sinon du texte commenté.
    assert body["format"] == "json"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0


def test_the_call_stays_on_the_loopback(local_mode):
    opener = _Opener(_chat_payload({"champs": []}))
    local_model_client.LocalModelClient(opener=opener).complete(
        model_id="qwen2.5:7b",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    assert opener.requests[0].full_url.startswith("http://127.0.0.1:")


def test_a_reasoning_block_is_never_kept(local_mode):
    """Certains modèles locaux encadrent leur réponse d'un bloc <think>."""
    opener = _Opener(
        {
            "message": {
                "role": "assistant",
                "content": "<think>raisonnement privé</think>" + json.dumps({"champs": []}),
            }
        }
    )

    content = local_model_client.LocalModelClient(opener=opener).complete(
        model_id="qwen2.5:7b",
        request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
    )

    assert content == {"champs": []}
    assert "raisonnement" not in json.dumps(content, ensure_ascii=False)


def test_a_missing_model_is_not_a_breakdown(local_mode):
    """404 d'Ollama = modèle absent : cela se corrige, cela ne se réessaie pas."""
    opener = _FailingOpener(
        urllib.error.HTTPError("http://127.0.0.1:11434/api/chat", 404, "Not Found", {}, None)
    )
    provider = ai_provider.LocalModelProvider(
        client=local_model_client.LocalModelClient(opener=opener)
    )

    with pytest.raises(ai_provider.ModelUnavailable):
        provider.complete(ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]))


def test_a_stopped_server_names_itself(local_mode):
    opener = _FailingOpener(urllib.error.URLError("Connection refused"))

    with pytest.raises(RuntimeError, match="ne répond pas"):
        local_model_client.LocalModelClient(opener=opener).installed_models()


def test_malformed_json_yields_no_value(local_mode):
    """Un petit modèle produit parfois autre chose que du JSON."""
    opener = _Opener({"message": {"role": "assistant", "content": "je pense que oui"}})

    with pytest.raises(RuntimeError, match="aucune valeur n'est retenue"):
        local_model_client.LocalModelClient(opener=opener).complete(
            model_id="qwen2.5:7b",
            request=ai_provider.AiRequest(role="TEST", instruction="lis", blocks=[]),
        )


# --------------------------------------------------------------------------
# Le découpage, adapté à la fenêtre du poste
# --------------------------------------------------------------------------


def test_batches_shrink_to_fit_a_local_context_window(local_mode):
    """Dépasser la fenêtre ne lève aucune erreur : le texte est tronqué."""
    budget_local = ai_semantic_reading.budget_for(ai_provider.get_provider())
    fenetre = get_settings().local_model_context

    assert budget_local < ai_semantic_reading.CHARS_PER_CALL
    # Le budget doit tenir dans la fenêtre, marge comprise pour la réponse.
    assert budget_local <= fenetre * ai_semantic_reading.CHARS_PER_TOKEN

    pages = {n: "x" * 6_000 for n in range(1, 11)}
    lots = ai_semantic_reading.build_batches(pages, budget_local)
    for lot in lots:
        total = sum(len(pages[p]) for p in lot)
        assert total <= budget_local or len(lot) == 1


def test_a_service_model_keeps_the_large_budget(monkeypatch):
    monkeypatch.setenv("ANALYSIS_MODE", "LOCAL_ONLY")
    reset_settings()
    try:
        distant = ai_provider.HybridStrictProvider(client=None)
        assert ai_semantic_reading.budget_for(distant) == ai_semantic_reading.CHARS_PER_CALL
    finally:
        reset_settings()


# --------------------------------------------------------------------------
# Bout en bout
# --------------------------------------------------------------------------


def _import(client, dossier, pages: list[str]):
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": ("dossier.pdf", synthetic.make_pdf(pages), "application/pdf")},
    )


def test_the_local_model_fills_a_field_no_label_announces(
    local_mode, client, dossier, session, monkeypatch
):
    assert _import(client, dossier, [PAGE_1]).status_code == 201

    opener = _Opener(
        _chat_payload(
            {
                "champs": [
                    {
                        "cle": "etablissement_organisateur",
                        "valeur": "Universite Fictive de Test",
                        "page": 1,
                        "extrait": "Universite Fictive de Test — Faculte des sciences",
                    }
                ],
                "non_trouves": [],
                "remarques": [],
            }
        )
    )
    real = local_model_client.LocalModelClient
    monkeypatch.setattr(
        local_model_client, "LocalModelClient", lambda **kw: real(opener=opener)
    )

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    assert job_service.work_once() == created["id"]

    state = client.get(f"/api/v1/dossiers/{dossier['id']}/traitement").json()["job"]
    assert state["state"] == JobState.COMPLETED, state["error_message"]

    lecture = state["lecture_assistee"]
    assert lecture["active"] is True
    assert lecture["proposed"] >= 1
    assert lecture["model_id"] == "qwen2.5:7b"
    # La garantie tient jusque dans le compte rendu affiché.
    assert lecture["pages_retenues_sur_le_poste"] == 0

    from app.models import ExtractedItem

    item = session.scalars(
        session.query(ExtractedItem)
        .filter(
            ExtractedItem.dossier_id == dossier["id"],
            ExtractedItem.key == "etablissement_organisateur",
        )
        .statement
    ).first()
    session.refresh(item)
    assert item.status == InformationStatus.A_VERIFIER


def test_an_invented_value_is_refused_just_as_strictly(
    local_mode, client, dossier, monkeypatch
):
    """Le point qui rend un petit modèle utilisable : il ne peut pas inventer."""
    assert _import(client, dossier, [PAGE_1]).status_code == 201

    opener = _Opener(
        _chat_payload(
            {
                "champs": [
                    {
                        "cle": "budget_total",
                        "valeur": "3 000 000 DA",
                        "page": 1,
                        "extrait": "Le budget previsionnel s'eleve a trois millions",
                    }
                ],
                "non_trouves": [],
                "remarques": [],
            }
        )
    )
    real = local_model_client.LocalModelClient
    monkeypatch.setattr(
        local_model_client, "LocalModelClient", lambda **kw: real(opener=opener)
    )

    created = client.post(f"/api/v1/dossiers/{dossier['id']}/traitement").json()
    job_service.work_once()

    state = client.get(f"/api/v1/dossiers/{dossier['id']}/traitement").json()["job"]
    assert state["state"] == JobState.COMPLETED, state["error_message"]

    lecture = state["lecture_assistee"]
    assert lecture["proposed"] == 0
    assert lecture["rejected"] >= 1
    assert "introuvable" in lecture["rejets"][0]["motif"]
    del created


# --------------------------------------------------------------------------
# Alertes devenues sans objet
# --------------------------------------------------------------------------


def test_a_coverage_alert_disappears_once_the_page_becomes_readable(client, dossier, session):
    """Mesuré : 51 alertes « page non extraite » survivaient à un OCR réussi."""
    from app.core.vocabulary import FindingStatus
    from app.models import Finding, Page
    from app.services import dossier_service

    assert _import(client, dossier, ["Page peu lisible ici", PAGE_1]).status_code == 201

    dossier_service.run_vigilance(session, dossier["id"])
    couverture = session.scalars(
        session.query(Finding)
        .filter(
            Finding.dossier_id == dossier["id"],
            Finding.category == "COUVERTURE_ANALYSE",
        )
        .statement
    ).all()
    assert couverture, "une page sans texte doit produire une alerte de couverture"
    illisible = couverture[0].page_no

    # La page devient lisible — exactement ce que fait un OCR réussi.
    page = session.scalars(
        session.query(Page).filter(Page.page_no == illisible).statement
    ).first()
    from app.core.crypto import encrypt_text
    from app.core.keyring import get_master_key

    page.corrected_text_cipher = encrypt_text(
        get_master_key(),
        "Texte desormais lisible sur cette page, avec assez de caracteres utiles.",
        dossier_service.page_aad(page.id, "corrected"),
    )
    session.commit()

    dossier_service.run_vigilance(session, dossier["id"])

    restantes = session.scalars(
        session.query(Finding)
        .filter(
            Finding.dossier_id == dossier["id"],
            Finding.category == "COUVERTURE_ANALYSE",
            Finding.page_no == illisible,
        )
        .statement
    ).all()
    assert restantes == [], "l'alerte doit disparaître avec sa cause"


def test_an_alert_qualified_by_the_evaluator_is_never_removed(client, dossier, session):
    """Le moteur ne réécrit jamais une décision humaine, même sans objet."""
    from app.core.vocabulary import FindingStatus
    from app.models import Finding, Page
    from app.services import dossier_service

    assert _import(client, dossier, ["Page peu lisible ici", PAGE_1]).status_code == 201
    dossier_service.run_vigilance(session, dossier["id"])

    finding = session.scalars(
        session.query(Finding)
        .filter(
            Finding.dossier_id == dossier["id"],
            Finding.category == "COUVERTURE_ANALYSE",
        )
        .statement
    ).first()
    finding.human_status = FindingStatus.CONFIRME
    page_no = finding.page_no
    session.commit()

    page = session.scalars(
        session.query(Page).filter(Page.page_no == page_no).statement
    ).first()
    from app.core.crypto import encrypt_text
    from app.core.keyring import get_master_key

    page.corrected_text_cipher = encrypt_text(
        get_master_key(),
        "Texte desormais lisible sur cette page, avec assez de caracteres utiles.",
        dossier_service.page_aad(page.id, "corrected"),
    )
    session.commit()

    dossier_service.run_vigilance(session, dossier["id"])

    session.refresh(finding)
    assert finding.human_status == FindingStatus.CONFIRME
