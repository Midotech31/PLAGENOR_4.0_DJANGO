"""Entités du module de recherche Internet contrôlée, des agents et du ranking.

Aucune de ces tables ne contient de document du dossier : seules des requêtes
publiques minimales validées par l'évaluateur, les sources consultées et les
affirmations atomiques qui en découlent y sont enregistrées (chiffrées).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.vocabulary import (
    ClaimNature,
    EvidenceStatus,
    RankingGrade,
    SourceTier,
    WebRunStatus,
)
from app.models.base import Base, UTCDateTime, new_id, utcnow


class WebResearchRun(Base):
    """Campagne de recherche publique, préparée puis validée par un humain."""

    __tablename__ = "web_research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default=WebRunStatus.PREPAREE, nullable=False)
    scope_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    connectivity_ok: Mapped[bool | None] = mapped_column(Boolean)
    providers_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    dismissal_justification: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    queries: Mapped[list["WebQuery"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class WebQuery(Base):
    """Requête minimale envoyée à un fournisseur, relue et modifiable avant envoi."""

    __tablename__ = "web_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_label: Mapped[str] = mapped_column(String(400), nullable=False)
    query_text: Mapped[str] = mapped_column(String(600), nullable=False)
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80))
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    http_status: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    redaction_report_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    run: Mapped[WebResearchRun] = relationship(back_populates="queries")


class WebSource(Base):
    """Source publique consultée : URL canonique, éditeur, dates, palier."""

    __tablename__ = "web_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    query_id: Mapped[str | None] = mapped_column(ForeignKey("web_queries.id", ondelete="SET NULL"))
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(600))
    publisher: Mapped[str | None] = mapped_column(String(300))
    published_on: Mapped[str | None] = mapped_column(String(30))
    consulted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    tier: Mapped[str] = mapped_column(String(40), default=SourceTier.T7_NON_ATTRIBUE, nullable=False)
    excerpt_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(10))


class OnlineClaim(Base):
    """Affirmation atomique restituée par un agent, avec sa source et son niveau de preuve."""

    __tablename__ = "online_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dossier_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    subject_label: Mapped[str] = mapped_column(String(400), nullable=False)
    statement_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nature: Mapped[str] = mapped_column(String(40), default=ClaimNature.OPINION, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=EvidenceStatus.A_VERIFIER, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    independent_source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    algerian_reference_id: Mapped[str | None] = mapped_column(
        ForeignKey("regulations.id", ondelete="SET NULL")
    )
    algerian_passage_id: Mapped[str | None] = mapped_column(
        ForeignKey("regulation_passages.id", ondelete="SET NULL")
    )
    human_status: Mapped[str] = mapped_column(
        String(40), default=EvidenceStatus.A_VERIFIER, nullable=False
    )
    human_comment_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class PersonWebProfile(Base):
    """Profil public consolidé d'une personne ou d'un organisme."""

    __tablename__ = "person_web_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="SET NULL")
    )
    subject_kind: Mapped[str] = mapped_column(String(40), default="PERSONNE", nullable=False)
    display_name: Mapped[str] = mapped_column(String(400), nullable=False)
    name_variants_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    declared_affiliation: Mapped[str | None] = mapped_column(String(400))
    verified_affiliations_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    public_identifiers_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=EvidenceStatus.A_VERIFIER, nullable=False)
    summary_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AssociationLink(Base):
    """Lien associatif ou engagement public constaté, jamais qualifié juridiquement."""

    __tablename__ = "association_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("person_web_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization: Mapped[str] = mapped_column(String(400), nullable=False)
    role: Mapped[str | None] = mapped_column(String(200))
    period: Mapped[str | None] = mapped_column(String(120))
    nature: Mapped[str] = mapped_column(String(40), default=ClaimNature.OPINION, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=EvidenceStatus.A_VERIFIER, nullable=False)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    legal_link_established: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class IdentityDisambiguation(Base):
    """Trace de désambiguïsation : les homonymies bloquent toute conclusion."""

    __tablename__ = "identity_disambiguations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("person_web_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_label: Mapped[str] = mapped_column(String(400), nullable=False)
    candidate_affiliation: Mapped[str | None] = mapped_column(String(400))
    discriminators_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    similarity: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(
        String(40), default=EvidenceStatus.HOMONYMIE_POSSIBLE, nullable=False
    )
    decided_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AgentAssessment(Base):
    """Restitution d'un agent, indépendante de celle des autres agents."""

    __tablename__ = "agent_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    agent_version: Mapped[str] = mapped_column(String(30), default="1.0", nullable=False)
    subject_label: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    axis_key: Mapped[str | None] = mapped_column(String(80), index=True)
    proposed_score: Mapped[float | None] = mapped_column(Float)
    uncertainty_low: Mapped[float | None] = mapped_column(Float)
    uncertainty_high: Mapped[float | None] = mapped_column(Float)
    evidence_sufficient: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rationale_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    claim_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AgentDisagreement(Base):
    """Désaccord entre agents : bloque toute conclusion consolidée."""

    __tablename__ = "agent_disagreements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    #: Nullable : un désaccord peut naître d'une orchestration hors campagne.
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="CASCADE"), index=True
    )
    subject_label: Mapped[str] = mapped_column(String(400), nullable=False)
    axis_key: Mapped[str | None] = mapped_column(String(80))
    agents_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    dispersion: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class EventRanking(Base):
    """Classement externe indicatif, strictement séparé de la grille officielle."""

    __tablename__ = "event_rankings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("web_research_runs.id", ondelete="SET NULL")
    )
    total: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str] = mapped_column(String(5), default=RankingGrade.NR, nullable=False)
    agreement_level: Mapped[float | None] = mapped_column(Float)
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    agents_versions_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    thresholds_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    comparison_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    axes: Mapped[list["EventRankingAxis"]] = relationship(
        back_populates="ranking", cascade="all, delete-orphan"
    )


class EventRankingAxis(Base):
    __tablename__ = "event_ranking_axes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    ranking_id: Mapped[str] = mapped_column(
        ForeignKey("event_rankings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    axis_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    proposed_score: Mapped[float | None] = mapped_column(Float)
    uncertainty_low: Mapped[float | None] = mapped_column(Float)
    uncertainty_high: Mapped[float | None] = mapped_column(Float)
    dispersion: Mapped[float | None] = mapped_column(Float)
    not_provided: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    justification_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    human_decision: Mapped[str] = mapped_column(String(30), default="A_VERIFIER", nullable=False)
    human_score: Mapped[float | None] = mapped_column(Float)
    human_justification_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)

    ranking: Mapped[EventRanking] = relationship(back_populates="axes")
