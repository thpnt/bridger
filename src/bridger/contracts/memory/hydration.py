"""Transient contracts for memory-harness Stage 3 context hydration."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator

from bridger.contracts.memory.core import (
    CandidateArtifactRef,
    CompletionStatus,
    FindingOrigin,
    ObligationApplicability,
    SourceBinding,
)


class WorkerContextMode(StrEnum):
    """Derived execution purpose for one hydrated worker context."""

    INITIAL = "initial"
    REPAIR = "repair"


class WorkerCycleFocusKind(StrEnum):
    """Deterministic semantic objective for one hydrated worker cycle."""

    OBLIGATION = "obligation"
    REPAIR_FINDINGS = "repair-findings"
    FINALIZATION_READINESS = "finalization-readiness"


class WorkerCycleFocus(BaseModel):
    """Transient projection of the authoritative work selected for this cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: WorkerCycleFocusKind
    obligation_id: str | None = Field(default=None, min_length=1)
    finding_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_focus(self) -> WorkerCycleFocus:
        """Keep the kind-specific focus payload exact and unambiguous."""
        if self.kind is WorkerCycleFocusKind.OBLIGATION:
            if self.obligation_id is None or self.finding_ids:
                raise ValueError("obligation focus requires only obligation_id")
        elif self.kind is WorkerCycleFocusKind.REPAIR_FINDINGS:
            if self.obligation_id is not None or not self.finding_ids:
                raise ValueError("repair focus requires only finding_ids")
            if len(self.finding_ids) != len(set(self.finding_ids)):
                raise ValueError("repair focus finding_ids must be unique")
        elif self.obligation_id is not None or self.finding_ids:
            raise ValueError("finalization-readiness focus has no identifiers")
        return self


class WorkerProfile(BaseModel):
    """Resolved immutable V0 worker and model context configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    tokenizer_encoding: str = Field(min_length=1)
    model_context_window_tokens: PositiveInt
    reserved_response_tokens: int = Field(ge=0)
    reasoning_effort: (
        Literal["minimal", "low", "medium", "high", "xhigh", "max"] | None
    ) = "xhigh"
    reasoning_context: Literal["auto", "current_turn", "all_turns"] | None = "all_turns"
    provider_input_hard_cap_tokens: int = Field(
        default=32_000,
        ge=1,
        le=32_000,
    )

    @model_validator(mode="after")
    def validate_context_capacity(self) -> WorkerProfile:
        """Require one normal request and its response reserve to fit."""
        if (
            self.provider_input_hard_cap_tokens + self.reserved_response_tokens
            > self.model_context_window_tokens
        ):
            raise ValueError(
                "provider input cap and reserved response exceed model context window"
            )
        return self


class PermissionProfile(BaseModel):
    """Resolved immutable worker permission identity and allowed tool names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    allowed_tool_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_tool_ids(self) -> PermissionProfile:
        """Require stable, unique, non-empty tool identities."""
        if any(not tool_id.strip() for tool_id in self.allowed_tool_ids):
            raise ValueError("allowed_tool_ids must be non-empty strings")
        if len(self.allowed_tool_ids) != len(set(self.allowed_tool_ids)):
            raise ValueError("allowed_tool_ids must be unique")
        return self


class WorkerInstructions(BaseModel):
    """Exact immutable instruction content resolved for one target contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    worker_profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    shared: str = Field(min_length=1)
    target_specific: str = Field(min_length=1)


class TargetContractView(BaseModel):
    """Worker-facing projection of immutable target semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_abstraction: str = Field(min_length=1)
    always_relevant_scope: tuple[str, ...]
    conditional_scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    boundary_guidance: tuple[str, ...]
    investigation_expectations: tuple[str, ...]
    evidence_expectations: tuple[str, ...]
    output_quality_expectations: tuple[str, ...]


class CompletionObligationView(BaseModel):
    """One target obligation joined with its current durable resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    obligation_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    applicability: ObligationApplicability
    condition_hint: str | None = None
    status: CompletionStatus
    resolution_note: str | None = None
    evidence_refs: tuple[str, ...]


class OpenQuestion(BaseModel):
    """Actionable currently open question exposed to the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


