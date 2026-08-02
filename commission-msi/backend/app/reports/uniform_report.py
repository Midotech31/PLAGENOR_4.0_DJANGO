"""Rapport d'évaluation **harmonisé** — format du modèle fourni par la commission.

Sept sections, dans cet ordre imposé — celui des douze rapports fournis par la
commission :

1. fiche d'information contrôlée — six rubriques condensées, pas un vidage de champs ;
2. appréciation scientifique commune — cinq dimensions sur 100, avec motif probant ;
3. matrice réglementaire uniforme — les 26 critères, `C/PC/NC/NV`, constat, fondement ;
4. contrôle des intervenants étrangers, avec **4.1 éléments relatifs au Maroc et
   à Israël** lorsque les pièces en portent, signalés à titre strictement
   informatif ;
5. points de vigilance institutionnelle ;
6. **réserves maintenues** sous avis favorable, **compléments indispensables**
   en ajournement — le titre suit l'orientation, comme dans les douze modèles ;
7. orientation technique motivée transmise au ministère.

Ce que le rapport ne porte pas — sources, versions de référentiel, règles de
décision déclenchées, contrôle en ligne des profils, contradictions connues —
n'a pas disparu : `details()` le restitue à l'interface. Ces éléments fondent le
rapport et doivent rester vérifiables, mais aucun des douze modèles ne les
imprime, et la pièce transmise au ministère n'a pas à s'en alourdir.

Deux différences de fond avec un rapport d'analyse ordinaire, et elles sont
délibérées :

* le vocabulaire est celui de l'**orientation technique** transmise au
  ministère, jamais celui d'une décision. « La décision finale appartient au
  ministère » figure en tête, en section 7, et dans les encadrés de portée ;
* aucune nationalité, origine ou opinion supposée ne fonde un constat
  défavorable. Les éléments de la section 4.1 sont informatifs : les qualifier
  relève du ministère seul, et l'encadré de portée énonce explicitement les
  critères que le contrôle refuse d'appliquer.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import SIGNATURE, get_settings
from app.core.vocabulary import NOT_PROVIDED, AgentName, ClaimNature, ReportFactKind
from app.models import Dossier
from app.reports.evaluation_report import Box, EvaluationReport, Section, _Context
from app.services import (
    assessment_service,
    audit_service,
    decision_engine,
    evidence_service,
    regulatory_engine,
    scientific_scoring,
)

TITLE = "RAPPORT D'ÉVALUATION"

#: Mention obligatoire : l'orientation est une aide, jamais une décision.
MINISTRY_NOTICE = "Décision finale : ministère."

SCORE_READING = (
    "Lecture : {total}/{maximum} mesure la qualité scientifique documentée ; il ne "
    "constitue ni une autorisation ni un avis réglementaire autonome."
)

MATRIX_LEGEND = (
    "Légende : C = conforme démontré ; PC = partiellement conforme ; NC = non conforme "
    "ou pièce absente ; NV = non vérifiable sur les pièces disponibles."
)

#: Portée unique de toute la section 4 — pièces (4.1) et veille en ligne (4.2).
#: Elle est énoncée une seule fois : trois encadrés successifs disant à peu près
#: la même chose coûtaient une page et se faisaient lire de moins en moins.
#: Ce qu'elle énonce n'est pas décoratif : sans la liste des critères refusés, un
#: lecteur pourrait prêter à l'application un profilage par l'origine, que son
#: propre référentiel lui interdit.
FOREIGN_SCOPE = (
    "Sources institutionnelles et scientifiques publiques consultables ; une homonymie, "
    "une page absente ou une affiliation ancienne n'est jamais transformée en fait. Seuls "
    "sont retenus les rattachements institutionnels et activités professionnelles "
    "publiquement documentés, et uniquement dans un contexte institutionnel — affiliation, "
    "programme, financement, partenariat : une citation bibliographique ou une simple "
    "mention géographique ne déclenche aucun signalement. Ne sont jamais examinés : la "
    "nationalité, l'origine ethnique, la religion, le lieu de naissance, la consonance "
    "d'un nom, une opinion supposée. Les éléments de la section 4.1 sont signalés à "
    "titre strictement informatif : une nationalité, une formation, une publication, une "
    "participation académique ou un lien institutionnel antérieur ne constitue pas "
    "automatiquement une non-conformité et ne préjuge d'aucune position personnelle ; leur "
    "appréciation et la décision finales relèvent exclusivement du ministère. L'absence "
    "d'élément relevé n'est pas une garantie et ne constitue pas une habilitation de "
    "sécurité : elle dépend de l'indexation, de la langue et de la date de consultation."
)

EVIDENCE_PRINCIPLE = (
    "Toute information non corroborée par une pièce identifiable "
    "ou une source publique fiable est classée NC ou NV ; aucune déduction à partir de "
    "la nationalité, de l'origine ou d'une opinion supposée."
)

DECISION_REASON = (
    "Motif commun : les éléments scientifiques utiles ne compensent pas les preuves "
    "réglementaires manquantes. Le dossier peut être réexaminé après fourniture et "
    "contrôle des compléments énumérés. La présente orientation constitue une aide "
    "technique à l'instruction ; l'appréciation et la décision finales appartiennent "
    "au ministère."
)

FAVORABLE_REASON = (
    "Motif commun : les exigences réglementaires opposables sont démontrées par les "
    "pièces du dossier. La présente orientation constitue une aide technique à "
    "l'instruction ; l'appréciation et la décision finales appartiennent au ministère."
)

NO_ASSESSMENT = (
    "Aucune analyse n'a encore été exécutée sur ce dossier. Lancez « Traiter le "
    "dossier » : la fiche contrôlée, l'appréciation scientifique, la matrice "
    "réglementaire et l'orientation technique seront alors établies sur pièces."
)

#: Rubriques de la fiche contrôlée, dans l'ordre du modèle.
FICHE_ROWS = ("Type", "Porteur", "Participants", "Comité", "Budget", "Publication")

#: Catégories de vigilance touchant le Maroc ou Israël — section 4.1.
SENSITIVE_CATEGORIES = frozenset(
    {"MENTIONS_MAROC", "INTEGRITE_TERRITORIALE", "RELATIONS_DIPLOMATIQUES", "CARTES_SYMBOLES"}
)


def build(session: Session, dossier_id: str) -> EvaluationReport:
    settings = get_settings()
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise ValueError("Dossier introuvable.")

    ctx = _Context(session, dossier)
    assessment = assessment_service.current_assessment(session, dossier_id)

    sections = [
        _section_fiche(ctx, assessment),
        _section_appreciation(ctx, assessment),
        _section_matrice(ctx, assessment),
        _section_intervenants(ctx),
        _section_vigilance(ctx),
        _section_complements(assessment),
        _section_orientation(assessment),
    ]

    return EvaluationReport(
        reference=dossier.reference,
        title=dossier.title,
        # Le modèle porte la pièce évaluée là où un rapport ordinaire mettrait
        # l'organisateur : celui-ci figure déjà dans la fiche, rubrique Porteur.
        organizer=_piece_line(ctx),
        evaluator=settings.evaluator_label,
        generated_at=datetime.now(timezone.utc),
        version=settings.version,
        is_draft=dossier.report_validated_at is None,
        subtitle=_subtitle(ctx),
        sections=sections,
        orphan_facts=ctx.orphan_facts,
        headline=_headline(assessment),
        signature=SIGNATURE,
        density="compact",
        show_fact_labels=False,
        heading=TITLE,
    )


#: Balise de statut ajoutée aux valeurs non confirmées ; elle a sa place dans les
#: tableaux, pas dans la ligne de titre.
STATUS_TAG = re.compile(r"\s*\[[A-Z_]+\]\s*$")


def _plain(ctx: _Context, key: str) -> str:
    """Valeur sans sa balise de statut, pour l'en-tête uniquement."""
    value, _page, _retained = ctx.value(key)
    return STATUS_TAG.sub("", value).strip()


