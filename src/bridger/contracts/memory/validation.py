"""Durable contracts introduced by memory-harness Stage 7."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bridger.contracts.memory.core import FindingOrigin, FindingRef


class ValidationVerdict(StrEnum):
    """Deterministic outcome of one target hard-validation round."""

    PASS = "pass"
    FAIL = "fail"


class ValidationFinding(BaseModel):
    """One immutable deterministic candidate-gate failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    finding_id: str = Field(min_length=1)
    validation_report_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    subject_kind: str = Field(min_length=1)
    subject_ref: str | None = Field(default=None, min_length=1)
    message: str = Field(min_length=1)


class TargetValidationReport(BaseModel):
    """Immutable Stage 7 verdict over one exact finalization checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    validation_report_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    finalization_request_id: str = Field(min_length=1)
    candidate_checkpoint_ref: str = Field(min_length=1)
    verdict: ValidationVerdict
    finding_refs: list[FindingRef]
    created_at: datetime

    @model_validator(mode="after")
    def validate_verdict(self) -> TargetValidationReport:
        """Keep the verdict and hard-validation finding projection aligned."""
        if any(
            reference.origin is not FindingOrigin.HARD_VALIDATION
            for reference in self.finding_refs
        ):
            raise ValueError("validation report findings must be HARD_VALIDATION")
        if self.verdict is ValidationVerdict.PASS and self.finding_refs:
            raise ValueError("PASS validation report cannot contain findings")
        if self.verdict is ValidationVerdict.FAIL and not self.finding_refs:
            raise ValueError("FAIL validation report requires findings")
        finding_ids = [reference.finding_id for reference in self.finding_refs]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("validation report finding references must be unique")
        return self


__all__ = [
    "TargetValidationReport",
    "ValidationFinding",
    "ValidationVerdict",
]
