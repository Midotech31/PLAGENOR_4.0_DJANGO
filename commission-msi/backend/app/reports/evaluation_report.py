"""Rapport d'évaluation professionnel — structure des rapports de référence.

Ce module construit le rapport tel qu'un membre de commission le rédige :
encadré d'avis, fiche d'information, tableau de conformité, anomalies,
vérification des profils étrangers, points sensibles, conditions suspensives,
constat de veille publique, proposition à la commission et sources vérifiées.

Règle absolue de construction : **aucune cellule n'est inventée**. Toute
information provient d'une donnée réellement présente dans le dossier, d'une
qualification humaine ou d'une source publique effectivement consultée. En
l'absence de donnée, la mention `NON_RENSEIGNE` est écrite telle quelle et
jamais complétée par supposition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import DRAFT_BANNER, SIGNATURE, get_settings
from app.core.crypto import decrypt_text
from app.core.keyring import get_master_key
from app.core.vocabulary import (
    ControlStatus,
    EvidenceStatus,
    FindingStatus,
    InformationStatus,
    PieceStatus,
    ReportFactKind,
    DISPLAYED_LIMITS,
)
from app.models import (
    AdministrativeCheck,
    Dossier,
    ExtractedItem,
    OnlineClaim,
    PersonWebProfile,
    PieceCheck,
    Regulation,
    SourceDocument,
    WebSource,
)
from app.services import dossier_service, evaluation_service

#: Mention écrite lorsqu'une information n'est pas présente au dossier.
NOT_PROVIDED = "Non renseigné dans le dossier"

#: Encadré de veille publique — le texte de garantie est invariable.
PUBLIC_WATCH_CAVEAT = (
    "Cette absence de signal ne constitue pas une habilitation : les contrôles "
    "administratifs, sécuritaires et diplomatiques compétents demeurent seuls "
    "habilités à se prononcer."
)

PERSONAL_PROPOSAL_NOTICE = (
    "Proposition personnelle de l'évaluateur — ne vaut pas décision de la commission."
)

MAROC_SECTION_TITLE = "Mentions relatives au Maroc — vérification institutionnelle obligatoire"

#: Correspondance statut de contrôle → état affiché dans le tableau de conformité.
CONTROL_STATE_LABEL = {
    ControlStatus.CONFIRME: "SATISFAIT",
    ControlStatus.NON_CONFIRME: "NON SATISFAIT",
    ControlStatus.INCOMPLET: "PARTIEL",
    ControlStatus.INCOHERENT: "INCOHÉRENT",
    ControlStatus.ILLISIBLE: "NON VÉRIFIABLE",
    ControlStatus.A_VERIFIER: "NON VÉRIFIÉ",
    ControlStatus.NON_APPLICABLE: "NON APPLICABLE",
}

#: Correspondance statut de preuve → état affiché pour un profil étranger.
PROFILE_STATE_LABEL = {
    EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE: "CONFIRMÉ PAR SOURCE OFFICIELLE",
    EvidenceStatus.SOURCES_CONCORDANTES: "CONFIRMÉ",
    EvidenceStatus.A_VERIFIER: "PARTIELLEMENT CONFIRMÉ",
    EvidenceStatus.HOMONYMIE_POSSIBLE: "HOMONYMIE POSSIBLE — NON IDENTIFIÉ",
    EvidenceStatus.SOURCES_CONTRADICTOIRES: "SOURCES CONTRADICTOIRES",
    EvidenceStatus.NON_ETABLI: "NON ÉTABLI",
    EvidenceStatus.ECARTE_PAR_HUMAIN: "ÉCARTÉ PAR L'ÉVALUATEUR",
}

#: Rubriques de la fiche d'information, dans l'ordre des rapports de référence.
FICHE_ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Intitulé", ("intitule",)),
    ("Nature et dates", ("type_manifestation", "date_debut", "date_fin")),
    ("Lieu et mode d'organisation", ("lieu", "format")),
    ("Établissement organisateur", ("etablissement_organisateur", "structure_porteuse")),
    ("Responsable scientifique", ("responsable_scientifique",)),
    ("Objet et axes", ("theme", "objectifs")),
    ("Comité scientifique", ("comite_scientifique",)),
    ("Comité d'organisation", ("comite_organisation",)),
    ("Intervenants annoncés", ("intervenants",)),
    ("Participation et pays représentés", ("participants", "pays_representes")),
    ("Institutions représentées", ("institutions_representees",)),
    ("Partenaires, sponsors et financeurs", ("partenaires", "sponsors", "financeurs")),
    ("Financement", ("budget_total", "montants_devise")),
    ("Publication et valorisation", ("modalites_publication", "livrables")),
    ("Retombées attendues", ("resultats_attendus", "retombees_scientifiques", "retombees_doctorales")),
    ("Références réglementaires citées", ("references_reglementaires",)),
)

#: Regroupement thématique des catégories d'alerte pour la section « points sensibles ».
SENSITIVE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Souveraineté, intégrité territoriale et symboles", ("INTEGRITE_TERRITORIALE", "CARTES_SYMBOLES")),
    ("Relations diplomatiques et communication institutionnelle", ("RELATIONS_DIPLOMATIQUES", "COMMUNICATION_INSTITUTIONNELLE")),
    ("Mémoire nationale, identité, langue et religion", ("MEMOIRE_NATIONALE", "IDENTITE_RELIGION_LANGUE")),
    ("Ordre public, discrimination et incitation", ("DISCRIMINATION_HAINE", "ORDRE_PUBLIC_VIOLENCE")),
    ("Défense, infrastructures critiques et double usage", ("DEFENSE_SECURITE", "INFRASTRUCTURES_CRITIQUES", "CYBER_DUAL_USE", "BIOSECURITE_DUAL_USE", "IA_DESINFORMATION")),
    ("Santé, données personnelles, génétiques et biométriques", ("SANTE_PUBLIQUE", "DONNEES_GENETIQUES_BIOMETRIQUES", "ETHIQUE_RECHERCHE")),
    ("Ressources biologiques, patrimoine et souveraineté des données", ("RESSOURCES_BIOLOGIQUES", "PATRIMOINE_ARCHIVES", "SOUVERAINETE_DONNEES")),
    ("Financement, influence et intégrité scientifique", ("FINANCEMENT_INFLUENCE", "REPUTATION_SCIENTIFIQUE")),
    ("Couverture de l'analyse", ("COUVERTURE_ANALYSE",)),
)


# --------------------------------------------------------------------------
# Structures de rendu
# --------------------------------------------------------------------------


@dataclass
class Box:
    """Encadré mis en valeur (avis proposé, veille publique, proposition)."""

    title: str
    body: str
    tone: str = "neutre"  # neutre | attention | critique


@dataclass
class Table:
    caption: str
    headers: list[str]
    rows: list[list[str]] = field(default_factory=list)
    note: str | None = None


@dataclass
class Paragraph:
    text: str
    kind: str = ReportFactKind.FAIT_EXTRAIT
    page_no: int | None = None

    @property
    def source_label(self) -> str:
        if self.page_no is not None:
            return f"page {self.page_no}"
        return ""


@dataclass
class Block:
    """Un bloc de contenu : encadré, tableau, paragraphe ou liste."""

    kind: str  # box | table | paragraph | list | subheading
    box: Box | None = None
    table: Table | None = None
    paragraph: Paragraph | None = None
    items: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class Section:
    number: str
    title: str
    blocks: list[Block] = field(default_factory=list)

    def box(self, title: str, body: str, tone: str = "neutre") -> None:
        self.blocks.append(Block(kind="box", box=Box(title=title, body=body, tone=tone)))

    def para(self, text: str, kind: str = ReportFactKind.FAIT_EXTRAIT, page_no: int | None = None) -> None:
        self.blocks.append(
            Block(kind="paragraph", paragraph=Paragraph(text=text, kind=kind, page_no=page_no))
        )

    def table(self, caption: str, headers: list[str], rows: list[list[str]], note: str | None = None) -> None:
        self.blocks.append(
            Block(kind="table", table=Table(caption=caption, headers=headers, rows=rows, note=note))
        )

    def bullets(self, items: list[str]) -> None:
        if items:
            self.blocks.append(Block(kind="list", items=items))

    def subheading(self, text: str) -> None:
        self.blocks.append(Block(kind="subheading", text=text))


#: Mois en français — évite toute dépendance à une locale système.
MONTHS_FR = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def format_date_fr(value: datetime) -> str:
    day = "1er" if value.day == 1 else str(value.day)
    return f"{day} {MONTHS_FR[value.month - 1]} {value.year}"


@dataclass
class EvaluationReport:
    reference: str
    title: str
    organizer: str
    evaluator: str
    generated_at: datetime
    version: str
    is_draft: bool
    subtitle: str
    sections: list[Section]
    orphan_facts: list[str]
    #: Encadré d'avis affiché en tête du rapport, avant la fiche d'information.
    headline: Box | None = None
    signature: str = SIGNATURE

    @property
    def banner(self) -> str:
        return DRAFT_BANNER


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------


def build(session: Session, dossier_id: str) -> EvaluationReport:
    settings = get_settings()
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise ValueError("Dossier introuvable.")

    ctx = _Context(session, dossier)
    sections = [
        _section_fiche(ctx),
        _section_objet(ctx),
        _section_conformite(ctx),
        _section_anomalies(ctx),
        _section_profils(ctx),
        _section_publication(ctx),
        _section_points_sensibles(ctx),
        _section_conditions(ctx),
        _section_avis(ctx),
        _section_sources(ctx),
        _section_annexe_tracabilite(ctx),
    ]

    return EvaluationReport(
        reference=dossier.reference,
        title=dossier.title,
        organizer=dossier.organizer,
        evaluator=settings.evaluator_label,
        generated_at=datetime.now(timezone.utc),
        version=settings.version,
        is_draft=dossier.report_validated_at is None,
        subtitle=_subtitle(ctx),
        sections=sections,
        orphan_facts=ctx.orphan_facts,
        headline=_headline(ctx),
    )


def _headline(ctx: "_Context") -> Box:
    """Encadré d'avis en tête : reprend la conclusion humaine, jamais une déduction."""
    blocking = [name for name, state in ctx.gates.items() if not state["satisfied"]]
    if ctx.conclusion is None:
        return Box(
            title="AVIS PROPOSÉ",
            body=(
                "AUCUN AVIS FORMULÉ EN L'ÉTAT. L'évaluateur n'a pas encore choisi de conclusion "
                "dans la liste fermée, et l'application n'en propose aucune."
                + (
                    " Portes de validation non satisfaites : " + ", ".join(blocking) + "."
                    if blocking
                    else ""
                )
            ),
            tone="attention",
        )
    body = decrypt_text(
        ctx.key, ctx.conclusion.body_cipher, evaluation_service.note_aad(ctx.conclusion.id)
    )
    return Box(
        title=f"AVIS PROPOSÉ : {ctx.conclusion.conclusion}",
        body=f"{body} {PERSONAL_PROPOSAL_NOTICE}",
        tone="critique",
    )