def _subtitle(ctx: _Context) -> str:
    """Lieu et dates, seuls — la pièce évaluée a sa propre ligne dans le modèle."""
    place = _plain(ctx, "lieu")
    start = _plain(ctx, "date_debut")
    end = _plain(ctx, "date_fin")
    when = f"{start} — {end}" if start != NOT_PROVIDED and end != NOT_PROVIDED else "dates non renseignées"
    return f"{place} — {when}"


def _piece_line(ctx: _Context) -> str:
    """« Pièce évaluée : <nom> (<n> pages) », ligne propre du modèle."""
    documents = list(ctx.dossier.documents)
    if not documents:
        return "Pièce évaluée : aucune pièce versée"
    pieces = " ; ".join(
        f"{document.original_name} ({ctx.dossier.page_count} pages)" for document in documents[:2]
    )
    return f"Pièce évaluée : {pieces}"


def _headline(assessment: dict) -> Box:
    """Encadré de tête : l'orientation proposée et le rappel du décideur."""
    decision = assessment.get("decision")
    if not decision:
        return Box(title="ORIENTATION TECHNIQUE — NON ENCORE ÉTABLIE", body=NO_ASSESSMENT,
                   tone="attention")
    retained = decision.get("human_decision")
    chosen = retained or decision["avis"]
    # Le libellé lisible porte les accents ; l'identifiant technique ne les a pas.
    label = decision_engine.LABELS.get(chosen, chosen.replace("_", " ")).upper()
    prefix = "ORIENTATION RETENUE PAR L'ÉVALUATEUR" if retained else "ORIENTATION TECHNIQUE PROPOSÉE"
    tone = "critique" if "TRANSMISSION" in chosen else "attention"
    if chosen == decision_engine.FAVORABLE:
        tone = "neutre"
    return Box(title=f"{prefix} — {label}", body=MINISTRY_NOTICE, tone=tone)


