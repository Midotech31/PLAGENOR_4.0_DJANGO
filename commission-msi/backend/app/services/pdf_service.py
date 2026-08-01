"""Validation, ingestion et analyse structurelle des PDF (PyMuPDF).

Le PDF original est conservé chiffré, sans aucune modification. L'analyse
classe chaque page (native, scannée, mixte, blanche, difficile, doublon
probable) et n'exécute jamais l'OCR automatiquement lorsque le texte natif est
suffisant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.core.errors import AppError, UnreliableContent
from app.core.text import useful_char_count
from app.core.vocabulary import ExtractionMode

PDF_MAGIC = b"%PDF-"

#: En dessous de ce nombre de caractères utiles, une page est jugée non native.
MIN_NATIVE_CHARS = 40
#: Une page avec des images et peu de texte est mixte plutôt que native.
MIXED_MAX_CHARS = 400
#: Une page vraiment vide.
BLANK_MAX_CHARS = 5


class PdfRefused(AppError):
    """Le fichier est refusé avant tout traitement."""

    code = "PDF_REFUSE"


@dataclass
class PageAnalysis:
    page_no: int
    mode: str
    text: str
    char_count: int
    image_count: int
    width: float
    height: float
    rotation: int
    is_blank: bool
    is_difficult: bool
    needs_ocr: bool
    text_fingerprint: str | None
    duplicate_of: int | None = None
    confidence: float | None = None


@dataclass
class DocumentAnalysis:
    page_count: int
    pages: list[PageAnalysis] = field(default_factory=list)
    engine_version: str = ""

    @property
    def pages_needing_ocr(self) -> list[int]:
        return [page.page_no for page in self.pages if page.needs_ocr]


def engine_version() -> str:
    return f"PyMuPDF {getattr(fitz, '__doc__', '').strip() or fitz.VersionBind}"


def validate_pdf_bytes(data: bytes, *, original_name: str) -> None:
    """Refuse tout fichier qui n'est pas un PDF exploitable.

    Refuse : fichier vide, faux PDF, trop volumineux, corrompu, ou protégé
    d'une manière incompatible avec une lecture locale.
    """
    settings = get_settings()
    if not data:
        raise PdfRefused(f"Le fichier « {original_name} » est vide.")
    if len(data) > settings.max_upload_bytes:
        raise PdfRefused(
            f"Le fichier dépasse la limite locale de {settings.max_upload_mb} Mo. "
            "Aucune analyse partielle n'est produite."
        )
    if not data.startswith(PDF_MAGIC):
        raise PdfRefused(
            "En-tête PDF absent : le fichier n'est pas un PDF valide et a été refusé sans traitement."
        )
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 - toute erreur d'ouverture est un refus
        raise PdfRefused(f"PDF illisible ou corrompu : refus sans traitement. ({type(exc).__name__})") from exc
    try:
        if document.needs_pass:
            raise PdfRefused(
                "PDF protégé par mot de passe : l'application refuse de deviner ou de contourner "
                "une protection. Fournissez une version lisible."
            )
        if document.page_count <= 0:
            raise PdfRefused("PDF sans page exploitable.")
    finally:
        document.close()


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze_pdf(data: bytes) -> DocumentAnalysis:
    """Analyse structurelle page par page, sans OCR."""
    document = fitz.open(stream=data, filetype="pdf")
    try:
        analysis = DocumentAnalysis(page_count=document.page_count, engine_version=engine_version())
        seen_fingerprints: dict[str, int] = {}
        for index in range(document.page_count):
            page = document.load_page(index)
            text = page.get_text("text") or ""
            useful = useful_char_count(text)
            images = page.get_images(full=True)
            rect = page.rect

            is_blank = useful <= BLANK_MAX_CHARS and not images
            if is_blank:
                mode = ExtractionMode.AUCUN
            elif useful >= MIN_NATIVE_CHARS and not images:
                mode = ExtractionMode.NATIF
            elif useful >= MIN_NATIVE_CHARS and images and useful <= MIXED_MAX_CHARS:
                mode = ExtractionMode.MIXTE
            elif useful >= MIN_NATIVE_CHARS:
                mode = ExtractionMode.NATIF
            else:
                mode = ExtractionMode.AUCUN

            # OCR requis seulement si le texte natif est insuffisant.
            needs_ocr = (not is_blank) and useful < MIN_NATIVE_CHARS
            # Page « difficile » : rotation inhabituelle, très peu de texte pour
            # une grande surface, ou page mixte peu lisible.
            is_difficult = bool(
                page.rotation % 90 != 0
                or (page.rotation not in (0, 180) and useful > 0)
                or (mode == ExtractionMode.MIXTE and useful < MIN_NATIVE_CHARS * 2)
            )

            fingerprint = None
            duplicate_of = None
            if useful >= MIN_NATIVE_CHARS:
                fingerprint = hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
                if fingerprint in seen_fingerprints:
                    duplicate_of = seen_fingerprints[fingerprint]
                else:
                    seen_fingerprints[fingerprint] = index + 1

            analysis.pages.append(
                PageAnalysis(
                    page_no=index + 1,
                    mode=mode,
                    text=text,
                    char_count=useful,
                    image_count=len(images),
                    width=round(rect.width, 2),
                    height=round(rect.height, 2),
                    rotation=page.rotation,
                    is_blank=is_blank,
                    is_difficult=is_difficult,
                    needs_ocr=needs_ocr,
                    text_fingerprint=fingerprint,
                    duplicate_of=duplicate_of,
                    # Le texte natif est fiable ; il n'est pas « certain » pour
                    # autant : la confiance native reste bornée à 0.95.
                    confidence=0.95 if mode in (ExtractionMode.NATIF, ExtractionMode.MIXTE) else None,
                )
            )
        return analysis
    finally:
        document.close()


def render_page_png(data: bytes, page_no: int, *, dpi: int | None = None) -> bytes:
    """Rend une page en PNG pour l'affichage local ou l'OCR."""
    settings = get_settings()
    document = fitz.open(stream=data, filetype="pdf")
    try:
        if page_no < 1 or page_no > document.page_count:
            raise AppError(f"Page {page_no} inexistante dans ce document.")
        page = document.load_page(page_no - 1)
        matrix = fitz.Matrix((dpi or settings.ocr_dpi) / 72, (dpi or settings.ocr_dpi) / 72)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def assert_text_usable(text: str | None, confidence: float | None) -> None:
    """Refuse d'utiliser un texte trop court ou trop peu fiable comme un fait."""
    settings = get_settings()
    if text is None or useful_char_count(text) < MIN_NATIVE_CHARS:
        raise UnreliableContent()
    if confidence is not None and confidence * 100 < settings.ocr_low_confidence:
        raise UnreliableContent()


def read_encrypted_document(path: Path, key: bytes, aad: str) -> bytes:
    from app.core.crypto import decrypt

    return decrypt(key, path.read_bytes(), aad)
