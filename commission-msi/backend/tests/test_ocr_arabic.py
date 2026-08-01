"""OCR de l'arabe — sens de lecture et pages scannées.

Deux défauts réels, trouvés en mesurant sur de l'arabe après n'avoir testé que
du latin :

1. **les mots d'une ligne arabe ressortaient à l'envers.** Les mots étaient
   triés par abscisse croissante, ce qui convient au français et inverse
   l'arabe : « طلب تنظيم تظاهرة » devenait « تظاهرة تنظيم طلب ». Toute
   recherche de terme, toute extraction et tout extrait de preuve portant sur
   de l'arabe étaient donc faux ;

2. **une ligne se coupait en deux sur un scan réduit.** La tolérance de
   regroupement des mots en lignes était une constante en pixels, alors que la
   hauteur du texte varie avec la résolution du rendu.

Ces tests fixent les deux comportements et vérifient l'absence de régression
sur le latin.
"""

from __future__ import annotations

import io

import pytest

from app.services import ocr_engines, ocr_service

pytestmark = pytest.mark.skipif(
    not ocr_service.is_available() or "ara" not in ocr_service.installed_languages(),
    reason="Paquet Tesseract « ara » absent : OCR arabe non testable.",
)

#: Trois lignes d'un formulaire réel, en arabe.
ARABIC_LINES = (
    "طلب تنظيم تظاهرة علمية دولية",
    "الجامعة الجزائرية للعلوم",
    "اللجنة العلمية",
)

LATIN_LINES = (
    "DEMANDE D'ORGANISATION",
    "Colloque international 2027",
    "Budget total : 1 000 000 DA",
)

ARABIC_FONT = "/usr/share/fonts/truetype/freefont/FreeSerif.ttf"
LATIN_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _render(lines, *, font_path: str, size: int = 34, blur: float = 0.0, scale: float = 1.0) -> bytes:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    image = Image.new("L", (900, 260), 255)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(font_path, size)
    except OSError:  # pragma: no cover - police absente du poste
        pytest.skip("Police de test absente.")
    for index, line in enumerate(lines):
        draw.text((40, 25 + index * 72), line, fill=25, font=font)
    if scale != 1.0:
        image = image.resize((int(900 * scale), int(260 * scale)), Image.LANCZOS)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _arabic(**kwargs) -> bytes:
    return _render(ARABIC_LINES, font_path=ARABIC_FONT, **kwargs)


def _exact_lines(text: str, expected) -> int:
    return sum(1 for line in expected if line in text)


# --------------------------------------------------------------------------
# Sens de lecture
# --------------------------------------------------------------------------


def test_arabic_words_keep_their_reading_order():
    """Le défaut central : une ligne arabe ne doit pas ressortir inversée."""
    outcome = ocr_engines.read_page(_arabic())

    assert ARABIC_LINES[0] in outcome.text, outcome.text
    # La graphie inversée mot à mot ne doit jamais apparaître.
    reversed_line = " ".join(reversed(ARABIC_LINES[0].split()))
    assert reversed_line not in outcome.text


def test_rtl_detection_ignores_digits_and_punctuation():
    """Un chiffre ou une ponctuation n'indique aucun sens de lecture."""
    assert ocr_service.is_rtl_text("طلب تنظيم") is True
    assert ocr_service.is_rtl_text("Colloque international") is False
    # Une ligne arabe contenant une date reste une ligne arabe.
    assert ocr_service.is_rtl_text("اللجنة العلمية 2027 (12/03)") is True
    # Une ligne latine contenant un mot arabe isolé reste latine.
    assert ocr_service.is_rtl_text("Universite de Oran — طلب") is False
    assert ocr_service.is_rtl_text("2027 12/03 —") is False


def test_latin_lines_are_still_read_left_to_right():
    outcome = ocr_engines.read_page(_render(LATIN_LINES, font_path=LATIN_FONT))

    assert _exact_lines(outcome.text, LATIN_LINES) == len(LATIN_LINES), outcome.text


# --------------------------------------------------------------------------
# Pages scannées
# --------------------------------------------------------------------------


def test_a_blurred_arabic_scan_is_read_exactly():
    outcome = ocr_engines.read_page(_arabic(blur=1.3))

    assert _exact_lines(outcome.text, ARABIC_LINES) == len(ARABIC_LINES), outcome.text
    assert outcome.human_transcription_required is False


def test_a_downscaled_arabic_scan_does_not_split_a_line_in_two():
    """La tolérance de regroupement suit la taille du texte, pas une constante."""
    outcome = ocr_engines.read_page(_arabic(scale=0.55))

    assert _exact_lines(outcome.text, ARABIC_LINES) == len(ARABIC_LINES), outcome.text
    assert len(outcome.text.strip().splitlines()) == len(ARABIC_LINES)


def test_a_clean_arabic_page_loses_no_line():
    """Une confiance élevée sur deux lignes ne doit pas clore la recherche."""
    outcome = ocr_engines.read_page(_arabic())

    assert _exact_lines(outcome.text, ARABIC_LINES) == len(ARABIC_LINES), outcome.text


# --------------------------------------------------------------------------
# Regroupement des lignes
# --------------------------------------------------------------------------


def test_line_grouping_scales_with_text_height():
    """Deux mots d'une même ligne restent groupés, quelle que soit l'échelle."""
    from app.services.ocr_service import OcrWord, _rebuild_text

    def word(text, left, top, height):
        return OcrWord(text=text, confidence=90, left=left, top=top, width=40, height=height)

    # Grand texte : 10 px d'écart vertical restent la même ligne.
    big = [word("Alpha", 10, 100, 40), word("Beta", 80, 110, 40)]
    assert _rebuild_text(big) == "Alpha Beta"

    # Petit texte : 10 px d'écart séparent bien deux lignes.
    small = [word("Alpha", 10, 100, 10), word("Beta", 80, 118, 10)]
    assert _rebuild_text(small).splitlines() == ["Alpha", "Beta"]


def test_lines_are_ordered_top_to_bottom_in_both_scripts():
    from app.services.ocr_service import OcrWord, _rebuild_text

    def word(text, left, top):
        return OcrWord(text=text, confidence=90, left=left, top=top, width=40, height=30)

    # Les mots arrivent dans le désordre ; la sortie suit la page.
    scrambled = [word("bas", 10, 200), word("haut", 10, 10), word("milieu", 10, 105)]
    assert _rebuild_text(scrambled).splitlines() == ["haut", "milieu", "bas"]
