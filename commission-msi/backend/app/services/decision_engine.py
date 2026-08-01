"""Moteur déterministe de proposition d'avis technique (§14 du prompt maître).

L'avis est choisi dans une **liste fermée**. Il est proposé, motivé, et
enregistre systématiquement les critères déclencheurs et leurs preuves.

Règles appliquées, dans cet ordre exact :

1. un critère obligatoire `NC` ou `NV` entraîne normalement
   `AJOURNEMENT_POUR_COMPLEMENTS` ;
2. un score scientifique élevé ne neutralise **jamais** cette règle ;
3. instruction complète mais caractère international non atteint →
   `REQUALIFICATION_NATIONALE_A_EXAMINER` ;
4. `FAVORABLE` exige que toutes les exigences obligatoires soient démontrées ;
5. `FAVORABLE_SOUS_RESERVES` n'est possible que pour des réserves non
   bloquantes, précises et vérifiables ;
6. une alerte publique grave, pertinente et suffisamment prouvée peut conduire
   à une transmission motivée — jamais à une culpabilité ni à un rejet ;
7. toute règle déclenchée est enregistrée avec ses critères et ses preuves.

Aucun modèle génératif n'intervient : l'avis est une fonction pure des statuts
réglementaires, des alertes qualifiées et de la complétude de l'instruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.regulatory_engine import CriterionResult, Status

#: Liste fermée des avis que l'application peut proposer.
FAVORABLE = "FAVORABLE"
FAVORABLE_SOUS_RESERVES = "FAVORABLE_SOUS_RESERVES"
AJOURNEMENT_POUR_COMPLEMENTS = "AJOURNEMENT_POUR_COMPLEMENTS"
REQUALIFICATION_NATIONALE_A_EXAMINER = "REQUALIFICATION_NATIONALE_A_EXAMINER"
TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE = "TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE"
NON_DETERMINABLE_INFORMATION_INSUFFISANTE = "NON_DETERMINABLE_INFORMATION_INSUFFISANTE"

CLOSED_LIST: tuple[str, ...] = (
    FAVORABLE,
    FAVORABLE_SOUS_RESERVES,
    AJOURNEMENT_POUR_COMPLEMENTS,
    REQUALIFICATION_NATIONALE_A_EXAMINER,
    TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE,
    NON_DETERMINABLE_INFORMATION_INSUFFISANTE,
)

LABELS: dict[str, str] = {
    FAVORABLE: "Avis favorable",
    FAVORABLE_SOUS_RESERVES: "Avis favorable sous réserves",
    AJOURNEMENT_POUR_COMPLEMENTS: "Ajournement pour compléments",
    REQUALIFICATION_NATIONALE_A_EXAMINER: "Requalification nationale à examiner",
    TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE: "Transmission à la tutelle avec alerte motivée",
    NON_DETERMINABLE_INFORMATION_INSUFFISANTE: "Non déterminable — information insuffisante",
}

#: Mention obligatoire du rapport (§14).
DISCLAIMER = (
    "Avis technique proposé par l'application — aide à la décision, ne valant pas "
    "décision officielle de la commission ou de la tutelle."
)

#: Seuil au-delà duquel l'instruction est jugée trop lacunaire pour conclure.
UNDETERMINABLE_NV_RATIO = 0.5

#: Familles portant le caractère international de la manifestation.
INTERNATIONAL_FAMILY = "INTERNATIONAL"

#: Gravités d'alerte pouvant fonder une transmission motivée.
SEVERE_PRIORITIES = frozenset({"CRITIQUE", "ELEVE"})

#: Seuls les constats qualifiés par un humain peuvent fonder une transmission.
CONFIRMED_FINDING_STATUSES = frozenset({"CONFIRME", "TRANSMIS"})


@dataclass
class TriggeredRule:
    """Trace d'une règle appliquée : elle est vérifiable ligne à ligne."""

    rule: str
    explanation: str
    criteria: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)


@dataclass
class ProposedDecision:
    avis: str
    label: str
    motivation: str
    triggered_rules: list[TriggeredRule]
    blocking_criteria: list[str]
    reserves: list[str]
    required_complements: list[str]
    disclaimer: str = DISCLAIMER

    def __post_init__(self) -> None:
        if self.avis not in CLOSED_LIST:
            raise ValueError(
                f"Avis « {self.avis} » hors de la liste fermée : le moteur ne peut pas "
                "produire de valeur inventée."
            )


def _complement_sentence(result: CriterionResult) -> str:
    verb = "à produire" if result.status == Status.NC else "à documenter"
    return f"{result.code} — {result.label} : {verb}. {result.finding}"


