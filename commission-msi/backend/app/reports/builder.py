"""Construction du rapport personnel (18 sections).

Chaque contenu porte une étiquette : `FAIT_EXTRAIT`, `CALCUL`, `ALERTE_SYSTEME`,
`COMMENTAIRE_EVALUATEUR`, `CONCLUSION_EVALUATEUR` ou `A_VERIFIER`. Un fait doit
être relié à une page ou déclaré comme saisie manuelle validée : sinon il est
exclu de la synthèse factuelle et signalé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DRAFT_BANNER, SIGNATURE, get_settings
from app.core.vocabulary import (
    ControlStatus,
    FindingStatus,
    InformationStatus,
    PieceStatus,
    ReportFactKind,
    DISPLAYED_LIMITS,
)
from app.models import Dossier, ExtractedItem, PieceCheck
from app.services import dossier_service, evaluation_service

PERSONAL_PROPOSAL_NOTICE = (
    "Proposition personnelle de l'évaluateur — ne vaut pas décision de la commission."
)
MAROC_SECTION_TITLE = "Mentions relatives au Maroc — vérification institutionnelle obligatoire"


@dataclass
class Line:
    kind: str
    text: str
    page_no: int | None = None
    manual_validated: bool = False

    @property
    def source_label(self) -> str:
        if self.page_no is not None:
            return f"page {self.page_no}"
        if self.manual_validated:
            return "saisie manuelle validée"
        return "sans source"


@dataclass
class Section:
    number: int
    title: str
    lines: list[Line] = field(default_factory=list)

    def add(self, kind: str, text: str, page_no: int | None = None, manual: bool = False) -> None:
        self.lines.append(Line(kind=kind, text=text, page_no=page_no, manual_validated=manual))


@dataclass
class ReportModel:
    dossier_reference: str
    dossier_title: str
    organizer: str
    evaluator: str
    generated_at: datetime
    version: str
    is_draft: bool
    sections: list[Section]
    orphan_facts: list[str]
    signature: str = SIGNATURE

    @property
    def banner(self) -> str:
        return DRAFT_BANNER


def build_report_model(session: Session, dossier_id: str) -> ReportModel:
    settings = get_settings()
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise ValueError("Dossier introuvable.")

    pages = dossier_service.dossier_pages(session, dossier_id)
    items = session.scalars(
        select(ExtractedItem).where(ExtractedItem.dossier_id == dossier_id).order_by(ExtractedItem.key)
    ).all()
    pieces = session.scalars(
        select(PieceCheck).where(PieceCheck.dossier_id == dossier_id).order_by(PieceCheck.label)
    ).all()
    findings = evaluation_service.findings_view(session, dossier_id)
    checks = evaluation_service.administrative_view(session, dossier_id)
    evaluation = evaluation_service.evaluation_state(session, dossier_id)
    conclusion = evaluation_service.current_conclusion(session, dossier_id)
    notes = evaluation_service.notes_view(session, dossier_id)
    gates = evaluation_service.gates_state(session, dossier_id)

    orphan_facts: list[str] = []
    sections: list[Section] = []

    # 1 — Identification -----------------------------------------------------
    section = Section(1, "Identification du dossier")
    section.add(ReportFactKind.FAIT_EXTRAIT, f"Référence : {dossier.reference}", manual=True)
    section.add(ReportFactKind.FAIT_EXTRAIT, f"Intitulé : {dossier.title}", manual=True)
    section.add(ReportFactKind.FAIT_EXTRAIT, f"Organisateur : {dossier.organizer}", manual=True)
    section.add(ReportFactKind.FAIT_EXTRAIT, f"État du dossier : {dossier.status}", manual=True)
    if dossier.sha256:
        section.add(
            ReportFactKind.FAIT_EXTRAIT,
            f"Empreinte SHA-256 du PDF original : {dossier.sha256}",
            manual=True,
        )
    section.add(ReportFactKind.CALCUL, f"Nombre de pages analysées : {len(pages)}")
    sections.append(section)

    # 2 — Synthèse factuelle -------------------------------------------------
    section = Section(2, "Synthèse factuelle")
    retained = 0
    for item in items:
        view = dossier_service.item_view(item)
        if view["status"] not in {InformationStatus.CONFIRME, InformationStatus.CORRIGE}:
            continue
        if view["page_no"] is None and not view["manual_entry_validated"]:
            orphan_facts.append(view["label"])
            continue
        section.add(
            ReportFactKind.FAIT_EXTRAIT,
            f"{view['label']} : {view['current_value']}",
            page_no=view["page_no"],
            manual=view["manual_entry_validated"],
        )
        retained += 1
    if retained == 0:
        section.add(
            ReportFactKind.A_VERIFIER,
            "Aucune information n'a encore été confirmée avec sa source. "
            "La synthèse factuelle est vide : cela ne signifie pas que le dossier est incomplet.",
        )
    sections.append(section)

    # 3 — Inventaire des pièces ---------------------------------------------
    section = Section(3, "Inventaire des pièces")
    for piece in pieces:
        kind = (
            ReportFactKind.FAIT_EXTRAIT
            if piece.status == PieceStatus.CONFIRMEE
            else ReportFactKind.A_VERIFIER
        )
        section.add(kind, f"{piece.label} : {piece.status}", page_no=piece.detected_page_no)
    section.add(
        ReportFactKind.A_VERIFIER,
        "La détection d'un titre ne vaut jamais confirmation de la validité juridique d'une pièce.",
    )
    sections.append(section)

    # 4 — Pages illisibles ou incertaines -----------------------------------
    section = Section(4, "Pages illisibles ou incertaines")
    uncertain = [
        page
        for page in pages
        if page.needs_ocr
        or page.is_difficult
        or (page.confidence is not None and page.confidence * 100 < settings.ocr_low_confidence)
    ]
    if not uncertain:
        section.add(ReportFactKind.CALCUL, "Aucune page marquée illisible ou incertaine.")
        section.add(
            ReportFactKind.A_VERIFIER,
            "L'absence de page signalée ne garantit pas l'exactitude de l'extraction.",
        )
    for page in uncertain:
        detail = f"confiance {round(page.confidence * 100, 1)} %" if page.confidence else "non extraite"
        section.add(
            ReportFactKind.A_VERIFIER,
            f"Page {page.page_no} — {detail}"
            + (" — doublon probable" if page.duplicate_of else ""),
            page_no=page.page_no,
        )
    sections.append(section)

    # 5 — Informations manquantes -------------------------------------------
    section = Section(5, "Informations manquantes")
    missing = [item for item in items if item.status == InformationStatus.A_VERIFIER]
    if not missing:
        section.add(ReportFactKind.CALCUL, "Toutes les informations attendues ont été qualifiées.")
    for item in missing:
        section.add(ReportFactKind.A_VERIFIER, f"{item.label} : non renseignée ou non vérifiée.")
    sections.append(section)

    # 6 — Incohérences -------------------------------------------------------
    section = Section(6, "Incohérences relevées")
    incoherent = [check for check in checks if check["status"] == ControlStatus.INCOHERENT]
    if not incoherent:
        section.add(ReportFactKind.CALCUL, "Aucune incohérence qualifiée par l'évaluateur.")
    for check in incoherent:
        section.add(
            ReportFactKind.COMMENTAIRE_EVALUATEUR,
            f"{check['label']} : {check['explanation'] or 'sans explication'}",
            page_no=check["page_no"],
        )
    sections.append(section)

    # 7 — Contrôle administratif --------------------------------------------
    section = Section(7, "Contrôle administratif")
    for check in checks:
        kind = (
            ReportFactKind.COMMENTAIRE_EVALUATEUR
            if check["status"] != ControlStatus.A_VERIFIER
            else ReportFactKind.A_VERIFIER
        )
        section.add(kind, f"{check['label']} : {check['status']}", page_no=check["page_no"])
    sections.append(section)

    # 8 — Éligibilité internationale ----------------------------------------
    section = Section(8, "Éligibilité internationale à apprécier")
    section.add(
        ReportFactKind.A_VERIFIER,
        "L'application ne qualifie pas le caractère international du dossier : "
        "la qualification du champ doit être demandée, sourcée et conservée.",
    )
    section.add(
        ReportFactKind.COMMENTAIRE_EVALUATEUR,
        f"Champ international déclaré : "
        f"{'oui' if dossier.international_scope_declared else 'non renseigné'}",
    )
    sections.append(section)

    # 9 — Grille scientifique ------------------------------------------------
    section = Section(9, "Grille scientifique saisie")
    for row in evaluation["criteria"]:
        if row["score"] is None:
            section.add(ReportFactKind.A_VERIFIER, f"{row['label']} : note non saisie (max {row['max']}).")
        else:
            source = ", ".join(str(page) for page in row["source_pages"]) or "aucune page citée"
            section.add(
                ReportFactKind.COMMENTAIRE_EVALUATEUR,
                f"{row['label']} : {row['score']}/{row['max']} — {row['justification']} (pages : {source})",
            )
    if evaluation["complete"]:
        section.add(
            ReportFactKind.CALCUL,
            f"Total (somme des notes saisies) : {evaluation['total']}/{evaluation['max_total']}.",
        )
    else:
        section.add(ReportFactKind.A_VERIFIER, evaluation["notice"])
    sections.append(section)

    # 10 — Conformité réglementaire -----------------------------------------
    section = Section(10, "Conformité réglementaire à vérifier")
    section.add(
        ReportFactKind.A_VERIFIER,
        "Aucune conformité n'est établie automatiquement : les règles normatives restent "
        "inactives tant que leur source officielle n'est pas présente, validée et non contredite.",
    )
    for name, state in gates.items():
        section.add(
            ReportFactKind.CALCUL if state["satisfied"] else ReportFactKind.A_VERIFIER,
            f"{name} : {state['message']}",
        )
    sections.append(section)

    # 11 — Risques institutionnels ------------------------------------------
    section = Section(11, "Risques institutionnels")
    institutional = [
        finding
        for finding in findings
        if finding["category"]
        in {
            "INTEGRITE_TERRITORIALE",
            "RELATIONS_DIPLOMATIQUES",
            "COMMUNICATION_INSTITUTIONNELLE",
            "CARTES_SYMBOLES",
            "MEMOIRE_NATIONALE",
        }
    ]
    if not institutional:
        section.add(ReportFactKind.CALCUL, "Aucune alerte institutionnelle détectée par le moteur textuel.")
        section.add(
            ReportFactKind.A_VERIFIER,
            "L'absence d'alerte ne prouve pas l'absence de risque : cartes, drapeaux, logos, "
            "tampons et signatures ne sont pas analysés.",
        )
    for finding in institutional:
        section.add(
            ReportFactKind.ALERTE_SYSTEME,
            f"[{finding['priority']}] {finding['label']} — déclencheur « {finding['trigger']} » "
            f"— statut humain : {finding['human_status']}",
            page_no=finding["page_no"],
        )
    sections.append(section)

    # 12 — Mentions relatives au Maroc --------------------------------------
    section = Section(12, MAROC_SECTION_TITLE)
    maroc = [finding for finding in findings if finding["category"] == "MENTIONS_MAROC"]
    section.add(
        ReportFactKind.A_VERIFIER,
        "Point de vigilance institutionnelle — vérifier les instructions officielles applicables "
        "à la session avant toute conclusion. Une ville, un domaine, un indicatif ou une "
        "nationalité ne suffit jamais à établir une collaboration, et ne produit jamais d'avis "
        "défavorable.",
    )
    if not maroc:
        section.add(ReportFactKind.CALCUL, "Aucune mention détectée par le moteur textuel.")
    for finding in maroc:
        relation = finding["relation_kind"] or "relation non qualifiée"
        section.add(
            ReportFactKind.ALERTE_SYSTEME,
            f"Déclencheur « {finding['trigger']} » — {relation} — statut humain : "
            f"{finding['human_status']} — contexte : {finding['context']}",
            page_no=finding["page_no"],
        )
    sections.append(section)

    # 13 — Autres points sensibles ------------------------------------------
    section = Section(13, "Autres points sensibles")
    others = [
        finding
        for finding in findings
        if finding["category"]
        not in {
            "MENTIONS_MAROC",
            "INTEGRITE_TERRITORIALE",
            "RELATIONS_DIPLOMATIQUES",
            "COMMUNICATION_INSTITUTIONNELLE",
            "CARTES_SYMBOLES",
            "MEMOIRE_NATIONALE",
        }
    ]
    if not others:
        section.add(ReportFactKind.CALCUL, "Aucun autre point sensible détecté par le moteur textuel.")
    for finding in others:
        section.add(
            ReportFactKind.ALERTE_SYSTEME,
            f"[{finding['priority']}] {finding['category']} — {finding['label']} — "
            f"statut humain : {finding['human_status']}",
            page_no=finding["page_no"],
        )
    sections.append(section)

    # 14 — Questions à la commission ----------------------------------------
    section = Section(14, "Questions à la commission")
    questions = [note for note in notes if note["kind"] == "QUESTION"]
    if not questions:
        section.add(ReportFactKind.A_VERIFIER, "Aucune question enregistrée.")
    for note in questions:
        section.add(ReportFactKind.COMMENTAIRE_EVALUATEUR, note["body"], page_no=note["page_no"])
    sections.append(section)

    # 15 — Réserves ----------------------------------------------------------
    section = Section(15, "Réserves")
    reserves = [note for note in notes if note["kind"] == "RESERVE"]
    if not reserves:
        section.add(ReportFactKind.A_VERIFIER, "Aucune réserve enregistrée.")
    for note in reserves:
        section.add(ReportFactKind.COMMENTAIRE_EVALUATEUR, note["body"], page_no=note["page_no"])
    sections.append(section)

    # 16 — Conclusion personnelle -------------------------------------------
    section = Section(16, "Conclusion personnelle motivée")
    section.add(ReportFactKind.CONCLUSION_EVALUATEUR, PERSONAL_PROPOSAL_NOTICE)
    if conclusion is None:
        section.add(
            ReportFactKind.A_VERIFIER,
            "Aucune conclusion n'a été choisie par l'évaluateur. Le système n'en propose aucune.",
        )
    else:
        from app.core.crypto import decrypt_text
        from app.core.keyring import get_master_key

        body = decrypt_text(
            get_master_key(), conclusion.body_cipher, evaluation_service.note_aad(conclusion.id)
        )
        section.add(ReportFactKind.CONCLUSION_EVALUATEUR, f"{conclusion.conclusion} — {body}")
    sections.append(section)

    # 17 — Références aux pages ---------------------------------------------
    section = Section(17, "Références aux pages")
    referenced = sorted(
        {line.page_no for current in sections for line in current.lines if line.page_no is not None}
    )
    section.add(
        ReportFactKind.CALCUL,
        "Pages citées dans ce rapport : "
        + (", ".join(str(page) for page in referenced) if referenced else "aucune"),
    )
    if orphan_facts:
        section.add(
            ReportFactKind.A_VERIFIER,
            "Faits exclus de la synthèse car sans page ni saisie manuelle validée : "
            + ", ".join(orphan_facts),
        )
    sections.append(section)

    # 18 — Identité, version, limites ---------------------------------------
    section = Section(18, "Identité de l'évaluateur, version et limites")
    section.add(ReportFactKind.COMMENTAIRE_EVALUATEUR, f"Évaluateur : {settings.evaluator_label}")
    section.add(ReportFactKind.CALCUL, f"Version de l'application : {settings.version}")
    for limit in DISPLAYED_LIMITS:
        section.add(ReportFactKind.A_VERIFIER, limit)
    section.add(ReportFactKind.COMMENTAIRE_EVALUATEUR, SIGNATURE)
    sections.append(section)

    # 19 — Classement externe indicatif (module en ligne, non décisionnel) -----
    sections.append(_ranking_section(session, dossier_id))

    return ReportModel(
        dossier_reference=dossier.reference,
        dossier_title=dossier.title,
        organizer=dossier.organizer,
        evaluator=settings.evaluator_label,
        generated_at=datetime.now(timezone.utc),
        version=settings.version,
        is_draft=dossier.report_validated_at is None,
        sections=sections,
        orphan_facts=orphan_facts,
    )


def _ranking_section(session: Session, dossier_id: str) -> Section:
    """Section dédiée au classement externe, portant le titre imposé.

    Le classement est indicatif : il n'est jamais présenté comme une décision,
    et il ne modifie jamais la grille scientifique officielle (section 9).
    """
    from app.core.vocabulary import NOT_PROVIDED, RANKING_TITLE
    from app.ranking import service as ranking_service
    from app.web_research import service as web_service

    section = Section(19, RANKING_TITLE)
    section.add(
        ReportFactKind.A_VERIFIER,
        "Ce classement provient d'agents connectés à Internet. Il est indicatif, non homologué, "
        "et ne peut jamais motiver à lui seul une acceptation, un rejet, une interdiction ou une "
        "transmission. Il ne modifie aucune note de la grille scientifique officielle.",
    )

    enriched = web_service.enriched_analysis_state(session, dossier_id)
    section.add(
        ReportFactKind.CALCUL if enriched["complete"] else ReportFactKind.A_VERIFIER,
        f"État de l'analyse enrichie : {enriched['reason']}",
    )

    view = ranking_service.ranking_view(session, dossier_id)
    if view is None:
        section.add(
            ReportFactKind.A_VERIFIER,
            "Aucun classement externe n'a été calculé pour ce dossier.",
        )
        return section

    if view["blocked_reason"]:
        section.add(ReportFactKind.ALERTE_SYSTEME, f"Classement bloqué : {view['blocked_reason']}")
    section.add(
        ReportFactKind.CALCUL,
        f"Classement : {view['grade']} — total indicatif "
        f"{view['total'] if view['total'] is not None else NOT_PROVIDED}/100 — "
        f"niveau d'accord des agents : {view['agreement_level'] if view['agreement_level'] is not None else NOT_PROVIDED}.",
    )
    for axis in view["axes"]:
        value = NOT_PROVIDED if axis["not_provided"] else f"{axis['proposed_score']}/{axis['max']}"
        decision = f" — décision de l'évaluateur : {axis['human_decision']}"
        section.add(
            ReportFactKind.ALERTE_SYSTEME,
            f"{axis['label']} : {value}{decision} — {axis['justification']} "
            f"({len(axis['sources'])} source(s) publique(s))",
        )
    for item in view["disagreements"]:
        section.add(ReportFactKind.ALERTE_SYSTEME, f"Désaccord : {item['description']}")
    section.add(
        ReportFactKind.CALCUL,
        f"Versions des agents : {view['agents_versions']} — calculé le "
        f"{view['created_at'].strftime('%Y-%m-%d %H:%M UTC') if view['created_at'] else 'date inconnue'}.",
    )
    return section


def unqualified_findings(findings: list[dict]) -> list[dict]:
    return [finding for finding in findings if finding["human_status"] == FindingStatus.A_VERIFIER]
