"""Cycle de vie d'un dossier : création, import, analyse, OCR, corrections.

Invariants appliqués ici :

* le PDF original est stocké chiffré et n'est jamais modifié ;
* une correction crée une nouvelle version et conserve la valeur initiale ;
* un fait sans document, page ou passage est refusé ;
* toute écriture est validée par `commit()` avant qu'un succès soit renvoyé.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt, encrypt_text, sha256_bytes, value_fingerprint
from app.core.errors import AppError, NotFound, ProvenanceRequired, ValidationRefused
from app.core.keyring import get_master_key
from app.core.security import resolve_within, safe_filename
from app.core.text import useful_char_count
from app.core.vocabulary import (
    ControlStatus,
    DossierStatus,
    ExtractionMode,
    FindingStatus,
    InformationStatus,
    PieceStatus,
    Sensitivity,
)
from app.models import (
    AdministrativeCheck,
    Correction,
    Document,
    Dossier,
    ExtractedItem,
    Finding,
    OcrRun,
    Page,
    PieceCheck,
    PieceDefinition,
)
from app.services import ocr_service, pdf_service, reference_data, rules_engine

DOCUMENT_AAD_PREFIX = "document"
PAGE_AAD_PREFIX = "page"


def page_aad(page_id: str, field: str) -> str:
    return f"{PAGE_AAD_PREFIX}:{page_id}:{field}"


def document_aad(document_id: str) -> str:
    return f"{DOCUMENT_AAD_PREFIX}:{document_id}"


def item_aad(item_id: str, field: str) -> str:
    return f"item:{item_id}:{field}"


def finding_aad(finding_id: str, field: str) -> str:
    return f"finding:{finding_id}:{field}"


# --------------------------------------------------------------------------
# Dossiers
# --------------------------------------------------------------------------


def create_dossier(session: Session, *, reference: str, title: str, organizer: str) -> Dossier:
    reference = (reference or "").strip()
    title = (title or "").strip()
    organizer = (organizer or "").strip()
    if not reference or not title or not organizer:
        raise ValidationRefused(
            "Référence, intitulé et organisateur sont obligatoires pour créer un dossier."
        )
    existing = session.scalar(select(Dossier).where(Dossier.reference == reference))
    if existing is not None:
        raise ValidationRefused(f"La référence « {reference} » est déjà utilisée.")

    dossier = Dossier(reference=reference, title=title, organizer=organizer)
    session.add(dossier)
    session.flush()
    _initialize_pieces(session, dossier)
    _initialize_administrative_checks(session, dossier)
    _initialize_information_fields(session, dossier)
    audit.record(
        session,
        audit.AuditAction.DOSSIER_CREATE,
        f"Création du dossier {reference}.",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
    )
    session.commit()
    return dossier


def get_dossier(session: Session, dossier_id: str) -> Dossier:
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")
    return dossier


def archive_dossier(session: Session, dossier_id: str) -> Dossier:
    dossier = get_dossier(session, dossier_id)
    dossier.status = DossierStatus.ARCHIVE
    audit.record(
        session,
        audit.AuditAction.DOSSIER_ARCHIVE,
        f"Archivage du dossier {dossier.reference}.",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
    )
    session.commit()
    return dossier


def _initialize_pieces(session: Session, dossier: Dossier) -> None:
    definitions = session.scalars(
        select(PieceDefinition).where(PieceDefinition.active.is_(True)).order_by(PieceDefinition.order_index)
    ).all()
    for definition in definitions:
        session.add(
            PieceCheck(
                dossier_id=dossier.id,
                piece_key=definition.key,
                label=definition.label,
                status=PieceStatus.ABSENTE,
                sensitivity=definition.sensitivity,
            )
        )


def _initialize_administrative_checks(session: Session, dossier: Dossier) -> None:
    for key, label in reference_data.ADMINISTRATIVE_CHECKLIST:
        session.add(
            AdministrativeCheck(
                dossier_id=dossier.id,
                check_key=key,
                label=label,
                status=ControlStatus.A_VERIFIER,
            )
        )


def _initialize_information_fields(session: Session, dossier: Dossier) -> None:
    for key, label, reinforced in reference_data.INFORMATION_FIELDS:
        session.add(
            ExtractedItem(
                dossier_id=dossier.id,
                key=key,
                label=label,
                status=InformationStatus.A_VERIFIER,
                extraction_mode=ExtractionMode.AUCUN,
                reinforced_control=reinforced,
            )
        )


# --------------------------------------------------------------------------
# Import et analyse du document
# --------------------------------------------------------------------------


def import_document(
    session: Session,
    dossier_id: str,
    *,
    content: bytes,
    original_name: str,
    sensitivity: str = Sensitivity.ORDINAIRE,
) -> Document:
    """Valide, empreinte, chiffre et analyse un PDF, sans jamais le modifier."""
    dossier = get_dossier(session, dossier_id)
    settings = get_settings()
    settings.ensure_directories()

    pdf_service.validate_pdf_bytes(content, original_name=original_name)
    digest = sha256_bytes(content)

    duplicate = session.scalar(
        select(Document).where(Document.dossier_id == dossier.id, Document.sha256 == digest)
    )
    if duplicate is not None:
        raise ValidationRefused(
            "Ce fichier est déjà importé dans ce dossier (empreinte SHA-256 identique)."
        )

    document = Document(
        dossier_id=dossier.id,
        original_name=safe_filename(original_name),
        encrypted_path="",
        sha256=digest,
        size=len(content),
        sensitivity=sensitivity,
    )
    session.add(document)
    session.flush()

    target = resolve_within(settings.documents_dir, f"{document.id}.enc")
    target.write_bytes(encrypt(get_master_key(), content, document_aad(document.id)))
    document.encrypted_path = str(target)

    analysis = pdf_service.analyze_pdf(content)
    document.page_count = analysis.page_count
    _persist_pages(session, document, analysis)

    dossier.original_name = document.original_name
    dossier.storage_path = document.encrypted_path
    dossier.sha256 = digest
    dossier.size = len(content)
    dossier.page_count = analysis.page_count
    dossier.status = DossierStatus.A_CONTROLER

    audit.record(
        session,
        audit.AuditAction.DOCUMENT_IMPORT,
        f"Import de « {document.original_name} » ({analysis.page_count} pages).",
        entity_type="document",
        entity_id=document.id,
        dossier_id=dossier.id,
        fingerprint=f"sha256:{digest}",
    )
    audit.record(
        session,
        audit.AuditAction.DOCUMENT_ANALYZE,
        f"Analyse structurelle : {len(analysis.pages_needing_ocr)} page(s) nécessitent un OCR.",
        entity_type="document",
        entity_id=document.id,
        dossier_id=dossier.id,
    )
    session.commit()

    # Analyse immédiate : l'application propose, l'évaluateur confirme.
    from app.services import coherence_service, extraction_service

    extraction_service.autofill_dossier(session, dossier.id)
    detect_pieces(session, dossier.id)
    coherence_service.run_automatic_checks(session, dossier.id)
    run_vigilance(session, dossier.id)
    return document


def _persist_pages(session: Session, document: Document, analysis: pdf_service.DocumentAnalysis) -> None:
    key = get_master_key()
    for page_analysis in analysis.pages:
        page = Page(
            document_id=document.id,
            page_no=page_analysis.page_no,
            mode=page_analysis.mode,
            confidence=page_analysis.confidence,
            char_count=page_analysis.char_count,
            image_count=page_analysis.image_count,
            width=page_analysis.width,
            height=page_analysis.height,
            rotation=page_analysis.rotation,
            needs_ocr=page_analysis.needs_ocr,
            is_blank=page_analysis.is_blank,
            is_difficult=page_analysis.is_difficult,
            duplicate_of=page_analysis.duplicate_of,
            text_fingerprint=page_analysis.text_fingerprint,
            engine_version=analysis.engine_version,
            analyzed_at=datetime.now(timezone.utc),
        )
        session.add(page)
        session.flush()
        if page_analysis.text:
            page.original_text_cipher = encrypt_text(
                key, page_analysis.text, page_aad(page.id, "original")
            )


def load_document_bytes(session: Session, document_id: str) -> bytes:
    document = session.get(Document, document_id)
    if document is None:
        raise NotFound("Document introuvable.")
    from pathlib import Path

    path = Path(document.encrypted_path)
    if not path.exists():
        raise NotFound("Fichier chiffré introuvable sur le disque local.")
    return pdf_service.read_encrypted_document(path, get_master_key(), document_aad(document.id))


def page_text(page: Page) -> str | None:
    """Texte courant d'une page : la correction humaine si elle existe."""
    key = get_master_key()
    corrected = decrypt_text(key, page.corrected_text_cipher, page_aad(page.id, "corrected"))
    if corrected is not None:
        return corrected
    return decrypt_text(key, page.original_text_cipher, page_aad(page.id, "original"))


