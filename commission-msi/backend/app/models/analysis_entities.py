"""Entités de l'analyse automatique (prompt V4, §17).

Ces tables portent :

* le **registre de preuves** (`evidence_items`) auquel chaque affirmation du
  rapport doit être rattachée ;
* les constats réglementaires (`criterion_results`) ;
* le score scientifique proposé (`scientific_scores`, `scientific_subscores`) ;
* l'avis proposé et ses règles déclenchées (`proposed_decisions`) ;
* le travail asynchrone durable (`analysis_jobs`, `analysis_checkpoints`) ;
* le contrôle qualité du rapport (`report_qa_results`) ;
* la trace des appels au modèle (`ai_calls`), **sans raisonnement privé**.

Aucune table d'authentification n'est ajoutée. Les contenus sensibles sont
chiffrés (`_cipher`) ; les journaux techniques ne contiennent aucun texte clair.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.vocabulary import JobState
from app.models.base import Base, UTCDateTime, new_id, utcnow


class EvidenceItem(Base):
    """Une preuve citable : page, extrait, empreinte, origine.

    Toute affirmation factuelle du rapport doit pouvoir désigner au moins un
    `evidence_id` existant. Le validateur rejette les identifiants inconnus.
    """

    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Identifiant lisible et stable, cité dans le rapport (« E-P3-004 »).
    reference: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    #: DOCUMENT | PAGE | PIECE | CALCUL | SOURCE_WEB | SAISIE_HUMAINE
    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    page_no: Mapped[int | None] = mapped_column(Integer)
    locator: Mapped[str | None] = mapped_column(String(300))
    excerpt_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    #: Empreinte du contenu source : permet de détecter une dérive silencieuse.
    content_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Restreint = pièce d'identité : jamais envoyée au modèle ni au Web.
    sensitivity: Mapped[str] = mapped_column(String(20), default="ORDINAIRE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("dossier_id", "reference", name="uq_evidence_reference"),)


class CriterionResult(Base):
    """Constat réglementaire pour un des 26 critères, avec son fondement exact."""

    __tablename__ = "criterion_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(30), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(400), nullable=False)
    #: C | PC | NC | NV — jamais vide.
    status: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    finding_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    exact_source: Mapped[str] = mapped_column(String(400), nullable=False)
    source_page: Mapped[str] = mapped_column(String(40), nullable=False)
    nature: Mapped[str] = mapped_column(String(20), nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    calculation_json: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    referential_version: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Qualification humaine éventuelle : elle prime toujours sur la proposition.
    human_status: Mapped[str | None] = mapped_column(String(3))
    human_comment_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("dossier_id", "code", name="uq_criterion_per_dossier"),)


class ScientificScore(Base):
    """Score scientifique proposé sur 100, recalculé localement."""

    __tablename__ = "scientific_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    grid_version: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Total confirmé par l'évaluateur ; tant qu'il est nul, le score est proposé.
    validated_total: Mapped[int | None] = mapped_column(Integer)
    validated_by: Mapped[str | None] = mapped_column(String(200))
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class ScientificSubScore(Base):
    """Sous-note détaillée, sa justification brève et ses preuves."""

    __tablename__ = "scientific_subscores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    score_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_scores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family_key: Mapped[str] = mapped_column(String(60), nullable=False)
    family_label: Mapped[str] = mapped_column(String(200), nullable=False)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum: Mapped[int] = mapped_column(Integer, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    human_score: Mapped[int | None] = mapped_column(Integer)
    human_justification: Mapped[str | None] = mapped_column(Text)


class ProposedDecision(Base):
    """Avis technique proposé — aide à la décision, jamais une décision."""

    __tablename__ = "proposed_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    avis: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    motivation: Mapped[str] = mapped_column(Text, nullable=False)
    triggered_rules_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    blocking_criteria: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    reserves_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    complements_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    scientific_total: Mapped[int | None] = mapped_column(Integer)
    referential_version: Mapped[str] = mapped_column(String(20), nullable=False)
    #: Avis retenu par l'évaluateur ; l'application ne le remplace jamais.
    human_decision: Mapped[str | None] = mapped_column(String(60))
    human_motivation_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    decided_by: Mapped[str | None] = mapped_column(String(200))
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AnalysisJob(Base):
    """Travail durable exécuté par un worker distinct du serveur HTTP."""

    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(30), default=JobState.QUEUED, nullable=False, index=True)
    step_label: Mapped[str] = mapped_column(String(200), default="En file d'attente", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pages_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    searches_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validations_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    #: Bail : un seul worker peut détenir le travail à un instant donné.
    lease_owner: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Message d'erreur explicatif, sans trace brute ni secret.
    error_message: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(60))
    analysis_mode: Mapped[str] = mapped_column(String(20), default="LOCAL_ONLY", nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(120))
    referential_version: Mapped[str | None] = mapped_column(String(20))
    grid_version: Mapped[str | None] = mapped_column(String(20))
    #: Empreinte du PDF traité : deux analyses du même fichier ne se doublonnent pas.
    source_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class AnalysisCheckpoint(Base):
    """Point de reprise : une étape réussie n'est jamais refaite inutilement."""

    __tablename__ = "analysis_checkpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    #: Empreinte de l'entrée : si elle change, l'étape est rejouée.
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="OK", nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("job_id", "step", name="uq_checkpoint_step"),)


class ReportQaResult(Base):
    """Résultat du contrôle qualité obligatoire avant `COMPLETED` (§16)."""

    __tablename__ = "report_qa_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    checks_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    docx_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AiCall(Base):
    """Trace d'un appel au modèle : jamais le contenu, jamais le raisonnement."""

    __tablename__ = "ai_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str | None] = mapped_column(String(36), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    input_sha256: Mapped[str | None] = mapped_column(String(64))
    output_sha256: Mapped[str | None] = mapped_column(String(64))
    #: Catégories de données transmises — jamais les données elles-mêmes.
    data_categories: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class AuditDisagreement(Base):
    """Désaccord entre l'analyste et l'auditeur indépendant (§13).

    Un désaccord non résolu devient `NV`. Aucune moyenne n'est jamais faite.
    """

    __tablename__ = "audit_disagreements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    subject: Mapped[str] = mapped_column(String(60), nullable=False)
    criterion_code: Mapped[str | None] = mapped_column(String(10), index=True)
    analyst_value: Mapped[str] = mapped_column(Text, nullable=False)
    auditor_value: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