# --------------------------------------------------------------------------
# 1. Fiche d'information contrôlée
# --------------------------------------------------------------------------


def _percent_fr(ratio: float) -> str:
    """Pourcentage à la française : virgule décimale et espace insécable."""
    return f"{ratio * 100:.1f}".replace(".", ",") + "\u00a0%"


def _marked(ctx: _Context, key: str) -> tuple[str, bool]:
    """Valeur propre et indicateur « reste à confirmer ».

    La balise de statut est retirée du texte : dans la fiche du modèle, un
    astérisque suffit, et la note du tableau en donne le sens une seule fois.
    """
    value, _page, retained = ctx.value(key)
    return STATUS_TAG.sub("", value).strip(), not retained


def _joined(ctx: _Context, *keys: str) -> tuple[str, bool]:
    parts, pending = [], False
    for key in keys:
        value, to_confirm = _marked(ctx, key)
        if value != NOT_PROVIDED:
            parts.append(value)
            pending = pending or to_confirm
    return " ; ".join(parts) or NOT_PROVIDED, pending


def _count_entries(value: str) -> int:
    from app.services.facts_service import _roster_entries

    return len(_roster_entries(value))


def _section_fiche(ctx: _Context, assessment: dict) -> Section:
    section = Section("1", "Fiche d'information contrôlée")

    kind, kind_pending = _marked(ctx, "type_manifestation")
    porteur, porteur_pending = _joined(ctx, "etablissement_organisateur", "structure_porteuse")

    committee_raw, committee_pending = _marked(ctx, "comite_scientifique")
    committee = NOT_PROVIDED
    if committee_raw != NOT_PROVIDED:
        facts = _facts_of(ctx)
        total = facts.observations.get("membres_total")
        foreign = facts.observations.get("membres_etrangers")
        named = _count_entries(committee_raw)
        if total:
            committee = (
                f"{named} membres, dont {foreign} affiliés à l'étranger "
                f"({_percent_fr(foreign / total)})."
            )
        else:
            committee = (
                f"{named} membres nommés ; affiliations non documentées nominativement, "
                "proportion internationale non calculable."
            )

    speakers, speakers_pending = _marked(ctx, "intervenants")
    countries, countries_pending = _marked(ctx, "pays_representes")
    participants = " ; ".join(
        part for part in (
            f"{_count_entries(speakers)} intervenants nommés" if speakers != NOT_PROVIDED else "",
            f"pays annoncés : {countries}" if countries != NOT_PROVIDED else "",
        ) if part
    ) or NOT_PROVIDED

    budget, budget_pending = _joined(ctx, "budget_total", "financeurs")
    publication, publication_pending = _marked(ctx, "modalites_publication")

    rows = [
        ["Type", kind, kind_pending],
        ["Porteur", porteur, porteur_pending],
        ["Participants", participants, speakers_pending or countries_pending],
        ["Comité", committee, committee_pending],
        ["Budget", budget, budget_pending],
        ["Publication", publication, publication_pending],
    ]
    # Six rubriques, sans ligne de titre : c'est la fiche du modèle de la
    # commission. L'astérisque des valeurs non confirmées reste, il porte une
    # information que le lecteur ne peut retrouver ailleurs ; sa légende, elle,
    # est passée dans l'interface.
    section.table(
        "Rubriques contrôlées",
        ["Rubrique", "Élément retenu au dossier"],
        [
            [label, f"{value}\u00a0*" if pending and value != NOT_PROVIDED else value]
            for label, value, pending in rows
        ],
        widths=[0.20, 0.80],
        show_headers=False,
    )
    return section


