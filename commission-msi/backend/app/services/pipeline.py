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
import time
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.vocabulary import JOB_STATE_LABELS, DossierStatus, JobState
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


def _keepalive(session: Session, job: AnalysisJob, last: float) -> float:
    """Renouvelle le bail et relit la demande d'annulation, pendant une étape longue.

    Deux défauts sont corrigés ici, et ils ont la même cause : le battement
    n'était émis qu'**au début** de chaque étape.

    * **le bail expirait pendant le travail.** Il dure 120 secondes ; l'OCR d'un
      dossier de 76 pages en demande plusieurs centaines, et une lecture par
      modèle local davantage encore. `heartbeat_at` restait figé, si bien que
      rien ne distinguait un worker à l'ouvrage d'un worker mort — exactement la
      distinction que ce champ existe pour établir ;
    * **« Annuler » restait sans effet** jusqu'à la fin de l'étape en cours. Sur
      une lecture de quarante minutes, un bouton qui ne répond pas n'est pas un
      bouton.

    Le rythme suit `HEARTBEAT_SECONDS` : appeler la base à chaque page coûterait
    plus que ce que la fraîcheur rapporte.
    """
    from app.services import job_service

    now = time.monotonic()
    if now - last < job_service.HEARTBEAT_SECONDS:
        return last

    job_service.heartbeat(session, job)
    # `heartbeat` valide la transaction : la relecture voit alors la demande
    # d'annulation posée par l'interface dans une autre session.
    session.refresh(job)
    if job.cancel_requested:
        raise job_service.Cancelled()
    return now


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
    battement = time.monotonic()
    for page in pages:
        try:
            dossier_service.run_page_ocr(session, page.id)
            done += 1
        except Exception:  # noqa: BLE001 - un échec OCR n'interrompt jamais la chaîne
            failed += 1
        job.pages_done = min(job.pages_total, job.pages_done + 1)
        # Une page difficile demande plusieurs prétraitements : sans battement,
        # le bail expirerait bien avant la fin du dossier.
        battement = _keepalive(session, job, battement)
    return {
        "traitees": done,
        "echecs": failed,
        "constat": f"{done} page(s) océrisée(s), {failed} échec(s)."
        if pages
        else "Aucune page ne nécessitait d'OCR : le texte natif suffisait.",
    }


