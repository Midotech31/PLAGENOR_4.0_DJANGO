"""OCR des images peu nettes : plusieurs prétraitements, le meilleur retenu.

Sur un rendu propre, la variante standard suffit et l'OCR s'arrête là. Sur une
image dégradée — floue, pâle, inclinée, à basse résolution — l'application
essaie plusieurs prétraitements et **retient le meilleur résultat mesuré**.

Ces tests fabriquent les dégradations, donc ils mesurent un gain réel plutôt
que de vérifier qu'une fonction a été appelée. Ils sont ignorés si Tesseract
n'est pas installé : l'absence de moteur ne doit jamais faire échouer la suite.
"""

from __future__ import annotations

import io
import random

import pytest

from app.services import ocr_service

pytestmark = pytest.mark.skipif(
    not ocr_service.is_available(), reason="Tesseract local absent : OCR non testable."
)

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
    except OSError:  # pragma: no cover - police absente du poste
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


def _attempt(result, variant: str) -> dict | None:
    return next(
        (
            item
            for item in result.parameters["variantes_essayees"]
            if item["variante"] == variant
        ),
        None,
    )


# --------------------------------------------------------------------------
# Sélection de variante
# --------------------------------------------------------------------------


def test_a_clean_page_stops_at_the_standard_variant():
    """Un document net ne paie pas le coût des variantes de secours."""
    result = ocr_service.run_ocr(_encode(_page()), languages="fra")

    assert result.parameters["variante_retenue"] == "standard"
    assert len(result.parameters["variantes_essayees"]) == 1
    assert _found(result.text) == len(KEYWORDS)


def test_a_blurred_page_is_rescued_by_a_stronger_contrast():
    from PIL import ImageFilter

    blurred = _encode(_page().filter(ImageFilter.GaussianBlur(2.6)))
    result = ocr_service.run_ocr(blurred, languages="fra")

    standard = _attempt(result, "standard")
    assert standard is not None
    retained = _attempt(result, result.parameters["variante_retenue"])
    assert retained is not None
    # La variante retenue fait strictement mieux que le passage standard.
    assert retained["confiance_moyenne"] > standard["confiance_moyenne"]
    assert result.confidence == retained["confiance_moyenne"]
    assert _found(result.text) >= 6


def test_a_low_resolution_page_is_rescued_by_upscaling():
    """Le cas le plus difficile : des caractères trop petits pour le moteur."""
    from PIL import Image

    small = _encode(_page(size=14).resize((450, 150), Image.BILINEAR))
    result = ocr_service.run_ocr(small, languages="fra")

    standard = _attempt(result, "standard")
    assert standard is not None
    assert result.parameters["variante_retenue"] == "agrandissement"
    # Le gain doit être franc, pas marginal.
    assert result.confidence is not None
    assert result.confidence > (standard["confiance_moyenne"] or 0) + 20
    assert len(result.text.strip()) > standard["caracteres"] * 2


def test_the_retained_text_comes_from_a_single_pass():
    """Aucune fusion entre variantes : le texte reste cohérent et refaisable."""
    from PIL import ImageFilter

    blurred = _encode(_page().filter(ImageFilter.GaussianBlur(2.6)))
    first = ocr_service.run_ocr(blurred, languages="fra")
    second = ocr_service.run_ocr(blurred, languages="fra")

    assert first.text == second.text
    assert first.parameters["variante_retenue"] == second.parameters["variante_retenue"]


def test_every_attempt_is_reported_to_the_evaluator():
    """L'évaluateur voit ce qui a été essayé, pas seulement le résultat."""
    from PIL import Image

    small = _encode(_page(size=14).resize((450, 150), Image.BILINEAR))
    result = ocr_service.run_ocr(small, languages="fra")

    assert len(result.parameters["variantes_essayees"]) > 1
    for attempt in result.parameters["variantes_essayees"]:
        assert attempt["variante"]
        assert "confiance_moyenne" in attempt
        assert "caracteres" in attempt
        assert 0 <= attempt["note_qualite"] <= 1
    assert result.parameters["preprocessing"]["applied"]


# --------------------------------------------------------------------------
# Briques de prétraitement
# --------------------------------------------------------------------------


def test_otsu_separates_ink_from_paper_on_a_pale_scan():
    from PIL import ImageEnhance

    pale = ImageEnhance.Contrast(_page()).enhance(0.25)
    threshold = ocr_service.otsu_threshold(pale)

    # Le seuil doit tomber entre l'encre et le papier, pas sur une extrémité.
    assert 0 < threshold < 255
    binarised = pale.point(lambda value, limit=threshold: 255 if value > limit else 0)
    levels = set(binarised.getdata())
    assert levels <= {0, 255}
    assert len(levels) == 2, "la binarisation doit conserver du texte et du fond"


def test_skew_is_measured_with_the_right_sign_and_magnitude():
    """L'angle retourné est la *correction* à appliquer, pas l'inclinaison.

    Une page penchée de 4° dans le sens horaire doit être redressée de +4°.
    C'est cette valeur que `rotate()` attend directement.
    """
    from PIL import Image

    tilted = _page().rotate(-4, resample=Image.BICUBIC, fillcolor=255, expand=True)
    angle = ocr_service.estimate_skew(tilted)

    assert 2.0 <= angle <= 6.0, f"correction mesurée : {angle}"


def test_a_straight_page_is_not_rotated_needlessly():
    assert abs(ocr_service.estimate_skew(_page())) < 1.0


def test_each_variant_produces_a_usable_image_and_names_its_steps():
    source = _encode(_page())
    for name, _handler in ocr_service.VARIANTS:
        processed, steps = ocr_service.preprocess(source, variant=name)
        assert processed[:4] == b"\x89PNG"
        assert steps["variante"] == name
        assert steps["applied"], f"{name} n'a nommé aucune opération"


def test_an_unreadable_image_is_passed_through_instead_of_crashing():
    """Une image illisible ne fait pas échouer la chaîne : elle est transmise."""
    processed, steps = ocr_service.preprocess(b"ceci n'est pas une image", variant="standard")

    assert processed == b"ceci n'est pas une image"
    assert "non exploitable" in steps["note"]


# --------------------------------------------------------------------------
# Comportement dégradé
# --------------------------------------------------------------------------


def test_a_noisy_page_still_yields_the_key_information():
    random.seed(7)
    image = _page()
    pixels = image.load()
    width, height = image.size
    for _ in range(int(width * height * 0.06)):
        pixels[random.randrange(width), random.randrange(height)] = random.choice((0, 255))

    result = ocr_service.run_ocr(_encode(image), languages="fra")
    assert _found(result.text) >= 5
