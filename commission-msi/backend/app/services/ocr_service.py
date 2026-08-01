"""OCR strictement local (Tesseract).

Aucune donnée ne quitte le poste : aucun service en ligne, aucune API, aucune
télémétrie. Si Tesseract n'est pas installé, l'OCR échoue explicitement et
l'application affiche le message d'incertitude — elle ne devine jamais un
contenu.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

ENGINE_NAME = "tesseract"


class OcrUnavailable(AppError):
    """Le moteur OCR local n'est pas disponible."""

    code = "OCR_INDISPONIBLE"
    status_code = 503


@dataclass
class OcrWord:
    text: str
    confidence: float
    left: int
    top: int
    width: int
    height: int

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < get_settings().ocr_low_confidence


@dataclass
class OcrResult:
    text: str
    confidence: float | None
    words: list[OcrWord] = field(default_factory=list)
    languages: str = ""
    engine_version: str = ""
    parameters: dict = field(default_factory=dict)
    preprocessed_png: bytes | None = None

    @property
    def low_confidence_words(self) -> list[OcrWord]:
        return [word for word in self.words if word.is_low_confidence]

    @property
    def is_uncertain(self) -> bool:
        """Vrai si la confiance moyenne est basse ou le texte utile trop court."""
        settings = get_settings()
        if self.confidence is None or self.confidence < settings.ocr_low_confidence:
            return True
        from app.core.text import useful_char_count

        return useful_char_count(self.text) < 40

    def boxes_json(self) -> str:
        return json.dumps(
            [
                {
                    "text": word.text,
                    "confidence": word.confidence,
                    "bbox": [word.left, word.top, word.width, word.height],
                    "low": word.is_low_confidence,
                }
                for word in self.words
            ],
            ensure_ascii=False,
        )


def tesseract_command() -> str | None:
    settings = get_settings()
    if settings.tesseract_cmd:
        return settings.tesseract_cmd if Path(settings.tesseract_cmd).exists() else None
    return shutil.which(ENGINE_NAME)


def is_available() -> bool:
    return tesseract_command() is not None