def page_original_text(page: Page) -> str | None:
    return decrypt_text(get_master_key(), page.original_text_cipher, page_aad(page.id, "original"))


def dossier_pages(session: Session, dossier_id: str) -> list[Page]:
    return list(
        session.scalars(
            select(Page)
            .join(Document, Document.id == Page.document_id)
            .where(Document.dossier_id == dossier_id)
            .order_by(Page.page_no)
        ).all()
    )


def dossier_page_texts(session: Session, dossier_id: str) -> dict[int, str]:
    texts: dict[int, str] = {}
    for page in dossier_pages(session, dossier_id):
        text = page_text(page)
        if text:
            texts[page.page_no] = text
    return texts


# --------------------------------------------------------------------------
# OCR d'une page
# --------------------------------------------------------------------------


def run_page_ocr(session: Session, page_id: str, *, force: bool = False) -> OcrRun:
    """Lance l'OCR local sur une page précise, à la demande.

    L'OCR n'est jamais lancé automatiquement sur tout le document quand le
    texte natif est suffisant.
    """
    page = session.get(Page, page_id)
    if page is None:
        raise NotFound("Page introuvable.")
    if not page.needs_ocr and not force:
        raise ValidationRefused(
            "Le texte natif de cette page est suffisant. Utilisez « forcer » pour lancer "
            "l'OCR malgré tout."
        )

    document = session.get(Document, page.document_id)
    content = load_document_bytes(session, document.id)
    png = pdf_service.render_page_png(content, page.page_no)
    result = ocr_service.run_ocr(png)

    key = get_master_key()
    run = OcrRun(
        page_id=page.id,
        engine=ocr_service.ENGINE_NAME,
        version=result.engine_version,
        languages=result.languages,
        parameters_json=json.dumps(result.parameters, ensure_ascii=False),
        confidence=result.confidence,
        low_confidence_words=len(result.low_confidence_words),
        succeeded=True,
    )
    session.add(run)
    session.flush()
    run.result_cipher = encrypt_text(key, result.text, f"ocr:{run.id}:text")
    run.boxes_cipher = encrypt_text(key, result.boxes_json(), f"ocr:{run.id}:boxes")

    # Le texte OCR n'écrase jamais le texte initial : s'il n'y avait aucun
    # texte natif, il devient le texte initial de la page ; sinon il est
    # conservé dans la trace OCR et proposé comme correction.
    if page.original_text_cipher is None:
        page.original_text_cipher = encrypt_text(key, result.text, page_aad(page.id, "original"))
    page.mode = ExtractionMode.OCR if page.char_count == 0 else ExtractionMode.MIXTE
    page.confidence = (result.confidence / 100) if result.confidence is not None else None
    page.char_count = useful_char_count(result.text)
    page.needs_ocr = False
    page.engine_version = result.engine_version
    page.analyzed_at = datetime.now(timezone.utc)

    audit.record(
        session,
        audit.AuditAction.PAGE_OCR,
        f"OCR local de la page {page.page_no} — confiance moyenne "
        f"{result.confidence if result.confidence is not None else 'inconnue'} "
        f"({len(result.low_confidence_words)} mot(s) sous le seuil).",
        entity_type="page",
        entity_id=page.id,
        dossier_id=document.dossier_id,
    )
    session.commit()
    run_vigilance(session, document.dossier_id)
    return run


