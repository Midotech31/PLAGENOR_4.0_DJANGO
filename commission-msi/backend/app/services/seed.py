"""Initialisation idempotente du référentiel local.

Ne réinitialise jamais une base contenant des données : les enregistrements
existants sont mis à jour, jamais supprimés. Les dossiers existants sont
toujours préservés.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.crypto import sha256_file
from app.core.vocabulary import Sensitivity
from app.models import (
    Conflict,
    EvaluationCriterion,
    PieceDefinition,
    Requirement,
    Rule,
    RuleVersion,
    SourceDocument,
)
from app.services import reference_data
from app.services.reference_data import ORIGINALS_DIR

#: Test d'acceptation couvrant chaque exigence (matrice exigence->source->page->test).
REQUIREMENT_TESTS: dict[str, list[str]] = {
    "EXG-001": ["ACC-003", "test_requirements_scope_not_inferred"],
    "EXG-002": ["ACC-003", "test_workflow_states_never_accept_or_reject"],
    "EXG-003": ["ACC-003", "test_gate_g2_requires_pieces"],
    "EXG-004": ["ACC-004", "test_no_invented_quorum"],
    "EXG-005": ["ACC-015", "test_report_is_personal_proposal"],
    "EXG-006": ["ACC-003", "test_deposit_delay_is_explained_not_decided"],
    "EXG-007": ["ACC-005", "test_session_calendar_conflict"],
    "EXG-008": ["ACC-003", "test_closure_deadline_no_automatic_send"],
    "EXG-009": ["ACC-003", "test_trilingual_summary_checks_are_separate"],
    "EXG-010": ["ACC-003", "test_pieces_catalogue_seeded"],
    "EXG-011": ["ACC-006", "test_no_semantic_conformity"],
    "EXG-012": ["ACC-004", "test_thresholds_are_versioned_rules"],
    "EXG-013": ["ACC-007", "test_nationality_alone_produces_no_appreciation"],
    "EXG-014": ["ACC-003", "test_declared_vs_proven_are_separate"],
    "EXG-015": ["ACC-004", "test_no_hardcoded_calendar"],
    "EXG-016": ["ACC-007", "test_funding_rule_is_alert_only"],
    "EXG-017": ["ACC-005", "test_format_conflict"],
    "EXG-018": ["ACC-003", "test_followup_phase_separates_plan_and_result"],
    "EXG-019": ["ACC-012", "test_passport_data_is_restricted"],
    "EXG-020": ["ACC-004", "test_guide_rule_inactive"],
    "EXG-021": ["ACC-004", "test_guide_rule_inactive"],
    "EXG-022": ["ACC-004", "test_manual_is_internal_practice_only"],
}


def seed_sources(session: Session) -> int:
    """Enregistre le manifeste des sources et vérifie leur présence locale."""
    manifest = reference_data.load_sources_manifest()
    count = 0
    for entry in manifest["sources"]:
        source_id = entry["id"]
        record = session.scalar(select(SourceDocument).where(SourceDocument.source_id == source_id))
        if record is None:
            record = SourceDocument(source_id=source_id)
            session.add(record)
        file_name = entry["file"].split("/")[-1]
        local_path = ORIGINALS_DIR / file_name
        present = local_path.is_file()
        record.file_name = file_name
        record.sha256 = entry["sha256"]
        record.fmt = entry["format"]
        record.pages_rendered = int(entry.get("pages_rendered") or 0)
        record.document_date = entry.get("date") or entry.get("date_document")
        record.reference = entry.get("reference")
        record.authority = entry.get("authority")
        record.status = entry["status"]
        record.role = entry["role"]
        record.present_locally = present
        record.integrity_ok = (sha256_file(local_path) == entry["sha256"]) if present else None
        count += 1
    return count


def seed_requirements(session: Session) -> int:
    data = reference_data.load_requirements()
    count = 0
    for entry in data["requirements"]:
        rid = entry["id"]
        record = session.scalar(select(Requirement).where(Requirement.requirement_id == rid))
        if record is None:
            record = Requirement(requirement_id=rid)
            session.add(record)
        record.label = entry["label"]
        record.statement = entry["statement"]
        record.source_id = entry["source_id"]
        record.pages_json = json.dumps(entry.get("pages", []))
        record.source_status = entry["source_status"]
        record.language = entry.get("language", "fr")
        record.translation_status = entry.get("translation_status", "NON_APPLICABLE")
        record.conflict_id = entry.get("conflict_id")
        record.implementation = entry["implementation"]
        record.test_ids_json = json.dumps(REQUIREMENT_TESTS.get(rid, []))
        # Une exigence n'est jamais activée automatiquement : elle exige une
        # source présente, validée et une traduction visée.
        record.active = False
        count += 1
    return count


def seed_conflicts(session: Session) -> int:
    data = reference_data.load_requirements()
    count = 0
    for entry in data.get("conflicts", []):
        cid = entry["id"]
        record = session.scalar(select(Conflict).where(Conflict.conflict_id == cid))
        if record is None:
            record = Conflict(conflict_id=cid)
            session.add(record)
        record.subject = entry["subject"]
        record.sources_json = json.dumps(entry.get("sources", []))
        record.required_output = entry["required_output"]
        count += 1
    return count


def seed_pieces(session: Session) -> int:
    """Charge les quatorze pièces sourcées puis les pièces complémentaires.

    Les pièces complémentaires portent explicitement une source « à confirmer » :
    leur absence ne peut jamais être présentée comme une non-conformité.
    """
    catalogue = reference_data.load_pieces_catalogue()
    complementary = reference_data.load_complementary_pieces()
    groups = (
        (catalogue["pieces"], catalogue.get("source_primary"), catalogue.get("source_page")),
        (complementary["pieces"], complementary["source_ref"], None),
    )
    count = 0
    for entries, source_ref, source_page in groups:
        for entry in entries:
            key = entry["key"]
            record = session.scalar(select(PieceDefinition).where(PieceDefinition.key == key))
            if record is None:
                record = PieceDefinition(key=key)
                session.add(record)
            record.label = entry["label"]
            record.order_index = int(entry["order"])
            record.sensitivity = entry.get("sensitivity", Sensitivity.ORDINAIRE)
            record.source_ref = source_ref
            record.source_page = source_page
            record.active = True
            count += 1
    return count


def seed_criteria(session: Session) -> int:
    grid = reference_data.load_grid()
    count = 0
    for index, entry in enumerate(grid["criteria"]):
        key = entry["key"]
        record = session.scalar(select(EvaluationCriterion).where(EvaluationCriterion.key == key))
        if record is None:
            record = EvaluationCriterion(key=key)
            session.add(record)
        record.label = entry["label"]
        record.max_score = int(entry["max"])
        record.order_index = index
        record.source_ref = "donnees/grille_scientifique.json"
        count += 1
    return count


def seed_rules(session: Session, *, recorded_by: str = "Référentiel initial") -> int:
    """Charge `rules/default_rules.json`.

    Les règles déjà présentes ne sont pas écrasées : une modification humaine
    du statut `active` ou de la validation est conservée. Seule une version
    supérieure du fichier remplace la définition, en historisant l'ancienne.
    """
    payload = reference_data.load_default_rules()
    count = 0
    for entry in payload["rules"]:
        code = entry["code"]
        record = session.scalar(select(Rule).where(Rule.code == code))
        if record is not None and record.version == entry["version"]:
            continue
        if record is None:
            record = Rule(code=code)
            session.add(record)
        else:
            session.add(
                RuleVersion(
                    rule_code=code,
                    version=record.version,
                    payload_json=json.dumps(_rule_payload(record), ensure_ascii=False),
                    change_reason="Remplacement par une version supérieure du référentiel.",
                    recorded_by=recorded_by,
                )
            )
        record.category = entry["category"]
        record.label = entry["label"]
        record.priority = entry["priority"]
        record.terms_json = json.dumps(entry.get("terms", []), ensure_ascii=False)
        record.secondary_terms_json = json.dumps(entry.get("secondary_terms", []), ensure_ascii=False)
        record.context_terms_json = json.dumps(entry.get("context_terms", []), ensure_ascii=False)
        record.guidance = entry["guidance"]
        record.source_ref = entry["source_ref"]
        record.source_date = entry.get("source_date")
        record.authority = entry.get("authority")
        record.scope = entry.get("scope")
        record.version = entry["version"]
        record.validated_at = None
        record.validated_by = None
        record.is_normative = bool(entry.get("is_normative", False))
        # Une règle normative ne peut pas être active sans source validée.
        record.active = bool(entry.get("active", False)) and not record.is_normative
        if record.is_normative:
            record.suspended_reason = (
                "Règle normative inactive : source officielle absente ou contradiction non arbitrée."
            )
        session.add(
            RuleVersion(
                rule_code=code,
                version=entry["version"],
                payload_json=json.dumps(entry, ensure_ascii=False),
                change_reason="Chargement du référentiel versionné.",
                recorded_by=recorded_by,
            )
        )
        count += 1
    return count


def _rule_payload(rule: Rule) -> dict:
    return {
        "code": rule.code,
        "category": rule.category,
        "label": rule.label,
        "priority": rule.priority,
        "terms": json.loads(rule.terms_json),
        "secondary_terms": json.loads(rule.secondary_terms_json),
        "context_terms": json.loads(rule.context_terms_json),
        "guidance": rule.guidance,
        "source_ref": rule.source_ref,
        "version": rule.version,
        "active": rule.active,
        "is_normative": rule.is_normative,
    }


def seed_all(session: Session) -> dict[str, int]:
    """Initialise ou met à jour tout le référentiel, puis valide la transaction."""
    result = {
        "sources": seed_sources(session),
        "requirements": seed_requirements(session),
        "conflicts": seed_conflicts(session),
        "pieces": seed_pieces(session),
        "criteria": seed_criteria(session),
        "rules": seed_rules(session),
    }
    audit.record(
        session,
        audit.AuditAction.RULE_IMPORT,
        "Chargement du référentiel local versionné : "
        + ", ".join(f"{key}={value}" for key, value in result.items()),
    )
    session.commit()
    return result