def _facts_of(ctx: _Context):
    from app.services import facts_service

    return facts_service.build_facts(ctx.session, ctx.dossier.id, rebuild_evidence=False)


# --------------------------------------------------------------------------
# 2. Appréciation scientifique commune
# --------------------------------------------------------------------------


def _family_reason(family: dict) -> str:
    """Motif probant : ce qui est documenté, puis ce qui manque. En une phrase."""
    documented = [sub["label"] for sub in family["subscores"] if sub["score"] > 0]
    missing = [sub["label"] for sub in family["subscores"] if sub["score"] == 0]
    parts = []
    if documented:
        parts.append(_lower_first(", ".join(documented[:3])) + (" documentés" if len(documented) > 1 else " documenté"))
    if missing:
        parts.append(_lower_first(", ".join(missing[:3])) + (" non documentés" if len(missing) > 1 else " non documenté"))
    return (" ; ".join(parts) or "aucun élément mesurable au dossier") + "."


def _lower_first(value: str) -> str:
    return value[:1].lower() + value[1:] if value else value


def _section_appreciation(ctx: _Context, assessment: dict) -> Section:
    section = Section("2", "Appréciation scientifique commune")
    score = assessment.get("score")
    if not score:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    rows = [
        [family["label"], str(family["max"]), str(family["score"]), _family_reason(family)]
        for family in score["families"]
    ]
    rows.append(
        [
            "TOTAL SCIENTIFIQUE",
            str(score["maximum"]),
            str(score["total"]),
            "Le score ne compense jamais une exigence réglementaire non satisfaite.",
        ]
    )
    section.table(
        f"Grille commune (version {score['grid_version']})",
        ["Dimension", "Max.", "Note", "Motif probant"],
        rows,
        widths=[0.26, 0.07, 0.07, 0.60],
    )
    section.para(
        SCORE_READING.format(total=score["total"], maximum=score["maximum"]),
        kind=ReportFactKind.CALCUL,
    )
    return section


# --------------------------------------------------------------------------
# 3. Matrice réglementaire uniforme
# --------------------------------------------------------------------------


def _short_labels() -> dict[str, str]:
    return {
        criterion["code"]: criterion.get("short_label", criterion["label"])
        for criterion in regulatory_engine.load_referential()["criteria"]
    }


def _section_matrice(ctx: _Context, assessment: dict) -> Section:
    section = Section("3", "Matrice réglementaire uniforme")
    criteria = assessment.get("criteria") or []
    if not criteria:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    short = _short_labels()
    rows = []
    for row in criteria:
        state = row["status"]
        if row.get("human_status"):
            state = f"{state}*"
        rows.append(
            [
                row["code"],
                short.get(row["code"], row["label"]),
                state,
                row["finding"],
                row["exact_source"],
            ]
        )

    version = criteria[0].get("referential_version", "—")
    # La légende précède le tableau dans le modèle, et c'est plus utile ainsi :
    # elle se lit avant les états qu'elle explique, pas après.
    section.para(MATRIX_LEGEND, kind=ReportFactKind.CALCUL)
    section.table(
        f"Les 26 critères communs (référentiel {version})",
        ["Réf.", "Critère commun", "État", "Constat / preuve au dossier", "Fondement"],
        rows,
        widths=[0.05, 0.20, 0.06, 0.42, 0.27],
    )
    return section