def correct_page_text(
    session: Session, page_id: str, *, corrected_text: str, reason: str
) -> Page:
    """Enregistre une correction humaine sans effacer le texte initial."""
    page = session.get(Page, page_id)
    if page is None:
        raise NotFound("Page introuvable.")
    reason = (reason or "").strip()
    if len(reason) < get_settings().min_motivation_length:
        raise ValidationRefused(
            "Une correction exige un motif d'au moins "
            f"{get_settings().min_motivation_length} caractères."
        )

    key = get_master_key()
    previous = page_text(page)
    page.corrected_text_cipher = encrypt_text(key, corrected_text, page_aad(page.id, "corrected"))
    session.add(
        Correction(
            entity_type="page",
            entity_id=page.id,
            field="text",
            previous_hash=value_fingerprint(previous),
            new_hash=value_fingerprint(corrected_text),
            reason=reason,
            evaluator_label=get_settings().evaluator_label,
        )
    )
    document = session.get(Document, page.document_id)
    audit.record(
        session,
        audit.AuditAction.PAGE_CORRECTION,
        f"Correction humaine du texte de la page {page.page_no}.",
        entity_type="page",
        entity_id=page.id,
        dossier_id=document.dossier_id,
        fingerprint=value_fingerprint(corrected_text),
    )
    session.commit()
    run_vigilance(session, document.dossier_id)
    return page


