"""Orchestration des agents : exécution indépendante puis comparaison.

Aucun agent ne lit la conclusion d'un autre avant sa propre analyse.
L'orchestrateur compare ensuite les propositions, calcule médiane et dispersion,
et bloque toute conclusion consolidée en cas de désaccord important.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from app.agents.base import AgentInput, AgentOutput, AxisProposal, Claim
from app.agents.specialists import ALL_AGENTS
from app.core.vocabulary import AGENT_DISAGREEMENT_MESSAGE, EvidenceStatus

#: Dispersion relative au-delà de laquelle le désaccord est jugé important.
DISAGREEMENT_THRESHOLD = 0.25


@dataclass
class AxisConsensus:
    axis_key: str
    proposals: list[AxisProposal]
    median: float | None
    dispersion: float | None
    agreement: float | None
    evidence_sufficient: bool
    blocked: bool
    message: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class Disagreement:
    subject_label: str
    axis_key: str | None
    agents: list[str]
    dispersion: float | None
    description: str


@dataclass
class OrchestrationResult:
    outputs: list[AgentOutput]
    claims: list[Claim]
    axes: list[AxisConsensus]
    disagreements: list[Disagreement]
    blocked: bool
    message: str


def run_agents(data: AgentInput) -> list[AgentOutput]:
    """Exécute chaque agent isolément, sur la même entrée immuable."""
    outputs: list[AgentOutput] = []
    for agent in ALL_AGENTS:
        isolated = AgentInput(
            subject_kind=data.subject_kind,
            subject_label=data.subject_label,
            declared_affiliation=data.declared_affiliation,
            results=list(data.results),
            algerian_references=list(data.algerian_references),
        )
        outputs.append(agent.run(isolated))
    return outputs


def orchestrate(data: AgentInput) -> OrchestrationResult:
    outputs = run_agents(data)
    claims = [claim for output in outputs for claim in output.claims]

    proposals: dict[str, list[tuple[str, AxisProposal]]] = {}
    for output in outputs:
        for proposal in output.axis_proposals:
            proposals.setdefault(proposal.axis_key, []).append((output.agent_name, proposal))

    axes: list[AxisConsensus] = []
    disagreements: list[Disagreement] = []

    for axis_key, entries in sorted(proposals.items()):
        scored = [(name, item) for name, item in entries if item.proposed_score is not None]
        sources = sorted({url for _, item in entries for url in item.source_urls})
        if not scored:
            axes.append(
                AxisConsensus(
                    axis_key=axis_key,
                    proposals=[item for _, item in entries],
                    median=None,
                    dispersion=None,
                    agreement=None,
                    evidence_sufficient=False,
                    blocked=False,
                    message="NR — NON RENSEIGNE : preuves insuffisantes, aucune note produite.",
                    source_urls=sources,
                )
            )
            continue

        values = [item.proposed_score for _, item in scored]
        median = round(statistics.median(values), 2)
        dispersion = round(statistics.pstdev(values), 3) if len(values) > 1 else 0.0
        relative = (dispersion / median) if median else 0.0
        blocked = relative > DISAGREEMENT_THRESHOLD
        if blocked:
            disagreements.append(
                Disagreement(
                    subject_label=data.subject_label,
                    axis_key=axis_key,
                    agents=[name for name, _ in scored],
                    dispersion=dispersion,
                    description=(
                        f"Dispersion relative {relative:.2f} sur l'axe « {axis_key} » "
                        f"(valeurs : {values}). {AGENT_DISAGREEMENT_MESSAGE}"
                    ),
                )
            )
        axes.append(
            AxisConsensus(
                axis_key=axis_key,
                proposals=[item for _, item in entries],
                median=median,
                dispersion=dispersion,
                agreement=round(max(0.0, 1.0 - relative), 3),
                evidence_sufficient=all(item.evidence_sufficient for _, item in scored),
                blocked=blocked,
                message=(
                    AGENT_DISAGREEMENT_MESSAGE
                    if blocked
                    else "Proposition indicative issue de la médiane des agents."
                ),
                source_urls=sources,
            )
        )

    # Une homonymie possible bloque également toute conclusion consolidée.
    homonyms = [claim for claim in claims if claim.status == EvidenceStatus.HOMONYMIE_POSSIBLE]
    for claim in homonyms:
        disagreements.append(
            Disagreement(
                subject_label=claim.subject_label,
                axis_key=None,
                agents=[claim.agent_name],
                dispersion=None,
                description=(
                    "Homonymie possible : l'identification du sujet n'est pas établie, "
                    "aucune conclusion consolidée n'est produite."
                ),
            )
        )

    contradictions = [
        claim for claim in claims if claim.status == EvidenceStatus.SOURCES_CONTRADICTOIRES
    ]
    for claim in contradictions:
        disagreements.append(
            Disagreement(
                subject_label=claim.subject_label,
                axis_key=None,
                agents=[claim.agent_name],
                dispersion=None,
                description="Sources contradictoires : arbitrage humain obligatoire.",
            )
        )

    blocked = bool(disagreements)
    return OrchestrationResult(
        outputs=outputs,
        claims=claims,
        axes=axes,
        disagreements=disagreements,
        blocked=blocked,
        message=(
            AGENT_DISAGREEMENT_MESSAGE
            if blocked
            else "Aucun désaccord bloquant. La synthèse reste soumise à validation humaine."
        ),
    )
