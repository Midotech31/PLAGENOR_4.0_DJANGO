"""Entités du modèle de données local.

Interdiction absolue : aucune table `users`, `sessions`, `credentials` ou
équivalente. Les champs suffixés `_cipher` contiennent des blobs AES-256-GCM.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.vocabulary import (
    ControlStatus,
    DossierStatus,
    ExtractionMode,
    FindingStatus,
    InformationStatus,
    PieceStatus,
    Priority,
    RegulationStatus,
    Sensitivity,
)
from app.models.base import Base, UTCDateTime, new_id, utcnow


class Dossier(Base):
    __tablename__ = "dossiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reference: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    organizer: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=DossierStatus.NOUVEAU, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default=Priority.MOYEN, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(300))
    storage_path: Mapped[str | None] = mapped_column(String(500))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    international_scope_declared: Mapped[bool | None] = mapped_column(Boolean, default=None)
    report_validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    report_validated_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    documents: Mapped[list["Document"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    extracted_items: Mapped[list["ExtractedItem"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    piece_checks: Mapped[list["PieceCheck"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    administrative_checks: Mapped[list["AdministrativeCheck"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    evaluation_entries: Mapped[list["EvaluationEntry"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="dossier", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(60), default="DOSSIER_ORIGINAL", nullable=False)
    original_name: Mapped[str] = mapped_column(String(300), nullable=False)
    encrypted_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(20), default=Sensitivity.ORDINAIRE, nullable=False
    )
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    dossier: Mapped[Dossier] = relationship(back_populates="documents")
    pages: Mapped[list["Page"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no", name="uq_page_document_no"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), default=ExtractionMode.AUCUN, nullable=False)
    original_text_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    corrected_text_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    confidence: Mapped[float | None] = mapped_column(Float)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    width: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    height: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rotation: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    needs_ocr: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_blank: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_difficult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    duplicate_of: Mapped[int | None] = mapped_column(Integer)
    text_fingerprint: Mapped[str | None] = mapped_column(String(64))
    engine_version: Mapped[str | None] = mapped_column(String(120))
    analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")
    ocr_runs: Mapped[list["OcrRun"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class OcrRun(Base):
    __tablename__ = "ocr_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engine: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    languages: Mapped[str] = mapped_column(String(60), nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    low_confidence_words: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    boxes_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    page: Mapped[Page] = relationship(back_populates="ocr_runs")


class ExtractedItem(Base):
    __tablename__ = "extracted_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(250), nullable=False)
    initial_value_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    current_value_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    page_no: Mapped[int | None] = mapped_column(Integer)
    source_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    bbox_json: Mapped[str | None] = mapped_column(Text)
    extraction_mode: Mapped[str] = mapped_column(
        String(25), default=ExtractionMode.AUCUN, nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(
        String(25), default=InformationStatus.A_VERIFIER, nullable=False
    )
    reinforced_control: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_entry_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="extracted_items")


class Correction(Base):
    """Historique immuable : la valeur initiale n'est jamais effacée."""

    __tablename__ = "corrections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(80), default="value", nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    new_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class PieceDefinition(Base):
    __tablename__ = "piece_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sensitivity: Mapped[str] = mapped_column(
        String(20), default=Sensitivity.ORDINAIRE, nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(String(300))
    source_page: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PieceCheck(Base):
    __tablename__ = "piece_checks"
    __table_args__ = (UniqueConstraint("dossier_id", "piece_key", name="uq_piece_dossier_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    piece_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(25), default=PieceStatus.ABSENTE, nullable=False)
    detected_page_no: Mapped[int | None] = mapped_column(Integer)
    detection_excerpt_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    detection_confidence: Mapped[float | None] = mapped_column(Float)
    sensitivity: Mapped[str] = mapped_column(
        String(20), default=Sensitivity.ORDINAIRE, nullable=False
    )
    comment_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    updated_by: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="piece_checks")


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(String(80))
    declared_nationality: Mapped[str | None] = mapped_column(String(120))
    page_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(25), default=InformationStatus.A_VERIFIER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    country: Mapped[str | None] = mapped_column(String(120))
    page_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(25), default=InformationStatus.A_VERIFIER, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Affiliation(Base):
    __tablename__ = "affiliations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    person_id: Mapped[str] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(25), default=InformationStatus.A_VERIFIER, nullable=False
    )


class Participation(Base):
    __tablename__ = "participations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str | None] = mapped_column(ForeignKey("persons.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="ANNONCEE", nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(25), default=InformationStatus.A_VERIFIER, nullable=False
    )


class AdministrativeCheck(Base):
    __tablename__ = "administrative_checks"
    __table_args__ = (UniqueConstraint("dossier_id", "check_key", name="uq_admin_dossier_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(25), default=ControlStatus.A_VERIFIER, nullable=False)
    explanation_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    comparison_json: Mapped[str | None] = mapped_column(Text)
    page_no: Mapped[int | None] = mapped_column(Integer)
    requires_human_confirmation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="administrative_checks")


class EvaluationCriterion(Base):
    __tablename__ = "evaluation_criteria"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(300))


