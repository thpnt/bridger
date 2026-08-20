"""Durable contract for memory-harness Stage 13 fleet acceptance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.memory import SourceBinding


class AcceptedMemoryFleetResult(BaseModel):
    """Immutable composition and provenance of one accepted memory fleet."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    accepted_memory_fleet_result_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    source: SourceBinding
    target_catalog_id: str = Field(min_length=1)
    target_catalog_version: str = Field(min_length=1)
    accepted_target_result_refs: list[str]
    fleet_validation_report_ref: str = Field(min_length=1)
    fleet_review_verdict_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_accepted_targets(self) -> AcceptedMemoryFleetResult:
        """Require one unambiguous non-empty accepted-target composition."""
        if not self.accepted_target_result_refs:
            raise ValueError("accepted memory fleet requires accepted targets")
        if len(self.accepted_target_result_refs) != len(
            set(self.accepted_target_result_refs)
        ):
            raise ValueError("accepted target result references must be unique")
        return self


__all__ = ["AcceptedMemoryFleetResult"]
