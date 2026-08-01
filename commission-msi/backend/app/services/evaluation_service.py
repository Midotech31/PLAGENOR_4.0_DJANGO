"""Grille scientifique, contrôle administratif, notes et conclusion.

Le moteur ne note jamais : il ne calcule que la somme des notes saisies par
l'évaluateur, et seulement lorsque tous les critères sont saisis, bornés et
justifiés.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import decrypt_text, encrypt_text, value_fingerprint
from app.core.errors import GateBlocked, NotFound, ValidationRefused
from app.core.keyring import get_master_key
from app.core.vocabulary import (
    Conclusion,
    ControlStatus,
    FindingStatus,
    InformationStatus,
    PieceStatus,
)
from app.models import (
    AdministrativeCheck,
    Correction,
    Dossier,
    EvaluationCriterion,
    EvaluationEntry,
    ExtractedItem,
    Finding,
    Note,
    PieceCheck,
)


def criterion_aad(entry_id: str) -> str:
    return f"evaluation:{entry_id}:justification"


def note_aad(note_id: str) -> str:
    return f"note:{note_id}:body"


def check_aad(check_id: str) -> str:
    return f"admin_check:{check_id}:explanation"


# --------------------------------------------------------------------------
# Grille scientifique
# --------------------------------------------------------------------------


def list_criteria(session: Session) -> list[EvaluationCriterion]:
    return list(
        session.scalars(select(EvaluationCriterion).order_by(EvaluationCriterion.order_index)).all()
    )


def set_score(
    session: Session,
    dossier_id: str,
    *,
    criterion_key: str,
    score: int,
    justification: str,
    source_pages: list[int] | None = None,
) -> EvaluationEntry:
    """Enregistre une note saisie par l'évaluateur.

    Aucune note n'est jamais proposée, suggérée ou complétée par le système.
    """
    settings = get_settings()
    criterion = session.scalar(
        select(EvaluationCriterion).where(EvaluationCriterion.key == criterion_key)
    )
    if criterion is None:
        raise NotFound("Critère d'évaluation inconnu.")
    if not isinstance(score, int) or isinstance(score, bool):
        raise ValidationRefused("La note doit être un entier saisi par l'évaluateur.")
    if score < 0 or score > criterion.max_score:
        raise ValidationRefused(
            f"Note hors bornes : « {criterion.label} » est noté de 0 à {criterion.max_score}. "
            "Aucune valeur de remplacement n'est proposée."
        )
    justification = (justification or "").strip()
    if len(justification) < settings.min_justification_length:
        raise ValidationRefused(
            "Justification obligatoire d'au moins "
            f"{settings.min_justification_length} caractères pour toute note. "
            "Le système n'apprécie pas la qualité de la justification : il en vérifie seulement la présence."
        )

    key = get_master_key()
    entry = session.scalar(
        select(EvaluationEntry).where(
            EvaluationEntry.dossier_id == dossier_id,
            EvaluationEntry.criterion_key == criterion_key,
        )
    )
    previous_score = entry.score if entry is not None else None
    if entry is None:
        entry = EvaluationEntry(
            dossier_id=dossier_id,
            criterion_key=criterion_key,
            score=score,
            justification_cipher=b"",
            entered_by=settings.evaluator_label,
        )
        session.add(entry)
        session.flush()
    entry.score = score
    entry.justification_cipher = encrypt_text(key, justification, criterion_aad(entry.id))
    entry.source_pages_json = json.dumps(sorted(set(source_pages or [])))
    entry.entered_by = settings.evaluator_label

    session.add(
        Correction(
            entity_type="evaluation_entry",
            entity_id=entry.id,
            field="score",
            previous_hash=value_fingerprint(str(previous_score) if previous_score is not None else None),
            new_hash=value_fingerprint(str(score)),
            reason=justification,
            evaluator_label=settings.evaluator_label,
        )
    )
    audit.record(
        session,
        audit.AuditAction.EVALUATION_ENTRY,
        f"Note saisie pour « {criterion.label} » : {score}/{criterion.max_score}.",
        entity_type="evaluation_entry",
        entity_id=entry.id,
        dossier_id=dossier_id,
        fingerprint=value_fingerprint(justification),
    )
    session.commit()
    return entry


def evaluation_state(session: Session, dossier_id: str) -> dict:
    """État de la grille : notes saisies, critères manquants, total si complet."""
    key = get_master_key()
    criteria = list_criteria(session)
    entries = {
        entry.criterion_key: entry
        for entry in session.scalars(
            select(EvaluationEntry).where(EvaluationEntry.dossier_id == dossier_id)
        ).all()
    }
    rows = []
    missing: list[str] = []
    for criterion in criteria:
        entry = entries.get(criterion.key)
        if entry is None:
            missing.append(criterion.key)
        rows.append(
            {
                "key": criterion.key,
                "label": criterion.label,
                "max": criterion.max_score,
                "score": entry.score if entry else None,
                "justification": (
                    decrypt_text(key, entry.justification_cipher, criterion_aad(entry.id))
                    if entry
                    else None
                ),
                "source_pages": json.loads(entry.source_pages_json) if entry else [],
                "entered_by": entry.entered_by if entry else None,
                "updated_at": entry.updated_at if entry else None,
            }
        )
    complete = not missing
    return {
        "criteria": rows,
        "missing": missing,
        "complete": complete,
        # Le total n'est calculé que si la grille est entièrement saisie.
        "total": sum(row["score"] for row in rows) if complete else None,
        "max_total": sum(criterion.max_score for criterion in criteria),
        "notice": (
            "Total calculé par simple somme des notes saisies par l'évaluateur."
            if complete
            else "Total non calculé : la grille est incomplète. Le système ne propose aucune note."
        ),
    }


# --------------------------------------------------------------------------
# Contrôle administratif
# --------------------------------------------------------------------------


def update_administrative_check(
    session: Session,
    check_id: str,
    *,
    status: str,
    explanation: str,
    page_no: int | None = None,
    comparison: dict | None = None,
) -> AdministrativeCheck:
    check = session.get(AdministrativeCheck, check_id)
    if check is None:
        raise NotFound("Point de contrôle introuvable.")
    if status not in set(ControlStatus):
        raise ValidationRefused("Statut de contrôle inconnu.")
    explanation = (explanation or "").strip()
    settings = get_settings()
    if status != ControlStatus.A_VERIFIER and len(explanation) < settings.min_motivation_length:
        raise ValidationRefused(
            f"Une explication d'au moins {settings.min_motivation_length} caractères est obligatoire."
        )

    check.status = status
    check.explanation_cipher = encrypt_text(get_master_key(), explanation, check_aad(check.id))
    check.page_no = page_no
    check.comparison_json = json.dumps(comparison, ensure_ascii=False) if comparison else None
    check.updated_by = settings.evaluator_label
    audit.record(
        session,
        audit.AuditAction.ADMIN_CHECK_UPDATE,
        f"Contrôle « {check.label} » → {status}.",
        entity_type="administrative_check",
        entity_id=check.id,
        dossier_id=check.dossier_id,
        fingerprint=value_fingerprint(explanation),
    )
    session.commit()
    return check


def administrative_view(session: Session, dossier_id: str) -> list[dict]:
    key = get_master_key()
    checks = session.scalars(
        select(AdministrativeCheck)
        .where(AdministrativeCheck.dossier_id == dossier_id)
        .order_by(AdministrativeCheck.label)
    ).all()
    return [
        {
            "id": check.id,
            "check_key": check.check_key,
            "label": check.label,
            "status": check.status,
            "explanation": decrypt_text(key, check.explanation_cipher, check_aad(check.id)),
            "page_no": check.page_no,
            "comparison": json.loads(check.comparison_json) if check.comparison_json else None,
            "updated_by": check.updated_by,
            "updated_at": check.updated_at,
        }
        for check in checks
    ]


# --------------------------------------------------------------------------
# Notes et conclusion
# --------------------------------------------------------------------------


def add_note(
    session: Session, dossier_id: str, *, body: str, kind: str = "NOTE", page_no: int | None = None
) -> Note:
    body = (body or "").strip()
    if not body:
        raise ValidationRefused("Une note vide ne peut pas être enregistrée.")
    settings = get_settings()
    note = Note(
        dossier_id=dossier_id,
        kind=kind,
        body_cipher=b"",
        page_no=page_no,
        author_label=settings.evaluator_label,
    )
    session.add(note)
    session.flush()
    note.body_cipher = encrypt_text(get_master_key(), body, note_aad(note.id))
    audit.record(
        session,
        audit.AuditAction.NOTE_WRITE,
        f"Note « {kind} » enregistrée.",
        entity_type="note",
        entity_id=note.id,
        dossier_id=dossier_id,
        fingerprint=value_fingerprint(body),
    )
    session.commit()
    return note


def set_conclusion(session: Session, dossier_id: str, *, conclusion: str, motivation: str) -> Note:
    """Enregistre la conclusion personnelle de l'évaluateur.

    La liste est fermée et le choix appartient exclusivement à l'humain.
    """
    if conclusion not in set(Conclusion):
        raise ValidationRefused(
            "Conclusion hors de la liste fermée. L'application ne produit aucune conclusion automatique."
        )
    motivation = (motivation or "").strip()
    settings = get_settings()
    if len(motivation) < settings.min_justification_length:
        raise ValidationRefused(
            f"La motivation de la conclusion est obligatoire ({settings.min_justification_length} caractères minimum)."
        )

    note = Note(
        dossier_id=dossier_id,
        kind="CONCLUSION",
        body_cipher=b"",
        conclusion=conclusion,
        author_label=settings.evaluator_label,
    )
    session.add(note)
    session.flush()
    note.body_cipher = encrypt_text(get_master_key(), motivation, note_aad(note.id))
    audit.record(
        session,
        audit.AuditAction.CONCLUSION_SET,
        f"Conclusion personnelle de l'évaluateur : {conclusion}.",
        entity_type="note",
        entity_id=note.id,
        dossier_id=dossier_id,
        fingerprint=value_fingerprint(motivation),
    )
    session.commit()
    return note


def current_conclusion(session: Session, dossier_id: str) -> Note | None:
    return session.scalar(
        select(Note)
        .where(Note.dossier_id == dossier_id, Note.kind == "CONCLUSION")
        .order_by(Note.created_at.desc())
    )


def notes_view(session: Session, dossier_id: str) -> list[dict]:
    key = get_master_key()
    notes = session.scalars(
        select(Note).where(Note.dossier_id == dossier_id).order_by(Note.created_at.desc())
    ).all()
    return [
        {
            "id": note.id,
            "kind": note.kind,
            "body": decrypt_text(key, note.body_cipher, note_aad(note.id)),
            "conclusion": note.conclusion,
            "page_no": note.page_no,
            "author_label": note.author_label,
            "created_at": note.created_at,
        }
        for note in notes
    ]


# --------------------------------------------------------------------------
# Portes de validation
# --------------------------------------------------------------------------


def gates_state(session: Session, dossier_id: str) -> dict[str, dict]:
    """État des portes G0..G7. Une porte non satisfaite bloque l'étape suivante,
    jamais ne transforme le dossier en rejet."""
    from app.models import Document, SourceDocument

    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")

    documents = session.scalars(select(Document).where(Document.dossier_id == dossier_id)).all()

    from app.services.dossier_service import dossier_pages, open_findings_count

    page_rows = dossier_pages(session, dossier_id)
    unreadable = [page.page_no for page in page_rows if page.needs_ocr and not page.is_blank]

    pieces = session.scalars(select(PieceCheck).where(PieceCheck.dossier_id == dossier_id)).all()
    unqualified_pieces = [piece.piece_key for piece in pieces if piece.status in {PieceStatus.ABSENTE, PieceStatus.DETECTEE, PieceStatus.A_VERIFIER}]

    items = session.scalars(select(ExtractedItem).where(ExtractedItem.dossier_id == dossier_id)).all()
    unsourced_items = [
        item.key
        for item in items
        if item.status in {InformationStatus.CONFIRME, InformationStatus.CORRIGE}
        and item.page_no is None
        and not item.manual_entry_validated
    ]

    evaluation = evaluation_state(session, dossier_id)
    open_findings = open_findings_count(session, dossier_id)
    conclusion = current_conclusion(session, dossier_id)

    sources = session.scalars(select(SourceDocument)).all()
    source_issue = [source.source_id for source in sources if source.integrity_ok is False]

    return {
        "G0_SOURCE": _gate(
            not source_issue,
            "Empreintes des sources officielles cohérentes."
            if not source_issue
            else f"Empreinte divergente : {', '.join(source_issue)}. Règles liées suspendues.",
        ),
        "G1_EXTRACTION": _gate(
            bool(documents) and not unreadable,
            "Toutes les pages sont lisibles ou explicitement marquées."
            if bool(documents) and not unreadable
            else (
                "Aucun document importé."
                if not documents
                else f"Pages en attente d'OCR ou de lecture humaine : {unreadable}."
            ),
            details={"pages_needing_ocr": unreadable},
        ),
        "G2_ADMINISTRATIF": _gate(
            not unqualified_pieces,
            "Toutes les pièces ont été qualifiées manuellement."
            if not unqualified_pieces
            else f"{len(unqualified_pieces)} pièce(s) restent à qualifier par l'évaluateur.",
            details={"pieces": unqualified_pieces},
        ),
        "G3_ELIGIBILITE": _gate(
            not unsourced_items,
            "Chaque information retenue possède une page source ou une saisie manuelle validée."
            if not unsourced_items
            else f"Informations sans source : {unsourced_items}.",
            details={"items": unsourced_items},
        ),
        "G4_SCIENTIFIQUE": _gate(
            evaluation["complete"],
            evaluation["notice"],
            details={"missing": evaluation["missing"]},
        ),
        "G5_VIGILANCE": _gate(
            open_findings == 0,
            "Toutes les alertes sont qualifiées et motivées."
            if open_findings == 0
            else f"{open_findings} alerte(s) restent au statut A_VERIFIER.",
            details={"open_findings": open_findings},
        ),
        "G6_RAPPORT": _gate(
            conclusion is not None and not unsourced_items,
            "Conclusion motivée enregistrée et aucune affirmation orpheline de source."
            if conclusion is not None and not unsourced_items
            else "Conclusion personnelle motivée manquante ou information non sourcée.",
        ),
        "G7_VALIDATION_HUMAINE": _gate(
            dossier.report_validated_at is not None,
            "Rapport explicitement validé par l'évaluateur."
            if dossier.report_validated_at is not None
            else "Validation humaine du rapport non enregistrée : seul un brouillon filigrané peut être produit.",
        ),
    }


def _gate(satisfied: bool, message: str, details: dict | None = None) -> dict:
    return {"satisfied": satisfied, "message": message, "details": details or {}}


def validate_report_gate(session: Session, dossier_id: str, *, statement: str) -> Dossier:
    """Porte G7 : validation humaine explicite avant tout export officiel."""
    from datetime import datetime, timezone

    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")
    statement = (statement or "").strip()
    settings = get_settings()
    if len(statement) < settings.min_justification_length:
        raise ValidationRefused(
            "La validation humaine exige une déclaration explicite de l'évaluateur "
            f"({settings.min_justification_length} caractères minimum)."
        )

    gates = gates_state(session, dossier_id)
    blocking = [
        name
        for name, state in gates.items()
        if name in {"G4_SCIENTIFIQUE", "G5_VIGILANCE", "G6_RAPPORT"} and not state["satisfied"]
    ]
    if blocking:
        raise GateBlocked(
            "Validation impossible : "
            + " ".join(f"{name} — {gates[name]['message']}" for name in blocking)
        )

    dossier.report_validated_at = datetime.now(timezone.utc)
    dossier.report_validated_by = settings.evaluator_label
    audit.record(
        session,
        audit.AuditAction.REPORT_VALIDATE,
        "Validation humaine du rapport (porte G7_VALIDATION_HUMAINE).",
        entity_type="dossier",
        entity_id=dossier.id,
        dossier_id=dossier.id,
        fingerprint=value_fingerprint(statement),
    )
    session.commit()
    return dossier


# --------------------------------------------------------------------------
# Alertes : qualification humaine
# --------------------------------------------------------------------------


def qualify_finding(
    session: Session,
    finding_id: str,
    *,
    status: str,
    comment: str,
    relation_kind: str | None = None,
) -> Finding:
    """Qualifie une alerte. Une alerte reste une alerte : elle ne devient
    jamais une décision, une note ou une conformité."""
    from app.core.vocabulary import FINDING_STATUSES_REQUIRING_MOTIVATION, MarocRelation
    from app.services.dossier_service import finding_aad

    finding = session.get(Finding, finding_id)
    if finding is None:
        raise NotFound("Alerte introuvable.")
    if status not in set(FindingStatus):
        raise ValidationRefused("Statut d'alerte inconnu.")
    comment = (comment or "").strip()
    settings = get_settings()
    if status in FINDING_STATUSES_REQUIRING_MOTIVATION and len(comment) < settings.min_motivation_length:
        raise ValidationRefused(
            f"Une motivation d'au moins {settings.min_motivation_length} caractères est obligatoire "
            f"pour le statut {status}."
        )
    if relation_kind is not None and relation_kind not in set(MarocRelation):
        raise ValidationRefused("Qualification de relation inconnue.")

    finding.human_status = status
    finding.human_comment_cipher = encrypt_text(
        get_master_key(), comment, finding_aad(finding.id, "comment")
    )
    if relation_kind is not None:
        finding.relation_kind = relation_kind
    audit.record(
        session,
        audit.AuditAction.FINDING_QUALIFY,
        f"Alerte {finding.rule_code} (page {finding.page_no}) → {status}.",
        entity_type="finding",
        entity_id=finding.id,
        dossier_id=finding.dossier_id,
        fingerprint=value_fingerprint(comment),
    )
    session.commit()
    return finding


def findings_view(session: Session, dossier_id: str, *, category: str | None = None) -> list[dict]:
    from app.services.dossier_service import finding_aad

    key = get_master_key()
    query = select(Finding).where(Finding.dossier_id == dossier_id)
    if category:
        query = query.where(Finding.category == category)
    findings = session.scalars(query.order_by(Finding.page_no, Finding.rule_code)).all()
    return [
        {
            "id": finding.id,
            "category": finding.category,
            "rule_code": finding.rule_code,
            "rule_version": finding.rule_version,
            "label": finding.label,
            "trigger": decrypt_text(key, finding.trigger_cipher, finding_aad(finding.id, "trigger")),
            "context": decrypt_text(key, finding.context_cipher, finding_aad(finding.id, "context")),
            "page_no": finding.page_no,
            "priority": finding.priority,
            "confidence": finding.confidence,
            "explanation": finding.explanation,
            "recommended_check": finding.recommended_check,
            "source_ref": finding.source_ref,
            "relation_kind": finding.relation_kind,
            "human_status": finding.human_status,
            "human_comment": decrypt_text(
                key, finding.human_comment_cipher, finding_aad(finding.id, "comment")
            ),
            "created_at": finding.created_at,
            "updated_at": finding.updated_at,
        }
        for finding in findings
    ]
