"""Rapport d'évaluation **harmonisé** — format du modèle fourni par la commission.

Huit sections, dans cet ordre imposé :

1. fiche d'information contrôlée — six rubriques condensées, pas un vidage de champs ;
2. appréciation scientifique commune — cinq dimensions sur 100, avec motif probant ;
3. matrice réglementaire uniforme — les 26 critères, `C/PC/NC/NV`, constat, fondement ;
4. contrôle des intervenants étrangers, dont **4.1 éléments relatifs au Maroc et
   à Israël** relevés dans les pièces, et **4.2 contrôle en ligne des profils**
   — rattachements institutionnels et activités publics, signalés à titre
   strictement informatif ;
5. points de vigilance institutionnelle ;
6. compléments indispensables avant appréciation ministérielle ;
7. orientation technique motivée transmise au ministère ;
8. sources et traçabilité, avec le principe probatoire.

Deux différences de fond avec un rapport d'analyse ordinaire, et elles sont
délibérées :

* le vocabulaire est celui de l'**orientation technique** transmise au
  ministère, jamais celui d'une décision. « La décision finale appartient au
  ministère » figure en tête, en section 7, et dans les encadrés de portée ;
* aucune nationalité, origine ou opinion supposée ne fonde un constat
  défavorable. Les éléments des sections 4.1 et 4.2 sont informatifs : les
  qualifier relève du ministère seul, et la section 4.2 énonce explicitement
  les critères qu'elle refuse d'appliquer.
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

TITLE = "RAPPORT D'ÉVALUATION HARMONISÉ"

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
    "d'un nom, une opinion supposée. Les éléments des sections 4.1 et 4.2 sont signalés à "
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
        _section_sources(ctx),
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
        headline=_headline(assessment),
        signature=SIGNATURE,
        density="compact",
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
    """Sous-titre : lieu, dates et pièce évaluée, comme en tête du modèle."""
    place = _plain(ctx, "lieu")
    start = _plain(ctx, "date_debut")
    end = _plain(ctx, "date_fin")
    when = f"{start} — {end}" if start != NOT_PROVIDED and end != NOT_PROVIDED else "dates non renseignées"

    documents = list(ctx.dossier.documents)
    if documents:
        pieces = " ; ".join(
            f"{document.original_name} ({ctx.dossier.page_count} pages)" for document in documents[:2]
        )
    else:
        pieces = "aucune pièce versée"
    return f"{place} — {when} · Pièce évaluée : {pieces}"


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
    section.table(
        "Rubriques contrôlées",
        ["Rubrique", "Élément retenu au dossier"],
        [
            [label, f"{value}\u00a0*" if pending and value != NOT_PROVIDED else value]
            for label, value, pending in rows
        ],
        note="Un astérisque signale une valeur lue au dossier mais non encore confirmée par "
        "l'évaluateur. « Non renseigné » signifie que la pièce ne le documente pas, jamais "
        "que l'organisateur ne l'a pas prévu.",
        widths=[0.20, 0.80],
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
        note="Un élément non documenté vaut zéro : ce zéro constate l'absence de preuve au "
        "dossier et ne préjuge d'aucune incapacité réelle de l'organisateur.",
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
    section.table(
        f"Les 26 critères communs (référentiel {version})",
        ["Réf.", "Critère commun", "État", "Constat / preuve au dossier", "Fondement"],
        rows,
        note=f"{MATRIX_LEGEND} Un état suivi d'un astérisque a été qualifié par l'évaluateur.",
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
    # -- 4.2 Contrôle en ligne des profils ---------------------------------
    _subsection_screening(ctx, section)

    urls = _facts_of(ctx).observations.get("urls") or []
    if urls:
        section.para("Sources spécifiques du contrôle :", kind=ReportFactKind.CALCUL)
        section.bullets([url for url in urls[:8]])
    section.box("Portée du contrôle", FOREIGN_SCOPE, tone="attention")
    return section


def _subsection_screening(ctx: _Context, section: Section) -> None:
    """4.2 — ce que la veille en ligne a établi sur les profils, et rien de plus.

    Deux principes gouvernent cette sous-section, et ils viennent du référentiel
    de l'application, non d'une prudence ajoutée : un rattachement ou une
    activité publiquement documentés se rapportent, une origine ne s'examine
    pas. Ce second principe est énoncé au lecteur dans l'encadré de portée qui
    clôt la section 4 — sans quoi il pourrait prêter à l'application un
    profilage qu'elle n'exerce pas.
    """
    section.subheading(
        "4.2. Contrôle en ligne des profils — rattachements et activités publics"
    )

    claims = ctx.claim_texts(AgentName.SOUVERAINETE_NATIONALE)
    established = [claim for claim in claims if claim.nature != ClaimNature.ABSENCE_DE_PREUVE]

    if not claims:
        section.para(
            "Aucun profil n'a été soumis à ce contrôle : la veille en ligne n'a pas été "
            "exécutée pour ce dossier, ou aucun intervenant étranger n'y a été identifié. "
            "Cette absence n'est ni un constat favorable, ni un constat défavorable.",
            kind=ReportFactKind.A_VERIFIER,
        )
    elif not established:
        section.para(
            f"{len({claim.subject_label for claim in claims})} profil(s) ont été contrôlés ; "
            "aucun rattachement institutionnel ni activité publique touchant une catégorie "
            "de vigilance nationale n'a été établi sur les sources consultées.",
            kind=ReportFactKind.CALCUL,
        )
    else:
        section.para(
            f"{len(established)} élément(s) publiquement documenté(s) sont portés à la "
            f"connaissance du ministère, sur {len({claim.subject_label for claim in claims})} "
            "profil(s) contrôlés. Ils sont rapportés tels que publiés, avec leur niveau de "
            "preuve ; aucun n'est qualifié par l'application.",
            kind=ReportFactKind.CALCUL,
        )
        section.table(
            "Éléments relevés sur les profils publics",
            ["Personne", "Élément relevé", "Sources indép.", "Niveau de preuve"],
            [
                [
                    claim.subject_label,
                    # Le corps stocké porte l'affirmation puis sa mention de
                    # portée ; celle-ci figure déjà dans l'encadré, la répéter
                    # dans chaque cellule rendrait le tableau illisible.
                    ctx.claim_body(claim).split("\n", 1)[0],
                    str(claim.independent_source_count),
                    claim.status,
                ]
                for claim in established
            ],
            widths=[0.22, 0.50, 0.10, 0.18],
        )


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


def _section_complements(assessment: dict) -> Section:
    """Actions attendues, une ligne par critère.

    Le constat détaillé vit en section 3 : le répéter ici doublerait la longueur
    du rapport sans rien apprendre au lecteur.
    """
    section = Section("6", "Compléments indispensables avant appréciation ministérielle")
    criteria = assessment.get("criteria") or []
    if not criteria:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    short = _short_labels()
    pending = [row for row in criteria if row["status"] in COMPLEMENT_ACTION]
    # D'abord ce qui bloque, puis le reste, chacun dans l'ordre du référentiel.
    pending.sort(key=lambda row: (not row["blocking"], row["order"]))
    if pending:
        section.bullets(
            [
                f"{row['code']} — {short.get(row['code'], row['label'])} : "
                f"{COMPLEMENT_ACTION[row['status']]}"
                + (" (bloquant)." if row["blocking"] else ".")
                for row in pending
            ]
        )
        section.para(
            f"{len(pending)} complément(s) attendus, dont "
            f"{sum(1 for row in pending if row['blocking'])} sur un critère bloquant. "
            "Le constat détaillé de chacun figure en section 3.",
            kind=ReportFactKind.CALCUL,
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
    section.table(
        "Règles de décision déclenchées",
        ["Règle", "Motif", "Critères"],
        [
            [rule["rule"], rule["explanation"], ", ".join(rule["criteria"]) or "—"]
            for rule in decision["triggered_rules"]
        ],
        note="Chaque règle enregistre ses critères déclencheurs et leurs preuves : "
        "le raisonnement est vérifiable ligne à ligne.",
        widths=[0.22, 0.62, 0.16],
    )
    return section


# --------------------------------------------------------------------------
# 8. Sources et traçabilité
# --------------------------------------------------------------------------


def _section_sources(ctx: _Context) -> Section:
    section = Section("8", "Sources et traçabilité")

    documents = [
        f"Pièce source : {document.original_name} — SHA-256 {document.sha256[:16]}… "
        f"({ctx.dossier.page_count} pages), analysée selon la lisibilité disponible."
        for document in ctx.dossier.documents
    ] or ["Aucune pièce source n'est versée au dossier."]

    referential = regulatory_engine.load_referential()
    evidence = evidence_service.listing(ctx.session, ctx.dossier.id)
    disagreements = [
        item for item in audit_service.listing(ctx.session, ctx.dossier.id) if not item["resolved"]
    ]

    section.bullets(
        documents
        + [
            "Envoi n° 595/SG du 19 mai 2025 — critères et calendrier des manifestations "
            "scientifiques internationales.",
            "Envoi n° 218/DCEU-SDPUR du 14 juillet 2026 et Guide des manifestations "
            "internationales — procédure régionale.",
            "Dossier et formulaire de demande d'organisation — liste des pièces et canevas.",
            f"Référentiel réglementaire appliqué : version {referential['referential_version']} "
            f"({referential.get('snapshot_label', 'instantané local')}).",
            f"Grille scientifique appliquée : version {scientific_scoring.load_grid()['grid_version']}.",
            f"Registre de preuves : {len(evidence)} preuve(s) citables, consultables dans "
            "l'application par « Voir les preuves ».",
            f"Application locale, version {get_settings().version}.",
        ]
    )

    for contradiction in referential.get("known_contradictions") or []:
        section.para(
            f"Contradiction enregistrée {contradiction['id']} — {contradiction['subject']} : "
            f"{contradiction['statement']} Elle n'est jamais résolue par supposition ; "
            "l'arbitrage relève de l'autorité compétente.",
            kind=ReportFactKind.ALERTE_SYSTEME,
        )

    if disagreements:
        section.para(
            f"{len(disagreements)} désaccord(s) non résolu(s) entre l'analyse et sa relecture "
            "indépendante : les critères concernés sont classés « non vérifiable ». Aucune "
            "moyenne n'est faite entre deux analyses divergentes.",
            kind=ReportFactKind.ALERTE_SYSTEME,
        )

    section.box("Principe probatoire", EVIDENCE_PRINCIPLE, tone="neutre")
    return section