# --------------------------------------------------------------------------
# 4. Contrôle des intervenants étrangers
# --------------------------------------------------------------------------


def _section_intervenants(ctx: _Context) -> Section:
    section = Section("4", "Contrôle des intervenants étrangers")

    corroborated = [
        profile
        for profile in ctx.profiles
        if profile.status in {"SOURCE_OFFICIELLE_TROUVEE", "SOURCES_CONCORDANTES"}
    ]
    pending = [profile for profile in ctx.profiles if profile not in corroborated]

    if ctx.profiles:
        section.para(
            f"{len(ctx.profiles)} profil(s) affilié(s) à l'étranger ont été contrôlés : "
            f"{len(corroborated)} sont corroborés par une source publique, {len(pending)} "
            "exigent actualisation, attestation ou correction du champ scientifique.",
            kind=ReportFactKind.CALCUL,
        )
        section.table(
            "Profils contrôlés",
            ["Personne", "Affiliation déclarée", "État de la vérification"],
            [
                [profile.display_name, profile.declared_affiliation or NOT_PROVIDED, profile.status]
                for profile in ctx.profiles
            ],
            widths=[0.30, 0.40, 0.30],
        )
    else:
        section.para(
            "Aucune vérification publique n'a été menée ou aucune n'a abouti : la réputation "
            "internationale des intervenants n'est pas établie par l'application. Cette "
            "absence n'est pas un constat défavorable.",
            kind=ReportFactKind.A_VERIFIER,
        )

    # -- 4.1 Éléments relatifs au Maroc et à Israël ------------------------
    section.subheading("4.1. Éléments relatifs au Maroc et à Israël — information au ministère")
    sensitive = [
        finding for finding in ctx.findings if finding["category"] in SENSITIVE_CATEGORIES
    ]
    if sensitive:
        section.bullets(
            [
                f"{finding['label']} — {finding['explanation']} "
                f"(page {finding['page_no'] or '—'}, statut {finding['human_status']})."
                for finding in sensitive
            ]
        )
    else:
        section.bullets(
            [
                "Aucun participant n'est explicitement déclaré de nationalité marocaine ou "
                "israélienne dans les pièces lues, et aucune institution de ces deux pays "
                "n'est désignée comme partenaire de la manifestation projetée.",
                "L'absence de mention repérée ne prouve pas l'absence de lien : la détection "
                "est textuelle et ne couvre ni les drapeaux, ni les cartes, ni les logos, ni "
                "les tampons.",
            ]
        )
    urls = _facts_of(ctx).observations.get("urls") or []
    if urls:
        section.para("Sources spécifiques du contrôle :", kind=ReportFactKind.CALCUL)
        section.bullets([url for url in urls[:8]])
    section.box("Portée du contrôle", FOREIGN_SCOPE, tone="attention")
    return section


# --------------------------------------------------------------------------
# 5. Points de vigilance institutionnelle
# --------------------------------------------------------------------------


def _section_vigilance(ctx: _Context) -> Section:
    section = Section("5", "Points de vigilance institutionnelle")
    others = [
        finding for finding in ctx.findings if finding["category"] not in SENSITIVE_CATEGORIES
    ]
    if others:
        section.bullets(
            [
                f"{finding['label']} — {finding['recommended_check']} "
                f"(priorité {finding['priority']}, statut {finding['human_status']})."
                for finding in others
            ]
        )
    else:
        section.para(
            "Aucune alerte n'a été levée par le moteur de vigilance sur les pièces lues. "
            "L'absence d'alerte ne prouve pas l'absence de risque.",
            kind=ReportFactKind.ALERTE_SYSTEME,
        )
    return section