class _Context:
    """Données du dossier, chargées une seule fois et jamais complétées."""

    def __init__(self, session: Session, dossier: Dossier) -> None:
        self.session = session
        self.dossier = dossier
        self.settings = get_settings()
        self.key = get_master_key()

        self.items = {
            item.key: dossier_service.item_view(item)
            for item in session.scalars(
                select(ExtractedItem).where(ExtractedItem.dossier_id == dossier.id)
            ).all()
        }
        self.pages = dossier_service.dossier_pages(session, dossier.id)
        self.pieces = list(
            session.scalars(
                select(PieceCheck)
                .where(PieceCheck.dossier_id == dossier.id)
                .order_by(PieceCheck.label)
            ).all()
        )
        self.checks = evaluation_service.administrative_view(session, dossier.id)
        self.findings = evaluation_service.findings_view(session, dossier.id)
        self.evaluation = evaluation_service.evaluation_state(session, dossier.id)
        self.conclusion = evaluation_service.current_conclusion(session, dossier.id)
        self.notes = evaluation_service.notes_view(session, dossier.id)
        self.gates = evaluation_service.gates_state(session, dossier.id)
        self.profiles = list(
            session.scalars(
                select(PersonWebProfile).where(PersonWebProfile.dossier_id == dossier.id)
            ).all()
        )
        self.claims = list(
            session.scalars(
                select(OnlineClaim).where(OnlineClaim.dossier_id == dossier.id)
            ).all()
        )
        self.orphan_facts: list[str] = []

    # -- accès aux informations -------------------------------------------

    def value(self, key: str) -> tuple[str, int | None, bool]:
        """Retourne (valeur affichable, page source, valeur retenue).

        Une information non confirmée n'est jamais présentée comme un fait :
        elle est rendue avec son statut réel.
        """
        item = self.items.get(key)
        if item is None:
            return NOT_PROVIDED, None, False
        raw = (item["current_value"] or "").strip()
        if not raw:
            return NOT_PROVIDED, None, False
        if item["status"] in {InformationStatus.CONFIRME, InformationStatus.CORRIGE}:
            if item["page_no"] is None and not item["manual_entry_validated"]:
                self.orphan_facts.append(item["label"])
                return f"{raw} [source manquante — exclu de la synthèse]", None, False
            return raw, item["page_no"], True
        return f"{raw} [{item['status']}]", item["page_no"], False

    def claim_texts(self, agent_name: str) -> list[OnlineClaim]:
        return [claim for claim in self.claims if claim.agent_name == agent_name]

    def claim_body(self, claim: OnlineClaim) -> str:
        from app.web_research.service import claim_aad

        return decrypt_text(self.key, claim.statement_cipher, claim_aad(claim.id, "statement")) or ""


