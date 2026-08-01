"""Journal d'audit local.

Le journal ne contient jamais de valeur sensible en clair : les valeurs sont
tracées par empreinte SHA-256 (`value_fingerprint`).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditEvent


class AuditAction:
    APP_START = "APP_START"
    APP_STOP = "APP_STOP"
    HEALTH_CHECK = "HEALTH_CHECK"
    DOSSIER_CREATE = "DOSSIER_CREATE"
    DOSSIER_UPDATE = "DOSSIER_UPDATE"
    DOSSIER_ARCHIVE = "DOSSIER_ARCHIVE"
    DOCUMENT_IMPORT = "DOCUMENT_IMPORT"
    DOCUMENT_FINGERPRINT = "DOCUMENT_FINGERPRINT"
    DOCUMENT_ANALYZE = "DOCUMENT_ANALYZE"
    DOCUMENT_VIEW_ORIGINAL = "DOCUMENT_VIEW_ORIGINAL"
    PAGE_OCR = "PAGE_OCR"
    PAGE_CORRECTION = "PAGE_CORRECTION"
    ITEM_CONFIRM = "ITEM_CONFIRM"
    ITEM_REJECT = "ITEM_REJECT"
    ITEM_CORRECTION = "ITEM_CORRECTION"
    PIECE_UPDATE = "PIECE_UPDATE"
    ADMIN_CHECK_UPDATE = "ADMIN_CHECK_UPDATE"
    EVALUATION_ENTRY = "EVALUATION_ENTRY"
    FINDING_QUALIFY = "FINDING_QUALIFY"
    NOTE_WRITE = "NOTE_WRITE"
    CONCLUSION_SET = "CONCLUSION_SET"
    REPORT_GENERATE = "REPORT_GENERATE"
    REPORT_DOWNLOAD = "REPORT_DOWNLOAD"
    REPORT_VALIDATE = "REPORT_VALIDATE"
    BACKUP_CREATE = "BACKUP_CREATE"
    BACKUP_VERIFY = "BACKUP_VERIFY"
    BACKUP_RESTORE = "BACKUP_RESTORE"
    RULE_IMPORT = "RULE_IMPORT"
    RULE_ACTIVATE = "RULE_ACTIVATE"
    RULE_DEACTIVATE = "RULE_DEACTIVATE"
    RULE_SUSPEND = "RULE_SUSPEND"
    REGULATION_IMPORT = "REGULATION_IMPORT"
    REGULATION_VALIDATE = "REGULATION_VALIDATE"
    REGULATION_INTEGRITY_ALERT = "REGULATION_INTEGRITY_ALERT"
    CONFLICT_ARBITRATION = "CONFLICT_ARBITRATION"
    RESTRICTED_ACCESS = "RESTRICTED_ACCESS"
    REFUSAL = "REFUSAL"
    # Évaluation automatique V4 -------------------------------------------
    CRITERION_ASSESS = "CRITERION_ASSESS"
    CRITERION_QUALIFY = "CRITERION_QUALIFY"
    SCORE_PROPOSE = "SCORE_PROPOSE"
    SCORE_UPDATE = "SCORE_UPDATE"
    DECISION_PROPOSE = "DECISION_PROPOSE"
    DECISION_RETAIN = "DECISION_RETAIN"
    EVIDENCE_REGISTER = "EVIDENCE_REGISTER"
    JOB_START = "JOB_START"
    JOB_RESUME = "JOB_RESUME"
    JOB_CANCEL = "JOB_CANCEL"
    JOB_FAIL = "JOB_FAIL"
    JOB_COMPLETE = "JOB_COMPLETE"
    AI_CALL = "AI_CALL"
    REPORT_QA = "REPORT_QA"
    # Module de recherche Internet contrôlée -----------------------------
    WEB_CONNECTIVITY_CHECK = "WEB_CONNECTIVITY_CHECK"
    WEB_RUN_PREPARE = "WEB_RUN_PREPARE"
    WEB_RUN_APPROVE = "WEB_RUN_APPROVE"
    WEB_RUN_START = "WEB_RUN_START"
    WEB_RUN_PAUSE = "WEB_RUN_PAUSE"
    WEB_RUN_RESUME = "WEB_RUN_RESUME"
    WEB_RUN_CANCEL = "WEB_RUN_CANCEL"
    WEB_RUN_DISMISS = "WEB_RUN_DISMISS"
    WEB_QUERY_EDIT = "WEB_QUERY_EDIT"
    WEB_QUERY_SENT = "WEB_QUERY_SENT"
    WEB_QUERY_REFUSED = "WEB_QUERY_REFUSED"
    WEB_PROVIDER_ERROR = "WEB_PROVIDER_ERROR"
    WEB_SOURCE_RECORDED = "WEB_SOURCE_RECORDED"
    WEB_CLAIM_RECORDED = "WEB_CLAIM_RECORDED"
    WEB_CLAIM_QUALIFY = "WEB_CLAIM_QUALIFY"
    EGRESS_REFUSED = "EGRESS_REFUSED"
    AGENT_RUN = "AGENT_RUN"
    AGENT_DISAGREEMENT = "AGENT_DISAGREEMENT"
    RANKING_BUILD = "RANKING_BUILD"
    RANKING_REVIEW = "RANKING_REVIEW"


def record(
    session: Session,
    action: str,
    summary: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    dossier_id: str | None = None,
    fingerprint: str | None = None,
    actor_label: str | None = None,
) -> AuditEvent:
    """Ajoute un événement au journal (sans commit : le service décide)."""
    event = AuditEvent(
        action=action,
        summary=summary,
        entity_type=entity_type,
        entity_id=entity_id,
        dossier_id=dossier_id,
        fingerprint=fingerprint,
        actor_label=actor_label or get_settings().evaluator_label,
    )
    session.add(event)
    return event