def search_pages(session: Session, dossier_id: str, query: str) -> list[dict]:
    """Recherche dans le texte des pages, avec retour direct à la page."""
    from app.core.text import contains_term, excerpt_around, normalize

    query = (query or "").strip()
    if len(query) < 2:
        raise ValidationRefused("La recherche exige au moins deux caractères.")
    results: list[dict] = []
    for page in dossier_pages(session, dossier_id):
        text = page_text(page)
        if not text:
            continue
        normalized = normalize(text)
        index = contains_term(normalized, query)
        if index is None:
            continue
        results.append(
            {
                "page_id": page.id,
                "page_no": page.page_no,
                "excerpt": excerpt_around(text, index, normalized),
                "mode": page.mode,
                "confidence": page.confidence,
            }
        )
    return results


# --------------------------------------------------------------------------
# Pièces
# --------------------------------------------------------------------------

#: Indices textuels de présence d'une pièce. La détection d'un titre ne vaut
#: jamais confirmation de la validité de la pièce.
PIECE_HINTS: dict[str, tuple[str, ...]] = {
    "demande_visee": ("demande visée", "demande d'organisation", "طلب تنظيم"),
    "validation_scientifique": (
        "conseil scientifique",
        "comité scientifique de l'établissement",
        "délibération",
        "procès-verbal",
        "المجلس العلمي",
    ),
    "fiche_technique": ("fiche technique", "البطاقة التقنية"),
    "appel_communication": ("appel à communication", "call for papers", "دعوة للمشاركة"),
    "conferenciers_etrangers_passports": (
        "conférenciers étrangers",
        "passeport",
        "passport",
        "جواز السفر",
    ),
    "partenaires_internationaux": ("partenaires internationaux", "international partners", "شركاء دوليون"),
    "partenaires_nationaux_socioeconomiques": (
        "partenaires nationaux",
        "secteur socio-économique",
        "socio-economic",
    ),
    "valorisations_programmees": ("valorisation", "valorisations programmées"),
    "indexation_bases_internationales": ("indexation", "scopus", "web of science", "indexed"),
    "publication_revues_renommee": ("publication dans des revues", "revue de renommée", "journal publication"),
    "proceedings": ("proceedings", "actes du colloque", "أعمال الملتقى"),
    "ouvrage_collectif": ("ouvrage collectif", "edited book", "مؤلف جماعي"),
    "depot_dspace": ("dspace", "dépôt institutionnel", "repository"),
    "session_valorisation": ("session de valorisation", "session prévue", "atelier de valorisation"),
}


