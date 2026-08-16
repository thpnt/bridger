"""Locked contracts for the Bridger memory-agent harness."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


class CompletionStatus(StrEnum):
    """Semantic resolution vocabulary for one completion obligation."""

    UNINVESTIGATED = "uninvestigated"
    COVERED = "covered"
    NOT_APPLICABLE = "not-applicable"
    UNKNOWN = "unknown"


class TargetPhase(StrEnum):
    """Authoritative lifecycle vocabulary for one target task."""

    INITIALIZED = "initialized"
    SCHEDULED = "scheduled"
    HYDRATING = "hydrating"
    WORKING = "working"
    FINALIZING = "finalizing"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    REPAIR = "repair"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    STOPPED = "stopped"


class FleetPhase(StrEnum):
    """Authoritative lifecycle vocabulary for one fleet run."""

    INITIALIZED = "initialized"
    RUNNING = "running"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    REPAIRING = "repairing"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    EXHAUSTED = "exhausted"
    FAILED = "failed"
    STOPPED = "stopped"


class FindingOrigin(StrEnum):
    """Authority that produced an unresolved finding reference."""

    HARD_VALIDATION = "hard-validation"
    TARGET_REVIEW = "target-review"
    FLEET_VALIDATION = "fleet-validation"
    FLEET_REVIEW = "fleet-review"


class SourceBinding(BaseModel):
    """Exact immutable upstream source identities for one memory run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repository_id: str = Field(min_length=1)
    repository_revision: str = Field(min_length=1)
    graph_snapshot_id: str = Field(min_length=1)
    enrichment_overlay_id: str | None = Field(default=None, min_length=1)


