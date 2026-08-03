"""Travail d'analyse durable, exécuté par un worker distinct du serveur HTTP.

Le clic sur **Traiter le dossier** crée une ligne en base, pas une tâche en
mémoire. Fermer le navigateur, redémarrer l'application ou perdre le processus
ne perd jamais le travail :

* un **bail** (`lease_owner` / `lease_expires_at`) garantit qu'un seul worker
  détient le travail à un instant donné ;
* un **battement** (`heartbeat_at`) permet de détecter un worker mort et de
  reprendre le travail après expiration du bail ;
* des **points de reprise** (`analysis_checkpoints`) évitent de refaire une
  étape déjà réussie, tant que son entrée n'a pas changé ;
* `Annuler` est **non destructif** : il arrête la progression sans effacer ce
  qui a déjà été produit.

Les journaux ne contiennent ni contenu de dossier, ni secret : seulement des
étapes, des compteurs et des empreintes.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.db import session_scope
from app.core.errors import NotFound, ValidationRefused
from app.core.vocabulary import (
    JOB_STATE_LABELS,
    TERMINAL_JOB_STATES,
    DossierStatus,
    JobState,
)
from app.models import AnalysisCheckpoint, AnalysisJob, Dossier, Document
from app.models.base import new_id, utcnow

#: Durée d'un bail ; au-delà, le travail est considéré comme abandonné.
LEASE_SECONDS = 120

#: Intervalle de battement du worker.
HEARTBEAT_SECONDS = 20

#: États actifs — un dossier ne peut pas avoir deux travaux actifs simultanés.
ACTIVE_STATES = tuple(state for state in JobState if state not in TERMINAL_JOB_STATES)

#: Ordre d'exécution des étapes et progression associée.
PIPELINE: tuple[tuple[str, int], ...] = (
    (JobState.VALIDATING, 5),
    (JobState.EXTRACTING, 15),
    (JobState.OCR, 28),
    (JobState.SEMANTIC_READING, 40),
    (JobState.STRUCTURING, 48),
    (JobState.REGULATORY_CHECK, 60),
    (JobState.SCIENTIFIC_SCORING, 70),
    (JobState.WEB_RESEARCH, 80),
    (JobState.INDEPENDENT_AUDIT, 88),
    (JobState.REPORT_BUILDING, 92),
    (JobState.REPORT_QA, 96),
    (JobState.REPORT_RENDERING, 99),
)


class Cancelled(RuntimeError):
    """Levée lorsque l'évaluateur demande l'arrêt : rien n'est effacé."""


def worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Création et consultation
# --------------------------------------------------------------------------


def active_job(session: Session, dossier_id: str) -> AnalysisJob | None:
    return session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.dossier_id == dossier_id, AnalysisJob.state.in_(ACTIVE_STATES))
        .order_by(AnalysisJob.created_at.desc())
    )


def latest_job(session: Session, dossier_id: str) -> AnalysisJob | None:
    return session.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.dossier_id == dossier_id)
        .order_by(AnalysisJob.created_at.desc())
    )


def enqueue(session: Session, dossier_id: str, *, analysis_mode: str = "LOCAL_ONLY") -> AnalysisJob:
    """Crée le travail durable. Refuse un doublon sur le même fichier."""
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise NotFound("Dossier introuvable.")

    document = session.scalar(
        select(Document).where(Document.dossier_id == dossier_id).order_by(Document.created_at)
    )
    if document is None:
        raise ValidationRefused(
            "Aucun PDF valide n'est chargé : le traitement ne peut pas démarrer. "
            "Importez d'abord le dossier au format PDF."
        )

    running = active_job(session, dossier_id)
    if running is not None and running.source_sha256 == document.sha256:
        raise ValidationRefused(
            "Une analyse du même fichier est déjà en cours "
            f"(étape « {running.step_label} »). Suivez sa progression ou annulez-la "
            "avant d'en relancer une."
        )

    pages = dossier.page_count or 0
    job = AnalysisJob(
        id=new_id(),
        dossier_id=dossier_id,
        state=JobState.QUEUED,
        step_label=JOB_STATE_LABELS[JobState.QUEUED],
        pages_total=pages,
        analysis_mode=analysis_mode,
        source_sha256=document.sha256,
    )
    session.add(job)
    if dossier.status == DossierStatus.NOUVEAU:
        dossier.status = DossierStatus.ANALYSE_EN_COURS
    audit.record(
        session,
        audit.AuditAction.JOB_START,
        f"Traitement du dossier demandé ({pages} page(s), mode {analysis_mode}). "
        "Le travail est enregistré en base : il survit à la fermeture de l'application.",
        entity_type="analysis_job",
        entity_id=job.id,
        dossier_id=dossier_id,
    )
    session.commit()
    return job