def detect_pieces(session: Session, dossier_id: str) -> int:
    """Propose des pièces détectées, sans jamais les confirmer.

    Une pièce déjà qualifiée par un humain n'est pas modifiée.
    """
    from app.core.text import contains_term, excerpt_around, normalize

    key = get_master_key()
    texts = dossier_page_texts(session, dossier_id)
    checks = session.scalars(select(PieceCheck).where(PieceCheck.dossier_id == dossier_id)).all()
    human_qualified = {
        PieceStatus.CONFIRMEE,
        PieceStatus.INCOMPLETE,
        PieceStatus.ILLISIBLE,
        PieceStatus.NON_CONFORME,
        PieceStatus.NON_APPLICABLE,
    }
    detected = 0
    for check in checks:
        if check.status in human_qualified:
            continue
        hints = PIECE_HINTS.get(check.piece_key, ())
        found = False
        for page_no in sorted(texts):
            normalized = normalize(texts[page_no])
            for hint in hints:
                index = contains_term(normalized, hint)
                if index is None:
                    continue
                check.status = PieceStatus.DETECTEE
                check.detected_page_no = page_no
                check.detection_confidence = 0.5
                check.detection_excerpt_cipher = encrypt_text(
                    key,
                    excerpt_around(texts[page_no], index, normalized),
                    f"piece:{check.id}:excerpt",
                )
                found = True
                detected += 1
                break
            if found:
                break
    session.commit()
    return detected


# --------------------------------------------------------------------------
# Vigilance
# --------------------------------------------------------------------------


def run_vigilance(session: Session, dossier_id: str) -> int:
    """(Re)calcule les alertes de vigilance du dossier.

    Les alertes déjà qualifiées par un humain sont conservées telles quelles :
    le moteur ne réécrit jamais une décision humaine.
    """
    key = get_master_key()
    specs = rules_engine.load_active_rules(session)
    texts = dossier_page_texts(session, dossier_id)
    detections = rules_engine.scan_pages(specs, texts)

    # Toute page sans texte exploitable produit une alerte de couverture.
    for page in dossier_pages(session, dossier_id):
        if page.is_blank:
            continue
        if page.page_no not in texts or useful_char_count(texts[page.page_no]) < 40:
            detections.append(rules_engine.unreadable_page_notice(page.page_no))

    existing = {
        finding.detection_signature: finding
        for finding in session.scalars(
            select(Finding).where(Finding.dossier_id == dossier_id)
        ).all()
    }
    created = 0
    for detection in detections:
        if detection.signature in existing:
            continue
        finding = Finding(
            dossier_id=dossier_id,
            category=detection.category,
            rule_code=detection.rule_code,
            rule_version=detection.rule_version,
            label=detection.label,
            page_no=detection.page_no,
            priority=detection.priority,
            confidence=detection.confidence,
            explanation=detection.explanation,
            recommended_check=detection.recommended_check,
            source_ref=detection.source_ref,
            human_status=FindingStatus.A_VERIFIER,
            detection_signature=detection.signature,
        )
        session.add(finding)
        session.flush()
        finding.trigger_cipher = encrypt_text(key, detection.trigger, finding_aad(finding.id, "trigger"))
        finding.context_cipher = encrypt_text(key, detection.context, finding_aad(finding.id, "context"))
        created += 1

    session.commit()
    return created


def open_findings_count(session: Session, dossier_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(
                Finding.dossier_id == dossier_id,
                Finding.human_status == FindingStatus.A_VERIFIER,
            )
        )
        or 0
    )


# --------------------------------------------------------------------------
# Informations structurées
# --------------------------------------------------------------------------


