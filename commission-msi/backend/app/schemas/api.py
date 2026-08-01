"""Schémas Pydantic : toutes les entrées de l'API locale sont validées."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.vocabulary import (
    Conclusion,
    ControlStatus,
    CriterionStatus,
    FindingStatus,
    InformationStatus,
    MarocRelation,
    PieceStatus,
)


class DossierCreate(BaseModel):
    reference: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=500)
    organizer: str = Field(min_length=1, max_length=300)


class DossierStatusUpdate(BaseModel):
    status: str


class DossierScopeUpdate(BaseModel):
    international_scope_declared: bool
    justification: str = Field(min_length=8, max_length=2000)


class PageCorrection(BaseModel):
    corrected_text: str = Field(max_length=200_000)
    reason: str = Field(min_length=8, max_length=2000)


class ItemUpdate(BaseModel):
    value: str = Field(default="", max_length=8000)
    status: InformationStatus
    reason: str = Field(default="", max_length=2000)
    page_no: int | None = Field(default=None, ge=1)
    source_excerpt: str | None = Field(default=None, max_length=4000)
    manual_entry_validated: bool = False


class PieceUpdate(BaseModel):
    status: PieceStatus
    comment: str = Field(default="", max_length=4000)
    detected_page_no: int | None = Field(default=None, ge=1)


class AdministrativeCheckUpdate(BaseModel):
    status: ControlStatus
    explanation: str = Field(default="", max_length=4000)
    page_no: int | None = Field(default=None, ge=1)
    comparison: dict | None = None


class ScoreUpdate(BaseModel):
    criterion_key: str
    score: int
    justification: str = Field(max_length=8000)
    source_pages: list[int] = Field(default_factory=list)


class CriterionQualification(BaseModel):
    """Qualification humaine d'un critère réglementaire.

    Elle prime sur la proposition de l'application, qui reste consultable.
    """

    status: CriterionStatus
    comment: str = Field(min_length=8, max_length=4000)


class SubScoreOverride(BaseModel):
    """Correction d'une sous-note ; la proposition initiale reste tracée."""

    score: int = Field(ge=0, le=30)
    justification: str = Field(min_length=8, max_length=4000)


class DecisionRetained(BaseModel):
    """Avis retenu par l'évaluateur, choisi dans la liste fermée."""

    avis: str
    motivation: str = Field(min_length=8, max_length=8000)


class FindingQualification(BaseModel):
    status: FindingStatus
    comment: str = Field(default="", max_length=4000)
    relation_kind: MarocRelation | None = None


class NoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    kind: str = Field(default="NOTE", max_length=40)
    page_no: int | None = Field(default=None, ge=1)


class ConclusionCreate(BaseModel):
    conclusion: Conclusion
    motivation: str = Field(max_length=20_000)


class ReportValidation(BaseModel):
    statement: str = Field(max_length=4000)


class ReportRequest(BaseModel):
    format: str = Field(default="docx", pattern="^(docx|pdf)$")
    official: bool = False
    #: « harmonise » : format de la commission, huit sections. « compact » :
    #: trois pages. « detaille » : rapport complet, quand les preuves l'exigent.
    layout: str = Field(default="harmonise", pattern="^(harmonise|compact|detaille)$")


class RuleToggle(BaseModel):
    active: bool
    reason: str = Field(min_length=8, max_length=2000)


class RegulationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    reference: str | None = Field(default=None, max_length=200)
    document_date: str | None = Field(default=None, max_length=20)
    version: str = Field(default="1.0", max_length=30)
    authority: str | None = Field(default=None, max_length=250)
    effective_from: str | None = Field(default=None, max_length=20)
    effective_to: str | None = Field(default=None, max_length=20)
    scope: str | None = Field(default=None, max_length=300)


class RegulationPassageCreate(BaseModel):
    passage: str = Field(min_length=1, max_length=20_000)
    page_no: int | None = Field(default=None, ge=1)
    translation_status: str = Field(default="NON_APPLICABLE", max_length=30)
    requirement_id: str | None = Field(default=None, max_length=30)


class RegulationValidation(BaseModel):
    validator: str = Field(min_length=2, max_length=200)


class ConflictArbitration(BaseModel):
    note: str = Field(max_length=8000)
    arbitrated_by: str = Field(min_length=2, max_length=200)


class RestoreRequest(BaseModel):
    archive_path: str = Field(min_length=1, max_length=1000)
    destination: str = Field(min_length=1, max_length=1000)


class DossierSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    title: str
    organizer: str
    status: str
    priority: str
    page_count: int
    sha256: str | None
    created_at: datetime
    updated_at: datetime