def _semantic_reading(session: Session, job: AnalysisJob) -> dict:
    """Lecture assistée du texte — n'a d'effet qu'en mode `HYBRID_STRICT`.

    Elle est placée **avant** la structuration, et pas après : la structuration
    calcule les contrôles, les alertes et le registre de preuves à partir des
    valeurs. Les produire avant que la lecture ait comblé les manques donnerait
    des contrôles portant sur un dossier à moitié vide.

    En `LOCAL_ONLY`, l'étape ne fait rien et l'écrit noir sur blanc. Elle ne
    bascule pas silencieusement vers une lecture dégradée : l'évaluateur doit
    pouvoir lire, dans le journal du traitement, que cette capacité n'était pas
    active.

    Une panne d'appel, elle, n'est pas absorbée : l'exception remonte, le
    travail devient reprenable, et les étapes déjà validées ne sont pas
    refaites. Absorber l'échec produirait un rapport d'apparence normale, bâti
    sur une lecture qui n'a pas eu lieu.
    """
    from app.services import ai_semantic_reading

    try:
        battement = time.monotonic()

        def _pendant_la_lecture(rang: int, total: int) -> None:
            # Chaque appel à un modèle local dure plusieurs minutes, et l'étape
            # entière peut durer des heures. Sans ce compteur, l'évaluateur n'a
            # aucun moyen de distinguer un traitement qui avance d'un traitement
            # bloqué — et c'est précisément la question qu'il se pose.
            nonlocal battement
            job.step_label = (
                f"{JOB_STATE_LABELS[JobState.SEMANTIC_READING]} — lot {rang}/{total}"
            )
            battement = _keepalive(session, job, battement)

        result = ai_semantic_reading.run(
            session, job.dossier_id, job_id=job.id, on_progress=_pendant_la_lecture
        )
    except ai_semantic_reading.NotAvailable as exc:
        return {
            "active": False,
            "motif": str(exc),
            "constat": "Lecture sémantique assistée inactive : "
            f"{exc}. Seules les détections déterministes locales ont été appliquées ; "
            "les informations rédigées en prose ou en tableau peuvent rester non "
            "extraites et sont alors signalées « non vérifiable ».",
        }

    job.model_id = result.get("model_id") or job.model_id
    job.validations_done += result["proposed"]
    return {
        "active": True,
        **result,
        "constat": f"{result['proposed']} information(s) lue(s) et proposée(s) au statut "
        f"A_VERIFIER, {result['rejected']} proposition(s) rejetée(s) faute d'extrait "
        f"vérifiable sur la page citée, {result['kept_local']} champ(s) déjà mieux établi(s) "
        f"conservé(s). {result['pages_transmises']} page(s) transmises en "
        f"{result['appels']} appel(s).",
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


def _render_report(session: Session, job: AnalysisJob) -> dict:
    """Produit le rapport harmonisé en Word et en PDF, sans second clic.

    Cette étape vient **après** le contrôle qualité, et l'ordre n'est pas
    arbitraire : un rapport dont un contrôle bloquant a échoué ne doit pas
    exister sous forme de fichier téléchargeable. Le travail échoue avant
    d'arriver ici.

    Les deux formats sont produits parce qu'ils ne servent pas au même usage :
    le Word se corrige et s'annote, le PDF se transmet et se compte en pages —
    ce comptage est d'ailleurs la seule mesure réelle du volume du rapport, et
    il est fait sur le fichier réellement écrit, jamais estimé.

    Le brouillon est filigrané. L'export officiel reste un acte humain distinct,
    soumis à la porte G7 : l'application produit le document, elle ne le valide
    pas à la place de l'évaluateur.
    """
    from app.services import report_service

    produced: list[dict] = []
    for fmt in ("docx", "pdf"):
        report = report_service.generate_report(
            session, job.dossier_id, fmt=fmt, layout=report_service.HARMONISE
        )
        produced.append(
            {
                "id": report.id,
                "format": fmt,
                "version": report.version,
                "sha256": report.sha256,
                "pages": report.page_count,
                "brouillon": report.is_draft,
            }
        )

    pages = next((item["pages"] for item in produced if item["pages"]), None)
    return {
        "rapports": produced,
        "constat": (
            "Rapport harmonisé produit en Word et en PDF"
            + (f", {pages} page(s) mesurées." if pages else ".")
            + " Brouillon filigrané : l'export officiel reste un acte humain distinct."
        ),
    }


STEPS: dict[str, Step] = {
    JobState.VALIDATING: Step(signature=_document_signature, run=_validate),
    JobState.EXTRACTING: Step(signature=_document_signature, run=_extract),
    JobState.OCR: Step(signature=_document_signature, run=_ocr),
    JobState.SEMANTIC_READING: Step(signature=_text_signature, run=_semantic_reading),
    JobState.STRUCTURING: Step(signature=_text_signature, run=_structure),
    JobState.REGULATORY_CHECK: Step(signature=_values_signature, run=_regulatory),
    JobState.SCIENTIFIC_SCORING: Step(signature=_values_signature, run=_scoring),
    JobState.WEB_RESEARCH: Step(signature=_values_signature, run=_web_research),
    JobState.INDEPENDENT_AUDIT: Step(signature=_values_signature, run=_independent_audit),
    JobState.REPORT_BUILDING: Step(signature=_values_signature, run=_decision),
    JobState.REPORT_QA: Step(signature=_values_signature, run=_report_qa),
    JobState.REPORT_RENDERING: Step(signature=_values_signature, run=_render_report),
}