class ExecutionBudget(BaseModel):
    """Immutable execution limits shared by fleet and target runtimes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_cycles: PositiveInt
    max_model_calls: PositiveInt
    max_tool_calls: PositiveInt
    max_repair_cycles: PositiveInt
    max_input_tokens: PositiveInt | None = None
    max_output_tokens: PositiveInt | None = None


class ExecutionUsage(BaseModel):
    """Mutable non-negative execution consumption counters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    cycles: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    repair_cycles: int = Field(default=0, ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class FindingRef(BaseModel):
    """Immutable reference to an external validation or review finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    origin: FindingOrigin


class CandidateArtifactRef(BaseModel):
    """Immutable reference to one exact candidate artifact revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    revision: int = Field(ge=1)
    digest: str = Field(min_length=1)


class MemoryFleetSpec(BaseModel):
    """Immutable definition of one exact memory-generation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    fleet_run_id: str = Field(min_length=1)
    source: SourceBinding
    target_catalog_id: str = Field(min_length=1)
    target_catalog_version: str = Field(min_length=1)
    target_ids: list[str]
    runtime_profile_id: str = Field(min_length=1)
    default_worker_profile_id: str = Field(min_length=1)
    default_reviewer_profile_id: str = Field(min_length=1)
    default_permission_profile_id: str = Field(min_length=1)
    fleet_budget: ExecutionBudget
    default_target_budget: ExecutionBudget
    max_concurrent_targets: PositiveInt = 1
    runtime_root: str = Field(min_length=1)
    output_root: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target_ids(self) -> MemoryFleetSpec:
        """Require an unambiguous ordered activated-target set."""
        if any(not target_id for target_id in self.target_ids):
            raise ValueError("target_ids must be non-empty strings")
        if len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("target_ids must be unique")
        return self


class FleetRunState(BaseModel):
    """Mutable global execution state for one fleet run."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: int = Field(default=1, ge=1)
    fleet_run_id: str = Field(min_length=1)
    phase: FleetPhase = FleetPhase.INITIALIZED
    target_task_ids: list[str] = Field(default_factory=list)
    usage: ExecutionUsage = Field(default_factory=ExecutionUsage)
    open_finding_refs: list[FindingRef] = Field(default_factory=list)
    last_error_ref: str | None = Field(default=None, min_length=1)
    termination_reason: str | None = Field(default=None, min_length=1)
    accepted_result_ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_state(self) -> FleetRunState:
        """Reject duplicate tasks and incoherent accepted-result state."""
        if len(self.target_task_ids) != len(set(self.target_task_ids)):
            raise ValueError("target_task_ids must be unique")
        if self.phase is FleetPhase.ACCEPTED and self.accepted_result_ref is None:
            raise ValueError("accepted fleet state requires accepted_result_ref")
        if (
            self.accepted_result_ref is not None
            and self.phase is not FleetPhase.ACCEPTED
        ):
            raise ValueError("accepted_result_ref requires accepted fleet state")
        return self


class TargetTaskSpec(BaseModel):
    """Immutable assignment for one instantiated target execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    target_task_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    source: SourceBinding
    worker_profile_id: str = Field(min_length=1)
    reviewer_profile_id: str = Field(min_length=1)
    permission_profile_id: str = Field(min_length=1)
    budget: ExecutionBudget
    target_workspace: str = Field(min_length=1)
    depends_on_target_task_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dependencies(self) -> TargetTaskSpec:
        """Require explicit, unique, non-self target dependencies."""
        dependencies = self.depends_on_target_task_ids
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("depends_on_target_task_ids must be unique")
        if self.target_task_id in dependencies:
            raise ValueError("a target task cannot depend on itself")
        return self


class TargetTaskState(BaseModel):
    """Mutable operational state of one target execution."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: int = Field(default=1, ge=1)
    target_task_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    phase: TargetPhase = TargetPhase.INITIALIZED
    usage: ExecutionUsage = Field(default_factory=ExecutionUsage)
    working_summary: str | None = None
    open_question_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[CandidateArtifactRef] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    open_finding_refs: list[FindingRef] = Field(default_factory=list)
    last_checkpoint_ref: str | None = Field(default=None, min_length=1)
    last_progress_signature: str | None = Field(default=None, min_length=1)
    stall_count: int = Field(default=0, ge=0)
    pending_finalization_request_ref: str | None = Field(default=None, min_length=1)
    last_error_ref: str | None = Field(default=None, min_length=1)
    termination_reason: str | None = Field(default=None, min_length=1)
    last_accepted_result_ref: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_phase_requirements(self) -> TargetTaskState:
        """Enforce the locked reference requirements of special phases."""
        if self.phase is TargetPhase.REPAIR and not self.open_finding_refs:
            raise ValueError("repair target state requires an open finding")
        if (
            self.phase is TargetPhase.FINALIZING
            and self.pending_finalization_request_ref is None
        ):
            raise ValueError(
                "finalizing target state requires pending_finalization_request_ref"
            )
        if self.phase is TargetPhase.ACCEPTED and self.last_accepted_result_ref is None:
            raise ValueError("accepted target state requires last_accepted_result_ref")
        return self


class CompletionItemState(BaseModel):
    """Mutable semantic resolution of one completion obligation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    obligation_id: str = Field(min_length=1)
    status: CompletionStatus = CompletionStatus.UNINVESTIGATED
    resolution_note: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_resolution_note(self) -> CompletionItemState:
        """Require a meaningful note for every terminal semantic resolution."""
        if self.status is not CompletionStatus.UNINVESTIGATED and (
            self.resolution_note is None or not self.resolution_note.strip()
        ):
            raise ValueError("terminal completion status requires resolution_note")
        return self


class TargetCompletionState(BaseModel):
    """Mutable runtime materialization of one target's obligations."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: int = Field(default=1, ge=1)
    target_task_id: str = Field(min_length=1)
    items: list[CompletionItemState]

    @model_validator(mode="after")
    def validate_items(self) -> TargetCompletionState:
        """Keep one unambiguous state item per obligation identity."""
        obligation_ids = [item.obligation_id for item in self.items]
        if len(obligation_ids) != len(set(obligation_ids)):
            raise ValueError("completion obligation IDs must be unique")
        return self


class ActivationMode(StrEnum):
    """Deterministic target activation mode."""

    ALWAYS = "always"
    CONDITIONAL = "conditional"


class ObligationApplicability(StrEnum):
    """Static applicability vocabulary for completion obligations."""

    ALWAYS = "always"
    CONDITIONAL = "conditional"


class TargetActivation(BaseModel):
    """Immutable deterministic activation configuration for one target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ActivationMode
    rule_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_rule(self) -> TargetActivation:
        """Require a rule exactly when activation is conditional."""
        if self.mode is ActivationMode.ALWAYS and self.rule_id is not None:
            raise ValueError("always activation cannot declare rule_id")
        if self.mode is ActivationMode.CONDITIONAL and self.rule_id is None:
            raise ValueError("conditional activation requires rule_id")
        return self


class CompletionObligationDefinition(BaseModel):
    """Immutable semantic definition of one target completion obligation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    obligation_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    applicability: ObligationApplicability
    condition_hint: str | None = Field(default=None, min_length=1)


class TargetDefinition(BaseModel):
    """Complete immutable semantic contract for one memory target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    activation: TargetActivation
    depends_on: list[str]
    canonical_question: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_abstraction: str = Field(min_length=1)
    always_relevant_scope: list[str]
    conditional_scope: list[str]
    exclusions: list[str]
    boundary_guidance: list[str]
    investigation_expectations: list[str]
    evidence_expectations: list[str]
    completion_obligations: list[CompletionObligationDefinition]
    output_quality_expectations: list[str]

    @model_validator(mode="after")
    def validate_contract(self) -> TargetDefinition:
        """Reject ambiguous dependencies and completion obligations."""
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("target dependencies must be unique")
        if self.target_id in self.depends_on:
            raise ValueError("a target cannot depend on itself")
        obligation_ids = [
            obligation.obligation_id for obligation in self.completion_obligations
        ]
        if len(obligation_ids) != len(set(obligation_ids)):
            raise ValueError("completion obligation IDs must be unique")
        return self


class TargetCatalogEntry(BaseModel):
    """Immutable catalog reference to one exact target contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)


class MemoryTargetCatalog(BaseModel):
    """Immutable target/version inventory and global ownership policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    targets: list[TargetCatalogEntry]
    cross_target_ownership_rules: list[str]

    @model_validator(mode="after")
    def validate_targets(self) -> MemoryTargetCatalog:
        """Require one deterministic catalog entry per semantic target."""
        target_ids = [entry.target_id for entry in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("catalog target IDs must be unique")
        return self


__all__ = [
    "ActivationMode",
    "CandidateArtifactRef",
    "CompletionItemState",
    "CompletionObligationDefinition",
    "CompletionStatus",
    "ExecutionBudget",
    "ExecutionUsage",
    "FindingOrigin",
    "FindingRef",
    "FleetPhase",
    "FleetRunState",
    "MemoryFleetSpec",
    "MemoryTargetCatalog",
    "ObligationApplicability",
    "SourceBinding",
    "TargetActivation",
    "TargetCatalogEntry",
    "TargetCompletionState",
    "TargetDefinition",
    "TargetPhase",
    "TargetTaskSpec",
    "TargetTaskState",
]
