"""Classement externe indicatif, strictement séparé de la grille officielle.

Le ranking n'écrit jamais dans `evaluation_entries`. Il est daté, sourcé,
révisable par l'évaluateur et bloqué en cas de désaccord entre agents.
"""

from __future__ import annotations

import json
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import OrchestrationResult
from app.core import audit
from app.core.config import PROJECT_DIR, get_settings
from app.core.crypto import decrypt_text, encrypt_text, value_fingerprint
from app.core.errors import NotFound, ValidationRefused
from app.core.keyring import get_master_key
from app.core.vocabulary import (
    AGENT_DISAGREEMENT_MESSAGE,
    NOT_PROVIDED,
    RANKING_TITLE,
    RankingGrade,
)
from app.models import AgentDisagreement, EventRanking, EventRankingAxis

AXES_FILE = PROJECT_DIR / "rules" / "ranking_axes.json"

HUMAN_DECISIONS = frozenset({"A_VERIFIER", "ACCEPTE", "CORRIGE", "ECARTE"})


@lru_cache(maxsize=1)
def load_axes_config() -> dict:
    if not AXES_FILE.exists():
        raise FileNotFoundError("rules/ranking_axes.json est absent : le ranking est indisponible.")
    return json.loads(AXES_FILE.read_text(encoding="utf-8"))


def clear_cache() -> None:
    load_axes_config.cache_clear()


def axis_aad(axis_id: str, field: str) -> str:
    return f"ranking_axis:{axis_id}:{field}"


def grade_for(total: float | None, scored_axes: int, config: dict) -> tuple[str, str | None]:
    """Attribue une lettre seulement si assez d'axes sont documentés."""
    minimum = int(config.get("minimum_axes_scored_for_grade", 5))
    if total is None or scored_axes < minimum:
        return RankingGrade.NR, (
            f"Classement non attribué : {scored_axes} axe(s) documenté(s) sur les {minimum} requis."
        )
    for threshold in config["grade_thresholds"]:
        if total >= threshold["min_total"]:
            return threshold["grade"], None
    return RankingGrade.NR, "Aucun seuil applicable."


