"""Étapes de la chaîne de traitement, chacune reprenable indépendamment.

Chaque étape expose deux fonctions :

* `signature` — l'empreinte de son entrée. Tant qu'elle ne change pas, l'étape
  déjà validée n'est pas rejouée ;
* `run` — l'exécution proprement dite, qui met à jour les compteurs du travail.

Aucune étape ne lève d'exception pour un dossier incomplet : elle produit un
constat explicite. Seule une panne technique réelle interrompt la chaîne, et le
travail redevient alors reprenable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vocabulary import DossierStatus, JobState
from app.models import AnalysisJob, Document, Dossier
from app.services import (
    assessment_service,
    coherence_service,
    dossier_service,
    evidence_service,
    extraction_service,
    ocr_service,
)


@dataclass(frozen=True)
class Step:
    signature: Callable[[Session, str], str]
    run: Callable[[Session, AnalysisJob], dict]


def _document_signature(session: Session, dossier_id: str) -> str:
    """Empreinte des documents importés : elle change si le dossier change."""
    documents = session.scalars(
        select(Document).where(Document.dossier_id == dossier_id).order_by(Document.created_at)
    ).all()
    return "|".join(f"{doc.id}:{doc.sha256}" for doc in documents) or "aucun-document"


def _text_signature(session: Session, dossier_id: str) -> str:
    """Empreinte du texte courant : une correction humaine rejoue les étapes aval."""
    texts = dossier_service.dossier_page_texts(session, dossier_id)
    digest = hashlib.sha256()
    for page_no in sorted(texts):
        digest.update(f"{page_no}:{texts[page_no]}".encode("utf-8"))
    return digest.hexdigest()


def _values_signature(session: Session, dossier_id: str) -> str:
    """Empreinte des faits : elle intègre le texte, les pièces et les alertes."""
    from app.services import facts_service

    facts = facts_service.build_facts(session, dossier_id, rebuild_evidence=False)
    digest = hashlib.sha256()
    digest.update(_text_signature(session, dossier_id).encode("utf-8"))
    for key in sorted(facts.values):
        digest.update(f"{key}={facts.values[key]}".encode("utf-8"))
    for key in sorted(facts.pieces):
        digest.update(f"{key}:{facts.pieces[key]}".encode("utf-8"))
    for finding in sorted(facts.findings, key=lambda item: str(item.get("id"))):
        digest.update(f"{finding.get('id')}:{finding.get('human_status')}".encode("utf-8"))
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Étapes
# --------------------------------------------------------------------------


def _validate(session: Session, job: AnalysisJob) -> dict:
    dossier = session.get(Dossier, job.dossier_id)
    documents = session.scalars(
        select(Document).where(Document.dossier_id == job.dossier_id)
    ).all()
    pages = dossier_service.dossier_pages(session, job.dossier_id)
    job.pages_total = len(pages)
    job.validations_done += 1
    return {
        "documents": len(documents),
        "pages": len(pages),
        "sha256": [doc.sha256 for doc in documents],
        "constat": f"{len(documents)} document(s) PDF et {len(pages)} page(s) enregistrés, "
        f"empreintes SHA-256 conservées. Dossier « {dossier.reference if dossier else '—'} ».",
    }


def _extract(session: Session, job: AnalysisJob) -> dict:
    texts = dossier_service.dossier_page_texts(session, job.dossier_id)
    job.pages_done = len(texts)
    return {
        "pages_avec_texte": len(texts),
        "constat": f"{len(texts)} page(s) porteuses de texte natif exploitable.",
    }


def _ocr(session: Session, job: AnalysisJob) -> dict:
    if not ocr_service.is_available():
        return {
            "disponible": False,
            "constat": "Moteur OCR local indisponible : les pages scannées restent non "
            "extraites et explicitement marquées « vérification humaine obligatoire ».",
        }
    pages = [
        page
        for page in dossier_service.dossier_pages(session, job.dossier_id)
        if page.needs_ocr and not page.is_blank
    ]
    done, failed = 0, 0
    for page in pages:
        try:
            dossier_service.run_page_ocr(session, page.id)
            done += 1
        except Exception:  # noqa: BLE001 - un échec OCR n'interrompt jamais la chaîne
            failed += 1
        job.pages_done = min(job.pages_total, job.pages_done + 1)
    return {
        "traitees": done,
        "echecs": failed,
        "constat": f"{done} page(s) océrisée(s), {failed} échec(s)."
        if pages
        else "Aucune page ne nécessitait d'OCR : le texte natif suffisait.",
    }


def _structure(session: Session, job: AnalysisJob) -> dict:
    extraction = extraction_service.autofill_dossier(session, job.dossier_id)
    detected = dossier_service.detect_pieces(session, job.dossier_id)
    checks = coherence_service.run_automatic_checks(session, job.dossier_id)
    created = dossier_service.run_vigilance(session, job.dossier_id)
    references = evidence_service.rebuild_registry(session, job.dossier_id)
    session.commit()
    job.validations_done += 1
    return {
        "informations_proposees": extraction["proposed"],
        "informations_preservees": extraction["preserved"],
        "pieces_reperees": detected,
        "controles": checks["proposed"],
        "alertes": created,
        "preuves": len(references),
        "constat": f"{extraction['proposed']} information(s) proposée(s), {detected} pièce(s) "
        f"repérée(s), {checks['proposed']} contrôle(s) calculé(s), {created} alerte(s) et "
        f"{len(references)} preuve(s) citables enregistrées.",
    }


def _regulatory(session: Session, job: AnalysisJob) -> dict:
    from app.services import facts_service, regulatory_engine

    facts = facts_service.build_facts(session, job.dossier_id)
    results = regulatory_engine.evaluate(facts)
    assessment_service.store_criteria(session, job.dossier_id, results, job_id=job.id)
    summary = regulatory_engine.summarize(results)
    job.referential_version = summary["referential_version"]
    job.validations_done += len(results)
    session.commit()
    return {
        "criteres": summary["total"],
        "counts": summary["counts"],
        "bloquants": [issue["code"] for issue in summary["blocking_issues"]],
        "constat": f"{summary['total']} critères appliqués : {summary['counts']['C']} C, "
        f"{summary['counts']['PC']} PC, {summary['counts']['NC']} NC, "
        f"{summary['counts']['NV']} NV.",
    }


def _scoring(session: Session, job: AnalysisJob) -> dict:
    from app.services import facts_service, scientific_scoring

    facts = facts_service.build_facts(session, job.dossier_id, rebuild_evidence=False)
    score = scientific_scoring.score(facts)
    assessment_service.store_score(session, job.dossier_id, score, job_id=job.id)
    job.grid_version = score.grid_version
    session.commit()
    undocumented = [sub.key for sub in score.subscores if not sub.documented]
    return {
        "total": score.total,
        "maximum": score.maximum,
        "grid_version": score.grid_version,
        "non_documentes": undocumented,
        "constat": f"Score scientifique proposé : {score.total}/{score.maximum} "
        f"({len(undocumented)} sous-critère(s) non documenté(s), notés zéro).",
    }


def _web_research(session: Session, job: AnalysisJob) -> dict:
    from app.web_research import service as web_service

    run = web_service.prepare_run(
        session,
        job.dossier_id,
        scope_note="Campagne préparée pendant le traitement automatique du dossier.",
    )
    job.searches_done = len(run.queries)
    session.commit()
    return {
        "run_id": run.id,
        "requetes": len(run.queries),
        "constat": f"{len(run.queries)} requête(s) publique(s) préparée(s), en attente de votre "
        "relecture. Aucune n'a été envoyée : rien ne quitte le poste sans votre approbation.",
    }


def _independent_audit(session: Session, job: AnalysisJob) -> dict:
    from app.services import audit_service

    report = audit_service.review(session, job.dossier_id, job_id=job.id)
    job.validations_done += report["checked"]
    session.commit()
    return report


def _decision(session: Session, job: AnalysisJob) -> dict:
    from app.services import audit_service, decision_engine, facts_service, regulatory_engine

    facts = facts_service.build_facts(session, job.dossier_id, rebuild_evidence=False)
    results = regulatory_engine.evaluate(facts)
    score_row = assessment_service.current_assessment(session, job.dossier_id)["score"]
    total = score_row["total"] if score_row else None
    decision = decision_engine.propose(
        results,
        scientific_total=total,
        findings=facts.findings,
        unresolved_disagreements=audit_service.unresolved(session, job.dossier_id),
    )
    assessment_service.store_decision(
        session, job.dossier_id, decision, scientific_total=total, job_id=job.id
    )
    session.commit()
    return {
        "avis": decision.avis,
        "regles": [rule.rule for rule in decision.triggered_rules],
        "constat": f"Avis technique proposé : {decision.label}. {decision.disclaimer}",
    }


def _report_qa(session: Session, job: AnalysisJob) -> dict:
    from app.services import report_qa_service

    result = report_qa_service.run(session, job.dossier_id, job_id=job.id)
    dossier = session.get(Dossier, job.dossier_id)
    if dossier is not None and dossier.status in {
        DossierStatus.NOUVEAU,
        DossierStatus.ANALYSE_EN_COURS,
    }:
        dossier.status = DossierStatus.A_CONTROLER
    session.commit()
    return result


STEPS: dict[str, Step] = {
    JobState.VALIDATING: Step(signature=_document_signature, run=_validate),
    JobState.EXTRACTING: Step(signature=_document_signature, run=_extract),
    JobState.OCR: Step(signature=_document_signature, run=_ocr),
    JobState.STRUCTURING: Step(signature=_text_signature, run=_structure),
    JobState.REGULATORY_CHECK: Step(signature=_values_signature, run=_regulatory),
    JobState.SCIENTIFIC_SCORING: Step(signature=_values_signature, run=_scoring),
    JobState.WEB_RESEARCH: Step(signature=_values_signature, run=_web_research),
    JobState.INDEPENDENT_AUDIT: Step(signature=_values_signature, run=_independent_audit),
    JobState.REPORT_BUILDING: Step(signature=_values_signature, run=_decision),
    JobState.REPORT_QA: Step(signature=_values_signature, run=_report_qa),
}