class RepairFinding(BaseModel):
    """Actionable open validation or review finding exposed in repair mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    origin: FindingOrigin
    content: str = Field(min_length=1)
    affected_scope: str | None = Field(default=None, min_length=1)
    affected_artifact_id: str | None = Field(default=None, min_length=1)
    affected_artifact_refs: tuple[str, ...] = ()
    affected_obligation_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class RemainingExecutionBudget(BaseModel):
    """Derived target-only execution headroom supplied to the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycles: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    repair_cycles: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class WorkerContext(BaseModel):
    """Immutable provider-neutral execution view for one worker execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_task_id: str = Field(min_length=1)
    mode: WorkerContextMode
    worker_profile_id: str = Field(min_length=1)
    permission_profile_id: str = Field(min_length=1)
    allowed_tool_ids: tuple[str, ...]
    source: SourceBinding
    shared_worker_instructions: str = Field(min_length=1)
    global_ownership_guidance: tuple[str, ...]
    target_worker_instructions: str = Field(min_length=1)
    target_contract: TargetContractView
    cycle_focus: WorkerCycleFocus
    completion_obligations: tuple[CompletionObligationView, ...]
    repair_findings: tuple[RepairFinding, ...]
    working_summary: str | None = None
    open_questions: tuple[OpenQuestion, ...]
    remaining_target_budget: RemainingExecutionBudget
    candidate_artifacts: tuple[CandidateArtifactRef, ...]

    @model_validator(mode="after")
    def validate_mode_findings(self) -> WorkerContext:
        """Keep repair findings aligned with the derived context mode."""
        if self.mode is WorkerContextMode.INITIAL and self.repair_findings:
            raise ValueError("initial worker context cannot include repair findings")
        if self.mode is WorkerContextMode.REPAIR and not self.repair_findings:
            raise ValueError("repair worker context requires repair findings")
        if self.repair_findings:
            expected_ids = tuple(item.finding_id for item in self.repair_findings)
            if (
                self.cycle_focus.kind is not WorkerCycleFocusKind.REPAIR_FINDINGS
                or self.cycle_focus.finding_ids != expected_ids
            ):
                raise ValueError("repair cycle focus must match routed findings")
            return self
        unresolved = tuple(
            item.obligation_id
            for item in self.completion_obligations
            if item.status is CompletionStatus.UNINVESTIGATED
        )
        if unresolved:
            if (
                self.cycle_focus.kind is not WorkerCycleFocusKind.OBLIGATION
                or self.cycle_focus.obligation_id != unresolved[0]
            ):
                raise ValueError("normal cycle focus must select first unresolved item")
        elif self.cycle_focus.kind is not WorkerCycleFocusKind.FINALIZATION_READINESS:
            raise ValueError("resolved target requires finalization-readiness focus")
        return self


class ContextWindowDiagnostics(BaseModel):
    """Derived request-token visibility for hydration and future worker calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_context_window_tokens: PositiveInt
    reserved_response_tokens: int = Field(ge=0)
    provider_input_hard_cap_tokens: PositiveInt
    fixed_request_input_tokens: int = Field(ge=0)
    maximum_worker_context_tokens: int = Field(ge=0)
    worker_context_tokens: int = Field(ge=0)
    complete_initial_provider_input_tokens: int = Field(ge=0)
    remaining_provider_input_tokens: int = Field(ge=0)
    remaining_model_context_tokens: int = Field(ge=0)
    within_provider_input_limit: bool
    within_model_context_limit: bool


class RequestContextWindowDiagnostics(BaseModel):
    """Model-context visibility for any current or future provider request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_context_window_tokens: PositiveInt
    current_request_input_tokens: int = Field(ge=0)
    reserved_response_tokens: int = Field(ge=0)
    remaining_context_tokens: int = Field(ge=0)
    within_context_limit: bool


__all__ = [
    "CompletionObligationView",
    "ContextWindowDiagnostics",
    "OpenQuestion",
    "PermissionProfile",
    "RequestContextWindowDiagnostics",
    "RemainingExecutionBudget",
    "RepairFinding",
    "TargetContractView",
    "WorkerContext",
    "WorkerContextMode",
    "WorkerCycleFocus",
    "WorkerCycleFocusKind",
    "WorkerInstructions",
    "WorkerProfile",
]
