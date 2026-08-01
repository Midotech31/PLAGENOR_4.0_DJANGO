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


def preprocess(png_bytes: bytes) -> tuple[bytes, dict]:
    """Prétraitement prudent : orientation, gris, contraste, bruit léger.

    Le prétraitement ne modifie jamais le document original : il travaille sur
    un rendu temporaire en mémoire.
    """
    steps: dict[str, object] = {"source": "rendu 300 dpi", "applied": []}
    try:
        import io

        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow est une dépendance déclarée
        return png_bytes, {"applied": [], "note": "Pillow indisponible : image brute utilisée."}

    image = Image.open(io.BytesIO(png_bytes))
    image = ImageOps.exif_transpose(image)
    steps["applied"].append("orientation_exif")  # type: ignore[union-attr]
    if image.mode != "L":
        image = image.convert("L")
        steps["applied"].append("niveaux_de_gris")  # type: ignore[union-attr]
    image = ImageOps.autocontrast(image, cutoff=1)
    steps["applied"].append("contraste_automatique")  # type: ignore[union-attr]
    try:
        from PIL import ImageFilter

        image = image.filter(ImageFilter.MedianFilter(size=3))
        steps["applied"].append("reduction_bruit_mediane_3")  # type: ignore[union-attr]
    except (ImportError, ValueError):  # pragma: no cover
        pass

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), steps


def run_ocr(png_bytes: bytes, *, languages: str | None = None) -> OcrResult:
    """Exécute l'OCR local et retourne texte, confiance et boîtes de mots."""
    command = tesseract_command()
    if command is None:
        raise OcrUnavailable(
            "Moteur OCR local introuvable. Installez Tesseract (avec les paquets fra, ara et eng) "
            "puis relancez l'analyse. Aucun service en ligne n'est utilisé."
        )

    langs = languages or effective_languages()
    processed, steps = preprocess(png_bytes)

    with tempfile.TemporaryDirectory(prefix="msi-ocr-") as tmp:
        tmp_dir = Path(tmp)
        image_path = tmp_dir / "page.png"
        image_path.write_bytes(processed)
        output_base = tmp_dir / "out"
        result = subprocess.run(  # noqa: S603
            [command, str(image_path), str(output_base), "-l", langs, "--psm", "3", "tsv"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        tsv_path = output_base.with_suffix(".tsv")
        if result.returncode != 0 or not tsv_path.exists():
            raise OcrUnavailable(
                "L'OCR local a échoué. L'état précédent est conservé et aucun texte supposé n'est produit."
            )
        words = _parse_tsv(tsv_path.read_text(encoding="utf-8", errors="replace"))

    text = _rebuild_text(words)
    confidences = [word.confidence for word in words if word.confidence >= 0]
    average = round(sum(confidences) / len(confidences), 2) if confidences else None
    return OcrResult(
        text=text,
        confidence=average,
        words=words,
        languages=langs,
        engine_version=engine_version(),
        parameters={"psm": 3, "dpi": get_settings().ocr_dpi, "preprocessing": steps},
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