# --------------------------------------------------------------------------
# 6. Compléments indispensables
# --------------------------------------------------------------------------


#: Action attendue selon l'état du critère.
COMPLEMENT_ACTION = {
    "NC": "à produire",
    "NV": "à documenter",
    "PC": "à compléter",
}


#: Titres de la section 6, selon l'orientation. Ce n'est pas une nuance de
#: style : sous réserves, la manifestation peut se tenir et les points listés
#: sont des conditions préalables ; en ajournement, elle ne le peut pas et les
#: mêmes points sont des compléments à produire avant tout examen. Les douze
#: rapports du modèle appliquent cette règle sans exception.
COMPLEMENTS_TITLE = "Compléments indispensables avant appréciation ministérielle"
RESERVES_TITLE = "Réserves maintenues et conditions préalables à la tenue"


def _complements_title(assessment: dict) -> str:
    decision = assessment.get("decision") or {}
    chosen = decision.get("human_decision") or decision.get("avis")
    if chosen in {decision_engine.FAVORABLE, decision_engine.FAVORABLE_SOUS_RESERVES}:
        return RESERVES_TITLE
    return COMPLEMENTS_TITLE


def _section_complements(assessment: dict) -> Section:
    """Actions attendues, une ligne par critère.

    Le constat détaillé vit en section 3 : le répéter ici doublerait la longueur
    du rapport sans rien apprendre au lecteur.
    """
    section = Section("6", _complements_title(assessment))
    criteria = assessment.get("criteria") or []
    if not criteria:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    short = _short_labels()
    pending = [row for row in criteria if row["status"] in COMPLEMENT_ACTION]
    # D'abord ce qui bloque, puis le reste, chacun dans l'ordre du référentiel.
    pending.sort(key=lambda row: (not row["blocking"], row["order"]))
    if pending:
        # Puces courtes, comme le modèle : le constat détaillé et le caractère
        # bloquant de chaque point vivent en section 3 et dans l'interface. Les
        # répéter ici doublerait la longueur sans rien apprendre.
        section.bullets(
            [
                f"{row['code']} — {short.get(row['code'], row['label'])}"
                for row in pending
            ]
        )
    else:
        section.para(
            "Aucun complément n'est requis en l'état des constats.", kind=ReportFactKind.CALCUL
        )
    return section


# --------------------------------------------------------------------------
# 7. Orientation technique motivée
# --------------------------------------------------------------------------


def _section_orientation(assessment: dict) -> Section:
    section = Section("7", "Orientation technique motivée transmise au ministère")
    decision = assessment.get("decision")
    if not decision:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    retained = decision.get("human_decision")
    chosen = retained or decision["avis"]
    label = decision_engine.LABELS.get(chosen, chosen.replace("_", " ")).upper()
    section.para(
        f"{label}.",
        kind=ReportFactKind.CONCLUSION_EVALUATEUR if retained else ReportFactKind.CALCUL,
    )
    section.para(
        FAVORABLE_REASON if chosen == decision_engine.FAVORABLE else DECISION_REASON,
        kind=ReportFactKind.CALCUL,
    )
    if retained and retained != decision["avis"]:
        section.para(
            "Proposition de l'application : "
            f"{decision_engine.LABELS.get(decision['avis'], decision['avis'])}. "
            "L'orientation retenue ci-dessus est celle de l'évaluateur.",
            kind=ReportFactKind.CONCLUSION_EVALUATEUR,
        )
    return section


# --------------------------------------------------------------------------
# Détails de traçabilité — pour l'interface, plus pour le fichier
# --------------------------------------------------------------------------


