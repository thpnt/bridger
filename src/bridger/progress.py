"""Rich-independent progress observation for Repository Brain initialization."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from bridger.contracts.memory.core import (
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.persistence import TaskEvent


class InitStage(StrEnum):
    """Semantic stages in Repository Brain initialization."""

    PREPARE_REPOSITORY = "prepare-repository"
    EXTRACT_FACTS = "extract-facts"
    BUILD_GRAPH = "build-graph"
    PUBLISH_GRAPH = "publish-graph"
    MODEL_ENRICHMENT = "model-enrichment"
    INITIALIZE_MEMORY_FLEET = "initialize-memory-fleet"
    PUBLISH_REPOSITORY_BRAIN = "publish-repository-brain"
    PREPARE_BRAIN_INDEX = "prepare-brain-index"


class InitProgressObserver(Protocol):
    """Observe authoritative initialization state without controlling it."""

    def stage_started(self, stage: InitStage) -> None:
        """Observe the start of one semantic initialization stage."""
        ...

    def fleet_initialized(
        self,
        fleet_spec: MemoryFleetSpec,
        target_specs: Sequence[TargetTaskSpec],
        target_states: Sequence[TargetTaskState],
        completion_states: Sequence[TargetCompletionState],
        fleet_state: FleetRunState,
    ) -> None:
        """Observe a complete authoritative fleet snapshot."""
        ...

    def runtime_event(self, event: TaskEvent) -> None:
        """Observe one newly committed runtime event."""
        ...

    def brain_index_started(self, total_chunks: int) -> None:
        """Observe the start of dense Repository Brain embedding."""
        ...

    def brain_index_progress(
        self,
        completed_chunks: int,
        total_chunks: int,
    ) -> None:
        """Observe one successfully embedded Repository Brain batch."""
        ...


def notify_stage_started(
    observer: InitProgressObserver | None,
    stage: InitStage,
) -> None:
    """Best-effort notify an observer that a stage started."""
    if observer is None:
        return
    try:
        observer.stage_started(stage)
    except Exception:
        pass


def notify_fleet_initialized(
    observer: InitProgressObserver | None,
    fleet_spec: MemoryFleetSpec,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    completion_states: Sequence[TargetCompletionState],
    fleet_state: FleetRunState,
) -> None:
    """Best-effort notify an observer with a complete fleet snapshot."""
    if observer is None:
        return
    try:
        observer.fleet_initialized(
            fleet_spec,
            target_specs,
            target_states,
            completion_states,
            fleet_state,
        )
    except Exception:
        pass


def notify_brain_index_started(
    observer: InitProgressObserver | None,
    total_chunks: int,
) -> None:
    """Best-effort notify an observer that dense embedding has started."""
    if observer is None:
        return
    try:
        observer.brain_index_started(total_chunks)
    except Exception:
        pass


def notify_brain_index_progress(
    observer: InitProgressObserver | None,
    completed_chunks: int,
    total_chunks: int,
) -> None:
    """Best-effort notify an observer after one dense embedding batch."""
    if observer is None:
        return
    try:
        observer.brain_index_progress(completed_chunks, total_chunks)
    except Exception:
        pass


__all__ = [
    "InitProgressObserver",
    "InitStage",
    "notify_brain_index_progress",
    "notify_brain_index_started",
    "notify_fleet_initialized",
    "notify_stage_started",
]
