"""Typed contracts for memory-harness Stage 8 target review."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.memory import (
    CandidateArtifactRef,
    FindingOrigin,
    FindingRef,
    TargetCompletionState,
    TargetDefinition,
)
from models.validation import TargetValidationReport
from models.worker_cycle import OpenQuestion


class ReviewVerdict(StrEnum):
    """Artifact-level outcome of one target review round."""

    PASS = "pass"
    NEEDS_WORK = "needs-work"


class ReviewFindingSeverity(StrEnum):
    """Acceptance effect of one reviewer finding."""

    BLOCKING = "blocking"
    NON_BLOCKING = "non-blocking"


class ReviewFindingDraft(BaseModel):
    """Provider-produced finding content without runtime-owned identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rubric_dimension: str = Field(min_length=1)
    affected_scope: str | None = Field(default=None, min_length=1)
    affected_artifact_id: str | None = Field(default=None, min_length=1)
    message: str = Field(min_length=1)
    repair_instruction: str = Field(min_length=1)


class TargetReviewModelResult(BaseModel):
    """Strict structured output requested from the read-only reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ReviewVerdict
    summary: str = Field(min_length=1)
    blocking_findings: list[ReviewFindingDraft] = Field(default_factory=list)
    non_blocking_findings: list[ReviewFindingDraft] = Field(default_factory=list)
    repair_priorities: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> TargetReviewModelResult:
        """Keep the structured decision aligned with its blocking findings."""
        if self.outcome is ReviewVerdict.PASS:
            if self.blocking_findings:
                raise ValueError("PASS review output cannot contain blocking findings")
            if self.repair_priorities:
                raise ValueError("PASS review output cannot contain repair priorities")
        elif not self.blocking_findings:
            raise ValueError("NEEDS_WORK review output requires a blocking finding")
        elif not self.repair_priorities:
            raise ValueError("NEEDS_WORK review output requires repair priorities")
        return self


class ReviewFinding(BaseModel):
    """One immutable runtime-identified target-review finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    finding_id: str = Field(min_length=1)
    review_verdict_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    severity: ReviewFindingSeverity
    rubric_dimension: str = Field(min_length=1)
    affected_scope: str | None = Field(default=None, min_length=1)
    affected_artifact_id: str | None = Field(default=None, min_length=1)
    message: str = Field(min_length=1)
    repair_instruction: str = Field(min_length=1)


class TargetReviewVerdict(BaseModel):
    """Immutable Stage 8 verdict over one exact validated checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    review_verdict_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    finalization_request_id: str = Field(min_length=1)
    candidate_checkpoint_ref: str = Field(min_length=1)
    validation_report_id: str = Field(min_length=1)
    reviewer_profile_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    provider_response_id: str | None = Field(default=None, min_length=1)
    verdict: ReviewVerdict
    summary: str = Field(min_length=1)
    blocking_finding_refs: list[FindingRef] = Field(default_factory=list)
    non_blocking_finding_refs: list[FindingRef] = Field(default_factory=list)
    repair_priorities: list[str] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def validate_verdict(self) -> TargetReviewVerdict:
        """Keep verdict, findings, and repair guidance internally coherent."""
        references = [
            *self.blocking_finding_refs,
            *self.non_blocking_finding_refs,
        ]
        if any(
            reference.origin is not FindingOrigin.TARGET_REVIEW
            for reference in references
        ):
            raise ValueError("review verdict findings must be TARGET_REVIEW")
        finding_ids = [reference.finding_id for reference in references]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("review verdict finding references must be unique")
        if self.verdict is ReviewVerdict.PASS:
            if self.blocking_finding_refs:
                raise ValueError("PASS review verdict cannot contain blocking findings")
            if self.repair_priorities:
                raise ValueError("PASS review verdict cannot contain repair priorities")
        elif not self.blocking_finding_refs:
            raise ValueError("NEEDS_WORK review verdict requires blocking findings")
        elif not self.repair_priorities:
            raise ValueError("NEEDS_WORK review verdict requires repair priorities")
        return self


class ReviewerInstructions(BaseModel):
    """Exact shared prompt and target rubric supplied to Stage 8."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    shared: str = Field(min_length=1)
    target_specific: str = Field(min_length=1)


class ReviewArtifact(BaseModel):
    """One exact checkpointed Markdown artifact exposed to the reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference: CandidateArtifactRef
    content: str


class TargetReviewContext(BaseModel):
    """Fresh immutable reviewer input for one exact Stage 7 PASS candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_task_id: str = Field(min_length=1)
    finalization_request_id: str = Field(min_length=1)
    candidate_checkpoint_ref: str = Field(min_length=1)
    reviewer_profile_id: str = Field(min_length=1)
    shared_reviewer_instructions: str = Field(min_length=1)
    target_reviewer_rubric: str = Field(min_length=1)
    cross_target_ownership_rules: list[str]
    target_definition: TargetDefinition
    completion_state: TargetCompletionState
    open_questions: list[OpenQuestion]
    candidate_artifacts: list[ReviewArtifact]
    hard_validation_report: TargetValidationReport
    previous_review_findings: list[ReviewFinding]


__all__ = [
    "ReviewArtifact",
    "ReviewFinding",
    "ReviewFindingDraft",
    "ReviewFindingSeverity",
    "ReviewerInstructions",
    "ReviewVerdict",
    "TargetReviewContext",
    "TargetReviewModelResult",
    "TargetReviewVerdict",
]
