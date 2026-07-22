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

from bridger.models.file_index import validate_repository_path

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
RepositoryPath = Annotated[str, StringConstraints(min_length=1)]
TopicSlug = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
PackageId = Annotated[
    str,
    StringConstraints(pattern=r"^pkg\.[a-z0-9]+(?:[.-][a-z0-9]+)*$"),
]
Checksum = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class ContextPlanModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


def validate_context_plan_path(path: str) -> str:
    if "\0" in path:
        raise ValueError("path must not contain NUL bytes")
    if path == ".":
        raise ValueError("path must identify a repository file")
    return validate_repository_path(path)


def validate_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class ContextPlanRepository(ContextPlanModel):
    root_name: NonEmptyString
    revision: NonEmptyString | None


class ContextPlanSummary(ContextPlanModel):
    repository_purpose: NonEmptyString | None
    project_type: NonEmptyString | None
    detected_stack: list[NonEmptyString]
    main_runtime_flow: NonEmptyString | None
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class ContextPackageItem(ContextPlanModel):
    path: RepositoryPath
    line_start: Annotated[int, Field(gt=0)]
    line_end: Annotated[int, Field(gt=0)]
    role: NonEmptyString
    reason: NonEmptyString
    expected_use: NonEmptyString

    _validate_path = field_validator("path")(validate_context_plan_path)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ContextPackageItem":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ContextProvenance(ContextPlanModel):
    source_type: Literal["file_excerpt"]
    path: RepositoryPath
    line_start: Annotated[int, Field(gt=0)]
    line_end: Annotated[int, Field(gt=0)]
    evidence_note: NonEmptyString

    _validate_path = field_validator("path")(validate_context_plan_path)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ContextProvenance":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ContextPackage(ContextPlanModel):
    package_id: PackageId
    title: NonEmptyString
    purpose: NonEmptyString
    priority: Annotated[int, Field(gt=0)]
    topics: Annotated[list[TopicSlug], Field(min_length=1, max_length=12)]
    ordered_items: Annotated[list[ContextPackageItem], Field(min_length=1)]
    provenance: Annotated[list[ContextProvenance], Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    warnings: list[NonEmptyString]
    unknowns: list[NonEmptyString]


class ContextPlanExclusion(ContextPlanModel):
    path_or_pattern: NonEmptyString
    reason: NonEmptyString


class ContextPlan(ContextPlanModel):
    schema_version: Literal[1] = 1
    artifact: Literal["context-plan"] = "context-plan"
    generated_at: datetime
    repo: ContextPlanRepository
    summary: ContextPlanSummary
    packages: Annotated[list[ContextPackage], Field(min_length=1)]
    intentionally_excluded: list[ContextPlanExclusion]
    global_warnings: list[NonEmptyString]
    global_unknowns: list[NonEmptyString]

    _validate_generated_at = field_validator("generated_at")(validate_aware_datetime)


class ContextPlanFinalizationRequest(ContextPlanModel):
    explored_areas: Annotated[list[NonEmptyString], Field(min_length=1)]
    key_evidence_paths: Annotated[list[RepositoryPath], Field(min_length=1)]
    unresolved_areas: list[NonEmptyString]
    sufficiency_reason: NonEmptyString

    _validate_paths = field_validator("key_evidence_paths")(
        lambda paths: [validate_context_plan_path(path) for path in paths]
    )


class ContextPlanRunStatus(StrEnum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    STALLED = "stalled"
    INTERRUPTED = "interrupted"


class ContextPlanRunPhase(StrEnum):
    INITIALIZATION = "initialization"
    ORIENTATION = "orientation"
    INVESTIGATION = "investigation"
    FINALIZATION = "finalization"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    WRITING = "writing"
    COMPLETED = "completed"


class ContextPlanInspectedExcerpt(ContextPlanModel):
    path: RepositoryPath
    line_start: Annotated[int, Field(gt=0)]
    line_end: Annotated[int, Field(gt=0)]

    _validate_path = field_validator("path")(validate_context_plan_path)

    @model_validator(mode="after")
    def validate_line_range(self) -> "ContextPlanInspectedExcerpt":
        if self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        return self


class ContextPlanInspectedSymbol(ContextPlanModel):
    identifier: NonEmptyString
    path: RepositoryPath | None

    @field_validator("path")
    @classmethod
    def validate_optional_path(cls, path: str | None) -> str | None:
        return validate_context_plan_path(path) if path is not None else None


class ContextPlanSearchRecord(ContextPlanModel):
    tool: NonEmptyString
    query: NonEmptyString
    result_count: Annotated[int, Field(ge=0)]


class ContextPlanGraphQueryRecord(ContextPlanModel):
    tool: NonEmptyString
    subject: NonEmptyString
    result_count: Annotated[int, Field(ge=0)]


class ContextPlanRunInspection(ContextPlanModel):
    safe_file_count: Annotated[int, Field(ge=0)]
    inspected_file_count: Annotated[int, Field(ge=0)]
    remaining_file_count: Annotated[int, Field(ge=0)]
    inspected_files: list[RepositoryPath]
    inspected_excerpts: list[ContextPlanInspectedExcerpt]
    inspected_symbols: list[ContextPlanInspectedSymbol]
    search_records: list[ContextPlanSearchRecord]
    graph_query_records: list[ContextPlanGraphQueryRecord]

    _validate_paths = field_validator("inspected_files")(
        lambda paths: [validate_context_plan_path(path) for path in paths]
    )


class ContextPlanValidationIssue(ContextPlanModel):
    code: NonEmptyString
    location: list[str | int]
    message: NonEmptyString
    context: dict[str, JsonValue]


class ContextPlanFinalizationRecord(ContextPlanModel):
    recorded_at: datetime
    request: ContextPlanFinalizationRequest

    _validate_recorded_at = field_validator("recorded_at")(validate_aware_datetime)


class ContextPlanValidationAttempt(ContextPlanModel):
    attempted_at: datetime
    succeeded: bool
    issues: list[ContextPlanValidationIssue]

    _validate_attempted_at = field_validator("attempted_at")(validate_aware_datetime)


class ContextPlanRunError(ContextPlanModel):
    occurred_at: datetime
    phase: ContextPlanRunPhase
    message: NonEmptyString

    _validate_occurred_at = field_validator("occurred_at")(validate_aware_datetime)


class ContextPlanRunOutput(ContextPlanModel):
    artifact_path: RepositoryPath
    sha256: Checksum

    _validate_path = field_validator("artifact_path")(validate_context_plan_path)


class ContextPlanRun(ContextPlanModel):
    schema_version: Literal[1] = 1
    artifact: Literal["context-plan-run"] = "context-plan-run"
    run_id: NonEmptyString
    repo: ContextPlanRepository
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    status: ContextPlanRunStatus
    phase: ContextPlanRunPhase
    model_profile: NonEmptyString | None
    model_name: NonEmptyString | None
    inspection: ContextPlanRunInspection
    finalization_requests: list[ContextPlanFinalizationRecord]
    validation_attempts: list[ContextPlanValidationAttempt]
    errors: list[ContextPlanRunError]
    output: ContextPlanRunOutput | None

    _validate_started_at = field_validator("started_at")(validate_aware_datetime)
    _validate_updated_at = field_validator("updated_at")(validate_aware_datetime)

    @field_validator("completed_at")
    @classmethod
    def validate_optional_datetime(cls, value: datetime | None) -> datetime | None:
        return validate_aware_datetime(value) if value is not None else None
