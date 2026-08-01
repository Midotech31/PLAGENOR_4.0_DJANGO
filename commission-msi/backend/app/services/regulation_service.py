"""Référentiel réglementaire personnel et contrôle d'intégrité des sources.

Aucune règle n'est jamais inventée à partir du titre d'un document. Seules les
règles reliées à un texte `VALIDE`, présent et d'empreinte cohérente peuvent
être appliquées comme normes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import encrypt, encrypt_text, sha256_bytes, sha256_file
from app.core.errors import NotFound, ValidationRefused
from app.core.keyring import get_master_key
from app.core.security import resolve_within, safe_filename
from app.core.vocabulary import RegulationStatus
from app.models import Conflict, Regulation, RegulationPassage, Rule, SourceDocument
from app.services.reference_data import ORIGINALS_DIR


def import_regulation(
    session: Session,
    *,
    content: bytes,
    original_name: str,
    title: str,
    reference: str | None = None,
    document_date: str | None = None,
    version: str = "1.0",
    authority: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    scope: str | None = None,
) -> Regulation:
    title = (title or "").strip()
    if not title:
        raise ValidationRefused("Le titre du texte réglementaire est obligatoire.")
    if not content:
        raise ValidationRefused("Fichier vide refusé.")

    settings = get_settings()
    settings.ensure_directories()
    digest = sha256_bytes(content)

    regulation = Regulation(
        title=title,
        reference=reference,
        document_date=document_date,
        version=version,
        authority=authority,
        effective_from=effective_from,
        effective_to=effective_to,
        scope=scope,
        status=RegulationStatus.BROUILLON,
        sha256=digest,
        original_name=safe_filename(original_name),
    )
    session.add(regulation)
    session.flush()

    target = resolve_within(settings.regulations_dir, f"{regulation.id}.enc")
    target.write_bytes(encrypt(get_master_key(), content, f"regulation:{regulation.id}"))
    regulation.encrypted_path = str(target)

    audit.record(
        session,
        audit.AuditAction.REGULATION_IMPORT,
        f"Import du texte « {title} » (statut initial BROUILLON, aucune règle activée).",
        entity_type="regulation",
        entity_id=regulation.id,
        fingerprint=f"sha256:{digest}",
    )
    session.commit()
    return regulation


def add_passage(
    session: Session,
    regulation_id: str,
    *,
    passage: str,
    page_no: int | None,
    translation_status: str = "NON_APPLICABLE",
    requirement_id: str | None = None,
) -> RegulationPassage:
    """Rattache un passage exact et sa page à un texte officiel."""
    regulation = session.get(Regulation, regulation_id)
    if regulation is None:
        raise NotFound("Texte réglementaire introuvable.")
    passage = (passage or "").strip()
    if not passage:
        raise ValidationRefused("Le passage exact du texte officiel est obligatoire.")
    if page_no is None:
        raise ValidationRefused(
            "La page du texte officiel est obligatoire : une disposition sans page ne peut pas "
            "être reliée à une règle."
        )

    record = RegulationPassage(
        regulation_id=regulation.id,
        page_no=page_no,
        passage_cipher=b"",
        translation_status=translation_status,
        requirement_id=requirement_id,
    )
    session.add(record)
    session.flush()
    record.passage_cipher = encrypt_text(
        get_master_key(), passage, f"regulation_passage:{record.id}"
    )
    session.commit()
    return record


def validate_regulation(session: Session, regulation_id: str, *, validator: str) -> Regulation:
    regulation = session.get(Regulation, regulation_id)
    if regulation is None:
        raise NotFound("Texte réglementaire introuvable.")
    if not regulation.passages:
        raise ValidationRefused(
            "Validation refusée : aucun passage sourcé et paginé n'est rattaché à ce texte."
        )
    regulation.status = RegulationStatus.VALIDE
    regulation.validated_by = validator
    regulation.validated_at = datetime.now(timezone.utc)
    audit.record(
        session,
        audit.AuditAction.REGULATION_VALIDATE,
        f"Texte « {regulation.title} » validé par {validator}.",
        entity_type="regulation",
        entity_id=regulation.id,
    )
    session.commit()
    return regulation


def check_regulation_integrity(session: Session, regulation_id: str) -> dict:
    """Recalcule l'empreinte d'un texte et suspend les règles liées si elle diverge."""
    regulation = session.get(Regulation, regulation_id)
    if regulation is None:
        raise NotFound("Texte réglementaire introuvable.")
    path = Path(regulation.encrypted_path) if regulation.encrypted_path else None
    if path is None or not path.exists():
        regulation.integrity_ok = False
        message = "Fichier source absent : toutes les règles liées sont suspendues."
    else:
        from app.core.crypto import decrypt

        try:
            plain = decrypt(get_master_key(), path.read_bytes(), f"regulation:{regulation.id}")
            current = sha256_bytes(plain)
        except Exception:  # noqa: BLE001 - toute erreur = intégrité non prouvée
            current = ""
        ok = bool(current) and current == regulation.sha256
        regulation.integrity_ok = ok
        message = (
            "Empreinte conforme."
            if ok
            else "Empreinte divergente : toutes les règles liées sont suspendues jusqu'à revalidation."
        )

    suspended = 0
    if not regulation.integrity_ok:
        regulation.status = RegulationStatus.SUSPENDU
        rules = session.scalars(select(Rule).where(Rule.regulation_id == regulation.id)).all()
        for rule in rules:
            rule.active = False
            rule.suspended_reason = (
                "Suspension automatique : empreinte du texte source divergente ou fichier absent."
            )
            suspended += 1
        audit.record(
            session,
            audit.AuditAction.REGULATION_INTEGRITY_ALERT,
            f"Alerte d'intégrité sur « {regulation.title} » : {suspended} règle(s) suspendue(s).",
            entity_type="regulation",
            entity_id=regulation.id,
        )
    session.commit()
    return {
        "regulation_id": regulation.id,
        "integrity_ok": bool(regulation.integrity_ok),
        "status": regulation.status,
        "suspended_rules": suspended,
        "message": message,
    }


def verify_official_sources(session: Session) -> list[dict]:
    """Porte G0_SOURCE : compare les originaux présents au manifeste versionné."""
    results = []
    sources = session.scalars(select(SourceDocument).order_by(SourceDocument.source_id)).all()
    for source in sources:
        path = ORIGINALS_DIR / source.file_name
        present = path.is_file()
        integrity: bool | None = None
        if present:
            integrity = sha256_file(path) == source.sha256
        source.present_locally = present
        source.integrity_ok = integrity
        results.append(
            {
                "source_id": source.source_id,
                "file_name": source.file_name,
                "status": source.status,
                "authority": source.authority,
                "present_locally": present,
                "integrity_ok": integrity,
                "message": (
                    "Original absent : aucune règle normative dérivée ne peut être activée."
                    if not present
                    else (
                        "Empreinte conforme au manifeste."
                        if integrity
                        else "EMPREINTE DIVERGENTE — règles liées suspendues, revalidation humaine obligatoire."
                    )
                ),
            }
        )
        if present and integrity is False:
            audit.record(
                session,
                audit.AuditAction.REGULATION_INTEGRITY_ALERT,
                f"Empreinte divergente pour la source {source.source_id}.",
                entity_type="source_document",
                entity_id=source.id,
            )
    session.commit()
    return results


def list_conflicts(session: Session) -> list[dict]:
    """Contradictions entre sources : jamais arbitrées automatiquement."""
    import json

    from app.core.config import CONTRADICTION_MESSAGE

    conflicts = session.scalars(select(Conflict).order_by(Conflict.conflict_id)).all()
    return [
        {
            "conflict_id": conflict.conflict_id,
            "subject": conflict.subject,
            "sources": json.loads(conflict.sources_json),
            "required_output": conflict.required_output,
            "arbitrated": conflict.arbitrated,
            "arbitration_note": conflict.arbitration_note,
            "arbitrated_by": conflict.arbitrated_by,
            "arbitrated_at": conflict.arbitrated_at,
            "message": CONTRADICTION_MESSAGE if not conflict.arbitrated else "Arbitrage humain enregistré.",
        }
        for conflict in conflicts
    ]


def arbitrate_conflict(session: Session, conflict_id: str, *, note: str, arbitrated_by: str) -> Conflict:
    conflict = session.scalar(select(Conflict).where(Conflict.conflict_id == conflict_id))
    if conflict is None:
        raise NotFound("Contradiction introuvable.")
    note = (note or "").strip()
    if len(note) < get_settings().min_justification_length:
        raise ValidationRefused(
            "L'arbitrage d'une contradiction exige une instruction écrite motivée "
            f"({get_settings().min_justification_length} caractères minimum)."
        )
    conflict.arbitrated = True
    conflict.arbitration_note = note
    conflict.arbitrated_by = arbitrated_by
    conflict.arbitrated_at = datetime.now(timezone.utc)
    audit.record(
        session,
        audit.AuditAction.CONFLICT_ARBITRATION,
        f"Arbitrage humain de la contradiction {conflict_id}.",
        entity_type="conflict",
        entity_id=conflict.id,
    )
    session.commit()
    return conflict


def set_rule_active(session: Session, code: str, *, active: bool, reason: str) -> Rule:
    """Active ou désactive une règle.

    Une règle normative ne peut être activée que si elle est rattachée à un
    texte `VALIDE`, présent et d'empreinte cohérente.
    """
    rule = session.scalar(select(Rule).where(Rule.code == code))
    if rule is None:
        raise NotFound("Règle introuvable.")
    reason = (reason or "").strip()
    if len(reason) < get_settings().min_motivation_length:
        raise ValidationRefused(
            f"Un motif d'au moins {get_settings().min_motivation_length} caractères est obligatoire."
        )

    if active and rule.is_normative:
        regulation = (
            session.get(Regulation, rule.regulation_id) if rule.regulation_id else None
        )
        if (
            regulation is None
            or regulation.status != RegulationStatus.VALIDE
            or not regulation.integrity_ok
            or not regulation.passages
        ):
            raise ValidationRefused(
                "Activation refusée : une règle normative exige un texte officiel validé, présent, "
                "d'empreinte cohérente et rattaché à un passage paginé. "
                "Elle ne peut jamais être présentée comme une interdiction sans cette preuve."
            )

    rule.active = active
    rule.suspended_reason = None if active else reason
    audit.record(
        session,
        audit.AuditAction.RULE_ACTIVATE if active else audit.AuditAction.RULE_DEACTIVATE,
        f"Règle {code} → {'active' if active else 'inactive'} ({reason}).",
        entity_type="rule",
        entity_id=rule.id,
    )
    session.commit()
    return rule