def cancel(session: Session, job_id: str) -> AnalysisJob:
    """Annulation non destructive : la progression s'arrête, rien n'est effacé."""
    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise NotFound("Travail introuvable.")
    if job.state in TERMINAL_JOB_STATES:
        return job

    job.cancel_requested = True
    if job.state == JobState.QUEUED or job.lease_owner is None:
        # Aucun worker ne le détient : l'arrêt est immédiat.
        job.state = JobState.CANCELLED
        job.step_label = JOB_STATE_LABELS[JobState.CANCELLED]
        job.finished_at = utcnow()
    audit.record(
        session,
        audit.AuditAction.JOB_CANCEL,
        "Annulation demandée par l'évaluateur. Les résultats déjà produits sont conservés : "
        "l'annulation n'efface rien.",
        entity_type="analysis_job",
        entity_id=job.id,
        dossier_id=job.dossier_id,
    )
    session.commit()
    return job


def resume(session: Session, job_id: str) -> AnalysisJob:
    """Remet le travail en file : il reprendra au dernier point de reprise valide."""
    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise NotFound("Travail introuvable.")
    if job.state == JobState.COMPLETED:
        raise ValidationRefused("Ce travail est déjà terminé : il n'y a rien à reprendre.")

    steps = [row.step for row in checkpoints(session, job_id)]
    job.state = JobState.QUEUED
    job.step_label = JOB_STATE_LABELS[JobState.QUEUED]
    # Une reprise demandée par l'évaluateur rouvre le compteur de tentatives :
    # sans cela l'écran affichait « Tentative : 6/3 », un rapport qui n'a pas de
    # sens et laisse croire à un dérèglement. Le compteur mesure les reprises
    # automatiques après panne, pas les décisions humaines.
    job.attempt = 0
    job.cancel_requested = False
    job.error_message = None
    job.error_code = None
    job.lease_owner = None
    job.lease_expires_at = None
    job.finished_at = None
    audit.record(
        session,
        audit.AuditAction.JOB_RESUME,
        f"Reprise demandée : {len(steps)} étape(s) déjà validée(s) ne seront pas refaites.",
        entity_type="analysis_job",
        entity_id=job.id,
        dossier_id=job.dossier_id,
    )
    session.commit()
    return job


def checkpoints(session: Session, job_id: str) -> list[AnalysisCheckpoint]:
    return list(
        session.scalars(
            select(AnalysisCheckpoint)
            .where(AnalysisCheckpoint.job_id == job_id, AnalysisCheckpoint.status == "OK")
            .order_by(AnalysisCheckpoint.created_at)
        ).all()
    )


