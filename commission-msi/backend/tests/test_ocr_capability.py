"""Ce qui manque à l'installation ne doit pas être imputé au document.

Un poste a refusé de lire une page arabe parfaitement nette. L'application
répondait « contenu illisible — vérification humaine obligatoire », ce qui était
faux : la page était lisible, c'est le poste qui n'avait aucun moteur capable de
l'arabe.

Deux mesures fondent ces tests, et elles sont reproductibles :

* Tesseract avec son paquet « ara » lit cette écriture à ~89 % de confiance ;
* **RapidOCR renvoie une chaîne vide sur la même image**, sans lever d'erreur.
  Ses modèles PP-OCR embarqués couvrent le latin et le chinois. Il compte donc
  comme « moteur disponible » tout en étant incapable de la page — et c'est
  précisément ce qui transformait un défaut d'installation en accusation portée
  contre le document.
"""

from __future__ import annotations

import io

import pytest

from app.services import ocr_engines, ocr_service

ARABIC_LINES = (
    "الجمهورية الجزائرية الديمقراطية الشعبية",
    "وزارة التعليم العالي و البحث العلمي",
    "الموضوع: طلب الموافقة لتنظيم ملتقى دولي",
)

FONT = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"


def _arabic_page() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (1000, 320), 255)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(FONT, 36)
    except OSError:  # pragma: no cover - police absente du poste
        pytest.skip("Police arabe de test absente.")
    for index, line in enumerate(ARABIC_LINES):
        draw.text((40, 25 + index * 90), line, fill=20, font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# --------------------------------------------------------------------------
# La mesure qui fonde tout le reste
# --------------------------------------------------------------------------


@pytest.mark.skipif(not ocr_engines.rapidocr_available(), reason="RapidOCR absent.")
def test_rapidocr_reads_nothing_of_arabic_and_that_is_not_an_error():
    """Le piège : un moteur disponible, sans erreur, et pourtant muet."""
    result = ocr_engines.rapidocr_engine(_arabic_page())

    assert result.available is True, "il ne signale aucune panne"
    # Il ne renvoie pas forcément le vide : mesuré, il produit « rmg » à 62 % de
    # confiance. Du bruit affirmé avec aplomb est pire qu'un silence.
    for line in ARABIC_LINES:
        assert line not in result.text
    from app.core.text import useful_char_count

    assert useful_char_count(result.text) < ocr_engines.MIN_USEFUL_CHARS


@pytest.mark.skipif(
    not ocr_service.is_available() or "ara" not in ocr_service.installed_languages(),
    reason="Paquet Tesseract « ara » absent.",
)
def test_tesseract_with_the_arabic_pack_reads_the_same_page():
    result = ocr_engines.tesseract_engine(_arabic_page())

    assert result.text.strip(), result.note
    assert ARABIC_LINES[0] in result.text, result.text


# --------------------------------------------------------------------------
# Ce que l'application déclare savoir lire
# --------------------------------------------------------------------------


def test_rapidocr_never_counts_as_an_arabic_reader():
    assert "arabe" not in ocr_engines.ENGINE_SCRIPTS["rapidocr"]


def test_the_remedies_listed_never_include_rapidocr():
    """Proposer RapidOCR pour lire l'arabe enverrait l'évaluateur dans un mur."""
    _capable, missing = ocr_engines.arabic_capable()

    assert all("rapidocr" not in item.lower() for item in missing), missing


def test_a_missing_arabic_pack_is_named_as_such(monkeypatch):
    monkeypatch.setattr(ocr_service, "is_available", lambda: True)
    monkeypatch.setattr(ocr_service, "installed_languages", lambda: ["eng", "fra"])

    capable, missing = ocr_engines.arabic_capable()

    assert capable is False
    assert any("ara" in item for item in missing), missing
    assert any("installé mais ne connaît pas l'arabe" in item for item in missing), missing


def test_an_absent_tesseract_is_distinguished_from_a_missing_pack(monkeypatch):
    """Les deux pannes n'ont pas le même remède : les confondre fait perdre du temps."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)

    _capable, missing = ocr_engines.arabic_capable()

    assert any("seul moteur local qui lise l'arabe" in item for item in missing), missing


def test_the_diagnostic_says_plainly_that_rapidocr_ignores_arabic():
    report = ocr_engines.diagnostic()

    rapid = next(item for item in report["barreaux"] if item["moteur"] == "rapidocr")
    assert "ne lit pas l'arabe" in rapid["portee"].lower()
    assert "arabe" not in rapid["ecritures"]
    assert "arabe_lisible" in report
    assert isinstance(report["manque_pour_l_arabe"], list)


def test_the_diagnostic_lists_the_installed_tesseract_languages():
    report = ocr_engines.diagnostic()

    tesseract = next(item for item in report["barreaux"] if item["moteur"] == "tesseract")
    assert isinstance(tesseract["langues"], list)
    if tesseract["disponible"]:
        assert tesseract["langues"], "un moteur présent doit dire ce qu'il connaît"


# --------------------------------------------------------------------------
# Le message rendu à l'évaluateur
# --------------------------------------------------------------------------


def test_an_unreadable_page_blames_the_installation_not_the_document(monkeypatch):
    """Le défaut central : accuser la page d'un manque qui est celui du poste."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)
    monkeypatch.setattr(ocr_engines, "rapidocr_available", lambda: False)

    outcome = ocr_engines.read_page(b"")

    assert outcome.engine == "aucun"
    assert "ne sait lire l'arabe" in outcome.notice
    assert "ce n'est pas elle qui est illisible" in outcome.notice
    assert "RapidOCR ne comble pas ce manque" in outcome.notice


def test_three_characters_of_noise_do_not_hide_the_missing_pack(monkeypatch):
    """Le cas réel : « rmg » à 62 % suffisait à masquer la cause véritable."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: False)
    monkeypatch.setattr(ocr_engines, "rapidocr_available", lambda: True)
    noisy = lambda *a, **k: ocr_engines.EngineResult(  # noqa: E731
        engine="rapidocr", text="rmg", confidence=61.95, quality=0.4344
    )
    monkeypatch.setattr(ocr_engines, "LADDER", (("rapidocr", noisy),))

    outcome = ocr_engines.read_page(b"")

    assert outcome.text == "rmg"
    assert outcome.human_transcription_required is True
    assert "moins de 40 caractères utiles" in outcome.notice
    assert "ne sait lire l'arabe" in outcome.notice, outcome.notice


def test_when_arabic_is_readable_the_message_stays_about_the_page(monkeypatch):
    """Si le poste sait lire l'arabe, une page vide est bien un problème de page."""
    monkeypatch.setattr(ocr_service, "is_available", lambda: True)
    monkeypatch.setattr(ocr_service, "installed_languages", lambda: ["ara", "fra"])
    monkeypatch.setattr(ocr_service, "run_ocr", lambda *a, **k: _empty_result())

    outcome = ocr_engines.read_page(b"")

    assert outcome.notice == ocr_engines.HUMAN_TRANSCRIPTION_REQUIRED


def _empty_result():
    from app.services.ocr_service import OcrResult

    return OcrResult(
        text="",
        confidence=None,
        words=[],
        languages="ara+fra",
        engine_version="test",
        parameters={},
    )


def test_the_diagnostic_is_reachable_without_a_terminal(client):
    response = client.get("/api/v1/diagnostic-ocr")

    assert response.status_code == 200
    payload = response.json()
    assert "barreaux" in payload
    assert "arabe_lisible" in payload
