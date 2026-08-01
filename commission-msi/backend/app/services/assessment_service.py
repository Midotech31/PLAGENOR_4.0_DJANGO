"""Évaluation automatique : 26 critères, score sur 100, avis proposé.

Ce service enchaîne les trois moteurs déterministes et **persiste** leurs
résultats avec leurs preuves :

1. `regulatory_engine` — les 26 critères, statut `C/PC/NC/NV`, jamais vide ;
2. `scientific_scoring` — le score sur 100, sous-note par sous-note ;
3. `decision_engine` — l'avis technique proposé, motivé et tracé.

Trois garde-fous ne sont jamais levés :

* une qualification humaine (statut de critère, sous-note corrigée, avis
  retenu) n'est jamais écrasée par une nouvelle exécution ;
* toute preuve citée est vérifiée contre le registre avant enregistrement ;
* l'avis reste une **proposition** : il n'a jamais valeur de décision.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import encrypt_text
from app.core.keyring import get_master_key
from app.models.base import new_id, utcnow
from app.models import CriterionResult as CriterionResultRow
from app.models import ProposedDecision as ProposedDecisionRow
from app.models import ScientificScore as ScientificScoreRow
from app.models import ScientificSubScore as ScientificSubScoreRow
from app.services import (
    decision_engine,
    evidence_service,
    facts_service,
    regulatory_engine,
    scientific_scoring,
)
from app.services.regulatory_engine import Status


def criterion_aad(row_id: str, field: str) -> str:
    return f"criterion:{row_id}:{field}"


def _keep_known(session: Session, dossier_id: str, references: list[str]) -> list[str]:
    """Ne conserve que les preuves réellement présentes au registre."""
    known = evidence_service.known_references(session, dossier_id)
    return [ref for ref in dict.fromkeys(references) if ref in known]


# --------------------------------------------------------------------------
# Constats réglementaires
# --------------------------------------------------------------------------


def store_criteria(
    session: Session,
    dossier_id: str,
    results: list[regulatory_engine.CriterionResult],
    *,
    job_id: str | None = None,
) -> int:
    key = get_master_key()
    version = regulatory_engine.load_referential()["referential_version"]
    existing = {
        row.code: row
        for row in session.scalars(
            select(CriterionResultRow).where(CriterionResultRow.dossier_id == dossier_id)
        ).all()
    }

    for result in results:
        # Les preuves sont résolues avant toute écriture : les requêtes qu'elles
        # déclenchent ne doivent pas provoquer le flush d'une ligne incomplète.
        evidence_refs = _keep_known(session, dossier_id, result.evidence_ids)
        if result.calculation:
            evidence_refs.append(
                evidence_service.register_calculation(
                    session,
                    dossier_id,
                    key_name=f"critere:{result.code}",
                    payload=result.calculation,
                )
            )

        row = existing.get(result.code)
        if row is None:
            # L'identifiant est fixé avant l'insertion : il entre dans l'AAD du
            # chiffrement, donc il doit exister avant de chiffrer le constat.
            row = CriterionResultRow(id=new_id(), dossier_id=dossier_id, code=result.code)
            session.add(row)
        row.job_id = job_id
        row.family = result.family
        row.position = result.order
        row.label = result.label
        row.status = result.status
        row.finding_cipher = encrypt_text(key, result.finding, criterion_aad(row.id, "finding"))
        row.exact_source = result.exact_source
        row.source_page = result.page
        row.nature = result.nature
        row.blocking = result.blocking
        row.evidence_refs = json.dumps(evidence_refs, ensure_ascii=False)
        row.calculation_json = (
            json.dumps(result.calculation, ensure_ascii=False) if result.calculation else None
        )
        row.note = result.note
        row.referential_version = version

    session.flush()
    return len(results)


# --------------------------------------------------------------------------
# Score scientifique
# --------------------------------------------------------------------------


def store_score(
    session: Session,
    dossier_id: str,
    result: scientific_scoring.ScientificScore,
    *,
    job_id: str | None = None,
) -> ScientificScoreRow:
    row = session.scalar(
        select(ScientificScoreRow).where(ScientificScoreRow.dossier_id == dossier_id)
    )
    if row is None:
        row = ScientificScoreRow(id=new_id(), dossier_id=dossier_id)
        session.add(row)

    row.job_id = job_id
    row.total = result.total
    row.maximum = result.maximum
    row.grid_version = result.grid_version

    previous = {
        sub.key: sub
        for sub in session.scalars(
            select(ScientificSubScoreRow).where(ScientificSubScoreRow.score_id == row.id)
        ).all()
    }
    position = 0
    for family in result.families:
        for sub in family.subscores:
            position += 1
            stored = previous.get(sub.key)
            if stored is None:
                stored = ScientificSubScoreRow(id=new_id(), score_id=row.id, key=sub.key)
                session.add(stored)
            stored.family_key = family.key
            stored.family_label = family.label
            stored.label = sub.label
            stored.position = position
            stored.score = sub.score
            stored.maximum = sub.max
            stored.justification = sub.justification
            stored.method = sub.method
            stored.evidence_refs = json.dumps(
                _keep_known(session, dossier_id, sub.evidence_ids), ensure_ascii=False
            )

    session.flush()
    return row


# --------------------------------------------------------------------------
# Avis proposé
# --------------------------------------------------------------------------


def store_decision(
    session: Session,
    dossier_id: str,
    decision: decision_engine.ProposedDecision,
    *,
    scientific_total: int | None,
    job_id: str | None = None,
) -> ProposedDecisionRow:
    row = session.scalar(
        select(ProposedDecisionRow).where(ProposedDecisionRow.dossier_id == dossier_id)
    )
    if row is None:
        row = ProposedDecisionRow(id=new_id(), dossier_id=dossier_id)
        session.add(row)

    payload = decision_engine.to_dict(decision)
    row.job_id = job_id
    row.avis = decision.avis
    row.label = decision.label
    row.motivation = decision.motivation
    row.triggered_rules_json = json.dumps(payload["triggered_rules"], ensure_ascii=False)
    row.blocking_criteria = json.dumps(decision.blocking_criteria, ensure_ascii=False)
    row.reserves_json = json.dumps(decision.reserves, ensure_ascii=False)
    row.complements_json = json.dumps(decision.required_complements, ensure_ascii=False)
    row.scientific_total = scientific_total
    row.referential_version = regulatory_engine.load_referential()["referential_version"]
    session.flush()
    return row


# --------------------------------------------------------------------------
# Exécution complète
# --------------------------------------------------------------------------


def assess(session: Session, dossier_id: str, *, job_id: str | None = None) -> dict:
    """Applique les trois moteurs et enregistre constats, score et avis."""
    facts = facts_service.build_facts(session, dossier_id)

    results = regulatory_engine.evaluate(facts)
    summary = regulatory_engine.summarize(results)
    store_criteria(session, dossier_id, results, job_id=job_id)

    score = scientific_scoring.score(facts)
    store_score(session, dossier_id, score, job_id=job_id)

    disagreements = facts.observations.get("unresolved_disagreements") or []
    decision = decision_engine.propose(
        results,
        scientific_total=score.total,
        findings=facts.findings,
        unresolved_disagreements=disagreements,
    )
    store_decision(session, dossier_id, decision, scientific_total=score.total, job_id=job_id)

    audit.record(
        session,
        audit.AuditAction.DOCUMENT_ANALYZE,
        f"Évaluation automatique : {summary['total']} critères appliqués "
        f"(référentiel {summary['referential_version']}), score scientifique proposé "
        f"{score.total}/{score.maximum} (grille {score.grid_version}), avis proposé "
        f"{decision.avis}. Proposition d'aide à la décision, sans valeur décisionnelle.",
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
    )
    session.commit()

    return {
        "criteria": [
            {
                "code": result.code,
                "label": result.label,
                "family": result.family,
                "order": result.order,
                "status": result.status,
                "finding": result.finding,
                "exact_source": result.exact_source,
                "page": result.page,
                "nature": result.nature,
                "blocking": result.blocking,
                "evidence_ids": result.evidence_ids,
                "calculation": result.calculation,
                "note": result.note,
            }
            for result in results
        ],
        "summary": summary,
        "score": scientific_scoring.to_dict(score),
        "decision": decision_engine.to_dict(decision),
    }


# --------------------------------------------------------------------------
# Qualifications humaines — elles priment toujours sur la proposition
# --------------------------------------------------------------------------


def qualify_criterion(
    session: Session, dossier_id: str, *, code: str, status: str, comment: str
) -> CriterionResultRow:
    from app.core.errors import NotFound, ValidationRefused

    if status not in {Status.C, Status.PC, Status.NC, Status.NV}:
        raise ValidationRefused(
            f"Statut « {status} » inconnu : seuls C, PC, NC et NV sont recevables."
        )
    row = session.scalar(
        select(CriterionResultRow).where(
            CriterionResultRow.dossier_id == dossier_id, CriterionResultRow.code == code
        )
    )
    if row is None:
        raise NotFound(f"Critère {code} introuvable pour ce dossier.")

    row.human_status = status
    row.human_comment_cipher = encrypt_text(
        get_master_key(), comment, criterion_aad(row.id, "human_comment")
    )
    audit.record(
        session,
        audit.AuditAction.CRITERION_QUALIFY,
        f"Critère {code} qualifié « {status} » par l'évaluateur "
        f"(proposition de l'application : « {row.status} »).",
        entity_type="criterion_result",
        entity_id=row.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return row


def override_subscore(
    session: Session, dossier_id: str, *, key: str, score: int, justification: str
) -> ScientificSubScoreRow:
    from app.core.errors import NotFound, ValidationRefused

    score_row = session.scalar(
        select(ScientificScoreRow).where(ScientificScoreRow.dossier_id == dossier_id)
    )
    if score_row is None:
        raise NotFound("Aucun score n'a encore été proposé pour ce dossier.")
    row = session.scalar(
        select(ScientificSubScoreRow).where(
            ScientificSubScoreRow.score_id == score_row.id, ScientificSubScoreRow.key == key
        )
    )
    if row is None:
        raise NotFound(f"Sous-critère « {key} » introuvable.")
    if not 0 <= score <= row.maximum:
        raise ValidationRefused(
            f"La note doit rester entre 0 et {row.maximum} pour ce sous-critère."
        )

    previous = row.score
    row.human_score = score
    row.human_justification = justification
    audit.record(
        session,
        audit.AuditAction.SCORE_UPDATE,
        f"Sous-note « {row.label} » portée à {score}/{row.maximum} par l'évaluateur "
        f"(proposition de l'application : {previous}/{row.maximum}).",
        entity_type="scientific_subscore",
        entity_id=row.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return row


def retain_decision(
    session: Session, dossier_id: str, *, avis: str, motivation: str
) -> ProposedDecisionRow:
    from app.core.errors import NotFound, ValidationRefused

    if avis not in decision_engine.CLOSED_LIST:
        raise ValidationRefused(
            f"Avis « {avis} » hors de la liste fermée : "
            + ", ".join(decision_engine.CLOSED_LIST)
            + "."
        )
    row = session.scalar(
        select(ProposedDecisionRow).where(ProposedDecisionRow.dossier_id == dossier_id)
    )
    if row is None:
        raise NotFound("Aucun avis n'a encore été proposé pour ce dossier.")

    row.human_decision = avis
    row.human_motivation_cipher = encrypt_text(
        get_master_key(), motivation, f"decision:{row.id}:motivation"
    )
    row.decided_by = get_settings().evaluator_label
    row.decided_at = utcnow()
    audit.record(
        session,
        audit.AuditAction.DECISION_RETAIN,
        f"Avis retenu par l'évaluateur : {avis} (proposition de l'application : {row.avis}).",
        entity_type="proposed_decision",
        entity_id=row.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return row


def current_assessment(session: Session, dossier_id: str) -> dict:
    """Relit l'évaluation enregistrée, sans rien recalculer."""
    from app.core.crypto import decrypt_text

    key = get_master_key()
    rows = session.scalars(
        select(CriterionResultRow)
        .where(CriterionResultRow.dossier_id == dossier_id)
        .order_by(CriterionResultRow.position)
    ).all()
    criteria = [
        {
            "code": row.code,
            "label": row.label,
            "family": row.family,
            "order": row.position,
            "status": row.human_status or row.status,
            "proposed_status": row.status,
            "human_status": row.human_status,
            "finding": decrypt_text(key, row.finding_cipher, criterion_aad(row.id, "finding")),
            "exact_source": row.exact_source,
            "page": row.source_page,
            "nature": row.nature,
            "blocking": row.blocking,
            "evidence_ids": json.loads(row.evidence_refs or "[]"),
            "calculation": json.loads(row.calculation_json) if row.calculation_json else None,
            "note": row.note,
            "referential_version": row.referential_version,
        }
        for row in rows
    ]

    score_row = session.scalar(
        select(ScientificScoreRow).where(ScientificScoreRow.dossier_id == dossier_id)
    )
    score: dict | None = None
    if score_row is not None:
        subs = session.scalars(
            select(ScientificSubScoreRow)
            .where(ScientificSubScoreRow.score_id == score_row.id)
            .order_by(ScientificSubScoreRow.position)
        ).all()
        families: dict[str, dict] = {}
        for sub in subs:
            family = families.setdefault(
                sub.family_key,
                {"key": sub.family_key, "label": sub.family_label, "score": 0, "max": 0,
                 "subscores": []},
            )
            retained = sub.human_score if sub.human_score is not None else sub.score
            family["score"] += retained
            family["max"] += sub.maximum
            family["subscores"].append(
                {
                    "key": sub.key,
                    "label": sub.label,
                    "score": retained,
                    "proposed_score": sub.score,
                    "human_score": sub.human_score,
                    "max": sub.maximum,
                    "justification": sub.human_justification or sub.justification,
                    "method": sub.method,
                    "evidence_ids": json.loads(sub.evidence_refs or "[]"),
                }
            )
        score = {
            "total": sum(family["score"] for family in families.values()),
            "proposed_total": score_row.total,
            "validated_total": score_row.validated_total,
            "maximum": score_row.maximum,
            "grid_version": score_row.grid_version,
            "families": list(families.values()),
        }

    decision_row = session.scalar(
        select(ProposedDecisionRow).where(ProposedDecisionRow.dossier_id == dossier_id)
    )
    decision: dict | None = None
    if decision_row is not None:
        decision = {
            "avis": decision_row.avis,
            "label": decision_row.label,
            "motivation": decision_row.motivation,
            "disclaimer": decision_engine.DISCLAIMER,
            "triggered_rules": json.loads(decision_row.triggered_rules_json or "[]"),
            "blocking_criteria": json.loads(decision_row.blocking_criteria or "[]"),
            "reserves": json.loads(decision_row.reserves_json or "[]"),
            "required_complements": json.loads(decision_row.complements_json or "[]"),
            "scientific_total": decision_row.scientific_total,
            "referential_version": decision_row.referential_version,
            "human_decision": decision_row.human_decision,
            "decided_by": decision_row.decided_by,
        }

    return {"criteria": criteria, "score": score, "decision": decision}
