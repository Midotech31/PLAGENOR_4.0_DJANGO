"""Référentiels, règles, textes réglementaires, contradictions, audit, sauvegardes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.vocabulary import DISPLAYED_LIMITS
from app.models import AuditEvent, Requirement, Rule, SourceDocument
from app.schemas.api import (
    ConflictArbitration,
    RegulationPassageCreate,
    RegulationValidation,
    RestoreRequest,
    RuleToggle,
)
from app.services import backup_service, regulation_service

router = APIRouter(tags=["référentiels"])


# --------------------------------------------------------------------------
# Règles
# --------------------------------------------------------------------------


@router.get("/regles")
def list_rules(session: Session = Depends(get_db)) -> dict:
    rules = session.scalars(select(Rule).order_by(Rule.category, Rule.code)).all()
    return {
        "items": [
            {
                "code": rule.code,
                "category": rule.category,
                "label": rule.label,
                "priority": rule.priority,
                "terms": json.loads(rule.terms_json),
                "secondary_terms": json.loads(rule.secondary_terms_json),
                "context_terms": json.loads(rule.context_terms_json),
                "guidance": rule.guidance,
                "source_ref": rule.source_ref,
                "source_date": rule.source_date,
                "authority": rule.authority,
                "scope": rule.scope,
                "version": rule.version,
                "validated_at": rule.validated_at,
                "active": rule.active,
                "is_normative": rule.is_normative,
                "suspended_reason": rule.suspended_reason,
                "presentable_as_prohibition": bool(rule.is_normative and rule.active),
            }
            for rule in rules
        ],
        "notice": (
            "Une règle sans source officielle validée est une règle de vigilance : elle demande "
            "une vérification humaine et ne peut jamais être présentée comme une interdiction."
        ),
    }


@router.post("/regles/{code}")
def toggle_rule(code: str, payload: RuleToggle, session: Session = Depends(get_db)) -> dict:
    rule = regulation_service.set_rule_active(
        session, code, active=payload.active, reason=payload.reason
    )
    return {"code": rule.code, "active": rule.active, "suspended_reason": rule.suspended_reason}


# --------------------------------------------------------------------------
# Textes réglementaires
# --------------------------------------------------------------------------


@router.post("/reglementation", status_code=201)
async def import_regulation(
    file: UploadFile = File(...),
    title: str = Form(...),
    reference: str | None = Form(default=None),
    document_date: str | None = Form(default=None),
    version: str = Form(default="1.0"),
    authority: str | None = Form(default=None),
    effective_from: str | None = Form(default=None),
    effective_to: str | None = Form(default=None),
    scope: str | None = Form(default=None),
    session: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    regulation = regulation_service.import_regulation(
        session,
        content=content,
        original_name=file.filename or "texte.pdf",
        title=title,
        reference=reference,
        document_date=document_date,
        version=version,
        authority=authority,
        effective_from=effective_from,
        effective_to=effective_to,
        scope=scope,
    )
    return {
        "id": regulation.id,
        "title": regulation.title,
        "status": regulation.status,
        "sha256": regulation.sha256,
        "notice": (
            "Texte importé au statut BROUILLON. Aucune règle n'est créée à partir de son titre : "
            "rattachez le passage exact et sa page avant toute validation."
        ),
    }


@router.post("/reglementation/{regulation_id}/passages", status_code=201)
def add_passage(
    regulation_id: str, payload: RegulationPassageCreate, session: Session = Depends(get_db)
) -> dict:
    passage = regulation_service.add_passage(
        session,
        regulation_id,
        passage=payload.passage,
        page_no=payload.page_no,
        translation_status=payload.translation_status,
        requirement_id=payload.requirement_id,
    )
    return {"id": passage.id, "page_no": passage.page_no}


@router.post("/reglementation/{regulation_id}/validation")
def validate_regulation(
    regulation_id: str, payload: RegulationValidation, session: Session = Depends(get_db)
) -> dict:
    regulation = regulation_service.validate_regulation(
        session, regulation_id, validator=payload.validator
    )
    return {"id": regulation.id, "status": regulation.status, "validated_at": regulation.validated_at}


@router.post("/reglementation/{regulation_id}/integrite")
def check_integrity(regulation_id: str, session: Session = Depends(get_db)) -> dict:
    return regulation_service.check_regulation_integrity(session, regulation_id)


# --------------------------------------------------------------------------
# Sources officielles, exigences, contradictions
# --------------------------------------------------------------------------


@router.get("/sources")
def list_sources(session: Session = Depends(get_db)) -> dict:
    sources = session.scalars(select(SourceDocument).order_by(SourceDocument.source_id)).all()
    return {
        "items": [
            {
                "source_id": source.source_id,
                "file_name": source.file_name,
                "sha256": source.sha256,
                "format": source.fmt,
                "pages_rendered": source.pages_rendered,
                "date": source.document_date,
                "reference": source.reference,
                "authority": source.authority,
                "status": source.status,
                "role": source.role,
                "present_locally": source.present_locally,
                "integrity_ok": source.integrity_ok,
            }
            for source in sources
        ],
        "notice": "Les originaux prévalent sur toute extraction, synthèse ou règle dérivée.",
    }


@router.post("/sources/verification")
def verify_sources(session: Session = Depends(get_db)) -> dict:
    return {"items": regulation_service.verify_official_sources(session)}


@router.get("/exigences")
def list_requirements(session: Session = Depends(get_db)) -> dict:
    rows = session.scalars(select(Requirement).order_by(Requirement.requirement_id)).all()
    return {
        "items": [
            {
                "requirement_id": row.requirement_id,
                "label": row.label,
                "statement": row.statement,
                "source_id": row.source_id,
                "pages": json.loads(row.pages_json),
                "source_status": row.source_status,
                "language": row.language,
                "translation_status": row.translation_status,
                "conflict_id": row.conflict_id,
                "implementation": row.implementation,
                "active": row.active,
                "tests": json.loads(row.test_ids_json),
            }
            for row in rows
        ],
        "notice": (
            "Matrice exigence → source → page → test. Une exigence reste inactive tant que sa "
            "source n'est pas présente, validée et sa traduction visée."
        ),
    }


@router.get("/contradictions")
def list_conflicts(session: Session = Depends(get_db)) -> dict:
    return {"items": regulation_service.list_conflicts(session)}


@router.post("/contradictions/{conflict_id}")
def arbitrate(
    conflict_id: str, payload: ConflictArbitration, session: Session = Depends(get_db)
) -> dict:
    conflict = regulation_service.arbitrate_conflict(
        session, conflict_id, note=payload.note, arbitrated_by=payload.arbitrated_by
    )
    return {"conflict_id": conflict.conflict_id, "arbitrated": conflict.arbitrated}


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------


@router.get("/audit")
def list_audit(
    limit: int = Query(default=200, ge=1, le=2000),
    action: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> dict:
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if action:
        query = select(AuditEvent).where(AuditEvent.action == action).order_by(
            AuditEvent.created_at.desc()
        ).limit(limit)
    events = session.scalars(query).all()
    return {
        "items": [
            {
                "id": event.id,
                "action": event.action,
                "summary": event.summary,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "dossier_id": event.dossier_id,
                "fingerprint": event.fingerprint,
                "actor_label": event.actor_label,
                "created_at": event.created_at,
            }
            for event in events
        ]
    }


# --------------------------------------------------------------------------
# Sauvegardes
# --------------------------------------------------------------------------


@router.get("/sauvegardes")
def list_backups(session: Session = Depends(get_db)) -> dict:
    backups = backup_service.list_backups(session)
    return {
        "items": [
            {
                "id": backup.id,
                "archive_path": backup.archive_path,
                "manifest_sha256": backup.manifest_sha256,
                "includes_master_key": backup.includes_master_key,
                "file_count": backup.file_count,
                "size": backup.size,
                "verified": backup.verified,
                "created_at": backup.created_at,
            }
            for backup in backups
        ],
        "warning": backup_service.WARNING,
    }


@router.post("/sauvegardes", status_code=201)
def create_backup(session: Session = Depends(get_db)) -> dict:
    backup = backup_service.create_backup(session)
    return {
        "id": backup.id,
        "archive_path": backup.archive_path,
        "manifest_sha256": backup.manifest_sha256,
        "includes_master_key": backup.includes_master_key,
        "file_count": backup.file_count,
        "size": backup.size,
        "verified": backup.verified,
        "warning": backup_service.WARNING,
    }


@router.post("/sauvegardes/{backup_id}/verification")
def verify_backup(backup_id: str, session: Session = Depends(get_db)) -> dict:
    result = backup_service.verify_backup(session, backup_id)
    return {key: value for key, value in result.items() if key != "manifest"}


@router.post("/sauvegardes/restauration")
def restore(payload: RestoreRequest, session: Session = Depends(get_db)) -> dict:
    return backup_service.restore_to_copy(
        session, Path(payload.archive_path), Path(payload.destination)
    )


@router.get("/limites")
def limits() -> dict:
    return {"limits": list(DISPLAYED_LIMITS), "evaluator": get_settings().evaluator_label}