def engine_version() -> str:
    command = tesseract_command()
    if command is None:
        return "indisponible"
    try:
        output = subprocess.run(  # noqa: S603 - binaire local explicite
            [command, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
        return (output.stdout or output.stderr).splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        return "version inconnue"


def installed_languages() -> list[str]:
    command = tesseract_command()
    if command is None:
        return []
    try:
        output = subprocess.run(  # noqa: S603
            [command, "--list-langs"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return []
    lines = (output.stdout or "").splitlines()
    return [line.strip() for line in lines[1:] if line.strip()]


def effective_languages() -> str:
    """Restreint les langues demandées à celles réellement installées."""
    requested = [part for part in get_settings().ocr_languages.split("+") if part]
    available = set(installed_languages())
    if not available:
        return "+".join(requested)
    kept = [lang for lang in requested if lang in available]
    return "+".join(kept) if kept else "eng"


def _load(png_bytes: bytes):
    """Ouvre l'image en niveaux de gris, orientation EXIF corrigée."""
    import io

    from PIL import Image, ImageOps

    image = Image.open(io.BytesIO(png_bytes))
    image = ImageOps.exif_transpose(image)
    if image.mode != "L":
        image = image.convert("L")
    return image


def _encode(image) -> bytes:
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def otsu_threshold(image) -> int:
    """Seuil d'Otsu calculé sur l'histogramme, sans dépendance numérique.

    Otsu cherche le seuil qui maximise la variance entre les deux classes de
    pixels. Sur un scan pâle ou surexposé, il sépare l'encre du papier bien
    mieux qu'un seuil fixe à 128.
    """
    histogram = image.histogram()[:256]
    total = sum(histogram)
    if total == 0:
        return 128
    sum_all = sum(index * count for index, count in enumerate(histogram))
    sum_background = 0.0
    weight_background = 0
    best_threshold, best_variance = 128, -1.0
    for threshold, count in enumerate(histogram):
        weight_background += count
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break
        sum_background += threshold * count
        mean_background = sum_background / weight_background
        mean_foreground = (sum_all - sum_background) / weight_foreground
        variance = (
            weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        )
        if variance > best_variance:
            best_variance, best_threshold = variance, threshold
    return best_threshold


def _ink_rows(image) -> list[int]:
    """Profil horizontal d'encre : une ligne de texte y forme un pic."""
    threshold = otsu_threshold(image)
    width, height = image.size
    pixels = image.load()
    step = max(1, width // 400)
    return [
        sum(1 for x in range(0, width, step) if pixels[x, y] < threshold)
        for y in range(height)
    ]


def estimate_skew(image, *, limit: float = 6.0, step: float = 0.5) -> float:
    """Correction d'inclinaison à appliquer, en degrés, par profil de projection.

    La valeur retournée est celle que `Image.rotate()` attend directement : une
    page penchée de 4° dans le sens horaire renvoie `+4`.

    Une page droite concentre l'encre sur peu de lignes : la variance du profil
    horizontal y est maximale. On teste donc quelques rotations et on retient
    celle qui produit le profil le plus contrasté. La recherche se fait sur une
    vignette, pour rester rapide.
    """
    from PIL import Image

    thumbnail = image.copy()
    thumbnail.thumbnail((700, 700), Image.LANCZOS)

    def sharpness(candidate: float) -> float:
        rotated = (
            thumbnail
            if candidate == 0
            else thumbnail.rotate(candidate, resample=Image.BILINEAR, fillcolor=255)
        )
        rows = _ink_rows(rotated)
        if not rows:
            return 0.0
        mean = sum(rows) / len(rows)
        return sum((value - mean) ** 2 for value in rows) / len(rows)

    angles = [i * step for i in range(int(-limit / step), int(limit / step) + 1)]
    best_angle, best_score = 0.0, sharpness(0.0)
    for angle in angles:
        if angle == 0:
            continue
        score = sharpness(angle)
        if score > best_score:
            best_angle, best_score = angle, score
    return best_angle


def detect_orientation(png_bytes: bytes) -> int:
    """Rotation en degrés signalée par l'analyse d'orientation de Tesseract.

    Une page scannée à l'envers ou en paysage donne un texte illisible tant
    qu'elle n'est pas remise droite. `--psm 0` le détecte sans rien inventer ;
    en cas d'échec, on retourne 0 plutôt qu'une supposition.
    """
    command = tesseract_command()
    if command is None or "osd" not in installed_languages():
        return 0
    with tempfile.TemporaryDirectory(prefix="msi-osd-") as tmp:
        path = Path(tmp) / "page.png"
        path.write_bytes(png_bytes)
        try:
            result = subprocess.run(  # noqa: S603
                [command, str(path), "stdout", "--psm", "0"],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):  # pragma: no cover
            return 0
        for line in result.stdout.splitlines():
            if line.startswith("Rotate:"):
                try:
                    return int(line.split(":", 1)[1].strip()) % 360
                except ValueError:  # pragma: no cover
                    return 0
    return 0


# --------------------------------------------------------------------------
# Variantes de prétraitement
# --------------------------------------------------------------------------


def _variant_standard(image, steps: list[str]):
    """Rendu propre : contraste automatique et bruit léger. Cas courant."""
    from PIL import ImageFilter, ImageOps

    result = ImageOps.autocontrast(image, cutoff=1)
    steps.append("contraste_automatique")
    result = result.filter(ImageFilter.MedianFilter(size=3))
    steps.append("reduction_bruit_mediane_3")
    return result


def _variant_contraste_fort(image, steps: list[str]):
    """Scan pâle ou délavé : contraste agressif et accentuation des contours."""
    from PIL import ImageFilter, ImageOps

    result = ImageOps.autocontrast(image, cutoff=4)
    steps.append("contraste_automatique_fort")
    result = result.filter(ImageFilter.UnsharpMask(radius=2, percent=160, threshold=3))
    steps.append("accentuation_contours")
    return result


def _variant_binarisation(image, steps: list[str]):
    """Fond sale, tampon ou ombre : séparation encre/papier par seuil d'Otsu."""
    from PIL import ImageFilter, ImageOps

    result = ImageOps.autocontrast(image, cutoff=2)
    result = result.filter(ImageFilter.MedianFilter(size=3))
    threshold = otsu_threshold(result)
    result = result.point(lambda value, limit=threshold: 255 if value > limit else 0)
    steps.append(f"binarisation_otsu_seuil_{threshold}")
    return result


def _variant_agrandissement(image, steps: list[str]):
    """Texte petit ou flou : agrandissement ×2 puis accentuation.

    Tesseract reconnaît mal les caractères de moins d'environ 20 pixels de
    hauteur. Agrandir avant de reconnaître donne au moteur la matière qui lui
    manque, sans rien ajouter à l'image.
    """
    from PIL import Image, ImageFilter, ImageOps

    width, height = image.size
    result = image.resize((width * 2, height * 2), Image.LANCZOS)
    steps.append("agrandissement_x2_lanczos")
    result = ImageOps.autocontrast(result, cutoff=2)
    result = result.filter(ImageFilter.UnsharpMask(radius=3, percent=140, threshold=2))
    steps.append("accentuation_contours")
    return result


def _variant_redressement(image, steps: list[str]):
    """Page inclinée : redressement mesuré puis contraste."""
    from PIL import Image, ImageFilter, ImageOps

    angle = estimate_skew(image)
    result = image
    if abs(angle) >= 0.5:
        result = image.rotate(angle, resample=Image.BICUBIC, fillcolor=255, expand=True)
        steps.append(f"redressement_{angle:+.1f}_degres")
    else:
        steps.append("redressement_inutile")
    result = ImageOps.autocontrast(result, cutoff=2)
    result = result.filter(ImageFilter.MedianFilter(size=3))
    steps.append("reduction_bruit_mediane_3")
    return result


#: Variantes essayées dans l'ordre. La première suffit sur un rendu propre ;
#: les suivantes ne sont tentées que si le résultat reste incertain.
VARIANTS: tuple[tuple[str, object], ...] = (
    ("standard", _variant_standard),
    ("contraste_fort", _variant_contraste_fort),
    ("binarisation_otsu", _variant_binarisation),
    ("agrandissement", _variant_agrandissement),
    ("redressement", _variant_redressement),
)


def preprocess(png_bytes: bytes, *, variant: str = "standard") -> tuple[bytes, dict]:
    """Applique une variante de prétraitement à un rendu de page.

    Le prétraitement ne modifie jamais le document original : il travaille sur
    un rendu temporaire en mémoire, et chaque opération appliquée est nommée
    dans le compte rendu.
    """
    steps: dict[str, object] = {
        "source": f"rendu {get_settings().ocr_dpi} dpi",
        "variante": variant,
        "applied": ["orientation_exif", "niveaux_de_gris"],
    }
    try:
        image = _load(png_bytes)
    except ImportError:  # pragma: no cover - Pillow est une dépendance déclarée
        return png_bytes, {"applied": [], "note": "Pillow indisponible : image brute utilisée."}
    except Exception as exc:  # noqa: BLE001 - une image illisible reste telle quelle
        return png_bytes, {
            "applied": [],
            "note": f"Image non exploitable par le prétraitement ({type(exc).__name__}) : "
            "rendu brut transmis au moteur.",
        }

    applied: list[str] = list(steps["applied"])  # type: ignore[arg-type]
    handler = dict(VARIANTS).get(variant, _variant_standard)
    image = handler(image, applied)  # type: ignore[operator]
    steps["applied"] = applied
    return _encode(image), steps


def _run_tesseract(processed: bytes, langs: str, psm: int) -> list[OcrWord]:
    """Un passage du moteur. Lève `OcrUnavailable` si l'exécution échoue."""
    command = tesseract_command()
    with tempfile.TemporaryDirectory(prefix="msi-ocr-") as tmp:
        tmp_dir = Path(tmp)
        image_path = tmp_dir / "page.png"
        image_path.write_bytes(processed)
        output_base = tmp_dir / "out"
        result = subprocess.run(  # noqa: S603
            [
                command,
                str(image_path),
                str(output_base),
                "-l",
                langs,
                "--psm",
                str(psm),
                "tsv",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        tsv_path = output_base.with_suffix(".tsv")
        if result.returncode != 0 or not tsv_path.exists():
            raise OcrUnavailable(
                "L'OCR local a échoué. L'état précédent est conservé et aucun texte supposé "
                "n'est produit."
            )
        return _parse_tsv(tsv_path.read_text(encoding="utf-8", errors="replace"))


def _quality(words: list[OcrWord], text: str) -> float:
    """Note de qualité d'un passage, pour comparer deux variantes.

    Ni la confiance ni la quantité de texte ne suffisent seules : un passage
    peut être très sûr de trois mots faux, ou produire beaucoup de bruit peu
    fiable. On combine donc la confiance moyenne et le volume de texte utile,
    ce dernier plafonné pour ne pas récompenser le bruit indéfiniment.
    """
    from app.core.text import useful_char_count

    confidences = [word.confidence for word in words if word.confidence >= 0]
    if not confidences:
        return 0.0
    average = sum(confidences) / len(confidences)
    volume = min(useful_char_count(text), 1200) / 1200
    return round(0.7 * (average / 100) + 0.3 * volume, 4)


def run_ocr(png_bytes: bytes, *, languages: str | None = None) -> OcrResult:
    """Exécute l'OCR local et retourne texte, confiance et boîtes de mots.

    Sur une image nette, la variante standard suffit et l'OCR s'arrête là. Sur
    une image dégradée — scan pâle, page inclinée, texte petit, fond sali —
    plusieurs prétraitements sont essayés et **le meilleur résultat mesuré**
    est retenu. Aucune fusion entre variantes : le texte retourné provient
    toujours d'un seul passage, donc il reste cohérent et reproductible.
    """
    command = tesseract_command()
    if command is None:
        raise OcrUnavailable(
            "Moteur OCR local introuvable. Installez Tesseract (avec les paquets fra, ara et eng) "
            "puis relancez l'analyse. Aucun service en ligne n'est utilisé."
        )

    settings = get_settings()
    langs = languages or effective_languages()

    # L'orientation est corrigée une seule fois, avant toute variante : une page
    # à l'envers rendrait tous les prétraitements inutiles.
    rotation = detect_orientation(png_bytes)
    source = png_bytes
    if rotation:
        try:
            image = _load(png_bytes).rotate(-rotation, expand=True, fillcolor=255)
            source = _encode(image)
        except Exception:  # noqa: BLE001 - sans Pillow on garde le rendu brut
            rotation = 0

    attempts: list[dict] = []
    best: tuple[float, str, list[OcrWord], bytes, dict] | None = None

    for name, _handler in VARIANTS:
        processed, steps = preprocess(source, variant=name)
        words = _run_tesseract(processed, langs, psm=3)
        text = _rebuild_text(words)
        score = _quality(words, text)
        confidences = [word.confidence for word in words if word.confidence >= 0]
        average = round(sum(confidences) / len(confidences), 2) if confidences else None
        attempts.append(
            {
                "variante": name,
                "confiance_moyenne": average,
                "caracteres": len(text.strip()),
                "note_qualite": score,
            }
        )
        if best is None or score > best[0]:
            best = (score, name, words, processed, steps)

        # Un résultat franchement bon arrête la recherche : inutile de payer
        # quatre passages supplémentaires sur un document déjà net.
        if average is not None and average >= settings.ocr_low_confidence + 10 and text.strip():
            break

    assert best is not None  # la boucle s'exécute toujours au moins une fois
    _score, variant, words, processed, steps = best
    text = _rebuild_text(words)
    confidences = [word.confidence for word in words if word.confidence >= 0]
    average = round(sum(confidences) / len(confidences), 2) if confidences else None

    return OcrResult(
        text=text,
        confidence=average,
        words=words,
        languages=langs,
        engine_version=engine_version(),
        parameters={
            "psm": 3,
            "dpi": settings.ocr_dpi,
            "rotation_osd": rotation,
            "variante_retenue": variant,
            "variantes_essayees": attempts,
            "preprocessing": steps,
        },
        preprocessed_png=processed,
    )


def _parse_tsv(content: str) -> list[OcrWord]:
    words: list[OcrWord] = []
    lines = content.splitlines()
    if not lines:
        return words
    header = lines[0].split("\t")
    try:
        idx = {name: header.index(name) for name in ("left", "top", "width", "height", "conf", "text")}
    except ValueError:
        return words
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= max(idx.values()):
            continue
        text = parts[idx["text"]].strip()
        if not text:
            continue
        try:
            confidence = float(parts[idx["conf"]])
            words.append(
                OcrWord(
                    text=text,
                    confidence=confidence,
                    left=int(float(parts[idx["left"]])),
                    top=int(float(parts[idx["top"]])),
                    width=int(float(parts[idx["width"]])),
                    height=int(float(parts[idx["height"]])),
                )
            )
        except ValueError:
            continue
    return words


def _rebuild_text(words: list[OcrWord]) -> str:
    if not words:
        return ""
    lines: list[list[OcrWord]] = []
    tolerance = 12
    for word in words:
        placed = False
        for line in lines:
            if abs(line[0].top - word.top) <= tolerance:
                line.append(word)
                placed = True
                break
        if not placed:
            lines.append([word])
    rendered = []
    for line in lines:
        line.sort(key=lambda item: item.left)
        rendered.append(" ".join(item.text for item in line))
    return "\n".join(rendered).strip()


def diagnostic() -> dict:
    """État du moteur OCR local, affiché dans le diagnostic de démarrage."""
    available = is_available()
    return {
        "available": available,
        "engine": ENGINE_NAME,
        "version": engine_version() if available else None,
        "requested_languages": get_settings().ocr_languages,
        "installed_languages": installed_languages(),
        "effective_languages": effective_languages() if available else None,
        "low_confidence_threshold": get_settings().ocr_low_confidence,
        "note": (
            "OCR local opérationnel."
            if available
            else "OCR local indisponible : les pages scannées resteront non extraites et "
            "marquées « vérification humaine obligatoire »."
        ),
    }
