"""Analyse complète en une opération.

Enchaîne, dans l'ordre, tout ce que l'application peut faire seule :

1. analyse structurelle et OCR des pages illisibles (si le moteur local existe) ;
2. extraction des informations structurées ;
3. repérage des pièces ;
4. contrôles administratifs calculés ;
5. moteur de vigilance déterministe ;
6. constitution du registre de preuves ;
7. application des 26 critères réglementaires (`C/PC/NC/NV`) ;
8. score scientifique proposé sur 100 ;
9. avis technique proposé, motivé et tracé ;
10. préparation des requêtes publiques pour l'analyse enrichie.

Depuis la version 2.0, l'application **propose** le score scientifique et
l'avis technique : ce sont des propositions motivées, rattachées à leurs
preuves, qui restent des aides à la décision. Les informations extraites
demeurent au statut `A_VERIFIER`, et la décision finale — confirmation des
informations, qualification des pièces et des alertes, note retenue, avis
retenu — appartient toujours à l'évaluateur.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core import audit
from app.core.vocabulary import DossierStatus
from app.models import Dossier
from app.services import (
    assessment_service,
    coherence_service,
    dossier_service,
    evidence_service,
    extraction_service,
    ocr_service,
)


def run_full_analysis(
    session: Session,
    dossier_id: str,
    *,
    run_ocr: bool = True,
    prepare_web: bool = True,
) -> dict:
    """Exécute la chaîne complète et retourne un compte rendu détaillé."""
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        from app.core.errors import NotFound

        raise NotFound("Dossier introuvable.")

    steps: list[dict] = []

    # 1. OCR des pages non extraites -------------------------------------
    ocr_done, ocr_failed = 0, 0
    ocr_message = "OCR non demandé."
    if run_ocr:
        if not ocr_service.is_available():
            ocr_message = (
                "Moteur OCR local indisponible : les pages scannées restent non extraites et "
                "explicitement marquées « vérification humaine obligatoire »."
            )
        else:
            pages = [
                page
                for page in dossier_service.dossier_pages(session, dossier_id)
                if page.needs_ocr and not page.is_blank
            ]
            for page in pages:
                try:
                    dossier_service.run_page_ocr(session, page.id)
                    ocr_done += 1
                except Exception:  # noqa: BLE001 - un échec OCR n'interrompt jamais la chaîne
                    ocr_failed += 1
            ocr_message = (
                f"{ocr_done} page(s) océrisée(s), {ocr_failed} échec(s)."
                if pages
                else "Aucune page ne nécessitait d'OCR : le texte natif était suffisant."
            )
    steps.append({"etape": "OCR local", "resultat": ocr_message, "traite": ocr_done, "echecs": ocr_failed})

    # 2. Extraction des informations --------------------------------------
    extraction = extraction_service.autofill_dossier(session, dossier_id)
    steps.append(
        {
            "etape": "Extraction des informations",
            "resultat": f"{extraction['proposed']} information(s) proposée(s) avec page et extrait "
            f"source ; {extraction['preserved']} champ(s) déjà qualifié(s) préservé(s).",
            "traite": extraction["proposed"],
            "echecs": 0,
        }
    )

    # 3. Repérage des pièces ----------------------------------------------
    detected = dossier_service.detect_pieces(session, dossier_id)
    steps.append(
        {
            "etape": "Repérage des pièces",
            "resultat": f"{detected} pièce(s) repérée(s) textuellement. Le repérage d'un titre ne "
            "vaut jamais confirmation de la validité de la pièce.",
            "traite": detected,
            "echecs": 0,
        }
    )

    # 4. Contrôles administratifs calculés --------------------------------
    checks = coherence_service.run_automatic_checks(session, dossier_id)
    steps.append(
        {
            "etape": "Contrôles administratifs",
            "resultat": f"{checks['proposed']} constat(s) calculé(s) et proposé(s) ; "
            f"{checks['preserved']} qualification(s) humaine(s) préservée(s).",
            "traite": checks["proposed"],
            "echecs": 0,
        }
    )

    # 5. Moteur de vigilance ----------------------------------------------
    created = dossier_service.run_vigilance(session, dossier_id)
    open_findings = dossier_service.open_findings_count(session, dossier_id)
    steps.append(
        {
            "etape": "Moteur de vigilance",
            "resultat": f"{created} nouvelle(s) alerte(s) ; {open_findings} au statut A_VERIFIER. "
            "L'absence d'alerte ne prouve pas l'absence de risque.",
            "traite": created,
            "echecs": 0,
        }
    )

    # 6-9. Évaluation automatique : preuves, 26 critères, score, avis --------
    assessment = assessment_service.assess(session, dossier_id)
    summary = assessment["summary"]
    counts = summary["counts"]
    steps.append(
        {
            "etape": "Registre de preuves",
            "resultat": f"{len(evidence_service.known_references(session, dossier_id))} preuve(s) "
            "citables enregistrées (pages, pièces, calculs). Toute affirmation du rapport "
            "renvoie à l'une d'elles.",
            "traite": len(evidence_service.known_references(session, dossier_id)),
            "echecs": 0,
        }
    )
    steps.append(
        {
            "etape": "Constats réglementaires",
            "resultat": f"{summary['total']} critères appliqués (référentiel "
            f"{summary['referential_version']}) : {counts['C']} conformes, {counts['PC']} "
            f"partiellement conformes, {counts['NC']} non conformes, {counts['NV']} non "
            "vérifiables. Aucune cellule n'est laissée vide.",
            "traite": summary["total"],
            "echecs": counts["NV"],
        }
    )
    score = assessment["score"]
    steps.append(
        {
            "etape": "Score scientifique",
            "resultat": f"{score['total']}/{score['maximum']} proposés (grille "
            f"{score['grid_version']}) ; {len(score['undocumented'])} sous-critère(s) non "
            "documenté(s) notés zéro, ce qui ne préjuge d'aucune incapacité de "
            "l'organisateur.",
            "traite": score["total"],
            "echecs": len(score["undocumented"]),
        }
    )
    decision = assessment["decision"]
    steps.append(
        {
            "etape": "Avis technique proposé",
            "resultat": f"{decision['label']} — {decision['motivation']} "
            f"{len(decision['triggered_rules'])} règle(s) de décision enregistrée(s) avec "
            "leurs critères déclencheurs.",
            "traite": len(decision["triggered_rules"]),
            "echecs": len(decision["blocking_criteria"]),
        }
    )

    # 10. Préparation de la recherche publique ------------------------------
    web_run_id = None
    web_message = "Préparation de la recherche publique non demandée."
    if prepare_web:
        from app.web_research import service as web_service

        run = web_service.prepare_run(
            session,
            dossier_id,
            scope_note="Campagne préparée automatiquement à partir des informations publiques du dossier.",
        )
        web_run_id = run.id
        queries = len(run.queries)
        web_message = (
            f"{queries} requête(s) publique(s) préparée(s), en attente de votre relecture. "
            "Aucune n'a été envoyée : rien ne quitte le poste sans votre approbation."
        )
    steps.append({"etape": "Recherche publique", "resultat": web_message, "traite": 0, "echecs": 0})

    if dossier.status in {DossierStatus.NOUVEAU, DossierStatus.ANALYSE_EN_COURS}:
        dossier.status = DossierStatus.A_CONTROLER

    audit.record(
        session,
        audit.AuditAction.DOCUMENT_ANALYZE,
        "Analyse complète exécutée : "
        + " | ".join(f"{step['etape']} → {step['traite']}" for step in steps),
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
    )
    session.commit()

    return {
        "dossier_id": dossier_id,
        "steps": steps,
        "web_run_id": web_run_id,
        "extraction_fields": extraction["fields"],
        "checks": checks["checks"],
        "assessment": assessment,
        "notice": (
            "L'analyse a proposé les valeurs, les constats réglementaires, le score "
            "scientifique et l'avis technique, tous rattachés à leurs preuves et à leur page "
            "source. Le score et l'avis sont des propositions motivées : ils constituent une "
            "aide à la décision et ne valent pas décision officielle de la commission ou de "
            "la tutelle. La note retenue et l'avis retenu vous appartiennent."
        ),
    }