def _subtitle(ctx: _Context) -> str:
    kind, _, _ = ctx.value("type_manifestation")
    if kind == NOT_PROVIDED:
        return "Demande d'organisation d'une manifestation scientifique internationale"
    return f"Demande d'organisation — {kind}"


# --------------------------------------------------------------------------
# §1 Fiche d'information
# --------------------------------------------------------------------------


def _section_fiche(ctx: _Context) -> Section:
    section = Section("1", "Fiche d'information de la manifestation")
    rows: list[list[str]] = [
        ["Référence du dossier", ctx.dossier.reference, "Saisie de l'évaluateur"],
        ["Organisateur déclaré", ctx.dossier.organizer, "Saisie de l'évaluateur"],
    ]
    for label, keys in FICHE_ROWS:
        parts: list[str] = []
        pages: list[int] = []
        for key in keys:
            value, page, _ = ctx.value(key)
            if value == NOT_PROVIDED:
                continue
            parts.append(value)
            if page is not None:
                pages.append(page)
        if not parts:
            rows.append([label, NOT_PROVIDED, "—"])
            continue
        source = ", ".join(f"p. {page}" for page in sorted(set(pages))) or "saisie manuelle validée"
        rows.append([label, " ; ".join(parts), source])

    if ctx.dossier.sha256:
        rows.append(
            [
                "Document original",
                f"{ctx.dossier.original_name or 'document'} — {ctx.dossier.page_count} pages",
                f"SHA-256 {ctx.dossier.sha256[:24]}…",
            ]
        )

    section.table(
        "Rubriques du dossier et leur source",
        ["Rubrique", "Information vérifiée dans le dossier", "Source"],
        rows,
        note=(
            "Chaque information retenue porte sa page source. La mention « "
            f"{NOT_PROVIDED} » signifie que la donnée est absente ou non encore "
            "qualifiée par l'évaluateur : elle n'est jamais suppléée."
        ),
    )
    return section


# --------------------------------------------------------------------------
# §2 Objet scientifique et intérêt
# --------------------------------------------------------------------------


