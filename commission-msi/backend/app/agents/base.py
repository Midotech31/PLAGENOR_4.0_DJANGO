"""Socle des agents spécialisés connectés à Internet.

Chaque agent :

* reçoit uniquement des sources publiques déjà collectées et son propre sujet ;
* ne lit jamais la conclusion d'un autre agent avant de produire la sienne ;
* restitue des **affirmations atomiques** accompagnées de leurs sources ;
* ne produit jamais de décision, de qualification juridique définitive, ni
  d'avis favorable ou défavorable.

Le raisonnement des agents est déterministe et explicable : il repose sur le
palier de la source, le nombre de sources indépendantes, les dates et les
concordances. Aucun modèle génératif n'intervient dans le chemin de décision
(voir `docs/DECISIONS_TECHNIQUES.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.text import containment, normalize
from app.core.vocabulary import (
    SOURCE_TIER_WEIGHT,
    AgentName,
    ClaimNature,
    EvidenceStatus,
    SourceTier,
)
from app.web_research.providers import SearchResult

AGENT_VERSION = "1.0"

#: Paliers considérés comme « officiels primaires » : une seule suffit.
PRIMARY_TIERS = frozenset({SourceTier.T1_AUTORITE_OFFICIELLE})
#: Paliers trop faibles pour confirmer seuls un point sensible.
WEAK_TIERS = frozenset({SourceTier.T6_RESEAU_SOCIAL_OFFICIEL, SourceTier.T7_NON_ATTRIBUE})

#: Deux sources indépendantes minimum pour une conclusion sensible.
MIN_INDEPENDENT_SOURCES = 2


@dataclass
class Claim:
    """Affirmation atomique produite par un agent."""

    agent_name: str
    subject_label: str
    statement: str
    nature: str
    status: str
    confidence: float | None
    source_urls: list[str] = field(default_factory=list)
    independent_source_count: int = 0
    notes: str = ""


@dataclass
class AxisProposal:
    """Proposition de note sur un axe du ranking externe."""

    axis_key: str
    proposed_score: float | None
    uncertainty_low: float | None
    uncertainty_high: float | None
    evidence_sufficient: bool
    rationale: str
    source_urls: list[str] = field(default_factory=list)


@dataclass
class AgentInput:
    """Entrée d'un agent : sujet + sources publiques, jamais le dossier."""

    subject_kind: str
    subject_label: str
    declared_affiliation: str | None
    results: list[SearchResult]
    algerian_references: list[dict] = field(default_factory=list)


@dataclass
class AgentOutput:
    agent_name: str
    agent_version: str
    subject_label: str
    claims: list[Claim] = field(default_factory=list)
    axis_proposals: list[AxisProposal] = field(default_factory=list)
    produced_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def independent_domains(results: list[SearchResult]) -> set[str]:
    from app.web_research.egress import domain_of

    return {domain_of(result.url) for result in results if result.url}


def evidence_status(results: list[SearchResult]) -> str:
    """Statut de preuve déterminé par le palier et le nombre de sources."""
    if not results:
        return EvidenceStatus.NON_ETABLI
    if any(result.tier in PRIMARY_TIERS for result in results):
        return EvidenceStatus.SOURCE_OFFICIELLE_TROUVEE
    strong = [result for result in results if result.tier not in WEAK_TIERS]
    if len(independent_domains(strong)) >= MIN_INDEPENDENT_SOURCES:
        return EvidenceStatus.SOURCES_CONCORDANTES
    return EvidenceStatus.A_VERIFIER


def confidence_of(results: list[SearchResult]) -> float | None:
    """Confiance de la détection documentaire, jamais du fait lui-même."""
    if not results:
        return None
    weights = [SOURCE_TIER_WEIGHT.get(result.tier, 0.0) for result in results]
    best = max(weights)
    breadth = min(len(independent_domains(results)), 3) / 3
    return round(min(0.95, 0.6 * best + 0.35 * breadth), 3)


def affiliation_agreement(declared: str | None, results: list[SearchResult]) -> float:
    """Concordance entre l'affiliation déclarée et celle des sources publiques.

    La métrique est un taux de contenance : elle répond à « l'affiliation
    déclarée apparaît-elle dans la source ? », et non à « les deux textes
    se ressemblent-ils ? ». Elle reste affichable telle quelle à l'évaluateur.
    """
    if not declared:
        return 0.0
    scores = [
        containment(declared, f"{result.title} {result.publisher or ''} {result.snippet}")
        for result in results
    ]
    return max(scores) if scores else 0.0


def label_matches(subject_label: str, result: SearchResult) -> float:
    """Taux de contenance du nom recherché dans une source."""
    return containment(subject_label, f"{result.title} {result.publisher or ''} {result.snippet}")


def mentions(term: str, results: list[SearchResult]) -> list[SearchResult]:
    needle = normalize(term)
    if not needle:
        return []
    return [
        result
        for result in results
        if needle in normalize(f"{result.title} {result.snippet} {result.publisher or ''}")
    ]


class Agent:
    """Interface commune. Un agent ne voit jamais la sortie d'un autre agent."""

    name: str = "AGENT"
    version: str = AGENT_VERSION

    def run(self, data: AgentInput) -> AgentOutput:  # pragma: no cover - interface
        raise NotImplementedError

    def _output(self, data: AgentInput) -> AgentOutput:
        return AgentOutput(
            agent_name=self.name, agent_version=self.version, subject_label=data.subject_label
        )


def no_result_claim(agent_name: str, subject_label: str) -> Claim:
    """L'absence de résultat n'est jamais une preuve d'absence."""
    return Claim(
        agent_name=agent_name,
        subject_label=subject_label,
        statement=(
            f"Aucune source publique exploitable n'a été trouvée pour « {subject_label} » "
            "avec les fournisseurs et la requête utilisés."
        ),
        nature=ClaimNature.ABSENCE_DE_PREUVE,
        status=EvidenceStatus.NON_ETABLI,
        confidence=None,
        notes=(
            "L'absence de résultat ne prouve ni l'absence d'activité, ni l'absence de risque. "
            "Elle peut résulter de la langue, de l'indexation ou de la date de consultation."
        ),
    )


__all__ = [
    "AGENT_VERSION",
    "Agent",
    "AgentInput",
    "AgentName",
    "AgentOutput",
    "AxisProposal",
    "Claim",
    "MIN_INDEPENDENT_SOURCES",
    "affiliation_agreement",
    "confidence_of",
    "evidence_status",
    "independent_domains",
    "label_matches",
    "mentions",
    "no_result_claim",
]
