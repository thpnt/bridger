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
from bridger.models.synthesis_manifest import SynthesisInputManifest
from bridger.models.working_state import ContextPlanWorkingStateSummary

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
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


class ToolExecutionStatus(StrEnum):
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ToolExecutionEventType(StrEnum):
    TOOL_CALL_REQUESTED = "tool_call_requested"
    TOOL_CALL_REJECTED = "tool_call_rejected"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    TOOL_CALL_FAILED = "tool_call_failed"


class FinalizationDecisionCode(StrEnum):
    ACCEPTED = "accepted"
    INVALID_REQUEST = "invalid_request"
    RUN_NOT_ACTIVE = "run_not_active"
    RUN_NOT_SYNTHESIZABLE = "run_not_synthesizable"
    RUN_STALLED = "run_stalled"
    RUN_FAILED = "run_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    UNSAFE_EVIDENCE_PATH = "unsafe_evidence_path"
    UNKNOWN_EVIDENCE_PATH = "unknown_evidence_path"
    UNINSPECTED_EVIDENCE_PATH = "uninspected_evidence_path"


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


class ContextPlanValidationIssue(ContextPlanModel):
    code: NonEmptyString
    location: list[str | int]
    message: NonEmptyString
    context: dict[str, JsonValue]


class ToolCallRequest(ContextPlanModel):
    call_id: NonEmptyString
    name: NonEmptyString
    arguments: dict[str, JsonValue]


class ToolBudgetCost(ContextPlanModel):
    tool_calls: Annotated[int, Field(ge=0)] = 1
    file_reads: Annotated[int, Field(ge=0)] = 0
    excerpts: Annotated[int, Field(ge=0)] = 0
    searches: Annotated[int, Field(ge=0)] = 0
    symbol_queries: Annotated[int, Field(ge=0)] = 0
    graph_queries: Annotated[int, Field(ge=0)] = 0


class ToolInspectionDelta(ContextPlanModel):
    discovered_paths: list[RepositoryPath] = Field(default_factory=list)
    evidence_paths: list[RepositoryPath] = Field(default_factory=list)
    excerpts_read: list[ContextPlanInspectedExcerpt] = Field(default_factory=list)
    symbols_inspected: list[ContextPlanInspectedSymbol] = Field(default_factory=list)
    searches_performed: list[ContextPlanSearchRecord] = Field(default_factory=list)
    graph_paths_inspected: list[RepositoryPath] = Field(default_factory=list)
    manifests_inspected: list[RepositoryPath] = Field(default_factory=list)

    _validate_paths = field_validator(
        "discovered_paths",
        "evidence_paths",
        "graph_paths_inspected",
        "manifests_inspected",
    )(lambda paths: [validate_context_plan_path(path) for path in paths])


class ToolExecutionResult(ContextPlanModel):
    call_id: NonEmptyString
    tool_name: NonEmptyString
    status: ToolExecutionStatus
    output: dict[str, JsonValue] | None = None
    issues: list[ContextPlanValidationIssue] = Field(default_factory=list)
    estimated_cost: ToolBudgetCost
    actual_cost: ToolBudgetCost
    inspection_delta: ToolInspectionDelta = Field(default_factory=ToolInspectionDelta)
    truncated: bool = False


class ToolExecutionEvent(ContextPlanModel):
    event_type: ToolExecutionEventType
    call_id: NonEmptyString
    tool_name: NonEmptyString
    fingerprint: NonEmptyString
    estimated_cost: ToolBudgetCost | None = None
    actual_cost: ToolBudgetCost | None = None
    inspection_delta: ToolInspectionDelta | None = None
    issue_codes: list[NonEmptyString] = Field(default_factory=list)
    truncated: bool = False
    occurred_at: datetime

    _validate_occurred_at = field_validator("occurred_at")(validate_aware_datetime)


class FinalizationContext(ContextPlanModel):
    run_status: ContextPlanRunStatus
    stalled: bool
    hard_budget_exhausted: bool
    evidence_paths: list[RepositoryPath] = Field(default_factory=list)
    finalization_request_count: Annotated[int, Field(ge=0)]

    _validate_evidence_paths = field_validator("evidence_paths")(
        lambda paths: [validate_context_plan_path(path) for path in paths]
    )


class FinalizationDecision(ContextPlanModel):
    accepted: bool
    code: FinalizationDecisionCode
    issues: list[ContextPlanValidationIssue] = Field(default_factory=list)


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
    model_turns: Annotated[int, Field(ge=0)] = 0
    tool_call_count: Annotated[int, Field(ge=0)] = 0
    token_usage: Annotated[int, Field(ge=0)] = 0
    input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0
    cached_input_tokens: Annotated[int, Field(ge=0)] = 0
    reasoning_tokens: Annotated[int, Field(ge=0)] = 0
    model_latency_ms: Annotated[int, Field(ge=0)] = 0
    inspection: ContextPlanRunInspection
    finalization_requests: list[ContextPlanFinalizationRecord]
    validation_attempts: list[ContextPlanValidationAttempt]
    errors: list[ContextPlanRunError]
    output: ContextPlanRunOutput | None
    working_state_path: RepositoryPath | None = None
    working_state_checksum: Checksum | None = None
    working_state_summary: ContextPlanWorkingStateSummary | None = None
    synthesis_input_manifest: SynthesisInputManifest | None = None

    _validate_started_at = field_validator("started_at")(validate_aware_datetime)
    _validate_updated_at = field_validator("updated_at")(validate_aware_datetime)

    _validate_working_state_path = field_validator("working_state_path")(
        lambda path: validate_context_plan_path(path) if path is not None else None
    )

    @field_validator("completed_at")
    @classmethod
    def validate_optional_datetime(cls, value: datetime | None) -> datetime | None:
        return validate_aware_datetime(value) if value is not None else None