def _section_objet(ctx: _Context) -> Section:
    section = Section("2", "Objet scientifique et intérêt")

    for key, label in (
        ("theme", "Thème"),
        ("objectifs", "Objectifs annoncés"),
        ("retombees_scientifiques", "Retombées scientifiques attendues"),
        ("retombees_doctorales", "Retombées doctorales attendues"),
        ("retombees_socio_economiques", "Retombées socio-économiques attendues"),
    ):
        value, page, retained = ctx.value(key)
        if value == NOT_PROVIDED:
            section.para(
                f"{label} : {NOT_PROVIDED}.",
                kind=ReportFactKind.A_VERIFIER,
            )
        else:
            section.para(
                f"{label} : {value}",
                kind=ReportFactKind.FAIT_EXTRAIT if retained else ReportFactKind.A_VERIFIER,
                page_no=page,
            )

    section.para(
        "L'adéquation aux priorités nationales relève de l'appréciation de l'évaluateur. "
        "L'application ne procède à aucune classification sémantique et ne conclut jamais "
        "à la conformité d'un thème.",
        kind=ReportFactKind.A_VERIFIER,
    )

    referentials = _applied_referentials(ctx)
    section.para(
        "Référentiel appliqué : " + ("; ".join(referentials) if referentials else
        "aucun texte officiel validé n'est actif dans le référentiel local. Aucune exigence "
        "réglementaire n'est donc opposée dans ce rapport."),
        kind=ReportFactKind.CALCUL,
    )
    return section


def _applied_referentials(ctx: _Context) -> list[str]:
    """Seuls les textes VALIDE, présents et intègres sont cités comme référentiel."""
    labels: list[str] = []
    for regulation in ctx.session.scalars(select(Regulation)).all():
        if regulation.status != "VALIDE" or not regulation.integrity_ok or not regulation.passages:
            continue
        parts = [regulation.title]
        if regulation.reference:
            parts.append(f"n° {regulation.reference}")
        if regulation.document_date:
            parts.append(f"du {regulation.document_date}")
        labels.append(" ".join(parts))
    return labels


# --------------------------------------------------------------------------
# §3 Contrôle de conformité réglementaire
# --------------------------------------------------------------------------


def _section_conformite(ctx: _Context) -> Section:
    section = Section("3", "Contrôle de conformité réglementaire")

    referentials = _applied_referentials(ctx)
    if not referentials:
        section.box(
            "PORTÉE DU CONTRÔLE",
            "Aucun texte officiel validé n'étant actif dans le référentiel local, les points "
            "ci-dessous constituent une liste de contrôle de travail et non un constat de "
            "conformité juridique. Aucune non-conformité réglementaire n'est établie par "
            "l'application.",
            tone="attention",
        )

    rows = [
        [
            check["label"],
            CONTROL_STATE_LABEL.get(check["status"], check["status"]),
            (check["explanation"] or "Non encore qualifié par l'évaluateur.")
            + (f" (p. {check['page_no']})" if check["page_no"] else ""),
        ]
        for check in ctx.checks
    ]
    section.table(
        "Points de contrôle administratif",
        ["Exigence contrôlée", "Statut", "Constat documenté"],
        rows,
        note=(
            "Statuts possibles : SATISFAIT, PARTIEL, NON SATISFAIT, INCOHÉRENT, NON VÉRIFIABLE, "
            "NON VÉRIFIÉ, NON APPLICABLE. Chaque statut est attribué par l'évaluateur."
        ),
    )

    section.subheading("Inventaire des pièces")
    piece_rows = [
        [
            piece.label,
            piece.status,
            (
                "Section restreinte — contenu masqué"
                if piece.sensitivity == "RESTREINT"
                else (f"Détectée p. {piece.detected_page_no}" if piece.detected_page_no else "—")
            ),
        ]
        for piece in ctx.pieces
    ]
    section.table(
        "Pièces attendues et leur état",
        ["Pièce", "État", "Constat"],
        piece_rows,
        note=(
            "La détection d'un titre ne vaut jamais confirmation de la validité juridique "
            "d'une pièce. Seule une qualification humaine fait foi."
        ),
    )
    return section


# --------------------------------------------------------------------------
# §4 Anomalies et incohérences
# --------------------------------------------------------------------------


def _section_anomalies(ctx: _Context) -> Section:
    section = Section("4", "Anomalies et incohérences documentaires")
    entries: list[str] = []

    for check in ctx.checks:
        if check["status"] in {ControlStatus.INCOHERENT, ControlStatus.INCOMPLET}:
            page = f" (p. {check['page_no']})" if check["page_no"] else ""
            entries.append(
                f"{check['label']} — {CONTROL_STATE_LABEL.get(check['status'], check['status'])} : "
                f"{check['explanation'] or 'sans explication enregistrée'}{page}"
            )

    duplicates = [page for page in ctx.pages if page.duplicate_of]
    for page in duplicates:
        entries.append(
            f"Page {page.page_no} — doublon probable de la page {page.duplicate_of} "
            "(empreinte de texte identique)."
        )

    unreadable = [page for page in ctx.pages if page.needs_ocr and not page.is_blank]
    if unreadable:
        entries.append(
            "Pages non extraites, donc non couvertes par l'analyse textuelle : "
            + ", ".join(str(page.page_no) for page in unreadable)
            + ". Ces pages peuvent contenir un élément sensible non détecté."
        )

    low_confidence = [
        page
        for page in ctx.pages
        if page.confidence is not None
        and page.confidence * 100 < ctx.settings.ocr_low_confidence
    ]
    for page in low_confidence:
        entries.append(
            f"Page {page.page_no} — confiance d'extraction {round(page.confidence * 100, 1)} %, "
            f"inférieure au seuil de {ctx.settings.ocr_low_confidence} % : "
            "contenu illisible ou insuffisamment fiable, vérification humaine obligatoire."
        )

    if ctx.orphan_facts:
        entries.append(
            "Informations saisies sans page source ni validation manuelle, exclues de la "
            "synthèse factuelle : " + ", ".join(sorted(set(ctx.orphan_facts))) + "."
        )

    if entries:
        section.bullets(entries)
    else:
        section.para(
            "Aucune incohérence n'a été qualifiée par l'évaluateur et aucune anomalie "
            "structurelle n'a été relevée par l'analyse.",
            kind=ReportFactKind.CALCUL,
        )
        section.para(
            "Ce constat porte sur les contrôles effectués : il ne garantit pas l'absence "
            "d'incohérence dans le dossier.",
            kind=ReportFactKind.A_VERIFIER,
        )
    return section