def propose(
    results: list[CriterionResult],
    *,
    scientific_total: int | None = None,
    findings: list[dict] | None = None,
    unresolved_disagreements: list[dict] | None = None,
) -> ProposedDecision:
    """Retourne l'avis proposé, motivé et tracé.

    `results` : les 26 constats réglementaires ;
    `scientific_total` : le score sur 100, jamais utilisé pour neutraliser une
    non-conformité ;
    `findings` : les alertes de vigilance **telles que qualifiées par l'humain** ;
    `unresolved_disagreements` : désaccords d'audit non résolus.
    """
    findings = findings or []
    unresolved_disagreements = unresolved_disagreements or []
    rules: list[TriggeredRule] = []

    mandatory = [r for r in results if r.nature == "OBLIGATOIRE"]
    blocking_ko = [r for r in results if r.blocking and r.status in {Status.NC, Status.NV}]
    mandatory_ko = [r for r in mandatory if r.status in {Status.NC, Status.NV}]
    partial = [r for r in results if r.status == Status.PC]
    non_evaluable = [r for r in results if r.status == Status.NV]

    reserves = [f"{r.code} — {r.label} : {r.finding}" for r in partial]
    complements = [_complement_sentence(r) for r in mandatory_ko]

    # --- Règle 7 : la trace du score est enregistrée, sans effet neutralisant.
    if scientific_total is not None:
        rules.append(
            TriggeredRule(
                rule="R2_SCORE_NON_NEUTRALISANT",
                explanation=f"Score scientifique proposé : {scientific_total}/100. Conformément "
                "au référentiel, un score élevé ne neutralise aucune non-conformité "
                "réglementaire et n'entre pas dans le choix de l'avis.",
            )
        )

    # --- Instruction trop lacunaire pour conclure.
    nv_ratio = len(non_evaluable) / len(results) if results else 1.0
    if not results or nv_ratio >= UNDETERMINABLE_NV_RATIO:
        rules.append(
            TriggeredRule(
                rule="R0_INSTRUCTION_INSUFFISANTE",
                explanation=f"{len(non_evaluable)} critère(s) sur {len(results) or 0} sont non "
                f"vérifiables ({nv_ratio:.0%}) : l'instruction ne permet pas de se prononcer, "
                "ni favorablement ni défavorablement.",
                criteria=[r.code for r in non_evaluable],
                evidence_ids=[eid for r in non_evaluable for eid in r.evidence_ids],
            )
        )
        return ProposedDecision(
            avis=NON_DETERMINABLE_INFORMATION_INSUFFISANTE,
            label=LABELS[NON_DETERMINABLE_INFORMATION_INSUFFISANTE],
            motivation="L'instruction est trop lacunaire pour qu'un avis puisse être proposé. "
            "Les pièces et informations manquantes sont listées ci-dessous ; leur absence "
            "n'est pas un motif de rejet.",
            triggered_rules=rules,
            blocking_criteria=[r.code for r in blocking_ko],
            reserves=reserves,
            required_complements=complements or [_complement_sentence(r) for r in non_evaluable],
        )

    # --- Désaccord d'audit non résolu : rien ne peut être conclu sur ce point.
    if unresolved_disagreements:
        codes = sorted({str(item.get("criterion_code") or "—") for item in unresolved_disagreements})
        rules.append(
            TriggeredRule(
                rule="R8_DESACCORD_AUDIT_NON_RESOLU",
                explanation=f"{len(unresolved_disagreements)} désaccord(s) d'audit non résolu(s) "
                f"({', '.join(codes)}) : ces points sont classés NV, aucune moyenne n'est "
                "faite entre les deux analyses.",
                criteria=codes,
            )
        )

    # --- Règle 6 : alerte publique grave, prouvée et qualifiée par un humain.
    severe = [
        finding
        for finding in findings
        if str(finding.get("status")) in CONFIRMED_FINDING_STATUSES
        and str(finding.get("priority")) in SEVERE_PRIORITIES
    ]
    if severe:
        rules.append(
            TriggeredRule(
                rule="R6_ALERTE_GRAVE_PROUVEE",
                explanation=f"{len(severe)} alerte(s) de vigilance qualifiée(s) par l'évaluateur "
                "au niveau élevé ou critique. La transmission motivée à la tutelle est "
                "proposée : elle ne constitue ni une culpabilité, ni un rejet, et la "
                "qualification juridique appartient aux autorités compétentes.",
                criteria=[str(finding.get("rule_code") or finding.get("id") or "—") for finding in severe],
                evidence_ids=[
                    str(finding["evidence_id"]) for finding in severe if finding.get("evidence_id")
                ],
            )
        )
        return ProposedDecision(
            avis=TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE,
            label=LABELS[TRANSMISSION_TUTELLE_AVEC_ALERTE_MOTIVEE],
            motivation="Une ou plusieurs alertes de vigilance qualifiées comme graves par "
            "l'évaluateur justifient une transmission motivée à l'autorité de tutelle, "
            "accompagnée du dossier complet et des constats réglementaires.",
            triggered_rules=rules,
            blocking_criteria=[r.code for r in blocking_ko],
            reserves=reserves,
            required_complements=complements,
        )

    # --- Règle 1 : un critère obligatoire NC ou NV → ajournement.
    if mandatory_ko:
        international_ko = [r for r in mandatory_ko if r.family == INTERNATIONAL_FAMILY]
        administrative_ko = [r for r in mandatory_ko if r.family != INTERNATIONAL_FAMILY]

        # --- Règle 3 : instruction complète, mais caractère international non atteint.
        if international_ko and not administrative_ko and not any(
            r.status == Status.NV for r in international_ko
        ):
            rules.append(
                TriggeredRule(
                    rule="R3_REQUALIFICATION_NATIONALE",
                    explanation="L'instruction administrative est complète, mais "
                    f"{len(international_ko)} condition(s) propre(s) au caractère international "
                    "ne sont pas atteintes. Une requalification en manifestation nationale "
                    "peut être examinée ; elle relève de la commission.",
                    criteria=[r.code for r in international_ko],
                    evidence_ids=[eid for r in international_ko for eid in r.evidence_ids],
                )
            )
            return ProposedDecision(
                avis=REQUALIFICATION_NATIONALE_A_EXAMINER,
                label=LABELS[REQUALIFICATION_NATIONALE_A_EXAMINER],
                motivation="Le dossier est instruit et documenté, mais les conditions du "
                "caractère international ne sont pas réunies en l'état. L'examen d'une "
                "requalification nationale est proposé, sans préjuger de la décision.",
                triggered_rules=rules,
                blocking_criteria=[r.code for r in blocking_ko],
                reserves=reserves,
                required_complements=complements,
            )

        rules.append(
            TriggeredRule(
                rule="R1_CRITERE_OBLIGATOIRE_NON_SATISFAIT",
                explanation=f"{len(mandatory_ko)} critère(s) obligatoire(s) au statut NC ou NV : "
                "l'ajournement pour compléments est la suite normale. Les pièces attendues "
                "sont listées ; leur production peut lever l'ajournement.",
                criteria=[r.code for r in mandatory_ko],
                evidence_ids=[eid for r in mandatory_ko for eid in r.evidence_ids],
            )
        )
        return ProposedDecision(
            avis=AJOURNEMENT_POUR_COMPLEMENTS,
            label=LABELS[AJOURNEMENT_POUR_COMPLEMENTS],
            motivation="Des exigences obligatoires ne sont pas démontrées en l'état du dossier. "
            "L'ajournement permet à l'organisateur de produire les compléments listés ; il ne "
            "constitue pas un refus.",
            triggered_rules=rules,
            blocking_criteria=[r.code for r in blocking_ko],
            reserves=reserves,
            required_complements=complements,
        )

    # --- Règle 5 : réserves non bloquantes, précises et vérifiables.
    if partial:
        rules.append(
            TriggeredRule(
                rule="R5_RESERVES_NON_BLOQUANTES",
                explanation=f"Toutes les exigences obligatoires sont satisfaites ; "
                f"{len(partial)} critère(s) restent partiellement conformes. Chaque réserve "
                "est précise, vérifiable et non bloquante.",
                criteria=[r.code for r in partial],
                evidence_ids=[eid for r in partial for eid in r.evidence_ids],
            )
        )
        return ProposedDecision(
            avis=FAVORABLE_SOUS_RESERVES,
            label=LABELS[FAVORABLE_SOUS_RESERVES],
            motivation="Les exigences obligatoires sont démontrées. Les réserves listées, toutes "
            "non bloquantes, doivent être levées avant la tenue de la manifestation.",
            triggered_rules=rules,
            blocking_criteria=[],
            reserves=reserves,
            required_complements=complements,
        )

    # --- Règle 4 : toutes les exigences obligatoires démontrées.
    rules.append(
        TriggeredRule(
            rule="R4_TOUTES_EXIGENCES_DEMONTREES",
            explanation=f"Les {len(mandatory)} critères obligatoires sont conformes et aucun "
            "critère n'est partiellement conforme, non conforme ou non vérifiable.",
            criteria=[r.code for r in mandatory],
            evidence_ids=[eid for r in mandatory for eid in r.evidence_ids],
        )
    )
    return ProposedDecision(
        avis=FAVORABLE,
        label=LABELS[FAVORABLE],
        motivation="L'ensemble des exigences obligatoires du référentiel est démontré par des "
        "pièces du dossier, sans réserve ni point non vérifiable.",
        triggered_rules=rules,
        blocking_criteria=[],
        reserves=[],
        required_complements=[],
    )


def to_dict(decision: ProposedDecision) -> dict:
    return {
        "avis": decision.avis,
        "label": decision.label,
        "motivation": decision.motivation,
        "disclaimer": decision.disclaimer,
        "blocking_criteria": decision.blocking_criteria,
        "reserves": decision.reserves,
        "required_complements": decision.required_complements,
        "triggered_rules": [
            {
                "rule": rule.rule,
                "explanation": rule.explanation,
                "criteria": rule.criteria,
                "evidence_ids": rule.evidence_ids,
            }
            for rule in decision.triggered_rules
        ],
    }
