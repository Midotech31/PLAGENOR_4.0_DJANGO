"""Routes des dossiers, documents, pages, pièces, informations, évaluation,
alertes, notes et rapports."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text, value_fingerprint
from app.core.db import get_db
from app.core.errors import NotFound, ValidationRefused
from app.core.keyring import get_master_key
from app.core.security import safe_filename
from app.core.vocabulary import DossierStatus, PieceStatus, Sensitivity
from app.models import Document, Dossier, ExtractedItem, Page, PieceCheck, Report
from app.schemas.api import (
    AdministrativeCheckUpdate,
    ConclusionCreate,
    CriterionQualification,
    DecisionRetained,
    DossierCreate,
    DossierScopeUpdate,
    DossierStatusUpdate,
    FindingQualification,
    ItemUpdate,
    NoteCreate,
    PageCorrection,
    PieceUpdate,
    ReportRequest,
    ReportValidation,
    ScoreUpdate,
    SubScoreOverride,
)
from app.services import (
    analysis_service,
    assessment_service,
    audit_service,
    dossier_service,
    evidence_service,
    evaluation_service,
    job_service,
    pdf_service,
    report_qa_service,
    report_service,
)

router = APIRouter(prefix="/dossiers", tags=["dossiers"])

MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


# --------------------------------------------------------------------------
# Dossiers
# --------------------------------------------------------------------------


@router.post("", status_code=201)
def create_dossier(payload: DossierCreate, session: Session = Depends(get_db)) -> dict:
    dossier = dossier_service.create_dossier(
        session,
        reference=payload.reference,
        title=payload.title,
        organizer=payload.organizer,
    )
    return _dossier_dict(session, dossier)


@router.get("")
def list_dossiers(
    session: Session = Depends(get_db),
    status: str | None = Query(default=None),
    organizer: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict:
    query = select(Dossier)
    if status:
        query = query.where(Dossier.status == status)
    if organizer:
        query = query.where(Dossier.organizer.ilike(f"%{organizer}%"))
    if priority:
        query = query.where(Dossier.priority == priority)
    if search:
        pattern = f"%{search}%"
        query = query.where(Dossier.title.ilike(pattern) | Dossier.reference.ilike(pattern))
    dossiers = session.scalars(query.order_by(Dossier.updated_at.desc())).all()
    return {"items": [_dossier_dict(session, dossier) for dossier in dossiers]}


@router.get("/tableau-de-bord")
def dashboard(session: Session = Depends(get_db)) -> dict:
    """Tableau de bord : ouverture directe, sans compte ni écran de connexion."""
    dossiers = session.scalars(select(Dossier).order_by(Dossier.updated_at.desc()).limit(20)).all()
    recent = [_dossier_dict(session, dossier) for dossier in dossiers]
    total_open_findings = sum(item["open_findings"] for item in recent)
    pages_needing_ocr = sum(item["pages_needing_ocr"] for item in recent)
    missing_pieces = sum(item["missing_pieces"] for item in recent)
    reports = len(list(session.scalars(select(Report)).all()))
    return {
        "recent_dossiers": recent,
        "open_findings": total_open_findings,
        "pages_needing_ocr": pages_needing_ocr,
        "missing_pieces": missing_pieces,
        "reports_generated": reports,
        "notice": (
            "L'absence d'alerte ne prouve pas l'absence de risque. Les compteurs portent sur les "
            "20 dossiers les plus récents."
        ),
    }


@router.get("/{dossier_id}")
def get_dossier(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    dossier = dossier_service.get_dossier(session, dossier_id)
    data = _dossier_dict(session, dossier)
    data["gates"] = evaluation_service.gates_state(session, dossier_id)
    return data


@router.post("/{dossier_id}/etat")
def set_status(
    dossier_id: str, payload: DossierStatusUpdate, session: Session = Depends(get_db)
) -> dict:
    dossier_service.guard_forbidden_status(payload.status)
    dossier = dossier_service.set_dossier_status(session, dossier_id, payload.status)
    return _dossier_dict(session, dossier)


@router.post("/{dossier_id}/champ-international")
def set_scope(
    dossier_id: str, payload: DossierScopeUpdate, session: Session = Depends(get_db)
) -> dict:
    """La qualification du champ international est demandée, jamais inférée."""
    dossier = dossier_service.get_dossier(session, dossier_id)
    dossier.international_scope_declared = payload.international_scope_declared
    audit.record(
        session,
        audit.AuditAction.DOSSIER_UPDATE,
        f"Qualification du champ international déclarée : {payload.international_scope_declared}.",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
        fingerprint=value_fingerprint(payload.justification),
    )
    session.commit()
    return _dossier_dict(session, dossier)


@router.post("/{dossier_id}/archiver")
def archive(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    dossier = dossier_service.archive_dossier(session, dossier_id)
    return _dossier_dict(session, dossier)


# --------------------------------------------------------------------------
# Documents et pages
# --------------------------------------------------------------------------


@router.post("/{dossier_id}/documents", status_code=201)
async def import_document(
    dossier_id: str,
    file: UploadFile = File(...),
    sensitivity: str = Query(default=Sensitivity.ORDINAIRE),
    session: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise ValidationRefused(
            f"Fichier trop volumineux (limite locale : {settings.max_upload_mb} Mo)."
        )
    document = dossier_service.import_document(
        session,
        dossier_id,
        content=content,
        original_name=file.filename or "document.pdf",
        sensitivity=sensitivity,
    )
    return _document_dict(session, document)


@router.get("/{dossier_id}/documents")
def list_documents(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    documents = session.scalars(select(Document).where(Document.dossier_id == dossier_id)).all()
    return {"items": [_document_dict(session, document) for document in documents]}


@router.get("/{dossier_id}/documents/{document_id}/original")
def download_original(
    dossier_id: str, document_id: str, session: Session = Depends(get_db)
) -> Response:
    """Renvoie le PDF original déchiffré, strictement inchangé."""
    document = session.get(Document, document_id)
    if document is None or document.dossier_id != dossier_id:
        raise NotFound("Document introuvable pour ce dossier.")
    content = dossier_service.load_document_bytes(session, document_id)
    audit.record(
        session,
        audit.AuditAction.DOCUMENT_VIEW_ORIGINAL,
        f"Consultation de l'original « {document.original_name} ».",
        entity_type="document",
        entity_id=document.id,
        dossier_id=dossier_id,
    )
    if document.sensitivity == Sensitivity.RESTREINT:
        audit.record(
            session,
            audit.AuditAction.RESTRICTED_ACCESS,
            "Accès à un document de niveau RESTREINT (documents d'identité).",
            entity_type="document",
            entity_id=document.id,
            dossier_id=dossier_id,
        )
    session.commit()
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{document.original_name}"'},
    )


@router.post("/{dossier_id}/analyse-complete")
def full_analysis(
    dossier_id: str,
    ocr: bool = Query(default=True),
    prepare_web: bool = Query(default=True),
    session: Session = Depends(get_db),
) -> dict:
    """Analyse tout ce qui peut l'être et propose le résultat à confirmation.

    Aucune information n'est confirmée, aucune note attribuée, aucun avis
    formulé : ces décisions appartiennent à l'évaluateur.
    """
    return analysis_service.run_full_analysis(
        session, dossier_id, run_ocr=ocr, prepare_web=prepare_web
    )


@router.get("/{dossier_id}/pages")
def list_pages(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    pages = dossier_service.dossier_pages(session, dossier_id)
    return {"items": [_page_dict(page) for page in pages]}


@router.get("/{dossier_id}/pages/{page_id}")
def get_page(dossier_id: str, page_id: str, session: Session = Depends(get_db)) -> dict:
    page = session.get(Page, page_id)
    if page is None:
        raise NotFound("Page introuvable.")
    data = _page_dict(page)
    data["original_text"] = dossier_service.page_original_text(page)
    data["current_text"] = dossier_service.page_text(page)
    data["corrections"] = [
        {
            "id": correction.id,
            "reason": correction.reason,
            "previous_hash": correction.previous_hash,
            "new_hash": correction.new_hash,
            "evaluator_label": correction.evaluator_label,
            "created_at": correction.created_at,
        }
        for correction in dossier_service.corrections_for(session, "page", page.id)
    ]
    return data


@router.get("/{dossier_id}/pages/{page_id}/image")
def page_image(
    dossier_id: str,
    page_id: str,
    dpi: int = Query(default=150, ge=72, le=400),
    session: Session = Depends(get_db),
) -> Response:
    page = session.get(Page, page_id)
    if page is None:
        raise NotFound("Page introuvable.")
    content = dossier_service.load_document_bytes(session, page.document_id)
    png = pdf_service.render_page_png(content, page.page_no, dpi=dpi)
    return Response(content=png, media_type="image/png")


@router.post("/{dossier_id}/pages/{page_id}/ocr")
def run_ocr(
    dossier_id: str,
    page_id: str,
    force: bool = Query(default=False),
    session: Session = Depends(get_db),
) -> dict:
    run = dossier_service.run_page_ocr(session, page_id, force=force)
    key = get_master_key()
    text = decrypt_text(key, run.result_cipher, f"ocr:{run.id}:text")
    settings = get_settings()
    uncertain = run.confidence is None or run.confidence < settings.ocr_low_confidence
    return {
        "id": run.id,
        "engine": run.engine,
        "version": run.version,
        "languages": run.languages,
        "confidence": run.confidence,
        "low_confidence_words": run.low_confidence_words,
        "text": text,
        "boxes": json.loads(decrypt_text(key, run.boxes_cipher, f"ocr:{run.id}:boxes") or "[]"),
        "uncertain": uncertain,
        "notice": (
            "Contenu illisible ou insuffisamment fiable — vérification humaine obligatoire."
            if uncertain
            else "Texte OCR obtenu. Il ne remplace jamais le texte initial et reste à contrôler."
        ),
    }


@router.post("/{dossier_id}/pages/{page_id}/correction")
def correct_page(
    dossier_id: str, page_id: str, payload: PageCorrection, session: Session = Depends(get_db)
) -> dict:
    page = dossier_service.correct_page_text(
        session, page_id, corrected_text=payload.corrected_text, reason=payload.reason
    )
    return _page_dict(page)


@router.get("/{dossier_id}/recherche")
def search(dossier_id: str, q: str = Query(min_length=2), session: Session = Depends(get_db)) -> dict:
    return {"items": dossier_service.search_pages(session, dossier_id, q)}


# --------------------------------------------------------------------------
# Pièces
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/pieces")
def list_pieces(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    key = get_master_key()
    pieces = session.scalars(
        select(PieceCheck).where(PieceCheck.dossier_id == dossier_id).order_by(PieceCheck.label)
    ).all()
    return {
        "items": [
            {
                "id": piece.id,
                "piece_key": piece.piece_key,
                "label": piece.label,
                "status": piece.status,
                "sensitivity": piece.sensitivity,
                "detected_page_no": piece.detected_page_no,
                "detection_confidence": piece.detection_confidence,
                "detection_excerpt": (
                    "[Contenu restreint — documents d'identité]"
                    if piece.sensitivity == Sensitivity.RESTREINT
                    else decrypt_text(key, piece.detection_excerpt_cipher, f"piece:{piece.id}:excerpt")
                ),
                "comment": decrypt_text(key, piece.comment_cipher, f"piece:{piece.id}:comment"),
                "updated_by": piece.updated_by,
                "updated_at": piece.updated_at,
            }
            for piece in pieces
        ],
        "notice": "La détection d'un titre ne vaut jamais confirmation de la validité de la pièce.",
    }


@router.post("/{dossier_id}/pieces/{piece_id}")
def update_piece(
    dossier_id: str, piece_id: str, payload: PieceUpdate, session: Session = Depends(get_db)
) -> dict:
    piece = session.get(PieceCheck, piece_id)
    if piece is None or piece.dossier_id != dossier_id:
        raise NotFound("Pièce introuvable pour ce dossier.")
    settings = get_settings()
    if payload.status != PieceStatus.ABSENTE and len(payload.comment.strip()) < settings.min_motivation_length:
        raise ValidationRefused(
            f"Un commentaire d'au moins {settings.min_motivation_length} caractères est obligatoire "
            "pour qualifier une pièce."
        )
    piece.status = payload.status
    piece.comment_cipher = encrypt_text(get_master_key(), payload.comment, f"piece:{piece.id}:comment")
    if payload.detected_page_no is not None:
        piece.detected_page_no = payload.detected_page_no
    piece.updated_by = settings.evaluator_label
    audit.record(
        session,
        audit.AuditAction.PIECE_UPDATE,
        f"Pièce « {piece.label} » → {payload.status}.",
        entity_type="piece_check",
        entity_id=piece.id,
        dossier_id=dossier_id,
        fingerprint=value_fingerprint(payload.comment),
    )
    session.commit()
    return {"id": piece.id, "status": piece.status}


# --------------------------------------------------------------------------
# Informations structurées
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/informations")
def list_items(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    items = session.scalars(
        select(ExtractedItem).where(ExtractedItem.dossier_id == dossier_id).order_by(ExtractedItem.key)
    ).all()
    return {
        "items": [dossier_service.item_view(item) for item in items],
        "notice": (
            "Chaque information possède une source ou reste au statut A_VERIFIER. "
            "Les champs à contrôle renforcé (noms, dates, montants, pays, institutions, "
            "affiliations, références réglementaires) exigent une relecture attentive."
        ),
    }


@router.post("/{dossier_id}/informations/{item_id}")
def update_item(
    dossier_id: str, item_id: str, payload: ItemUpdate, session: Session = Depends(get_db)
) -> dict:
    item = dossier_service.set_item_value(
        session,
        item_id,
        value=payload.value,
        status=payload.status,
        reason=payload.reason,
        page_no=payload.page_no,
        source_excerpt=payload.source_excerpt,
        manual_entry_validated=payload.manual_entry_validated,
    )
    return dossier_service.item_view(item)


# --------------------------------------------------------------------------
# Contrôle administratif
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/controle-administratif")
def list_checks(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    return {
        "items": evaluation_service.administrative_view(session, dossier_id),
        "notice": "Les comparaisons automatiques sont explicables et exigent une confirmation humaine.",
    }


@router.post("/{dossier_id}/controle-administratif/{check_id}")
def update_check(
    dossier_id: str,
    check_id: str,
    payload: AdministrativeCheckUpdate,
    session: Session = Depends(get_db),
) -> dict:
    check = evaluation_service.update_administrative_check(
        session,
        check_id,
        status=payload.status,
        explanation=payload.explanation,
        page_no=payload.page_no,
        comparison=payload.comparison,
    )
    return {"id": check.id, "status": check.status}


# --------------------------------------------------------------------------
# Évaluation scientifique
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/evaluation")
def get_evaluation(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    return evaluation_service.evaluation_state(session, dossier_id)


@router.post("/{dossier_id}/evaluation")
def set_score(dossier_id: str, payload: ScoreUpdate, session: Session = Depends(get_db)) -> dict:
    evaluation_service.set_score(
        session,
        dossier_id,
        criterion_key=payload.criterion_key,
        score=payload.score,
        justification=payload.justification,
        source_pages=payload.source_pages,
    )
    return evaluation_service.evaluation_state(session, dossier_id)


# --------------------------------------------------------------------------
# Évaluation automatique : 26 critères, score sur 100, avis proposé
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/evaluation-automatique")
def get_assessment(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Relit les constats, le score et l'avis enregistrés, sans rien recalculer."""
    dossier_service.get_dossier(session, dossier_id)
    return assessment_service.current_assessment(session, dossier_id)


