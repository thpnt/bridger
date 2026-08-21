"""Durable contracts introduced by memory-harness Stage 5."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bridger.contracts.memory.core import (
    SourceBinding,
    TargetCompletionState,
    TargetTaskState,
)
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion


class TaskEvent(BaseModel):
    """One immutable fleet-global audit record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str | None = Field(default=None, min_length=1)
    sequence: int = Field(ge=1)
    event_type: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    operation_id: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any]


class TaskCheckpoint(BaseModel):
    """Immutable known-good target recovery snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    checkpoint_id: str = Field(min_length=1)
    checkpoint_sequence: int = Field(ge=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    source: SourceBinding
    target_task_spec_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_sequence: int = Field(ge=0)
    created_at: str = Field(min_length=1)
    task_state: TargetTaskState
    completion_state: TargetCompletionState
    evidence_records: list[EvidenceReference]
    open_questions: list[OpenQuestion]
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class TargetFinalizationRequest(BaseModel):
    """Immutable identity of one candidate submitted for evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    finalization_request_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str = Field(min_length=1)
    candidate_checkpoint_ref: str = Field(min_length=1)
    created_at: datetime


class RuntimeErrorRecord(BaseModel):
    """Immutable detail for one runtime or infrastructure failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    error_id: str = Field(min_length=1)
    fleet_run_id: str = Field(min_length=1)
    target_task_id: str | None = Field(default=None, min_length=1)
    phase: str | None = Field(default=None, min_length=1)
    category: str = Field(min_length=1)
    operation: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool
    operation_id: str | None = Field(default=None, min_length=1)
    cause_ref: str | None = Field(default=None, min_length=1)
    debug_ref: str | None = Field(default=None, min_length=1)
    timestamp: str = Field(min_length=1)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Keep the V0 runtime error vocabulary deliberately small."""
        allowed = {
            "provider",
            "storage",
            "runtime",
            "integrity",
            "context-capacity",
            "configuration",
        }
        if value not in allowed:
            raise ValueError(f"unsupported runtime error category: {value}")
        return value


__all__ = [
    "RuntimeErrorRecord",
    "TargetFinalizationRequest",
    "TaskCheckpoint",
    "TaskEvent",
]