# --------------------------------------------------------------------------
# §5 Vérification des profils étrangers
# --------------------------------------------------------------------------


def _section_profils(ctx: _Context) -> Section:
    section = Section("5", "Vérification ouverte des profils et affiliations")

    consulted = ctx.session.scalars(select(WebSource)).all()
    consult_date = (
        format_date_fr(max(source.consulted_at for source in consulted)) if consulted else None
    )
    section.box(
        "PORTÉE ET LIMITE",
        (
            f"Contrôle de l'identité professionnelle, de l'affiliation et de la fonction à partir "
            f"de sources publiques institutionnelles{f', consultées le {consult_date}' if consult_date else ''}. "
            "Cette vérification ne porte ni sur les opinions, ni sur la vie privée, ni sur la "
            "nationalité. Elle ne constitue ni une enquête, ni une habilitation, ni une "
            "qualification juridique. L'absence de résultat ne prouve ni l'absence d'activité "
            "ni l'absence de risque."
        ),
        tone="attention",
    )

    if not ctx.profiles:
        section.para(
            "Aucune campagne de recherche publique n'a été menée pour ce dossier : "
            "les profils déclarés n'ont pas été confrontés à des sources externes.",
            kind=ReportFactKind.A_VERIFIER,
        )
        section.para(
            "Analyse enrichie incomplète — vérification humaine externe obligatoire.",
            kind=ReportFactKind.A_VERIFIER,
        )
        return section

    rows: list[list[str]] = []
    for profile in ctx.profiles:
        related = [claim for claim in ctx.claims if claim.subject_label == profile.display_name]
        verified = json.loads(profile.verified_affiliations_json)
        findings_text: list[str] = []
        for claim in related:
            body = ctx.claim_body(claim).split("\n")[0].strip()
            if body:
                findings_text.append(f"[{claim.agent_name.removeprefix('AGENT_')}] {body}")
        rows.append(
            [
                f"{profile.display_name}"
                + (f" — affiliation déclarée : {profile.declared_affiliation}" if profile.declared_affiliation else ""),
                (" ".join(findings_text) or "Aucune affirmation produite.")
                + (f" Affiliations retrouvées : {', '.join(verified)}." if verified else ""),
                PROFILE_STATE_LABEL.get(profile.status, profile.status),
            ]
        )

    section.table(
        "Profils déclarés et résultat de la vérification ouverte",
        ["Personne ou organisme déclaré", "Résultat de la vérification ouverte", "État"],
        rows,
        note=(
            "Un état « HOMONYMIE POSSIBLE » ou « SOURCES CONTRADICTOIRES » interdit toute "
            "conclusion consolidée sur la personne concernée. Une nationalité, une origine ou "
            "une affiliation ne produit jamais, à elle seule, une appréciation défavorable."
        ),
    )

    homonyms = [
        profile for profile in ctx.profiles if profile.status == EvidenceStatus.HOMONYMIE_POSSIBLE
    ]
    if homonyms:
        section.box(
            "IDENTIFICATION NON ÉTABLIE",
            "Les profils suivants n'ont pas pu être identifiés de manière univoque : "
            + ", ".join(profile.display_name for profile in homonyms)
            + ". Aucune conclusion les concernant ne peut être consolidée en l'état.",
            tone="critique",
        )
    return section


# --------------------------------------------------------------------------
# §6 Publication, indexation et intégrité scientifique
# --------------------------------------------------------------------------


def _section_publication(ctx: _Context) -> Section:
    section = Section("6", "Publication, indexation et intégrité scientifique")

    for key, label in (
        ("modalites_publication", "Modalités de publication annoncées"),
        ("livrables", "Livrables annoncés"),
    ):
        value, page, retained = ctx.value(key)
        section.para(
            f"{label} : {value}",
            kind=ReportFactKind.FAIT_EXTRAIT if retained else ReportFactKind.A_VERIFIER,
            page_no=page,
        )

    reputation = ctx.claim_texts("AGENT_REPUTATION_SCIENTIFIQUE")
    if reputation:
        section.bullets(
            [
                f"{ctx.claim_body(claim).split(chr(10))[0]} — statut de preuve : {claim.status}"
                for claim in reputation
            ]
        )
    else:
        section.para(
            "Aucune vérification publique de réputation éditoriale n'a été effectuée pour "
            "ce dossier.",
            kind=ReportFactKind.A_VERIFIER,
        )

    section.para(
        "L'engagement d'indexation ou de publication annoncé par les organisateurs doit être "
        "justifié par une pièce contractuelle vérifiable. L'application ne valide aucun "
        "engagement éditorial.",
        kind=ReportFactKind.A_VERIFIER,
    )
    return section


# --------------------------------------------------------------------------
# §7 Points sensibles à encadrer
# --------------------------------------------------------------------------


