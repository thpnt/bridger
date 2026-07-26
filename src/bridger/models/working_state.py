"""Typed durable state accumulated during Context Plan investigation."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from bridger.models.repository_path import RepositoryPath, validate_repository_path

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
StableId = NonEmptyString


class WorkingStateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


class EvidenceKind(StrEnum):
    FILE_EXCERPT = "file_excerpt"
    SEARCH_HIT = "search_hit"
    SYMBOL_METADATA = "symbol_metadata"
    MANIFEST_FACT = "manifest_fact"
    FILE_METADATA = "file_metadata"
    REPOSITORY_FACT = "repository_fact"


class InspectionLevel(StrEnum):
    DISCOVERED = "discovered"
    LOCATED = "located"
    SYMBOL_ONLY = "symbol_only"
    LINE_OBSERVED = "line_observed"
    EXCERPT_INSPECTED = "excerpt_inspected"
    IMPLEMENTATION_INSPECTED = "implementation_inspected"


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class FindingStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class RelationshipStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class QuestionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    UNANSWERABLE = "unanswerable"
    SUPERSEDED = "superseded"


class PackageCandidateStatus(StrEnum):
    ACTIVE = "active"
    MERGED = "merged"
    DISCARDED = "discarded"
    SUPERSEDED = "superseded"


class FileInspectionStatus(StrEnum):
    DISCOVERED = "discovered"
    SYMBOL_ONLY = "symbol_only"
    PARTIALLY_INSPECTED = "partially_inspected"
    IMPLEMENTATION_INSPECTED = "implementation_inspected"


class EvidenceLineRange(WorkingStateModel):
    line_start: Annotated[int, Field(gt=0)]
    line_end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def validate_order(self) -> EvidenceLineRange:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class EvidenceRecord(WorkingStateModel):
    evidence_id: StableId
    kind: EvidenceKind
    source_tool: NonEmptyString
    source_call_id: NonEmptyString
    path: RepositoryPath | None = None
    line_ranges: list[EvidenceLineRange] = Field(default_factory=list)
    symbol_id: NonEmptyString | None = None
    structured_payload: dict[str, JsonValue] = Field(default_factory=dict)
    content: str | None = None
    content_digest: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    inspection_level: InspectionLevel
    truncated: bool = False
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    sequence_number: Annotated[int, Field(gt=0)]
    area_key: NonEmptyString = "repository"

    @field_validator("path")
    @classmethod
    def validate_optional_path(cls, path: str | None) -> str | None:
        return validate_repository_path(path) if path is not None else None


class InspectedFileState(WorkingStateModel):
    path: RepositoryPath
    total_lines: Annotated[int, Field(ge=0)] | None = None
    inspected_ranges: list[EvidenceLineRange] = Field(default_factory=list)
    observed_lines: Annotated[int, Field(ge=0)] = 0
    symbol_ids_seen: list[NonEmptyString] = Field(default_factory=list)
    symbol_ids_inspected: list[NonEmptyString] = Field(default_factory=list)
    inspection_status: FileInspectionStatus = FileInspectionStatus.DISCOVERED

    _validate_path = field_validator("path")(validate_repository_path)


class EstablishedFinding(WorkingStateModel):
    finding_id: StableId
    statement: NonEmptyString
    evidence_ids: Annotated[list[StableId], Field(min_length=1)]
    area_key: NonEmptyString
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    status: FindingStatus = FindingStatus.ACTIVE
    supersedes: StableId | None = None
    created_sequence: Annotated[int, Field(gt=0)]
    updated_sequence: Annotated[int, Field(gt=0)]


class RelationshipRecord(WorkingStateModel):
    relationship_id: StableId
    source_entity: NonEmptyString
    relationship_type: NonEmptyString
    target_entity: NonEmptyString
    evidence_ids: Annotated[list[StableId], Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    status: RelationshipStatus = RelationshipStatus.ACTIVE
    area_key: NonEmptyString = "repository"
    created_sequence: Annotated[int, Field(gt=0)]
    updated_sequence: Annotated[int, Field(gt=0)]


class OpenQuestion(WorkingStateModel):
    question_id: StableId
    question: NonEmptyString
    area_key: NonEmptyString
    related_evidence_ids: list[StableId] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=1, le=5)] = 3
    status: QuestionStatus = QuestionStatus.OPEN
    resolution: NonEmptyString | None = None
    resolution_evidence_ids: list[StableId] = Field(default_factory=list)
    created_sequence: Annotated[int, Field(gt=0)]
    updated_sequence: Annotated[int, Field(gt=0)]


class PackageCandidate(WorkingStateModel):
    candidate_id: StableId
    title: NonEmptyString
    purpose: NonEmptyString
    target_memory_kind: NonEmptyString | None = None
    area_keys: Annotated[list[NonEmptyString], Field(min_length=1)]
    finding_ids: list[StableId] = Field(default_factory=list)
    evidence_ids: list[StableId] = Field(default_factory=list)
    question_ids: list[StableId] = Field(default_factory=list)
    priority: Annotated[int, Field(ge=1)]
    status: PackageCandidateStatus = PackageCandidateStatus.ACTIVE
    merged_into: StableId | None = None
    created_sequence: Annotated[int, Field(gt=0)]
    updated_sequence: Annotated[int, Field(gt=0)]


class ContextPlanWorkingStateSummary(WorkingStateModel):
    mutation_sequence: Annotated[int, Field(ge=0)]
    evidence_count: Annotated[int, Field(ge=0)]
    inspected_file_count: Annotated[int, Field(ge=0)]
    active_finding_count: Annotated[int, Field(ge=0)]
    active_relationship_count: Annotated[int, Field(ge=0)]
    open_question_count: Annotated[int, Field(ge=0)]
    active_candidate_count: Annotated[int, Field(ge=0)]
    represented_area_keys: list[str] = Field(default_factory=list)


class ContextPlanWorkingState(WorkingStateModel):
    schema_version: Literal[1] = 1
    artifact: Literal["context-plan-working-state"] = "context-plan-working-state"
    run_id: NonEmptyString
    repository_revision: NonEmptyString | None = None
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    inspected_files: list[InspectedFileState] = Field(default_factory=list)
    findings: list[EstablishedFinding] = Field(default_factory=list)
    relationships: list[RelationshipRecord] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    package_candidates: list[PackageCandidate] = Field(default_factory=list)
    mutation_sequence: Annotated[int, Field(ge=0)] = 0
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def sort_collections(self) -> ContextPlanWorkingState:
        self.evidence.sort(key=lambda item: item.evidence_id)
        self.inspected_files.sort(key=lambda item: item.path)
        self.findings.sort(key=lambda item: item.finding_id)
        self.relationships.sort(key=lambda item: item.relationship_id)
        self.open_questions.sort(key=lambda item: item.question_id)
        self.package_candidates.sort(key=lambda item: item.candidate_id)
        return self

    def summary(self) -> ContextPlanWorkingStateSummary:
        areas = {
            record.area_key
            for record in self.evidence
            if record.status is EvidenceStatus.ACTIVE
        }
        areas.update(
            finding.area_key
            for finding in self.findings
            if finding.status is FindingStatus.ACTIVE
        )
        return ContextPlanWorkingStateSummary(
            mutation_sequence=self.mutation_sequence,
            evidence_count=len(self.evidence),
            inspected_file_count=len(self.inspected_files),
            active_finding_count=sum(
                item.status is FindingStatus.ACTIVE for item in self.findings
            ),
            active_relationship_count=sum(
                item.status is RelationshipStatus.ACTIVE for item in self.relationships
            ),
            open_question_count=sum(
                item.status is QuestionStatus.OPEN for item in self.open_questions
            ),
            active_candidate_count=sum(
                item.status is PackageCandidateStatus.ACTIVE
                for item in self.package_candidates
            ),
            represented_area_keys=sorted(areas),
        )