class EvaluationEntry(Base):
    __tablename__ = "evaluation_entries"
    __table_args__ = (
        UniqueConstraint("dossier_id", "criterion_key", name="uq_evaluation_dossier_criterion"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    criterion_key: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    justification_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    source_pages_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    entered_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="evaluation_entries")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    trigger_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    context_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    page_no: Mapped[int | None] = mapped_column(Integer)
    bbox_json: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default=Priority.MOYEN, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_check: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(400))
    relation_kind: Mapped[str | None] = mapped_column(String(40))
    human_status: Mapped[str] = mapped_column(
        String(25), default=FindingStatus.A_VERIFIER, nullable=False
    )
    human_comment_cipher: Mapped[bytes | None] = mapped_column(LargeBinary)
    detection_signature: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="findings")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default=Priority.MOYEN, nullable=False)
    terms_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    context_terms_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    secondary_terms_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    guidance: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(String(400), nullable=False)
    source_date: Mapped[str | None] = mapped_column(String(20))
    authority: Mapped[str | None] = mapped_column(String(200))
    scope: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(20), default="1.0", nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    validated_by: Mapped[str | None] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    suspended_reason: Mapped[str | None] = mapped_column(Text)
    regulation_id: Mapped[str | None] = mapped_column(
        ForeignKey("regulations.id", ondelete="SET NULL")
    )
    is_normative: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(200), index=True)
    document_date: Mapped[str | None] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(30), default="1.0", nullable=False)
    authority: Mapped[str | None] = mapped_column(String(250))
    effective_from: Mapped[str | None] = mapped_column(String(20))
    effective_to: Mapped[str | None] = mapped_column(String(20))
    scope: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        String(20), default=RegulationStatus.BROUILLON, nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_path: Mapped[str | None] = mapped_column(String(500))
    original_name: Mapped[str | None] = mapped_column(String(300))
    validated_by: Mapped[str | None] = mapped_column(String(200))
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    integrity_ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    passages: Mapped[list["RegulationPassage"]] = relationship(
        back_populates="regulation", cascade="all, delete-orphan"
    )


class RegulationPassage(Base):
    __tablename__ = "regulation_passages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    regulation_id: Mapped[str] = mapped_column(
        ForeignKey("regulations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_no: Mapped[int | None] = mapped_column(Integer)
    passage_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    translation_status: Mapped[str] = mapped_column(
        String(30), default="NON_APPLICABLE", nullable=False
    )
    requirement_id: Mapped[str | None] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    regulation: Mapped[Regulation] = relationship(back_populates="passages")


class Requirement(Base):
    """Exigence sourcée : base de la matrice exigence -> source -> page -> test."""

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    requirement_id: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    pages_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    source_status: Mapped[str] = mapped_column(String(60), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="fr", nullable=False)
    translation_status: Mapped[str] = mapped_column(
        String(30), default="NON_APPLICABLE", nullable=False
    )
    conflict_id: Mapped[str | None] = mapped_column(String(40), index=True)
    implementation: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    test_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)


class SourceDocument(Base):
    """Manifeste des sources officielles (donnees/manifest_sources.json)."""

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(400), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fmt: Mapped[str] = mapped_column(String(30), nullable=False)
    pages_rendered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    document_date: Mapped[str | None] = mapped_column(String(20))
    reference: Mapped[str | None] = mapped_column(String(120))
    authority: Mapped[str | None] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    present_locally: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    integrity_ok: Mapped[bool | None] = mapped_column(Boolean)


class Conflict(Base):
    """Contradiction entre sources : jamais arbitrée automatiquement."""

    __tablename__ = "conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conflict_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    required_output: Mapped[str] = mapped_column(String(60), nullable=False)
    arbitrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    arbitration_note: Mapped[str | None] = mapped_column(Text)
    arbitrated_by: Mapped[str | None] = mapped_column(String(200))
    arbitrated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="NOTE", nullable=False)
    body_cipher: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    conclusion: Mapped[str | None] = mapped_column(String(60))
    page_no: Mapped[int | None] = mapped_column(Integer)
    author_label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    dossier: Mapped[Dossier] = relationship(back_populates="notes")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dossier_id: Mapped[str] = mapped_column(
        ForeignKey("dossiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fmt: Mapped[str] = mapped_column(String(10), nullable=False)
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    evaluator_label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)

    dossier: Mapped[Dossier] = relationship(back_populates="reports")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    dossier_id: Mapped[str | None] = mapped_column(String(36), index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(80))
    actor_label: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class Backup(Base):
    __tablename__ = "backups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    archive_path: Mapped[str] = mapped_column(String(500), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    includes_master_key: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
