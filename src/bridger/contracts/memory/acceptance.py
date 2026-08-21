"""Durable contract for memory-harness Stage 10 target acceptance."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bridger.contracts.memory.core import (
    CandidateArtifactRef,
    CompletionItemState,
    SourceBinding,
)


class AcceptedTargetResult(BaseModel):
    """Immutable provenance for one exact locally accepted target candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    accepted_target_result_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    source: SourceBinding
    artifact_refs: list[CandidateArtifactRef]
    completion_items: list[CompletionItemState]
    evidence_refs: list[str]
    finalization_request_ref: str = Field(min_length=1)
    validation_report_ref: str = Field(min_length=1)
    review_verdict_ref: str = Field(min_length=1)


__all__ = ["AcceptedTargetResult"]
