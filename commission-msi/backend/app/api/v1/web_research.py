"""Routes du module de recherche Internet contrôlée, des agents et du ranking."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import NotFound
from app.core.vocabulary import (
    RANKING_TITLE,
    WEB_UNAVAILABLE_MESSAGE,
    AgentName,
    ClaimNature,
    EvidenceStatus,
    SourceTier,
    WebRunStatus,
)
from app.models import AgentDisagreement, PersonWebProfile
from app.ranking import service as ranking_service
from app.web_research import egress, providers
from app.web_research import service as web_service

router = APIRouter(tags=["recherche-web"])


class QueryEdit(BaseModel):
    query_text: str = Field(min_length=1, max_length=300)
    approved: bool = False


class RunApproval(BaseModel):
    approved_by: str = Field(min_length=2, max_length=200)


class RunTransition(BaseModel):
    status: WebRunStatus
    justification: str = Field(default="", max_length=4000)


class RunPrepare(BaseModel):
    scope_note: str = Field(default="", max_length=4000)


class ClaimQualification(BaseModel):
    status: EvidenceStatus
    comment: str = Field(default="", max_length=4000)


class AxisReview(BaseModel):
    decision: str = Field(pattern="^(A_VERIFIER|ACCEPTE|CORRIGE|ECARTE)$")
    score: float | None = None
    justification: str = Field(default="", max_length=4000)


# --------------------------------------------------------------------------
# État du module
# --------------------------------------------------------------------------


@router.get("/recherche-web/connectivite")
def connectivity(session: Session = Depends(get_db)) -> dict:
    return web_service.connectivity(session)


@router.get("/recherche-web/fournisseurs")
def provider_list() -> dict:
    return {
        "providers": providers.provider_states(),
        "egress": egress.policy_state(),
        "notice": (
            "Chaque fournisseur peut être désactivé indépendamment sans arrêter le reste de "
            "l'application. Les clés API proviennent uniquement de l'environnement local."
        ),
    }


@router.get("/recherche-web/vocabulaire")
def web_vocabulary() -> dict:
    return {
        "evidence_status": [item.value for item in EvidenceStatus],
        "claim_nature": [item.value for item in ClaimNature],
        "source_tiers": [item.value for item in SourceTier],
        "agents": [item.value for item in AgentName],
        "run_status": [item.value for item in WebRunStatus],
        "unavailable_message": WEB_UNAVAILABLE_MESSAGE,
        "ranking_title": RANKING_TITLE,
    }


# --------------------------------------------------------------------------
# Campagnes
# --------------------------------------------------------------------------


@router.get("/dossiers/{dossier_id}/recherche-web")
def list_runs(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    return {
        "items": web_service.list_runs(session, dossier_id),
        "enriched_state": web_service.enriched_analysis_state(session, dossier_id),
    }


@router.post("/dossiers/{dossier_id}/recherche-web", status_code=201)
def prepare_run(
    dossier_id: str, payload: RunPrepare, session: Session = Depends(get_db)
) -> dict:
    run = web_service.prepare_run(session, dossier_id, scope_note=payload.scope_note)
    return web_service.run_view(session, run.id)


@router.get("/recherche-web/{run_id}")
def get_run(run_id: str, session: Session = Depends(get_db)) -> dict:
    return web_service.run_view(session, run_id)


@router.post("/recherche-web/{run_id}/requetes/{query_id}")
def edit_query(
    run_id: str, query_id: str, payload: QueryEdit, session: Session = Depends(get_db)
) -> dict:
    query = web_service.edit_query(
        session, query_id, query_text=payload.query_text, approved=payload.approved
    )
    return {"id": query.id, "query_text": query.query_text, "approved": query.approved}


@router.post("/recherche-web/{run_id}/approbation")
def approve(run_id: str, payload: RunApproval, session: Session = Depends(get_db)) -> dict:
    run = web_service.approve_run(session, run_id, approved_by=payload.approved_by)
    return {"id": run.id, "approved_at": run.approved_at, "approved_by": run.approved_by}


@router.post("/recherche-web/{run_id}/execution")
def execute(run_id: str, session: Session = Depends(get_db)) -> dict:
    return web_service.execute_run(session, run_id)


@router.post("/recherche-web/{run_id}/etat")
def transition(run_id: str, payload: RunTransition, session: Session = Depends(get_db)) -> dict:
    run = web_service.set_run_status(
        session, run_id, status=payload.status, justification=payload.justification
    )
    return {"id": run.id, "status": run.status}


@router.post("/dossiers/{dossier_id}/analyse-enrichie")
def mark_complete(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    dossier = web_service.mark_enriched_complete(session, dossier_id)
    return {"id": dossier.id, "status": dossier.status}


# --------------------------------------------------------------------------
# Profils, affirmations, désaccords
# --------------------------------------------------------------------------


@router.get("/dossiers/{dossier_id}/profils-publics")
def profiles(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    import json

    rows = session.scalars(
        select(PersonWebProfile).where(PersonWebProfile.dossier_id == dossier_id)
    ).all()
    return {
        "items": [
            {
                "id": profile.id,
                "subject_kind": profile.subject_kind,
                "display_name": profile.display_name,
                "declared_affiliation": profile.declared_affiliation,
                "verified_affiliations": json.loads(profile.verified_affiliations_json),
                "status": profile.status,
                "created_at": profile.created_at,
            }
            for profile in rows
        ],
        "notice": (
            "Une homonymie possible bloque toute conclusion consolidée. Une affiliation "
            "déclarée non confirmée reste au statut A_VERIFIER."
        ),
    }


@router.post("/recherche-web/affirmations/{claim_id}")
def qualify_claim(
    claim_id: str, payload: ClaimQualification, session: Session = Depends(get_db)
) -> dict:
    claim = web_service.qualify_claim(
        session, claim_id, status=payload.status, comment=payload.comment
    )
    return {"id": claim.id, "human_status": claim.human_status}


@router.get("/dossiers/{dossier_id}/desaccords-agents")
def disagreements(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    import json

    from app.models import WebResearchRun

    run_ids = [
        run.id
        for run in session.scalars(
            select(WebResearchRun).where(WebResearchRun.dossier_id == dossier_id)
        ).all()
    ]
    rows = (
        session.scalars(
            select(AgentDisagreement).where(AgentDisagreement.run_id.in_(run_ids))
        ).all()
        if run_ids
        else []
    )
    return {
        "items": [
            {
                "id": item.id,
                "subject_label": item.subject_label,
                "axis_key": item.axis_key,
                "agents": json.loads(item.agents_json),
                "dispersion": item.dispersion,
                "description": item.description,
                "resolved": item.resolved,
                "resolution_note": item.resolution_note,
            }
            for item in rows
        ]
    }


# --------------------------------------------------------------------------
# Ranking externe indicatif
# --------------------------------------------------------------------------


@router.get("/dossiers/{dossier_id}/ranking")
def ranking(dossier_id: str, session: Session = Depends(get_db)) -> dict:
    view = ranking_service.ranking_view(session, dossier_id)
    if view is None:
        return {
            "ranking": None,
            "title": RANKING_TITLE,
            "message": (
                "Aucun classement externe n'a encore été calculé pour ce dossier. "
                "Il est indicatif et n'influence jamais la grille scientifique officielle."
            ),
        }
    return {"ranking": view, "title": RANKING_TITLE}


@router.get("/ranking/axes")
def ranking_axes() -> dict:
    config = ranking_service.load_axes_config()
    return {
        "title": config["title"],
        "warning": config["warning"],
        "axes": config["axes"],
        "grade_thresholds": config["grade_thresholds"],
        "minimum_axes_scored_for_grade": config["minimum_axes_scored_for_grade"],
        "rules": config["rules"],
    }


@router.post("/ranking/axes/{axis_id}")
def review_axis(axis_id: str, payload: AxisReview, session: Session = Depends(get_db)) -> dict:
    axis = ranking_service.review_axis(
        session,
        axis_id,
        decision=payload.decision,
        score=payload.score,
        justification=payload.justification,
    )
    return {
        "id": axis.id,
        "human_decision": axis.human_decision,
        "human_score": axis.human_score,
        "notice": (
            "Révision enregistrée dans le classement externe indicatif uniquement. "
            "La grille scientifique officielle n'est pas modifiée."
        ),
    }


@router.get("/recherche-web/{run_id}/journal-sortie")
def egress_journal(run_id: str, session: Session = Depends(get_db)) -> dict:
    from app.models import WebResearchRun

    run = session.get(WebResearchRun, run_id)
    if run is None:
        raise NotFound("Campagne introuvable.")
    return {
        "run_id": run.id,
        "egress": egress.policy_state(),
        "evaluator": get_settings().evaluator_label,
    }