def build_ranking(
    session: Session,
    dossier_id: str,
    *,
    run_id: str | None,
    orchestration: OrchestrationResult,
    comparison_note: str | None = None,
) -> EventRanking:
    """Enregistre un ranking à partir des propositions comparées des agents."""
    config = load_axes_config()
    key = get_master_key()
    axis_labels = {axis["key"]: axis for axis in config["axes"]}
    consensus = {axis.axis_key: axis for axis in orchestration.axes}

    ranking = EventRanking(
        dossier_id=dossier_id,
        run_id=run_id,
        thresholds_json=json.dumps(config["grade_thresholds"], ensure_ascii=False),
        agents_versions_json=json.dumps(
            {output.agent_name: output.agent_version for output in orchestration.outputs},
            ensure_ascii=False,
        ),
        comparison_note=comparison_note,
    )
    session.add(ranking)
    session.flush()

    total = 0.0
    scored = 0
    agreements: list[float] = []
    for axis_key, definition in axis_labels.items():
        state = consensus.get(axis_key)
        blocked = bool(state and state.blocked)
        has_score = bool(state and state.median is not None and not blocked)
        axis = EventRankingAxis(
            ranking_id=ranking.id,
            axis_key=axis_key,
            label=definition["label"],
            max_score=int(definition["max"]),
            proposed_score=state.median if has_score else None,
            dispersion=state.dispersion if state else None,
            not_provided=not has_score,
            source_ids_json=json.dumps(state.source_urls if state else [], ensure_ascii=False),
            human_decision="A_VERIFIER",
        )
        if state and has_score:
            lows = [item.uncertainty_low for item in state.proposals if item.uncertainty_low is not None]
            highs = [item.uncertainty_high for item in state.proposals if item.uncertainty_high is not None]
            axis.uncertainty_low = min(lows) if lows else None
            axis.uncertainty_high = max(highs) if highs else None
            total += float(state.median)
            scored += 1
            if state.agreement is not None:
                agreements.append(state.agreement)
        session.add(axis)
        session.flush()
        rationale = (
            AGENT_DISAGREEMENT_MESSAGE
            if blocked
            else (state.message if state else f"{NOT_PROVIDED} : aucun agent n'a documenté cet axe.")
        )
        axis.justification_cipher = encrypt_text(key, rationale, axis_aad(axis.id, "justification"))

    if orchestration.blocked:
        ranking.total = None
        ranking.grade = RankingGrade.NR
        ranking.blocked_reason = AGENT_DISAGREEMENT_MESSAGE
    else:
        ranking.total = round(total, 2) if scored else None
        grade, reason = grade_for(ranking.total, scored, config)
        ranking.grade = grade
        ranking.blocked_reason = reason
    ranking.agreement_level = round(sum(agreements) / len(agreements), 3) if agreements else None

    for disagreement in orchestration.disagreements:
        session.add(
            AgentDisagreement(
                run_id=run_id,
                subject_label=disagreement.subject_label,
                axis_key=disagreement.axis_key,
                agents_json=json.dumps(disagreement.agents, ensure_ascii=False),
                dispersion=disagreement.dispersion,
                description=disagreement.description,
            )
        )

    audit.record(
        session,
        audit.AuditAction.RANKING_BUILD,
        f"Ranking externe indicatif calculé : grade {ranking.grade}, "
        f"{scored} axe(s) documenté(s), {len(orchestration.disagreements)} désaccord(s).",
        entity_type="event_ranking",
        entity_id=ranking.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return ranking


def ranking_view(session: Session, dossier_id: str) -> dict | None:
    key = get_master_key()
    ranking = session.scalar(
        select(EventRanking)
        .where(EventRanking.dossier_id == dossier_id)
        .order_by(EventRanking.created_at.desc())
    )
    if ranking is None:
        return None
    axes = session.scalars(
        select(EventRankingAxis).where(EventRankingAxis.ranking_id == ranking.id)
    ).all()
    disagreement_filter = (
        AgentDisagreement.run_id == ranking.run_id
        if ranking.run_id
        else AgentDisagreement.run_id.is_(None)
    )
    disagreements = session.scalars(select(AgentDisagreement).where(disagreement_filter)).all()
    return {
        "id": ranking.id,
        "title": RANKING_TITLE,
        "dossier_id": ranking.dossier_id,
        "run_id": ranking.run_id,
        "total": ranking.total,
        "grade": ranking.grade,
        "agreement_level": ranking.agreement_level,
        "blocked_reason": ranking.blocked_reason,
        "thresholds": json.loads(ranking.thresholds_json),
        "agents_versions": json.loads(ranking.agents_versions_json),
        "comparison_note": ranking.comparison_note,
        "created_at": ranking.created_at,
        "axes": [
            {
                "id": axis.id,
                "axis_key": axis.axis_key,
                "label": axis.label,
                "max": axis.max_score,
                "proposed_score": axis.proposed_score,
                "uncertainty_low": axis.uncertainty_low,
                "uncertainty_high": axis.uncertainty_high,
                "dispersion": axis.dispersion,
                "not_provided": axis.not_provided,
                "display_score": NOT_PROVIDED if axis.not_provided else axis.proposed_score,
                "justification": decrypt_text(
                    key, axis.justification_cipher, axis_aad(axis.id, "justification")
                ),
                "sources": json.loads(axis.source_ids_json),
                "human_decision": axis.human_decision,
                "human_score": axis.human_score,
                "human_justification": decrypt_text(
                    key, axis.human_justification_cipher, axis_aad(axis.id, "human")
                ),
            }
            for axis in axes
        ],
        "disagreements": [
            {
                "subject_label": item.subject_label,
                "axis_key": item.axis_key,
                "agents": json.loads(item.agents_json),
                "dispersion": item.dispersion,
                "description": item.description,
                "resolved": item.resolved,
            }
            for item in disagreements
        ],
        "separation_notice": (
            "Ce classement est indicatif et strictement séparé de la grille scientifique "
            "officielle. Il ne modifie aucune note saisie par l'évaluateur."
        ),
    }


def review_axis(
    session: Session,
    axis_id: str,
    *,
    decision: str,
    score: float | None,
    justification: str,
) -> EventRankingAxis:
    """L'évaluateur accepte, corrige ou écarte un axe, avec justification."""
    axis = session.get(EventRankingAxis, axis_id)
    if axis is None:
        raise NotFound("Axe de ranking introuvable.")
    if decision not in HUMAN_DECISIONS:
        raise ValidationRefused("Décision inconnue (A_VERIFIER, ACCEPTE, CORRIGE ou ECARTE).")
    settings = get_settings()
    justification = (justification or "").strip()
    if decision != "A_VERIFIER" and len(justification) < settings.min_motivation_length:
        raise ValidationRefused(
            f"Une justification d'au moins {settings.min_motivation_length} caractères est "
            "obligatoire pour réviser un axe."
        )
    if decision == "CORRIGE":
        if score is None:
            raise ValidationRefused("Une correction exige une note saisie par l'évaluateur.")
        if score < 0 or score > axis.max_score:
            raise ValidationRefused(
                f"Note hors bornes : l'axe « {axis.label} » est noté de 0 à {axis.max_score}."
            )
        axis.human_score = float(score)
    elif decision == "ECARTE":
        axis.human_score = None

    axis.human_decision = decision
    axis.human_justification_cipher = encrypt_text(
        get_master_key(), justification, axis_aad(axis.id, "human")
    )
    ranking = session.get(EventRanking, axis.ranking_id)
    audit.record(
        session,
        audit.AuditAction.RANKING_REVIEW,
        f"Axe de ranking « {axis.label} » → {decision} par l'évaluateur.",
        entity_type="event_ranking_axis",
        entity_id=axis.id,
        dossier_id=ranking.dossier_id if ranking else None,
        fingerprint=value_fingerprint(justification),
    )
    session.commit()
    return axis