def _section_points_sensibles(ctx: _Context) -> Section:
    section = Section("7", "Points sensibles à encadrer en Algérie")

    maroc = [item for item in ctx.findings if item["category"] == "MENTIONS_MAROC"]
    section.subheading(MAROC_SECTION_TITLE)
    section.box(
        "POINT DE VIGILANCE INSTITUTIONNELLE",
        "Vérifier les instructions officielles applicables à la session avant toute "
        "conclusion. Une ville, un domaine internet, un indicatif téléphonique, un nom ou une "
        "nationalité ne suffit jamais à établir une collaboration. La nationalité d'une "
        "personne ne produit jamais un avis défavorable.",
        tone="attention",
    )
    if maroc:
        section.table(
            "Mentions détectées et leur qualification",
            ["Déclencheur", "Page", "Contexte relevé", "Qualification de la relation", "Statut humain"],
            [
                [
                    item["trigger"] or "—",
                    str(item["page_no"]) if item["page_no"] else "—",
                    (item["context"] or "—")[:220],
                    item["relation_kind"] or "NON QUALIFIÉE",
                    item["human_status"],
                ]
                for item in maroc
            ],
        )
    else:
        section.para(
            "Aucune mention détectée par le moteur textuel dans les pages extraites.",
            kind=ReportFactKind.CALCUL,
        )
        section.para(
            "Ce constat ne vaut que pour le texte effectivement extrait : les cartes, drapeaux, "
            "logos, tampons et images ne sont pas analysés.",
            kind=ReportFactKind.A_VERIFIER,
        )

    for title, categories in SENSITIVE_GROUPS:
        group = [item for item in ctx.findings if item["category"] in categories]
        if not group:
            continue
        section.subheading(title)
        section.table(
            title,
            ["Constat", "Page", "Priorité", "Vérification recommandée", "Statut humain"],
            [
                [
                    f"{item['label']} — déclencheur « {item['trigger']} »",
                    str(item["page_no"]) if item["page_no"] else "—",
                    item["priority"],
                    item["recommended_check"][:260],
                    item["human_status"],
                ]
                for item in group
            ],
        )

    section.para(
        "Chaque point ci-dessus est une demande de vérification humaine. Aucun ne constitue une "
        "interdiction, une non-conformité établie ni une décision. L'absence d'alerte ne prouve "
        "pas l'absence de risque.",
        kind=ReportFactKind.A_VERIFIER,
    )
    return section


# --------------------------------------------------------------------------
# §8 Conditions minimales avant réexamen
# --------------------------------------------------------------------------


def _section_conditions(ctx: _Context) -> Section:
    section = Section("8", "Conditions minimales avant réexamen")
    conditions: list[str] = []

    missing_pieces = [
        piece.label for piece in ctx.pieces if piece.status == PieceStatus.ABSENTE
    ]
    if missing_pieces:
        conditions.append(
            "Produire les pièces absentes du dossier : " + " ; ".join(missing_pieces) + "."
        )

    to_qualify = [
        piece.label
        for piece in ctx.pieces
        if piece.status in {PieceStatus.DETECTEE, PieceStatus.A_VERIFIER, PieceStatus.INCOMPLETE}
    ]
    if to_qualify:
        conditions.append(
            "Faire confirmer par l'évaluateur les pièces détectées mais non qualifiées : "
            + " ; ".join(to_qualify)
            + "."
        )

    unverified = [
        item["label"]
        for item in ctx.items.values()
        if item["status"] == InformationStatus.A_VERIFIER
    ]
    if unverified:
        conditions.append(
            "Renseigner et sourcer les informations manquantes : " + " ; ".join(sorted(unverified)) + "."
        )

    if ctx.orphan_facts:
        conditions.append(
            "Rattacher à leur page source les informations suivantes, actuellement exclues de "
            "la synthèse factuelle : " + " ; ".join(sorted(set(ctx.orphan_facts))) + "."
        )

    unreadable = [page.page_no for page in ctx.pages if page.needs_ocr and not page.is_blank]
    if unreadable:
        conditions.append(
            "Rendre lisibles ou faire lire manuellement les pages non extraites : "
            + ", ".join(str(page) for page in unreadable)
            + "."
        )

    open_findings = [item for item in ctx.findings if item["human_status"] == FindingStatus.A_VERIFIER]
    if open_findings:
        conditions.append(
            f"Qualifier et motiver les {len(open_findings)} alerte(s) restées au statut "
            "A_VERIFIER avant tout export officiel."
        )

    if not ctx.evaluation["complete"]:
        missing = ", ".join(ctx.evaluation["missing"])
        conditions.append(
            f"Compléter la grille scientifique : critère(s) non saisi(s) — {missing}. "
            "Le total ne peut être calculé tant que la grille est incomplète."
        )

    if not ctx.profiles:
        conditions.append(
            "Mener la campagne de recherche publique sur les intervenants, comités, partenaires "
            "et institutions étrangères, ou justifier par écrit sa mise à l'écart."
        )

    homonyms = [p for p in ctx.profiles if p.status == EvidenceStatus.HOMONYMIE_POSSIBLE]
    if homonyms:
        conditions.append(
            "Lever l'ambiguïté d'identification pour : "
            + ", ".join(profile.display_name for profile in homonyms)
            + " (CV daté, attestation institutionnelle, identifiant scientifique public)."
        )

    for name, state in ctx.gates.items():
        if not state["satisfied"]:
            conditions.append(f"Satisfaire la porte {name} : {state['message']}")

    if conditions:
        section.bullets(conditions)
        section.para(
            "Ces conditions sont déduites de l'état documenté du dossier. Leur caractère "
            "suspensif relève de l'appréciation de l'évaluateur et de la commission.",
            kind=ReportFactKind.A_VERIFIER,
        )
    else:
        section.para(
            "Aucune condition suspensive n'est déduite de l'état actuel du dossier : toutes les "
            "portes de validation sont satisfaites.",
            kind=ReportFactKind.CALCUL,
        )
    return section


