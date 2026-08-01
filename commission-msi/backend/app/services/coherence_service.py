"""Contrôles administratifs calculés automatiquement.

Seuls des constats **objectifs et recalculables** sont produits : comparaison
de dates, arithmétique d'un budget, dénombrement de pays, présence d'une pièce.
Chaque constat affiche les deux valeurs comparées et la méthode employée, de
sorte que l'évaluateur puisse le refaire à la main.

Aucun constat n'est confirmé automatiquement : le statut proposé accompagne
toujours la mention « proposition de l'analyse — à confirmer ». L'évaluateur
peut l'accepter, corriger ou écarter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.core.config import get_settings
from app.core.crypto import encrypt_text
from app.core.keyring import get_master_key
from app.core.vocabulary import ControlStatus, PieceStatus
from app.models import AdministrativeCheck, PieceCheck
from app.services import dossier_service, evaluation_service, extraction_service

#: Préfixe systématique : un constat calculé n'est jamais une décision.
PROPOSAL_PREFIX = "Proposition de l'analyse — à confirmer par l'évaluateur."


@dataclass
class Proposal:
    check_key: str
    status: str
    explanation: str
    page_no: int | None = None
    comparison: dict | None = None


def _parse(value: str) -> date | None:
    try:
        day, month, year = (int(part) for part in value.split("/"))
        return date(year, month, day)
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------
# Contrôles individuels
# --------------------------------------------------------------------------


def _check_dates(observations: dict) -> Proposal | None:
    entries = observations.get("dates") or []
    parsed = [(entry, _parse(entry["value"])) for entry in entries]
    parsed = [(entry, value) for entry, value in parsed if value is not None]
    if len(parsed) < 2:
        return None

    # Regroupe par page : des dates d'événement divergentes entre pages sont
    # le signal d'incohérence le plus fréquent dans ces dossiers.
    by_page: dict[int, set[str]] = {}
    for entry, _ in parsed:
        by_page.setdefault(entry["page"], set()).add(entry["value"])

    distinct = {entry["value"] for entry, _ in parsed}
    if len(distinct) <= 1:
        return Proposal(
            check_key="coherence_dates",
            status=ControlStatus.CONFIRME,
            explanation=(
                f"{PROPOSAL_PREFIX} Une seule date est présente dans le document "
                f"({next(iter(distinct))}) : aucune divergence n'est calculable."
            ),
            comparison={"dates": sorted(distinct)},
        )

    pages_with_multiple = {page: sorted(values) for page, values in by_page.items() if len(values) > 1}
    values = sorted(distinct)
    spread_days = (max(v for _, v in parsed) - min(v for _, v in parsed)).days

    if spread_days > 30 and len(by_page) > 1:
        return Proposal(
            check_key="coherence_dates",
            status=ControlStatus.INCOHERENT,
            explanation=(
                f"{PROPOSAL_PREFIX} Des dates divergentes figurent dans le document : "
                + ", ".join(f"page {page} → {', '.join(sorted(vals))}" for page, vals in sorted(by_page.items()))
                + f". Écart maximal calculé : {spread_days} jours. Méthode : comparaison de "
                "toutes les dates reconnues, sans interprétation de leur rôle."
            ),
            page_no=min(by_page),
            comparison={"par_page": {str(k): sorted(v) for k, v in by_page.items()}, "ecart_jours": spread_days},
        )

    return Proposal(
        check_key="coherence_dates",
        status=ControlStatus.A_VERIFIER,
        explanation=(
            f"{PROPOSAL_PREFIX} {len(values)} dates distinctes ont été reconnues "
            f"({', '.join(values[:8])}). L'analyse ne peut pas déterminer laquelle correspond à "
            "la manifestation, au dépôt ou aux annexes : vérification humaine nécessaire."
        ),
        comparison={"dates": values, "pages_multi": pages_with_multiple},
    )


def _check_budget(observations: dict) -> Proposal | None:
    amounts = observations.get("amounts") or []
    if not amounts:
        return None

    totals = [item for item in amounts if item["is_total"]]
    others = [item for item in amounts if not item["is_total"]]
    if not totals or not others:
        return Proposal(
            check_key="budget_totaux_devise",
            status=ControlStatus.INCOMPLET,
            explanation=(
                f"{PROPOSAL_PREFIX} {len(amounts)} montant(s) détecté(s) mais la structure "
                "budgétaire (total et sous-totaux distincts) n'est pas identifiable "
                "automatiquement : le contrôle arithmétique n'a pas pu être effectué."
            ),
            page_no=amounts[0]["page"],
            comparison={"montants": [f"{a['value']} {a['currency']}" for a in amounts[:15]]},
        )

    currencies = {item["currency"] for item in amounts}
    total = totals[0]
    same_currency = [item for item in others if item["currency"] == total["currency"]]
    subtotal_sum = sum(item["value"] for item in same_currency)

    if len(currencies) > 1:
        status = ControlStatus.A_VERIFIER
        detail = (
            f"Plusieurs devises coexistent ({', '.join(sorted(currencies))}) : "
            "aucune conversion n'est effectuée et la somme n'est pas comparable."
        )
    elif subtotal_sum == total["value"]:
        status = ControlStatus.CONFIRME
        detail = (
            f"Somme des {len(same_currency)} montant(s) hors total = {subtotal_sum} "
            f"{total['currency']}, égale au total déclaré ({total['value']} {total['currency']})."
        )
    else:
        status = ControlStatus.INCOHERENT
        detail = (
            f"Total déclaré : {total['value']} {total['currency']}. Somme des "
            f"{len(same_currency)} autre(s) montant(s) : {subtotal_sum} {total['currency']}. "
            f"Écart : {abs(subtotal_sum - total['value'])} {total['currency']}. "
            "Méthode : addition de tous les montants détectés hors mention « total »."
        )

    return Proposal(
        check_key="budget_totaux_devise",
        status=status,
        explanation=f"{PROPOSAL_PREFIX} {detail}",
        page_no=total["page"],
        comparison={
            "total_declare": f"{total['value']} {total['currency']}",
            "somme_calculee": f"{subtotal_sum} {total['currency']}",
            "devises": sorted(currencies),
            "montants": [f"{a['value']} {a['currency']} (p. {a['page']})" for a in amounts[:20]],
        },
    )


def _check_countries(observations: dict) -> Proposal | None:
    declared = observations.get("declared_country_counts") or []
    found = observations.get("countries") or []
    if not declared and not found:
        return None

    if not declared:
        return Proposal(
            check_key="pays_annonces_vs_liste",
            status=ControlStatus.INCOMPLET,
            explanation=(
                f"{PROPOSAL_PREFIX} {len(found)} pays sont reconnus dans le texte "
                f"({', '.join(found[:12])}), mais aucun nombre de pays n'est annoncé "
                "explicitement : la comparaison n'est pas possible."
            ),
            comparison={"pays_reconnus": found},
        )

    announced = max(item["count"] for item in declared)
    if announced > len(found):
        status = ControlStatus.INCOHERENT
        detail = (
            f"{announced} pays sont annoncés, mais seulement {len(found)} sont nommément "
            f"identifiables dans le document ({', '.join(found) or 'aucun'})."
        )
    elif announced == len(found):
        status = ControlStatus.CONFIRME
        detail = f"{announced} pays annoncés et {len(found)} pays nommément identifiés : concordance."
    else:
        status = ControlStatus.A_VERIFIER
        detail = (
            f"{announced} pays annoncés mais {len(found)} noms de pays reconnus : "
            "des pays cités peuvent relever de références bibliographiques."
        )

    return Proposal(
        check_key="pays_annonces_vs_liste",
        status=status,
        explanation=f"{PROPOSAL_PREFIX} {detail} Méthode : dénombrement des noms de pays reconnus.",
        page_no=declared[0]["page"],
        comparison={"annonce": announced, "identifies": len(found), "pays": found},
    )


def _check_regulations(observations: dict, pages: dict[int, str]) -> Proposal:
    from app.services.extraction_service import REGULATION_REF

    refs: list[str] = []
    page_ref: int | None = None
    for page_no in sorted(pages):
        for match in REGULATION_REF.finditer(pages[page_no]):
            ref = " ".join(match.group(0).split())
            if ref not in refs:
                refs.append(ref)
                page_ref = page_ref or page_no

    if refs:
        return Proposal(
            check_key="references_reglementaires",
            status=ControlStatus.A_VERIFIER,
            explanation=(
                f"{PROPOSAL_PREFIX} {len(refs)} référence(s) réglementaire(s) citée(s) : "
                + " ; ".join(refs[:8])
                + ". L'application ne vérifie ni leur existence ni leur portée : chacune doit "
                "être confrontée au texte officiel avant tout usage."
            ),
            page_no=page_ref,
            comparison={"references": refs},
        )
    return Proposal(
        check_key="references_reglementaires",
        status=ControlStatus.INCOMPLET,
        explanation=(
            f"{PROPOSAL_PREFIX} Aucune référence réglementaire (loi, décret, arrêté, envoi, "
            "circulaire) n'a été reconnue dans le texte extrait."
        ),
    )


def _check_pieces(session: Session, dossier_id: str) -> Proposal:
    pieces = session.scalars(select(PieceCheck).where(PieceCheck.dossier_id == dossier_id)).all()
    absent = [piece.label for piece in pieces if piece.status == PieceStatus.ABSENTE]
    detected = [piece.label for piece in pieces if piece.status == PieceStatus.DETECTEE]

    if absent:
        return Proposal(
            check_key="pieces_obligatoires",
            status=ControlStatus.INCOMPLET,
            explanation=(
                f"{PROPOSAL_PREFIX} {len(detected)} pièce(s) repérée(s) dans le texte et "
                f"{len(absent)} non repérée(s). Non repérées : "
                + " ; ".join(absent[:12])
                + (" …" if len(absent) > 12 else "")
                + ". Une pièce non repérée textuellement peut être présente sous une autre "
                "formulation ou en image : vérification humaine obligatoire."
            ),
            comparison={"detectees": detected, "non_reperees": absent},
        )
    return Proposal(
        check_key="pieces_obligatoires",
        status=ControlStatus.A_VERIFIER,
        explanation=(
            f"{PROPOSAL_PREFIX} Toutes les pièces du catalogue ont été repérées textuellement. "
            "Le repérage d'un titre ne vaut jamais confirmation de la validité de la pièce."
        ),
        comparison={"detectees": detected},
    )


def _check_readability(session: Session, dossier_id: str) -> Proposal | None:
    pages = dossier_service.dossier_pages(session, dossier_id)
    if not pages:
        return None
    unreadable = [page.page_no for page in pages if page.needs_ocr and not page.is_blank]
    if not unreadable:
        return None
    return Proposal(
        check_key="expiration_documents",
        status=ControlStatus.ILLISIBLE,
        explanation=(
            f"{PROPOSAL_PREFIX} {len(unreadable)} page(s) n'ont pas de texte exploitable "
            f"(pages {', '.join(str(p) for p in unreadable)}). Les contrôles automatiques ne "
            "portent pas sur ces pages : leur contenu doit être lu manuellement ou océrisé."
        ),
        page_no=unreadable[0],
        comparison={"pages_non_extraites": unreadable},
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def run_automatic_checks(session: Session, dossier_id: str) -> dict:
    """Calcule les constats objectifs et les propose à la confirmation humaine."""
    settings = get_settings()
    key = get_master_key()
    pages = dossier_service.dossier_page_texts(session, dossier_id)
    report = extraction_service.analyze_text(pages)
    observations = report.observations

    proposals = [
        _check_dates(observations),
        _check_budget(observations),
        _check_countries(observations),
        _check_regulations(observations, pages),
        _check_pieces(session, dossier_id),
        _check_readability(session, dossier_id),
    ]
    proposals = [proposal for proposal in proposals if proposal is not None]

    checks = {
        check.check_key: check
        for check in session.scalars(
            select(AdministrativeCheck).where(AdministrativeCheck.dossier_id == dossier_id)
        ).all()
    }

    applied, preserved = 0, 0
    for proposal in proposals:
        check = checks.get(proposal.check_key)
        if check is None:
            continue
        # Un contrôle déjà qualifié par l'évaluateur n'est jamais réécrit.
        if check.status != ControlStatus.A_VERIFIER and check.updated_by not in (
            None,
            "Analyse automatique",
        ):
            preserved += 1
            continue
        check.status = proposal.status
        check.explanation_cipher = encrypt_text(
            key, proposal.explanation, evaluation_service.check_aad(check.id)
        )
        check.page_no = proposal.page_no
        check.comparison_json = (
            json.dumps(proposal.comparison, ensure_ascii=False) if proposal.comparison else None
        )
        check.requires_human_confirmation = True
        check.updated_by = "Analyse automatique"
        applied += 1

    audit.record(
        session,
        audit.AuditAction.ADMIN_CHECK_UPDATE,
        f"Contrôles automatiques : {applied} constat(s) calculé(s) et proposé(s), "
        f"{preserved} qualification(s) humaine(s) préservée(s).",
        entity_type="dossier",
        entity_id=dossier_id,
        dossier_id=dossier_id,
        actor_label=settings.evaluator_label,
    )
    session.commit()

    return {
        "proposed": applied,
        "preserved": preserved,
        "checks": [
            {"check_key": proposal.check_key, "status": proposal.status, "explanation": proposal.explanation}
            for proposal in proposals
        ],
        "notice": (
            "Chaque constat est recalculable à la main : les deux valeurs comparées et la "
            "méthode sont affichées. Aucun constat ne vaut conformité ou non-conformité tant "
            "que l'évaluateur ne l'a pas confirmé."
        ),
    }