def _step_result(session: Session, job_id: str, step: str) -> dict | None:
    """Résultat enregistré d'une étape, s'il existe et reste lisible."""
    row = checkpoint_for(session, job_id, step)
    if row is None or not row.result_json:
        return None
    try:
        payload = json.loads(row.result_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def job_view(session: Session, job: AnalysisJob) -> dict:
    done = [row.step for row in checkpoints(session, job.id)]
    remaining = [state for state, _ in PIPELINE if state not in done]
    return {
        # Ce que la lecture assistée a proposé, et surtout ce qu'elle a rejeté :
        # un compte de rejets visible vaut mieux qu'une confiance implicite.
        "lecture_assistee": _step_result(session, job.id, JobState.SEMANTIC_READING),
        "id": job.id,
        "dossier_id": job.dossier_id,
        "state": job.state,
        "step_label": job.step_label,
        "progress": job.progress,
        "pages_total": job.pages_total,
        "pages_done": job.pages_done,
        "searches_done": job.searches_done,
        "validations_done": job.validations_done,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "cancel_requested": job.cancel_requested,
        "error_message": job.error_message,
        "error_code": job.error_code,
        "analysis_mode": job.analysis_mode,
        "model_id": job.model_id,
        "referential_version": job.referential_version,
        "grid_version": job.grid_version,
        "steps_done": done,
        "steps_remaining": remaining,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "can_resume": job.state in {JobState.FAILED, JobState.CANCELLED},
        "estimate": _estimate(job, remaining),
    }


def _estimate(job: AnalysisJob, remaining: list[str]) -> str:
    """Estimation prudente, présentée comme telle."""
    if job.state == JobState.COMPLETED:
        return "Terminé."
    if job.state in TERMINAL_JOB_STATES:
        return "Arrêté."
    if not remaining:
        return "Dernière étape en cours."
    # 20 s par étape plus 2 s par page restante : ordre de grandeur, jamais une promesse.
    pages_left = max(job.pages_total - job.pages_done, 0)
    seconds = len(remaining) * 20 + pages_left * 2
    minutes = max(1, round(seconds / 60))
    return f"Estimation prudente : environ {minutes} minute(s) restante(s), selon le poste."


# --------------------------------------------------------------------------
# Bail et points de reprise
# --------------------------------------------------------------------------


def claim(session: Session, *, owner: str) -> AnalysisJob | None:
    """Prend le bail d'un travail en attente ou d'un bail expiré.

    L'écriture conditionnelle sur `lease_owner` sert de verrou : deux workers
    concurrents ne peuvent pas détenir le même travail.
    """
    now = utcnow()
    candidates = session.scalars(
        select(AnalysisJob)
        .where(AnalysisJob.state.in_(ACTIVE_STATES))
        .order_by(AnalysisJob.created_at)
    ).all()

    for job in candidates:
        expired = job.lease_expires_at is None or job.lease_expires_at <= now
        if job.lease_owner is not None and not expired:
            continue
        job.lease_owner = owner
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.heartbeat_at = now
        if job.started_at is None:
            job.started_at = now
        job.attempt += 1
        session.commit()
        return job
    return None


def heartbeat(session: Session, job: AnalysisJob) -> None:
    now = utcnow()
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
    session.commit()


def checkpoint_for(session: Session, job_id: str, step: str) -> AnalysisCheckpoint | None:
    return session.scalar(
        select(AnalysisCheckpoint).where(
            AnalysisCheckpoint.job_id == job_id, AnalysisCheckpoint.step == step
        )
    )


def save_checkpoint(
    session: Session,
    job_id: str,
    *,
    step: str,
    input_signature: str,
    result: dict | None = None,
    status: str = "OK",
    message: str | None = None,
) -> AnalysisCheckpoint:
    row = checkpoint_for(session, job_id, step)
    if row is None:
        row = AnalysisCheckpoint(id=new_id(), job_id=job_id, step=step, input_sha256="")
        session.add(row)
    row.input_sha256 = _sha256(input_signature)
    row.result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    row.status = status
    row.message = message
    row.created_at = utcnow()
    session.commit()
    return row


def is_step_done(session: Session, job_id: str, step: str, input_signature: str) -> bool:
    """Une étape n'est sautée que si son entrée est rigoureusement identique."""
    row = checkpoint_for(session, job_id, step)
    return (
        row is not None and row.status == "OK" and row.input_sha256 == _sha256(input_signature)
    )


# --------------------------------------------------------------------------
# Exécution
# --------------------------------------------------------------------------


def _set_state(session: Session, job: AnalysisJob, state: str, progress: int) -> None:
    if job.cancel_requested:
        raise Cancelled()
    job.state = state
    job.step_label = JOB_STATE_LABELS[state]
    job.progress = progress
    heartbeat(session, job)


def run_job(session: Session, job: AnalysisJob) -> dict:
    """Exécute le pipeline complet, en sautant les étapes déjà validées."""
    from app.services import pipeline

    dossier_id = job.dossier_id
    summary: dict = {}
    try:
        for state, progress in PIPELINE:
            step = pipeline.STEPS.get(state)
            if step is None:
                continue
            signature = step.signature(session, dossier_id)
            if is_step_done(session, job.id, state, signature):
                job.progress = max(job.progress, progress)
                session.commit()
                continue
            _set_state(session, job, state, progress)
            result = step.run(session, job)
            save_checkpoint(
                session, job.id, step=state, input_signature=signature, result=result
            )
            summary[state] = result

        job.state = JobState.COMPLETED
        job.step_label = JOB_STATE_LABELS[JobState.COMPLETED]
        job.progress = 100
        job.finished_at = utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        audit.record(
            session,
            audit.AuditAction.JOB_COMPLETE,
            f"Traitement terminé en {job.attempt} tentative(s) : "
            f"{len(summary)} étape(s) exécutée(s).",
            entity_type="analysis_job",
            entity_id=job.id,
            dossier_id=dossier_id,
        )
        session.commit()

    except Cancelled:
        job.state = JobState.CANCELLED
        job.step_label = JOB_STATE_LABELS[JobState.CANCELLED]
        job.finished_at = utcnow()
        job.lease_owner = None
        job.lease_expires_at = None
        session.commit()

    except Exception as exc:  # noqa: BLE001 - l'erreur est expliquée, jamais brute
        # Le libellé de l'étape est retenu **avant** d'être remplacé par celui de
        # l'état terminal : sans cela, le message annonçait « L'étape
        # "Interrompu" n'a pas abouti », ce qui ne nomme aucune étape et ne dit
        # donc pas où chercher.
        failed_step = job.step_label
        job.state = (
            JobState.FAILED if job.attempt >= job.max_attempts else JobState.QUEUED
        )
        job.step_label = JOB_STATE_LABELS[job.state]
        job.error_code = type(exc).__name__
        job.error_message = _explain(exc, job, failed_step)
        job.lease_owner = None
        job.lease_expires_at = None
        if job.state == JobState.FAILED:
            job.finished_at = utcnow()
        audit.record(
            session,
            audit.AuditAction.JOB_FAIL,
            f"Étape « {job.step_label} » interrompue ({job.error_code}) à la tentative "
            f"{job.attempt}/{job.max_attempts}.",
            entity_type="analysis_job",
            entity_id=job.id,
            dossier_id=dossier_id,
        )
        session.commit()

    return summary


#: Codes d'erreur qui se corrigent dans la configuration, jamais dans le dossier.
#: Envoyer « vérifiez le dossier importé » pour une clé refusée fait chercher la
#: panne exactement là où elle n'est pas.
CONFIGURATION_ERRORS = frozenset(
    {"AiError", "ModelUnavailable", "ExternalAiNotConfigured", "RestrictedContentRefused"}
)

#: Marche à suivre pour un échec de configuration : une commande qui nomme la
#: cause précise, plutôt qu'une invitation à deviner.
CONFIGURATION_ACTION = (
    "Ce point ne se corrige pas dans le dossier. Lancez, depuis le dossier de "
    "l'application :\n"
    "    backend\\.venv\\Scripts\\python.exe scripts\\verifier_ia.py --appel\n"
    "Ce contrôle nomme la cause exacte : clé refusée, crédit absent, modèle "
    "inconnu ou réseau bloqué. Corrigez-la, puis utilisez « Reprendre » : les "
    "étapes déjà validées ne seront pas refaites. Le mode LOCAL_ONLY reste "
    "utilisable en attendant."
)


def _explain(exc: Exception, job: AnalysisJob, failed_step: str | None = None) -> str:
    """Message compréhensible : la cause et l'action possible, sans trace brute."""
    causes = {
        "FileNotFoundError": "un fichier de référence attendu est absent",
        "UnknownEvidence": "une affirmation citait une preuve absente du registre",
        "ValidationRefused": "une donnée du dossier a été refusée par les contrôles",
        "PermissionError": "un fichier local n'a pas pu être lu ou écrit",
        # Modes d'échec du mode hybride : nommés, parce qu'ils se corrigent dans
        # la configuration et non dans le dossier.
        "ModelUnavailable": "le modèle configuré n'est pas disponible pour ce compte ; "
        "aucun repli vers un modèle moins performant n'a été fait",
        "ExternalAiNotConfigured": "le mode HYBRID_STRICT est incomplètement configuré",
        "RestrictedContentRefused": "une donnée restreinte allait être transmise : "
        "la transmission a été refusée",
        "AiError": "l'appel au modèle n'a pas abouti",
    }
    code = type(exc).__name__
    cause = causes.get(code, "une erreur technique est survenue")

    if code in CONFIGURATION_ERRORS:
        action = CONFIGURATION_ACTION
    elif job.state != JobState.FAILED:
        action = (
            "Vous pouvez relancer le traitement avec « Reprendre » : les étapes déjà "
            "validées ne seront pas refaites."
        )
    else:
        action = (
            "Vérifiez le dossier importé, puis utilisez « Reprendre » pour continuer au "
            "dernier point de reprise valide."
        )

    # Le libellé retenu est celui de l'étape qui a échoué, pas celui de l'état
    # dans lequel le travail se trouve maintenant.
    etape = failed_step or job.step_label
    return f"L'étape « {etape} » n'a pas abouti : {cause}. {action}"


# --------------------------------------------------------------------------
# Boucle du worker
# --------------------------------------------------------------------------


def work_once(*, owner: str | None = None) -> str | None:
    """Prend un travail et l'exécute. Retourne son identifiant, ou None."""
    owner = owner or worker_identity()
    with session_scope() as session:
        job = claim(session, owner=owner)
        if job is None:
            return None
        job_id = job.id
        run_job(session, job)
        return job_id


def work_forever(*, stop: threading.Event, poll_seconds: float = 1.0) -> None:
    """Boucle du worker : elle survit aux erreurs et s'arrête proprement."""
    owner = worker_identity()
    while not stop.is_set():
        try:
            if work_once(owner=owner) is None:
                stop.wait(poll_seconds)
        except Exception:  # noqa: BLE001 - un échec ne doit jamais tuer le worker
            stop.wait(poll_seconds)


def start_background_worker() -> tuple[threading.Thread, threading.Event]:
    """Démarre le worker dans un fil dédié, distinct du serveur HTTP."""
    stop = threading.Event()
    thread = threading.Thread(
        target=work_forever, kwargs={"stop": stop}, name="msi-analysis-worker", daemon=True
    )
    thread.start()
    return thread, stop


def wait_for(job_id: str, *, timeout: float = 60.0, poll: float = 0.2) -> dict:
    """Attend l'issue d'un travail — utilisé par les tests et le mode synchrone."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session_scope() as session:
            job = session.get(AnalysisJob, job_id)
            if job is not None and job.state in TERMINAL_JOB_STATES:
                return job_view(session, job)
        time.sleep(poll)
    raise TimeoutError(
        f"Le traitement n'a pas abouti dans le délai imparti ({timeout:.0f} s). "
        "Il reste enregistré en base et peut être repris."
    )
