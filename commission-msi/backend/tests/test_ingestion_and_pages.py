"""ACC-001 / ACC-002 : ingestion PDF, classification des pages et OCR."""

from __future__ import annotations

import pytest

from app.core.crypto import sha256_bytes
from app.core.vocabulary import ExtractionMode
from app.services import pdf_service
from tests.fixtures import synthetic


def _import(client, dossier, content: bytes, name: str = "dossier_fictif.pdf"):
    return client.post(
        f"/api/v1/dossiers/{dossier['id']}/documents",
        files={"file": (name, content, "application/pdf")},
    )


def test_native_pdf_is_stored_unchanged_and_fingerprinted(client, dossier):
    """ACC-001 : original inchangé, SHA-256 conservé, pages rendues."""
    content = synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])
    response = _import(client, dossier, content)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sha256"] == sha256_bytes(content)
    assert body["page_count"] == 1

    original = client.get(
        f"/api/v1/dossiers/{dossier['id']}/documents/{body['id']}/original"
    )
    assert original.status_code == 200
    # Le PDF original est restitué octet pour octet.
    assert original.content == content
    assert sha256_bytes(original.content) == body["sha256"]


def test_page_classification_native_blank_mixed_and_duplicate(client, dossier):
    content = synthetic.make_pdf(
        [
            synthetic.NATIVE_TEXT_FR,
            "",
            synthetic.NATIVE_TEXT_FR,
        ]
    )
    assert _import(client, dossier, content).status_code == 201
    pages = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"]
    assert len(pages) == 3
    assert pages[0]["mode"] == ExtractionMode.NATIF
    assert pages[1]["is_blank"] is True
    assert pages[2]["duplicate_of"] == 1


def test_scanned_pdf_requires_ocr_and_is_marked_uncertain(client, dossier):
    assert _import(client, dossier, synthetic.make_scanned_pdf()).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    assert page["needs_ocr"] is True
    assert page["uncertain"] is True
    assert "vérification humaine obligatoire" in page["notice"]


def test_mixed_pdf_is_detected(client, dossier):
    assert _import(client, dossier, synthetic.make_mixed_pdf()).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    assert page["image_count"] >= 1
    assert page["mode"] in {ExtractionMode.MIXTE, ExtractionMode.NATIF}


def test_rotated_page_is_flagged_difficult(client, dossier):
    content = synthetic.make_pdf([synthetic.NATIVE_TEXT_FR], rotation=90)
    assert _import(client, dossier, content).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    assert page["rotation"] == 90
    assert page["is_difficult"] is True


def test_table_and_english_and_arabic_pages_are_ingested(client, dossier):
    content = synthetic.make_pdf(
        [synthetic.ENGLISH_TEXT, synthetic.NATIVE_TEXT_FR]
    )
    assert _import(client, dossier, content).status_code == 201
    assert _import(client, dossier, synthetic.make_table_pdf(), "tableau.pdf").status_code == 201
    assert _import(client, dossier, synthetic.make_arabic_pdf(), "arabe.pdf").status_code == 201
    pages = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"]
    assert len(pages) >= 4


@pytest.mark.parametrize(
    "payload, fragment",
    [
        (b"", "vide"),
        (synthetic.fake_pdf_bytes(), "En-tête PDF absent"),
        (synthetic.corrupted_pdf_bytes(), "illisible ou corrompu"),
        (synthetic.make_encrypted_pdf(), "protégé par mot de passe"),
    ],
)
def test_invalid_pdfs_are_refused_without_partial_result(client, dossier, payload, fragment):
    """ACC-001 : aucun résultat partiel n'est présenté comme valide."""
    response = _import(client, dossier, payload)
    assert response.status_code >= 400
    assert fragment in response.json()["error"]["message"]
    assert client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"] == []


def test_oversized_pdf_is_refused(client, dossier, monkeypatch):
    from app.core import config

    settings = config.get_settings()
    huge = synthetic.make_huge_pdf(2048)
    monkeypatch.setattr(type(settings), "max_upload_bytes", property(lambda _self: 1024))
    response = _import(client, dossier, huge)
    assert response.status_code >= 400
    assert "volumineux" in response.json()["error"]["message"].lower()


def test_duplicate_import_is_refused(client, dossier):
    content = synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])
    assert _import(client, dossier, content).status_code == 201
    second = _import(client, dossier, content)
    assert second.status_code >= 400
    assert "déjà importé" in second.json()["error"]["message"]


def test_ocr_refused_when_native_text_is_sufficient(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    response = client.post(f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}/ocr")
    assert response.status_code >= 400
    assert "texte natif" in response.json()["error"]["message"]


def test_ocr_unavailable_is_explicit(client, dossier, tesseract_absent):
    """Sans moteur local, l'échec est explicite : aucun texte supposé."""
    assert _import(client, dossier, synthetic.make_scanned_pdf()).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    response = client.post(f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}/ocr")
    assert response.status_code == 503
    assert "OCR local introuvable" in response.json()["error"]["message"]
    assert "aucun service en ligne" in response.json()["error"]["message"].lower()


def test_page_correction_keeps_initial_text(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    before = client.get(f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}").json()
    initial = before["original_text"]

    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}/correction",
        json={"corrected_text": "Texte corrige par l'evaluateur.", "reason": "Correction de lecture."},
    )
    assert response.status_code == 200
    after = client.get(f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}").json()
    assert after["original_text"] == initial
    assert after["current_text"] == "Texte corrige par l'evaluateur."
    assert len(after["corrections"]) == 1
    # L'audit trace des empreintes, jamais la valeur en clair.
    assert after["corrections"][0]["previous_hash"].startswith("sha256:")


def test_short_correction_reason_is_refused(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])).status_code == 201
    page = client.get(f"/api/v1/dossiers/{dossier['id']}/pages").json()["items"][0]
    response = client.post(
        f"/api/v1/dossiers/{dossier['id']}/pages/{page['id']}/correction",
        json={"corrected_text": "x", "reason": "court"},
    )
    assert response.status_code == 422


def test_search_returns_page_reference(client, dossier):
    assert _import(client, dossier, synthetic.make_pdf([synthetic.NATIVE_TEXT_FR])).status_code == 201
    results = client.get(
        f"/api/v1/dossiers/{dossier['id']}/recherche", params={"q": "proceedings"}
    ).json()["items"]
    assert results and results[0]["page_no"] == 1


def test_unreliable_text_is_refused_as_fact():
    from app.core.errors import UnreliableContent

    with pytest.raises(UnreliableContent):
        pdf_service.assert_text_usable("trop court", 0.9)
    with pytest.raises(UnreliableContent):
        pdf_service.assert_text_usable(synthetic.NATIVE_TEXT_FR, 0.2)
