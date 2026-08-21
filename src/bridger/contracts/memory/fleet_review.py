"""Contracts for memory-harness Stage 12 fleet reconciliation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bridger.contracts.memory.acceptance import AcceptedTargetResult
from bridger.contracts.memory.core import (
    CandidateArtifactRef,
    FindingOrigin,
    FindingRef,
    SourceBinding,
    TargetDefinition,
)
from bridger.contracts.memory.fleet_validation import FleetValidationReport
from bridger.contracts.memory.review import ReviewVerdict


class FleetReviewFindingDraft(BaseModel):
    """Provider-produced fleet finding without runtime-owned identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion_id: str = Field(min_length=1)
    affected_target_task_ids: list[str]
    affected_artifact_paths: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1)
    required_outcome: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_affected_targets(self) -> FleetReviewFindingDraft:
        """Require an unambiguous actionable repair-routing set."""
        if not self.affected_target_task_ids:
            raise ValueError("fleet review finding requires an affected target")
        if len(self.affected_target_task_ids) != len(
            set(self.affected_target_task_ids)
        ):
            raise ValueError("affected target task IDs must be unique")
        if len(self.affected_artifact_paths) != len(set(self.affected_artifact_paths)):
            raise ValueError("affected artifact paths must be unique")
        return self


class FleetReviewModelResult(BaseModel):
    """Strict structured output requested from the fleet reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: ReviewVerdict
    summary: str = Field(min_length=1)
    findings: list[FleetReviewFindingDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> FleetReviewModelResult:
        """Keep the semantic verdict aligned with its findings."""
        if self.outcome is ReviewVerdict.PASS and self.findings:
            raise ValueError("PASS fleet review output cannot contain findings")
        if self.outcome is ReviewVerdict.NEEDS_WORK and not self.findings:
            raise ValueError("NEEDS_WORK fleet review output requires a finding")
        return self


class FleetReviewArtifact(BaseModel):
    """One exact accepted artifact exposed to the fleet reviewer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_task_id: str = Field(min_length=1)
    fleet_relative_path: str = Field(min_length=1)
    reference: CandidateArtifactRef
    content: str


class FleetReviewContext(BaseModel):
    """Fresh immutable full-corpus input for one exact Stage 11 PASS."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_review_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    source: SourceBinding
    target_catalog_id: str = Field(min_length=1)
    target_catalog_version: str = Field(min_length=1)
    fleet_validation_report_ref: str = Field(min_length=1)
    reviewer_profile_id: str = Field(min_length=1)
    fleet_reviewer_instructions: str = Field(min_length=1)
    fleet_reconciliation_rubric: str = Field(min_length=1)
    cross_target_ownership_rules: list[str]
    target_definitions: list[TargetDefinition]
    accepted_target_results: list[AcceptedTargetResult]
    accepted_artifacts: list[FleetReviewArtifact]
    fleet_validation_report: FleetValidationReport


class FleetReviewFinding(BaseModel):
    """One immutable runtime-identified fleet reconciliation finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    finding_id: str = Field(min_length=1)
    fleet_review_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    criterion_id: str = Field(min_length=1)
    affected_target_task_ids: list[str]
    affected_artifact_paths: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1)
    required_outcome: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_affected_targets(self) -> FleetReviewFinding:
        """Require one unambiguous non-empty repair-routing target set."""
        if not self.affected_target_task_ids:
            raise ValueError("fleet review finding requires an affected target")
        if len(self.affected_target_task_ids) != len(
            set(self.affected_target_task_ids)
        ):
            raise ValueError("affected target task IDs must be unique")
        if len(self.affected_artifact_paths) != len(set(self.affected_artifact_paths)):
            raise ValueError("affected artifact paths must be unique")
        return self


class FleetReviewVerdict(BaseModel):
    """Immutable Stage 12 verdict over one exact Stage 11 PASS fleet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    fleet_review_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    fleet_validation_report_ref: str = Field(min_length=1)
    verdict: ReviewVerdict
    finding_refs: list[FindingRef]
    reviewer_profile_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_verdict(self) -> FleetReviewVerdict:
        """Keep verdict and fleet-review finding references aligned."""
        if any(
            reference.origin is not FindingOrigin.FLEET_REVIEW
            for reference in self.finding_refs
        ):
            raise ValueError("fleet review findings must be FLEET_REVIEW")
        finding_ids = [reference.finding_id for reference in self.finding_refs]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("fleet review finding references must be unique")
        if self.verdict is ReviewVerdict.PASS and self.finding_refs:
            raise ValueError("PASS fleet review verdict cannot contain findings")
        if self.verdict is ReviewVerdict.NEEDS_WORK and not self.finding_refs:
            raise ValueError("NEEDS_WORK fleet review verdict requires findings")
        return self


__all__ = [
    "FleetReviewArtifact",
    "FleetReviewContext",
    "FleetReviewFinding",
    "FleetReviewFindingDraft",
    "FleetReviewModelResult",
    "FleetReviewVerdict",
]