def details(session: Session, dossier_id: str) -> dict:
    """Tout ce que le rapport ne porte plus, à destination de l'écran.

    Les douze rapports de la commission n'ont que sept sections : ni sources,
    ni règles de décision, ni contrôle en ligne des profils. Ces éléments ne
    sont pas pour autant sans valeur — ils fondent le rapport et doivent rester
    vérifiables. Ils quittent donc le document pour l'interface, où l'évaluateur
    peut les consulter sans alourdir la pièce transmise au ministère.
    """
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise ValueError("Dossier introuvable.")

    ctx = _Context(session, dossier)
    assessment = assessment_service.current_assessment(session, dossier_id)
    referential = regulatory_engine.load_referential()
    evidence = evidence_service.listing(session, dossier_id)
    decision = assessment.get("decision") or {}

    return {
        "sources": [
            f"Pièce source : {document.original_name} — SHA-256 {document.sha256[:16]}… "
            f"({dossier.page_count} pages), analysée selon la lisibilité disponible."
            for document in dossier.documents
        ]
        or ["Aucune pièce source n'est versée au dossier."],
        "fondements": [
            "Envoi n° 595/SG du 19 mai 2025 — critères et calendrier des manifestations "
            "scientifiques internationales.",
            "Envoi n° 218/DCEU-SDPUR du 14 juillet 2026 et Guide des manifestations "
            "internationales — procédure régionale.",
            "Dossier et formulaire de demande d'organisation — liste des pièces et canevas.",
        ],
        "versions": {
            "referentiel": referential["referential_version"],
            "grille": scientific_scoring.load_grid()["grid_version"],
            "application": get_settings().version,
        },
        "preuves": len(evidence),
        "regles_de_decision": [
            {
                "regle": rule["rule"],
                "motif": rule["explanation"],
                "criteres": rule["criteria"],
            }
            for rule in decision.get("triggered_rules") or []
        ],
        "controle_en_ligne": _screening_details(ctx),
        "contradictions": [
            {
                "id": item["id"],
                "sujet": item["subject"],
                "constat": item["statement"],
                "traitement": item.get("required_output", "CONTRADICTION_A_ARBITRER"),
            }
            for item in referential.get("known_contradictions") or []
        ],
        "desaccords_audit": [
            item
            for item in audit_service.listing(session, dossier_id)
            if not item["resolved"]
        ],
        "faits_orphelins": ctx.orphan_facts,
        "legendes": {
            "asterisque": "Un astérisque signale une valeur lue au dossier mais non encore "
            "confirmée par l'évaluateur. « Non renseigné » signifie que la pièce ne le "
            "documente pas, jamais que l'organisateur ne l'a pas prévu.",
            "score_zero": "Un élément non documenté vaut zéro : ce zéro constate l'absence "
            "de preuve au dossier et ne préjuge d'aucune incapacité réelle de "
            "l'organisateur.",
            "matrice": MATRIX_LEGEND,
        },
        "principe_probatoire": EVIDENCE_PRINCIPLE,
        "portee_controle": FOREIGN_SCOPE,
    }


def _screening_details(ctx: _Context) -> dict:
    """Contrôle en ligne des profils — sorti du rapport, conservé à l'écran."""
    claims = ctx.claim_texts(AgentName.SOUVERAINETE_NATIONALE)
    established = [claim for claim in claims if claim.nature != ClaimNature.ABSENCE_DE_PREUVE]
    return {
        "profils_controles": len({claim.subject_label for claim in claims}),
        "veille_executee": bool(claims),
        "elements": [
            {
                "personne": claim.subject_label,
                "element": ctx.claim_body(claim).split("\n", 1)[0],
                "sources_independantes": claim.independent_source_count,
                "niveau_de_preuve": claim.status,
            }
            for claim in established
        ],
        "constat": (
            "Aucun profil n'a été soumis à ce contrôle : la veille en ligne n'a pas été "
            "exécutée pour ce dossier, ou aucun intervenant étranger n'y a été identifié. "
            "Cette absence n'est ni un constat favorable, ni un constat défavorable."
            if not claims
            else (
                f"{len(established)} élément(s) publiquement documenté(s) sur "
                f"{len({claim.subject_label for claim in claims})} profil(s) contrôlés. "
                "Ils sont rapportés tels que publiés ; aucun n'est qualifié par "
                "l'application."
                if established
                else f"{len({claim.subject_label for claim in claims})} profil(s) contrôlés ; "
                "aucun rattachement institutionnel ni activité publique touchant une "
                "catégorie de vigilance nationale n'a été établi."
            )
        ),
    }