def set_item_value(
    session: Session,
    item_id: str,
    *,
    value: str,
    status: str,
    reason: str,
    page_no: int | None = None,
    source_excerpt: str | None = None,
    manual_entry_validated: bool = False,
) -> ExtractedItem:
    """Confirme, corrige ou saisit une information.

    Refus explicite (porte G1/G6) : aucun fait ne peut être enregistré sans
    page et passage source, sauf saisie manuelle explicitement validée.
    """
    item = session.get(ExtractedItem, item_id)
    if item is None:
        raise NotFound("Information introuvable.")
    if status not in set(InformationStatus):
        raise ValidationRefused("Statut d'information inconnu.")

    value = (value or "").strip()
    reason = (reason or "").strip()
    settings = get_settings()

    if status in {InformationStatus.CONFIRME, InformationStatus.CORRIGE}:
        if not value:
            raise ValidationRefused("Une information confirmée ou corrigée doit avoir une valeur.")
        has_source = page_no is not None and bool((source_excerpt or "").strip())
        if not has_source and not manual_entry_validated:
            raise ProvenanceRequired(
                "Enregistrement refusé : un fait doit indiquer sa page et son passage source, "
                "ou être explicitement déclaré comme saisie manuelle validée par l'évaluateur."
            )
        if len(reason) < settings.min_motivation_length:
            raise ValidationRefused(
                f"Une motivation d'au moins {settings.min_motivation_length} caractères est obligatoire."
            )

    key = get_master_key()
    previous = decrypt_text(key, item.current_value_cipher, item_aad(item.id, "current"))
    if item.initial_value_cipher is None and value:
        item.initial_value_cipher = encrypt_text(key, value, item_aad(item.id, "initial"))
    item.current_value_cipher = encrypt_text(key, value, item_aad(item.id, "current"))
    if source_excerpt:
        item.source_cipher = encrypt_text(key, source_excerpt, item_aad(item.id, "source"))
    item.page_no = page_no
    item.status = status
    item.manual_entry_validated = manual_entry_validated
    item.extraction_mode = (
        ExtractionMode.SAISIE_MANUELLE if manual_entry_validated else ExtractionMode.NATIF
    )
    item.updated_by = settings.evaluator_label

    if previous != value:
        session.add(
            Correction(
                entity_type="extracted_item",
                entity_id=item.id,
                field="value",
                previous_hash=value_fingerprint(previous),
                new_hash=value_fingerprint(value),
                reason=reason or "Première saisie.",
                evaluator_label=settings.evaluator_label,
            )
        )

    action = {
        InformationStatus.CONFIRME: audit.AuditAction.ITEM_CONFIRM,
        InformationStatus.REJETE: audit.AuditAction.ITEM_REJECT,
    }.get(status, audit.AuditAction.ITEM_CORRECTION)
    audit.record(
        session,
        action,
        f"Information « {item.label} » → {status}.",
        entity_type="extracted_item",
        entity_id=item.id,
        dossier_id=item.dossier_id,
        fingerprint=value_fingerprint(value),
    )
    session.commit()
    return item


def item_view(item: ExtractedItem) -> dict:
    key = get_master_key()
    return {
        "id": item.id,
        "key": item.key,
        "label": item.label,
        "initial_value": decrypt_text(key, item.initial_value_cipher, item_aad(item.id, "initial")),
        "current_value": decrypt_text(key, item.current_value_cipher, item_aad(item.id, "current")),
        "source_excerpt": decrypt_text(key, item.source_cipher, item_aad(item.id, "source")),
        "page_no": item.page_no,
        "extraction_mode": item.extraction_mode,
        "confidence": item.confidence,
        "status": item.status,
        "reinforced_control": item.reinforced_control,
        "manual_entry_validated": item.manual_entry_validated,
        "updated_by": item.updated_by,
        "updated_at": item.updated_at,
    }


def corrections_for(session: Session, entity_type: str, entity_id: str) -> list[Correction]:
    return list(
        session.scalars(
            select(Correction)
            .where(Correction.entity_type == entity_type, Correction.entity_id == entity_id)
            .order_by(Correction.created_at.desc())
        ).all()
    )


def set_dossier_status(session: Session, dossier_id: str, status: str) -> Dossier:
    if status not in set(DossierStatus):
        raise ValidationRefused("État de dossier inconnu.")
    dossier = get_dossier(session, dossier_id)
    dossier.status = status
    audit.record(
        session,
        audit.AuditAction.DOSSIER_UPDATE,
        f"État du dossier {dossier.reference} → {status}.",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
    )
    session.commit()
    return dossier


def guard_forbidden_status(value: str) -> None:
    """Interdit toute sortie automatique de type « accepté » ou « rejeté »."""
    from app.core.vocabulary import FORBIDDEN_AUTOMATIC_OUTPUTS

    if value.upper() in FORBIDDEN_AUTOMATIC_OUTPUTS:
        raise AppError(
            "Sortie interdite : l'application ne produit jamais automatiquement "
            "un état équivalent à « accepté », « rejeté » ou « interdit »."
        )