# --------------------------------------------------------------------------
# §9 Avis motivé
# --------------------------------------------------------------------------


def _section_avis(ctx: _Context) -> Section:
    section = Section("9", "Avis motivé")

    # -- grille scientifique ------------------------------------------------
    section.subheading("Grille scientifique saisie par l'évaluateur")
    section.table(
        "Notes saisies et leur justification",
        ["Critère", "Note", "Justification", "Pages sources"],
        [
            [
                row["label"],
                "NON SAISIE" if row["score"] is None else f"{row['score']}/{row['max']}",
                row["justification"] or "—",
                ", ".join(str(page) for page in row["source_pages"]) or "—",
            ]
            for row in ctx.evaluation["criteria"]
        ],
        note=ctx.evaluation["notice"],
    )
    if ctx.evaluation["complete"]:
        section.para(
            f"Total : {ctx.evaluation['total']}/{ctx.evaluation['max_total']} — somme des notes "
            "saisies par l'évaluateur. Aucun seuil de décision n'est dérivé de ce total.",
            kind=ReportFactKind.CALCUL,
        )

    # -- classement externe -------------------------------------------------
    ranking = _ranking_summary(ctx)
    if ranking:
        section.subheading(
            "Classement externe indicatif assisté par IA — non décisionnel, fondé sur des "
            "sources publiques consultées à la date indiquée"
        )
        section.para(ranking, kind=ReportFactKind.ALERTE_SYSTEME)
        section.para(
            "Ce classement ne modifie aucune note de la grille scientifique officielle et ne "
            "peut motiver à lui seul une acceptation, un rejet, une interdiction ou une "
            "transmission.",
            kind=ReportFactKind.A_VERIFIER,
        )

    # -- constat de veille publique ----------------------------------------
    section.box("CONSTAT DE VEILLE PUBLIQUE", _public_watch_statement(ctx), tone="attention")

    # -- réserves et questions ---------------------------------------------
    reserves = [note for note in ctx.notes if note["kind"] == "RESERVE"]
    questions = [note for note in ctx.notes if note["kind"] == "QUESTION"]
    if reserves:
        section.subheading("Réserves de l'évaluateur")
        section.bullets([note["body"] or "—" for note in reserves])
    if questions:
        section.subheading("Questions à la commission")
        section.bullets([note["body"] or "—" for note in questions])

    # -- proposition --------------------------------------------------------
    section.box("PROPOSITION À LA COMMISSION", _proposal_statement(ctx), tone="critique")
    section.para(PERSONAL_PROPOSAL_NOTICE, kind=ReportFactKind.CONCLUSION_EVALUATEUR)
    return section


def _ranking_summary(ctx: _Context) -> str | None:
    from app.ranking import service as ranking_service

    view = ranking_service.ranking_view(ctx.session, ctx.dossier.id)
    if view is None:
        return None
    scored = [axis for axis in view["axes"] if not axis["not_provided"]]
    parts = [
        f"Classement : {view['grade']}",
        f"total indicatif {view['total'] if view['total'] is not None else 'NR — NON RENSEIGNE'}/100",
        f"{len(scored)} axe(s) documenté(s) sur {len(view['axes'])}",
    ]
    if view["blocked_reason"]:
        parts.append(f"blocage : {view['blocked_reason']}")
    return " — ".join(parts) + "."


def _public_watch_statement(ctx: _Context) -> str:
    """Constat de veille : n'énonce que ce qui a été réellement consulté."""
    if not ctx.profiles and not ctx.claims:
        return (
            "Aucune veille publique n'a été menée pour ce dossier : aucune source externe n'a "
            "été consultée. Aucun constat, favorable ou défavorable, ne peut donc être formulé. "
            + PUBLIC_WATCH_CAVEAT
        )

    adverse = [
        claim
        for claim in ctx.claims
        if claim.status
        in {EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE, EvidenceStatus.SOURCES_CONCORDANTES}
        and claim.agent_name == "AGENT_INTEGRITE_PUBLIQUE"
    ]
    sources_count = len(ctx.session.scalars(select(WebSource)).all())

    if not adverse:
        return (
            f"Aucun élément public institutionnel défavorable directement pertinent n'a été "
            f"identifié dans les {sources_count} source(s) effectivement consultée(s). "
            + PUBLIC_WATCH_CAVEAT
        )

    return (
        f"{len(adverse)} élément(s) public(s) documenté(s) appellent une vérification, sur "
        f"{sources_count} source(s) consultée(s). Ces éléments sont des constats d'activité "
        "publique et non des qualifications juridiques : une appartenance, une présence à un "
        "événement ou une signature collective ne prouve pas l'adhésion à toutes les positions "
        "d'une organisation. " + PUBLIC_WATCH_CAVEAT
    )