@router.post("/{dossier_id}/evaluation-automatique")
def run_assessment(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Relance les trois moteurs déterministes sur l'état courant du dossier.

    Le score et l'avis produits sont des **propositions motivées** : aide à la
    décision, sans valeur de décision officielle.
    """
    dossier_service.get_dossier(session, dossier_id)
    return assessment_service.assess(session, dossier_id)


@router.post("/{dossier_id}/evaluation-automatique/criteres/{code}")
def qualify_criterion(
    dossier_id: str,
    code: str,
    payload: CriterionQualification,
    session: Session = Depends(get_db),
) -> dict:
    """Qualification humaine d'un critère : elle prime toujours sur la proposition."""
    dossier_service.get_dossier(session, dossier_id)
    assessment_service.qualify_criterion(
        session,
        dossier_id,
        code=code,
        status=payload.status,
        comment=payload.comment,
    )
    return assessment_service.current_assessment(session, dossier_id)


@router.post("/{dossier_id}/evaluation-automatique/sous-notes/{key}")
def override_subscore(
    dossier_id: str,
    key: str,
    payload: SubScoreOverride,
    session: Session = Depends(get_db),
) -> dict:
    """Correction d'une sous-note par l'évaluateur ; la proposition reste tracée."""
    dossier_service.get_dossier(session, dossier_id)
    assessment_service.override_subscore(
        session,
        dossier_id,
        key=key,
        score=payload.score,
        justification=payload.justification,
    )
    return assessment_service.current_assessment(session, dossier_id)


@router.post("/{dossier_id}/evaluation-automatique/avis")
def retain_decision(
    dossier_id: str,
    payload: DecisionRetained,
    session: Session = Depends(get_db),
) -> dict:
    """Avis retenu par l'évaluateur : l'application ne le remplace jamais."""
    dossier_service.get_dossier(session, dossier_id)
    assessment_service.retain_decision(
        session,
        dossier_id,
        avis=payload.avis,
        motivation=payload.motivation,
    )
    return assessment_service.current_assessment(session, dossier_id)


# --------------------------------------------------------------------------
# Traiter le dossier : travail durable exécuté par le worker
# --------------------------------------------------------------------------


@router.post("/{dossier_id}/traitement", status_code=201)
def start_processing(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Crée le travail durable. Fermer l'application ne le perd pas."""
    dossier_service.get_dossier(session, dossier_id)
    job = job_service.enqueue(
        session, dossier_id, analysis_mode=get_settings().analysis_mode
    )
    return job_service.job_view(session, job)


@router.get("/{dossier_id}/traitement")
def processing_state(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """État détaillé du traitement : étape, pages, recherches, estimation."""
    dossier_service.get_dossier(session, dossier_id)
    job = job_service.latest_job(session, dossier_id)
    if job is None:
        return {
            "job": None,
            "notice": "Aucun traitement n'a encore été lancé pour ce dossier.",
        }
    return {"job": job_service.job_view(session, job), "notice": None}


@router.post("/{dossier_id}/traitement/{job_id}/annuler")
def cancel_processing(dossier_id: str, job_id: str, session: Session = Depends(get_db)) -> dict:
    """Annulation non destructive : les résultats déjà produits sont conservés."""
    dossier_service.get_dossier(session, dossier_id)
    job = job_service.cancel(session, job_id)
    return job_service.job_view(session, job)


@router.post("/{dossier_id}/traitement/{job_id}/reprendre")
def resume_processing(dossier_id: str, job_id: str, session: Session = Depends(get_db)) -> dict:
    """Reprend au dernier point de reprise valide, sans refaire l'acquis."""
    dossier_service.get_dossier(session, dossier_id)
    job = job_service.resume(session, job_id)
    return job_service.job_view(session, job)


@router.get("/{dossier_id}/controle-qualite")
def quality_control(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Dernier contrôle qualité exécuté avant remise du rapport."""
    dossier_service.get_dossier(session, dossier_id)
    result = report_qa_service.latest(session, dossier_id)
    return result or {
        "passed": False,
        "failures": 0,
        "checks": [],
        "notice": "Aucun contrôle qualité n'a encore été exécuté pour ce dossier.",
    }


@router.get("/{dossier_id}/desaccords")
def disagreements(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Désaccords de la relecture indépendante : jamais moyennés, toujours affichés."""
    dossier_service.get_dossier(session, dossier_id)
    return {
        "items": audit_service.listing(session, dossier_id),
        "notice": (
            "Un désaccord non résolu classe le critère « non vérifiable ». Aucune moyenne "
            "n'est faite entre les deux analyses : l'arbitrage vous revient."
        ),
    }


@router.get("/{dossier_id}/preuves")
def list_evidence(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    """Registre de preuves consultable : « Voir les preuves »."""
    dossier_service.get_dossier(session, dossier_id)
    return {"items": evidence_service.listing(session, dossier_id)}


# --------------------------------------------------------------------------
# Alertes
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/alertes")
def list_findings(
    dossier_id: str,
    category: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    return {
        "items": evaluation_service.findings_view(session, dossier_id, category=category),
        "notice": (
            "Une alerte est une demande de vérification humaine. Elle ne produit ni note, ni "
            "conformité, ni décision. L'absence d'alerte ne prouve pas l'absence de risque."
        ),
    }


@router.post("/{dossier_id}/alertes/{finding_id}")
def qualify_finding(
    dossier_id: str,
    finding_id: str,
    payload: FindingQualification,
    session: Session = Depends(get_db),
) -> dict:
    finding = evaluation_service.qualify_finding(
        session,
        finding_id,
        status=payload.status,
        comment=payload.comment,
        relation_kind=payload.relation_kind,
    )
    return {"id": finding.id, "human_status": finding.human_status, "relation_kind": finding.relation_kind}


@router.post("/{dossier_id}/alertes/recalcul")
def rescan(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    created = dossier_service.run_vigilance(session, dossier_id)
    return {"created": created, "open": dossier_service.open_findings_count(session, dossier_id)}


# --------------------------------------------------------------------------
# Notes et conclusion
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/notes")
def list_notes(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    return {"items": evaluation_service.notes_view(session, dossier_id)}


@router.post("/{dossier_id}/notes", status_code=201)
def add_note(dossier_id: str, payload: NoteCreate, session: Session = Depends(get_db)) -> dict:
    note = evaluation_service.add_note(
        session, dossier_id, body=payload.body, kind=payload.kind, page_no=payload.page_no
    )
    return {"id": note.id, "kind": note.kind}


@router.post("/{dossier_id}/conclusion", status_code=201)
def set_conclusion(
    dossier_id: str, payload: ConclusionCreate, session: Session = Depends(get_db)
) -> dict:
    note = evaluation_service.set_conclusion(
        session, dossier_id, conclusion=payload.conclusion, motivation=payload.motivation
    )
    return {
        "id": note.id,
        "conclusion": note.conclusion,
        "notice": "Proposition personnelle de l'évaluateur — ne vaut pas décision de la commission.",
    }


# --------------------------------------------------------------------------
# Rapports
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/rapports")
def list_reports(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    reports = report_service.list_reports(session, dossier_id)
    return {
        "items": [
            {
                "id": report.id,
                "format": report.fmt,
                "is_draft": report.is_draft,
                "version": report.version,
                "sha256": report.sha256,
                "evaluator_label": report.evaluator_label,
                "created_at": report.created_at,
            }
            for report in reports
        ]
    }


@router.post("/{dossier_id}/rapports", status_code=201)
def generate_report(
    dossier_id: str, payload: ReportRequest, session: Session = Depends(get_db)
) -> dict:
    report = report_service.generate_report(
        session,
        dossier_id,
        fmt=payload.format,
        official=payload.official,
        layout=payload.layout,
    )
    return {
        "id": report.id,
        "format": report.fmt,
        "layout": payload.layout,
        "is_draft": report.is_draft,
        "version": report.version,
        "sha256": report.sha256,
        "page_count": getattr(report, "page_count", None),
    }


@router.get("/{dossier_id}/rapports/{report_id}/fichier")
def download_report(dossier_id: str, report_id: str, session: Session = Depends(get_db)) -> Response:
    report, content = report_service.read_report(session, report_id)
    # Le nom porte la référence du dossier et son état : un identifiant
    # technique ne se classe pas dans un dossier de commission.
    dossier = dossier_service.get_dossier(session, dossier_id)
    etat = "officiel" if not report.is_draft else "brouillon"
    filename = safe_filename(
        f"Rapport_{dossier.reference}_v{report.version}_{etat}.{report.fmt}"
    )
    return Response(
        content=content,
        media_type=MIME[report.fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{dossier_id}/rapports/validation-humaine")
def validate_report(
    dossier_id: str, payload: ReportValidation, session: Session = Depends(get_db)
) -> dict:
    dossier = evaluation_service.validate_report_gate(session, dossier_id, statement=payload.statement)
    return {
        "validated_at": dossier.report_validated_at,
        "validated_by": dossier.report_validated_by,
        "gates": evaluation_service.gates_state(session, dossier_id),
    }


# --------------------------------------------------------------------------
# Historique
# --------------------------------------------------------------------------


@router.get("/{dossier_id}/historique")
def history(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    from app.models import AuditEvent

    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.dossier_id == dossier_id)
        .order_by(AuditEvent.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": event.id,
                "action": event.action,
                "summary": event.summary,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "fingerprint": event.fingerprint,
                "actor_label": event.actor_label,
                "created_at": event.created_at,
            }
            for event in events
        ],
        "notice": "Le journal ne contient jamais une valeur sensible en clair : seules des empreintes.",
    }


# --------------------------------------------------------------------------
# Sérialisation
# --------------------------------------------------------------------------


def _dossier_dict(session: Session, dossier: Dossier) -> dict:
    pages = dossier_service.dossier_pages(session, dossier.id)
    pieces = session.scalars(select(PieceCheck).where(PieceCheck.dossier_id == dossier.id)).all()
    evaluation = evaluation_service.evaluation_state(session, dossier.id)
    return {
        "id": dossier.id,
        "reference": dossier.reference,
        "title": dossier.title,
        "organizer": dossier.organizer,
        "status": dossier.status,
        "priority": dossier.priority,
        "page_count": dossier.page_count,
        "original_name": dossier.original_name,
        "sha256": dossier.sha256,
        "size": dossier.size,
        "international_scope_declared": dossier.international_scope_declared,
        "report_validated_at": dossier.report_validated_at,
        "report_validated_by": dossier.report_validated_by,
        "open_findings": dossier_service.open_findings_count(session, dossier.id),
        "pages_needing_ocr": sum(1 for page in pages if page.needs_ocr),
        "missing_pieces": sum(1 for piece in pieces if piece.status == PieceStatus.ABSENTE),
        "score_total": evaluation["total"],
        "score_max": evaluation["max_total"],
        "created_at": dossier.created_at,
        "updated_at": dossier.updated_at,
    }


def _document_dict(session: Session, document: Document) -> dict:
    return {
        "id": document.id,
        "dossier_id": document.dossier_id,
        "type": document.type,
        "original_name": document.original_name,
        "sha256": document.sha256,
        "size": document.size,
        "version": document.version,
        "sensitivity": document.sensitivity,
        "page_count": document.page_count,
        "created_at": document.created_at,
    }


def _page_dict(page: Page) -> dict:
    settings = get_settings()
    low_confidence = page.confidence is not None and page.confidence * 100 < settings.ocr_low_confidence
    return {
        "id": page.id,
        "document_id": page.document_id,
        "page_no": page.page_no,
        "mode": page.mode,
        "confidence": page.confidence,
        "char_count": page.char_count,
        "image_count": page.image_count,
        "width": page.width,
        "height": page.height,
        "rotation": page.rotation,
        "needs_ocr": page.needs_ocr,
        "is_blank": page.is_blank,
        "is_difficult": page.is_difficult,
        "duplicate_of": page.duplicate_of,
        "engine_version": page.engine_version,
        "analyzed_at": page.analyzed_at,
        "uncertain": bool(low_confidence or page.needs_ocr),
        "notice": (
            "Contenu illisible ou insuffisamment fiable — vérification humaine obligatoire."
            if (low_confidence or page.needs_ocr)
            else None
        ),
    }
