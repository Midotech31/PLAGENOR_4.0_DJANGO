"""Échelle d'escalade OCR : plusieurs moteurs, et un aveu quand tout échoue.

Le point critique n'est pas de lire davantage — c'est de **ne jamais présenter
une lecture fausse comme fiable**. Un moteur peut être très sûr d'un texte
erroné ; ces tests vérifient que trois doutes indépendants (confiance basse,
volume dérisoire, désaccord entre moteurs) déclenchent chacun la relecture
humaine.
"""

from __future__ import annotations

import io
import random

import pytest

from app.services import ocr_engines

LINES = (
    "DEMANDE D'ORGANISATION",
    "Colloque international 2027",
    "Budget total : 1 000 000 DA",
    "Comite scientifique : Pr Dubois",
)
KEYWORDS = ("demande", "colloque", "international", "budget", "1000000", "scientifique", "dubois")
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _page(size: int = 26):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (900, 300), 255)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(FONT_PATH, size)
    except OSError:  # pragma: no cover
        pytest.skip("Police de test absente.")
    for index, line in enumerate(LINES):
        draw.text((25, 15 + index * 68), line, fill=30, font=font)
    return image


def _encode(image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _found(text: str) -> int:
    compact = text.lower().replace(" ", "")
    return sum(1 for word in KEYWORDS if word in compact)


def _unreadable() -> bytes:
    """Page franchement illisible : caractères de 10 px après réduction."""
    from PIL import Image

    return _encode(_page(size=10).resize((300, 100), Image.BILINEAR))


# --------------------------------------------------------------------------
# Le contrat central : ne jamais présenter une lecture fausse comme sûre
# --------------------------------------------------------------------------


def test_an_unreadable_page_always_demands_human_transcription():
    """Le cas qui compte : illisible en fait, et déclaré tel."""
    outcome = ocr_engines.read_page(_unreadable(), languages="fra")

    assert _found(outcome.text) < 3, "prérequis du test : la page reste illisible"
    assert outcome.human_transcription_required is True
    assert "Relecture humaine obligatoire" in outcome.notice


def test_a_confident_engine_does_not_override_disagreement():
    """Une confiance élevée sur un texte faux ne suffit jamais.

    Deux lecteurs indépendants qui divergent constituent un doute : c'est la
    même règle que la relecture indépendante des constats réglementaires.
    """
    outcome = ocr_engines.read_page(_unreadable(), languages="fra")

    if outcome.agreement is not None:
        assert outcome.agreement < ocr_engines.MIN_CROSS_ENGINE_AGREEMENT
        assert "désaccord entre moteurs" in outcome.notice
    assert outcome.human_transcription_required is True


def test_a_readable_page_is_not_flagged_needlessly():
    outcome = ocr_engines.read_page(_encode(_page()), languages="fra")

    assert _found(outcome.text) == len(KEYWORDS)
    assert outcome.human_transcription_required is False
    assert "contrôle des noms, dates et montants" in outcome.notice


def test_the_reason_for_every_doubt_is_named():
    outcome = ocr_engines.read_page(_unreadable(), languages="fra")

    reasons = ("confiance", "caractères utiles", "désaccord entre moteurs")
    assert any(reason in outcome.notice for reason in reasons)


# --------------------------------------------------------------------------
# Composition de l'échelle
# --------------------------------------------------------------------------


def test_every_rung_is_reported_with_its_outcome():
    outcome = ocr_engines.read_page(_encode(_page()), languages="fra")

    assert outcome.attempts
    for attempt in outcome.attempts:
        assert attempt["moteur"] in {"tesseract", "rapidocr", "vision"}
        assert "disponible" in attempt
        assert "note_qualite" in attempt


def test_a_missing_engine_is_a_note_not_a_failure():
    """L'absence d'un moteur optionnel n'interrompt jamais la lecture."""
    outcome = ocr_engines.read_page(_encode(_page()), languages="fra")
    unavailable = [item for item in outcome.attempts if not item["disponible"]]

    for attempt in unavailable:
        assert attempt["remarque"], f"{attempt['moteur']} indisponible sans explication"
    assert outcome.text.strip(), "la lecture aboutit malgré un barreau manquant"


def test_the_retained_text_comes_from_a_single_engine():
    """Aucune fusion : recoller deux lectures produirait une page inexistante."""
    source = _encode(_page())
    first = ocr_engines.read_page(source, languages="fra")
    second = ocr_engines.read_page(source, languages="fra")

    assert first.engine == second.engine
    assert first.text == second.text


# --------------------------------------------------------------------------
# Confidentialité — inconditionnelle, vérifiée dans le code
# --------------------------------------------------------------------------


def test_a_restricted_page_never_reaches_the_vision_rung():
    result = ocr_engines.vision_engine(b"peu importe", sensitivity="RESTREINT")

    assert result.available is False
    assert "jamais transmise" in result.note
    assert result.text == ""


def test_local_only_mode_opens_no_outbound_call():
    result = ocr_engines.vision_engine(b"peu importe", sensitivity="ORDINAIRE")

    assert result.available is False
    assert "indisponible" in result.note


def test_an_image_without_classification_is_refused_by_the_provider():
    """L'expurgation lit du texte : elle ne voit rien dans une image."""
    from app.core.config import reset_settings
    from app.services import ai_provider

    import os

    for key, value in (
        ("ANALYSIS_MODE", "HYBRID_STRICT"),
        ("ANTHROPIC_API_KEY", "cle-de-test"),
        ("ANTHROPIC_MODEL_ANALYSIS", "modele-de-test"),
        ("ALLOW_EXTERNAL_AI", "true"),
        ("MSI_PRIVACY_ACKNOWLEDGED", "true"),
    ):
        os.environ[key] = value
    reset_settings()
    try:
        provider = ai_provider.HybridStrictProvider(client=_SpyClient())
        with pytest.raises(ai_provider.RestrictedContentRefused):
            provider.complete(
                ai_provider.AiRequest(
                    role="OCR_VISION",
                    instruction="Transcris.",
                    blocks=[{"kind": "image/png", "bytes": b"..."}],  # sans sensitivity
                )
            )
    finally:
        for key in (
            "ANALYSIS_MODE",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL_ANALYSIS",
            "ALLOW_EXTERNAL_AI",
            "MSI_PRIVACY_ACKNOWLEDGED",
        ):
            os.environ.pop(key, None)
        reset_settings()


def test_the_vision_rung_asks_the_model_never_to_invent():
    assert "N'invente rien" in ocr_engines.VISION_INSTRUCTION
    assert "[illisible]" in ocr_engines.VISION_INSTRUCTION


# --------------------------------------------------------------------------
# Diagnostic affiché à l'évaluateur
# --------------------------------------------------------------------------


def test_the_diagnostic_names_what_is_never_transmitted():
    state = ocr_engines.diagnostic()

    assert {rung["moteur"] for rung in state["barreaux"]} == {
        "tesseract",
        "rapidocr",
        "vision",
    }
    assert "passeport" in state["jamais_transmis"]
    assert "n'invente jamais" in state["limite"]


class _SpyClient:
    def complete(self, *, model_id, request):  # pragma: no cover - ne doit pas être atteint
        raise AssertionError("aucune transmission ne devait avoir lieu")