def _proposal_statement(ctx: _Context) -> str:
    if ctx.conclusion is None:
        blocking = [name for name, state in ctx.gates.items() if not state["satisfied"]]
        return (
            "AUCUNE PROPOSITION FORMULÉE. L'évaluateur n'a pas encore choisi de conclusion dans "
            "la liste fermée. L'application n'en propose aucune et n'en déduit aucune."
            + (
                " Portes de validation non satisfaites : " + ", ".join(blocking) + "."
                if blocking
                else ""
            )
        )

    body = decrypt_text(
        ctx.key, ctx.conclusion.body_cipher, evaluation_service.note_aad(ctx.conclusion.id)
    )
    return f"{ctx.conclusion.conclusion}. {body} {PERSONAL_PROPOSAL_NOTICE}"


# --------------------------------------------------------------------------
# Sources vérifiées
# --------------------------------------------------------------------------


def _section_sources(ctx: _Context) -> Section:
    consulted = list(ctx.session.scalars(select(WebSource).order_by(WebSource.consulted_at)).all())
    date_label = format_date_fr(
        max(source.consulted_at for source in consulted)
        if consulted
        else datetime.now(timezone.utc)
    )
    section = Section("10", f"Sources vérifiées — consultation du {date_label}")

    rows: list[list[str]] = []

    for source in ctx.session.scalars(select(SourceDocument).order_by(SourceDocument.source_id)).all():
        if not source.present_locally:
            continue
        rows.append(
            [
                f"{source.authority or 'Autorité non précisée'} — {source.file_name}",
                "Pièce réglementaire du référentiel local",
                "Empreinte conforme" if source.integrity_ok else "EMPREINTE DIVERGENTE",
            ]
        )

    for regulation in ctx.session.scalars(select(Regulation)).all():
        rows.append(
            [
                f"{regulation.title}"
                + (f" — n° {regulation.reference}" if regulation.reference else ""),
                f"Texte importé ({regulation.status})",
                f"SHA-256 {regulation.sha256[:20]}…",
            ]
        )

    for source in consulted:
        rows.append(
            [
                source.title or source.url,
                f"{source.publisher or source.domain} — {source.tier}",
                f"consultée le {source.consulted_at.strftime('%d/%m/%Y')}"
                + (f", publiée le {source.published_on}" if source.published_on else ", non datée"),
            ]
        )

    if rows:
        section.table(
            "Sources effectivement consultées",
            ["Source", "Nature", "Contrôle"],
            rows,
            note=(
                "Seules figurent ici les sources réellement consultées ou déposées localement. "
                "Aucune référence n'est citée de mémoire."
            ),
        )
    else:
        section.para(
            "Aucune source externe n'a été consultée et aucun texte officiel n'est déposé dans "
            "le référentiel local.",
            kind=ReportFactKind.A_VERIFIER,
        )

    section.subheading("Document analysé")
    section.para(
        f"{ctx.dossier.original_name or 'aucun document importé'} — "
        f"{ctx.dossier.page_count} page(s) — "
        f"SHA-256 {ctx.dossier.sha256 or 'non calculée'}.",
        kind=ReportFactKind.CALCUL,
    )
    return section


# --------------------------------------------------------------------------
# Annexe — traçabilité intégrale exigée par le contrat de fiabilité
# --------------------------------------------------------------------------


def _section_annexe_tracabilite(ctx: _Context) -> Section:
    section = Section("A", "Annexe — traçabilité, portes de validation et limites")

    section.subheading("Portes de validation")
    section.table(
        "État des portes G0 à G7",
        ["Porte", "État", "Constat"],
        [
            [name, "SATISFAITE" if state["satisfied"] else "NON SATISFAITE", state["message"]]
            for name, state in ctx.gates.items()
        ],
        note=(
            "Une porte non satisfaite bloque l'étape suivante ; elle ne transforme jamais le "
            "dossier en rejet."
        ),
    )

    section.subheading("Couverture de l'analyse documentaire")
    modes: dict[str, int] = {}
    for page in ctx.pages:
        modes[page.mode] = modes.get(page.mode, 0) + 1
    section.table(
        "Modes d'extraction par page",
        ["Mode d'extraction", "Nombre de pages"],
        [[mode, str(count)] for mode, count in sorted(modes.items())]
        or [["Aucun document importé", "0"]],
    )

    section.subheading("Nature des contenus de ce rapport")
    section.table(
        "Étiquetage des contenus",
        ["Étiquette", "Signification"],
        [
            ["FAIT_EXTRAIT", "Donnée extraite du dossier, rattachée à une page source"],
            ["CALCUL", "Résultat calculé par l'application (somme, comptage, empreinte)"],
            ["ALERTE_SYSTEME", "Détection automatique appelant une vérification humaine"],
            ["COMMENTAIRE_EVALUATEUR", "Appréciation saisie par l'évaluateur"],
            ["CONCLUSION_EVALUATEUR", "Conclusion personnelle choisie par l'évaluateur"],
            ["A_VERIFIER", "Élément incertain, manquant ou non encore qualifié"],
        ],
    )

    section.subheading("Limites opposables à ce rapport")
    section.bullets(list(DISPLAYED_LIMITS))

    section.subheading("Identification")
    section.table(
        "Identification du rapport",
        ["Élément", "Valeur"],
        [
            ["Évaluateur", ctx.settings.evaluator_label],
            ["Version de l'application", ctx.settings.version],
            ["Dossier", f"{ctx.dossier.reference} — {ctx.dossier.title}"],
            ["État du dossier", ctx.dossier.status],
            [
                "Validation humaine (G7)",
                ctx.dossier.report_validated_at.strftime("%d/%m/%Y %H:%M UTC")
                if ctx.dossier.report_validated_at
                else "NON VALIDÉ",
            ],
            ["Conçu par", SIGNATURE],
        ],
    )
    return section
