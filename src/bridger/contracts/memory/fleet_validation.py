"""Durable contracts for memory-harness Stage 11 fleet validation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bridger.contracts.memory.core import FindingOrigin, FindingRef
from bridger.contracts.memory.validation import ValidationVerdict


class FleetValidationFinding(BaseModel):
    """One immutable deterministic accepted-fleet composition failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    finding_id: str = Field(min_length=1)
    fleet_validation_report_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    affected_target_task_ids: list[str]
    subject_kind: str = Field(min_length=1)
    subject_ref: str | None = Field(default=None, min_length=1)
    message: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_affected_targets(self) -> FleetValidationFinding:
        """Require one unambiguous non-empty repair-routing target set."""
        if not self.affected_target_task_ids:
            raise ValueError("fleet validation finding requires an affected target")
        if len(self.affected_target_task_ids) != len(
            set(self.affected_target_task_ids)
        ):
            raise ValueError("affected target task IDs must be unique")
        return self


class FleetValidationReport(BaseModel):
    """Immutable Stage 11 verdict over one exact ordered accepted fleet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    fleet_validation_report_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    accepted_target_result_refs: list[str]
    verdict: ValidationVerdict
    finding_refs: list[FindingRef]

    @model_validator(mode="after")
    def validate_verdict(self) -> FleetValidationReport:
        """Keep verdict and fleet-validation finding references aligned."""
        if not self.accepted_target_result_refs:
            raise ValueError("fleet validation report requires accepted targets")
        if len(self.accepted_target_result_refs) != len(
            set(self.accepted_target_result_refs)
        ):
            raise ValueError("accepted target result references must be unique")
        if any(
            reference.origin is not FindingOrigin.FLEET_VALIDATION
            for reference in self.finding_refs
        ):
            raise ValueError("fleet validation findings must be FLEET_VALIDATION")
        finding_ids = [reference.finding_id for reference in self.finding_refs]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("fleet validation finding references must be unique")
        if self.verdict is ValidationVerdict.PASS and self.finding_refs:
            raise ValueError("PASS fleet validation report cannot contain findings")
        if self.verdict is ValidationVerdict.FAIL and not self.finding_refs:
            raise ValueError("FAIL fleet validation report requires findings")
        return self


__all__ = ["FleetValidationFinding", "FleetValidationReport"]
