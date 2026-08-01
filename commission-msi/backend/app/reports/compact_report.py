"""Rapport compact — trois pages (§15 du prompt maître).

Structure imposée :

* **Page 1** — identification, organisateur, dates, lieu, mode, participants,
  comité, budget, valorisation, score scientifique détaillé sur 100, résumé
  factuel bref et avis technique proposé clairement visible ;
* **Page 2** — la matrice des 26 critères, dans le même ordre, avec statut
  `C/PC/NC/NV`, constat précis, page ou preuve et fondement réglementaire exact ;
* **Page 3** — contrôle des intervenants étrangers, points de vigilance,
  contradictions et limites, compléments indispensables, avis motivé, sources
  et traçabilité, empreintes et versions.

Deux pages suffisent si tout reste lisible ; on dépasse trois pages seulement
lorsque les preuves ou les alertes l'exigent. **Rien n'est jamais tronqué pour
tenir dans un nombre de pages.**

Aucun numéro de passeport, aucune adresse privée, aucune donnée personnelle
inutile n'est reproduit : la section restreinte n'est mentionnée que par sa
présence et son statut.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import SIGNATURE, get_settings
from app.core.vocabulary import CRITERION_STATUS_LABELS, NOT_PROVIDED, ReportFactKind
from app.models import Dossier
from app.models import ProposedDecision as ProposedDecisionRow
from app.reports.evaluation_report import (
    Box,
    EvaluationReport,
    Section,
    _Context,
    format_date_fr,
)
from app.services import (
    assessment_service,
    audit_service,
    decision_engine,
    evidence_service,
    regulatory_engine,
    report_qa_service,
    scientific_scoring,
)

#: Ce que le rapport dit de lui-même, en tête de page 1.
COMPACT_SUBTITLE = (
    "Rapport technique d'évaluation — analyse automatique proposée, décision humaine réservée"
)

NO_ASSESSMENT = (
    "Aucune évaluation automatique n'a encore été exécutée pour ce dossier. Lancez "
    "« Traiter le dossier » : la matrice réglementaire, le score et l'avis proposé seront "
    "alors établis à partir des pièces versées."
)


def build(session: Session, dossier_id: str) -> EvaluationReport:
    settings = get_settings()
    dossier = session.get(Dossier, dossier_id)
    if dossier is None:
        raise ValueError("Dossier introuvable.")

    ctx = _Context(session, dossier)
    assessment = assessment_service.current_assessment(session, dossier_id)

    sections = [
        _page_one(ctx, assessment),
        _page_two(ctx, assessment),
        _page_three(ctx, assessment),
    ]

    return EvaluationReport(
        reference=dossier.reference,
        title=dossier.title,
        organizer=dossier.organizer,
        evaluator=settings.evaluator_label,
        generated_at=datetime.now(timezone.utc),
        version=settings.version,
        is_draft=dossier.report_validated_at is None,
        subtitle=COMPACT_SUBTITLE,
        sections=sections,
        orphan_facts=ctx.orphan_facts,
        headline=_headline(assessment),
        signature=SIGNATURE,
    )


def _headline(assessment: dict) -> Box:
    """Avis proposé, en tête et clairement visible — jamais présenté comme décidé."""
    decision = assessment.get("decision")
    if not decision:
        return Box(
            title="Avis technique — non encore établi",
            body=NO_ASSESSMENT,
            tone="attention",
        )
    retained = decision.get("human_decision")
    if retained:
        return Box(
            title=f"Avis retenu par l'évaluateur : {retained}",
            body=f"Proposition de l'application : {decision['label']}. "
            f"{decision['disclaimer']}",
            tone="neutre",
        )
    tone = {
        decision_engine.FAVORABLE: "neutre",
        decision_engine.FAVORABLE_SOUS_RESERVES: "attention",
        decision_engine.AJOURNEMENT_POUR_COMPLEMENTS: "attention",
        decision_engine.REQUALIFICATION_NATIONALE_A_EXAMINER: "attention",
        decision_engine.TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE: "critique",
        decision_engine.NON_DETERMINABLE_INFORMATION_INSUFFISANTE: "attention",
    }.get(decision["avis"], "attention")
    return Box(
        title=f"Avis technique proposé : {decision['label']}",
        body=f"{decision['motivation']} {decision['disclaimer']}",
        tone=tone,
    )


# --------------------------------------------------------------------------
# Page 1 — informations et appréciation scientifique
# --------------------------------------------------------------------------


def _page_one(ctx: _Context, assessment: dict) -> Section:
    section = Section("1", "Informations et appréciation scientifique")

    rows: list[list[str]] = []
    for key, label in (
        ("intitule", "Intitulé"),
        ("type_manifestation", "Type"),
        ("etablissement_organisateur", "Établissement organisateur"),
        ("structure_porteuse", "Structure porteuse"),
        ("date_debut", "Date d'ouverture"),
        ("date_fin", "Date de clôture"),
        ("lieu", "Lieu"),
        ("format", "Mode d'organisation"),
        ("responsable_scientifique", "Responsable scientifique"),
        ("comite_scientifique", "Comité scientifique"),
        ("comite_organisation", "Comité d'organisation"),
        ("intervenants", "Intervenants annoncés"),
        ("pays_representes", "Pays représentés"),
        ("budget_total", "Budget total déclaré"),
        ("financeurs", "Sources de financement"),
        ("modalites_publication", "Valorisation prévue"),
    ):
        value, page_no, _retained = ctx.value(key)
        rows.append([label, value, f"page {page_no}" if page_no else "—"])

    section.table(
        "Identification du dossier",
        ["Rubrique", "Valeur au dossier", "Source"],
        rows,
        note="Une valeur non confirmée est affichée avec son statut réel : l'application ne "
        "présente jamais une proposition comme un fait établi.",
    )

    score = assessment.get("score")
    if not score:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    section.subheading(f"Score scientifique proposé : {score['total']}/{score['maximum']}")
    score_rows = []
    for family in score["families"]:
        score_rows.append(
            [family["label"], f"{family['score']}/{family['max']}", "", ""]
        )
        for sub in family["subscores"]:
            evidence = ", ".join(sub["evidence_ids"][:3]) or "—"
            score_rows.append(
                [f"    {sub['label']}", f"{sub['score']}/{sub['max']}", sub["justification"], evidence]
            )
    section.table(
        f"Grille scientifique (version {score['grid_version']})",
        ["Critère", "Note", "Justification", "Preuves"],
        score_rows,
        note="Un élément non documenté vaut zéro, avec la mention explicite « non documenté » ; "
        "ce zéro ne préjuge d'aucune incapacité réelle de l'organisateur. Les totaux sont "
        "recalculés localement à chaque édition.",
    )

    section.subheading("Résumé factuel")
    section.para(_factual_summary(ctx, assessment), kind=ReportFactKind.CALCUL)
    return section


def _factual_summary(ctx: _Context, assessment: dict) -> str:
    """Résumé strictement factuel : rien qui ne soit lisible dans le dossier."""
    title, _, _ = ctx.value("intitule")
    place, _, _ = ctx.value("lieu")
    start, _, _ = ctx.value("date_debut")
    end, _, _ = ctx.value("date_fin")
    mode, _, _ = ctx.value("format")

    counts = (assessment.get("summary") or {}).get("counts") if assessment else None
    if counts is None:
        criteria = assessment.get("criteria") or []
        counts = {
            status: sum(1 for row in criteria if row["status"] == status)
            for status in ("C", "PC", "NC", "NV")
        }
    score = assessment.get("score") or {}

    period = (
        f"du {start} au {end}"
        if start != NOT_PROVIDED and end != NOT_PROVIDED
        else "à des dates non renseignées au dossier"
    )
    return (
        f"Le dossier porte sur « {title} », prévu {period} à {place}, en mode {mode}. "
        f"Sur les 26 critères réglementaires, {counts.get('C', 0)} sont conformes, "
        f"{counts.get('PC', 0)} partiellement conformes, {counts.get('NC', 0)} non conformes "
        f"et {counts.get('NV', 0)} non vérifiables en l'état des pièces versées. "
        f"Le score scientifique proposé s'établit à {score.get('total', '—')}/"
        f"{score.get('maximum', 100)}. Ces constats décrivent le dossier tel qu'il a été "
        "déposé ; ils n'anticipent aucune décision."
    )


# --------------------------------------------------------------------------
# Page 2 — matrice réglementaire
# --------------------------------------------------------------------------


def _page_two(ctx: _Context, assessment: dict) -> Section:
    section = Section("2", "Matrice réglementaire — 26 critères")
    criteria = assessment.get("criteria") or []
    if not criteria:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)
        return section

    rows = []
    for row in criteria:
        status = row["status"]
        label = f"{status} — {CRITERION_STATUS_LABELS.get(status, status)}"
        if row.get("human_status"):
            label += f" (qualifié par l'évaluateur ; proposition : {row['proposed_status']})"
        evidence = ", ".join(row["evidence_ids"][:3]) or "—"
        source = f"page {row['page']}" if row["page"] else "—"
        rows.append(
            [
                row["code"],
                row["label"],
                label,
                row["finding"],
                f"{evidence} / {source}",
                row["exact_source"],
            ]
        )

    version = criteria[0].get("referential_version", "—")
    section.table(
        f"Constats réglementaires (référentiel {version})",
        ["Code", "Critère", "Statut", "Constat", "Preuve / page", "Fondement exact"],
        rows,
        note="Aucune cellule n'est laissée vide. « NV » signifie que le dossier ne permet pas "
        "de vérifier le critère : ce n'est ni une conformité, ni une non-conformité.",
    )
    return section


# --------------------------------------------------------------------------
# Page 3 — vérifications et conclusion
# --------------------------------------------------------------------------


def _page_three(ctx: _Context, assessment: dict) -> Section:
    section = Section("3", "Vérifications, limites et conclusion")

    # -- intervenants étrangers ------------------------------------------
    section.subheading("Contrôle des intervenants étrangers")
    if ctx.profiles:
        section.table(
            "Profils recherchés dans les sources publiques",
            ["Personne", "Affiliation déclarée", "Statut de vérification"],
            [
                [
                    profile.display_name,
                    profile.declared_affiliation or "—",
                    profile.status,
                ]
                for profile in ctx.profiles
            ],
            note="Une recherche publique ne porte que sur des identités professionnelles et des "
            "informations déjà publiques. L'absence de résultat ne prouve ni l'absence "
            "d'activité, ni l'absence de risque. Le risque d'homonymie subsiste.",
        )
    else:
        section.para(
            "Aucune vérification publique n'a été menée ou aucune n'a abouti : la réputation "
            "internationale des intervenants n'est pas établie par l'application. Cette "
            "absence n'est pas un constat défavorable.",
            kind=ReportFactKind.A_VERIFIER,
        )
    section.para(
        "Aucun numéro de passeport, aucune adresse privée ni donnée personnelle inutile n'est "
        "reproduit dans ce rapport. Les pièces d'identité restent en section restreinte, "
        "chiffrées, et ne sont jamais transmises à l'extérieur.",
        kind=ReportFactKind.CALCUL,
    )

    # -- vigilance institutionnelle ---------------------------------------
    section.subheading("Points de vigilance institutionnelle")
    open_findings = [item for item in ctx.findings if item["human_status"] == "A_VERIFIER"]
    if ctx.findings:
        section.table(
            "Alertes du moteur de vigilance",
            ["Catégorie", "Alerte", "Priorité", "Statut", "Page"],
            [
                [
                    item["category"],
                    item["label"],
                    item["priority"],
                    item["human_status"],
                    str(item["page_no"] or "—"),
                ]
                for item in ctx.findings
            ],
            note=f"{len(open_findings)} alerte(s) restent à qualifier. La qualification "
            "juridique ou diplomatique relève des seules autorités compétentes ; "
            "l'application signale, elle ne qualifie pas.",
        )
    else:
        section.para(
            "Aucune alerte n'a été levée par le moteur de vigilance. L'absence d'alerte ne "
            "prouve pas l'absence de risque.",
            kind=ReportFactKind.ALERTE_SYSTEME,
        )

    # -- contradictions et limites ----------------------------------------
    section.subheading("Contradictions et limites")
    disagreements = audit_service.listing(ctx.session, ctx.dossier.id)
    unresolved = [item for item in disagreements if not item["resolved"]]
    if unresolved:
        section.table(
            "Désaccords de la relecture indépendante",
            ["Critère", "Première analyse", "Relecture", "Effet"],
            [
                [
                    item["criterion_code"] or "—",
                    item["analyst_value"],
                    item["auditor_value"],
                    "Critère classé « non vérifiable »",
                ]
                for item in unresolved
            ],
            note="Aucune moyenne n'est faite entre deux analyses divergentes : l'arbitrage "
            "revient à l'évaluateur.",
        )
    else:
        section.para(
            "La relecture indépendante ne relève aucun désaccord non résolu sur les faits "
            "courants.",
            kind=ReportFactKind.CALCUL,
        )

    known = regulatory_engine.load_referential().get("known_contradictions") or []
    if known:
        section.bullets(
            [
                f"{item['id']} — {item['subject']} : {item['statement']} "
                "Contradiction enregistrée et jamais résolue par supposition ; "
                "l'arbitrage relève de l'autorité compétente."
                if item.get("resolution_forbidden")
                else f"{item['id']} — {item['subject']} : {item['statement']}"
                for item in known
            ]
        )

    # -- compléments indispensables ----------------------------------------
    decision = assessment.get("decision")
    section.subheading("Compléments indispensables")
    if decision and decision["required_complements"]:
        section.bullets(decision["required_complements"])
    elif decision and decision["reserves"]:
        section.para(
            "Aucune pièce obligatoire ne manque. Les réserves listées ci-dessous doivent être "
            "levées avant la tenue de la manifestation.",
            kind=ReportFactKind.CALCUL,
        )
        section.bullets(decision["reserves"])
    else:
        section.para(
            "Aucun complément n'est requis en l'état des constats.",
            kind=ReportFactKind.CALCUL,
        )

    # -- avis motivé --------------------------------------------------------
    section.subheading("Avis motivé")
    if decision:
        section.box(
            f"Avis technique proposé : {decision['label']}",
            f"{decision['motivation']}\n\n{decision['disclaimer']}",
            tone="attention",
        )
        section.table(
            "Règles de décision déclenchées",
            ["Règle", "Motif", "Critères déclencheurs"],
            [
                [rule["rule"], rule["explanation"], ", ".join(rule["criteria"]) or "—"]
                for rule in decision["triggered_rules"]
            ],
            note="Chaque règle enregistre ses critères déclencheurs et leurs preuves : le "
            "raisonnement est vérifiable ligne à ligne.",
        )
        if ctx.conclusion:
            section.para(
                f"Conclusion retenue par l'évaluateur : {ctx.conclusion['conclusion']}.",
                kind=ReportFactKind.CONCLUSION_EVALUATEUR,
            )
        else:
            section.para(
                "Aucune conclusion humaine n'a encore été enregistrée. L'avis ci-dessus reste "
                "une proposition de l'application.",
                kind=ReportFactKind.A_VERIFIER,
            )
    else:
        section.para(NO_ASSESSMENT, kind=ReportFactKind.A_VERIFIER)

    # -- sources, traçabilité, empreintes ----------------------------------
    section.subheading("Sources, traçabilité, empreintes et versions")
    evidence = evidence_service.listing(ctx.session, ctx.dossier.id)
    section.table(
        "Registre de preuves",
        ["Référence", "Origine", "Localisation", "Empreinte SHA-256"],
        [
            [
                item["reference"],
                item["kind"],
                item["locator"] or "—",
                (item["content_sha256"] or "—")[:16] + "…",
            ]
            for item in evidence[:40]
        ],
        note=f"{len(evidence)} preuve(s) au registre. Chaque fait de ce rapport renvoie à l'une "
        "d'elles, consultable dans l'application par « Voir les preuves ».",
    )

    qa = report_qa_service.latest(ctx.session, ctx.dossier.id)
    versions = [
        f"Application : version {get_settings().version}.",
        f"Référentiel réglementaire : version "
        f"{regulatory_engine.load_referential()['referential_version']}.",
        f"Grille scientifique : version {scientific_scoring.load_grid()['grid_version']}.",
        f"Documents versés : "
        + ", ".join(
            f"{document.original_name} — SHA-256 {document.sha256[:16]}…"
            for document in ctx.dossier.documents
        )
        or "aucun document versé.",
    ]
    if qa:
        versions.append(
            f"Contrôle qualité du rapport : {len(qa['checks'])} contrôle(s), "
            f"{qa['failures']} échec(s) bloquant(s), verdict "
            f"{'conforme' if qa['passed'] else 'non conforme'}."
        )
    section.bullets(versions)
    section.para(
        f"Rapport établi le {format_date_fr(datetime.now(timezone.utc))} par "
        f"{get_settings().evaluator_label}. {SIGNATURE}.",
        kind=ReportFactKind.CALCUL,
    )
    return section
