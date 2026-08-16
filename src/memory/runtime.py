"""High-level composition surface for the memory-agent runtime."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from memory.initialisation import initialize_fleet as _initialize_fleet
from memory.scheduling import schedule_runnable_targets as _schedule_runnable_targets
from memory.stage_zero import ActivationRule
from memory.stage_zero import bind_memory_run as _bind_memory_run
from memory.stage_zero import resolve_target_activation as _resolve_target_activation
from models.enrichment import GraphEnrichmentOverlay
from models.files import FileIndex
from models.graph import GraphBuildResult
from models.memory import (
    ExecutionBudget,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    TargetCompletionState,
    TargetDefinition,
    TargetTaskSpec,
    TargetTaskState,
)
from models.repository import RepositoryContext
from models.symbols import SymbolIndex


def resolve_target_activation(
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    repository_context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    *,
    activation_rules: Mapping[str, ActivationRule] | None = None,
) -> list[str]:
    """Compose the deterministic target-activation portion of Stage 0."""
    return _resolve_target_activation(
        catalog,
        definitions,
        repository_context,
        file_index,
        symbol_index,
        graph_build,
        activation_rules=activation_rules,
    )


def bind_memory_run(
    repository_context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
    *,
    runtime_profile_id: str,
    default_worker_profile_id: str,
    default_reviewer_profile_id: str,
    default_permission_profile_id: str,
    fleet_budget: ExecutionBudget,
    default_target_budget: ExecutionBudget,
    runtime_root: Path,
    output_root: Path,
    max_concurrent_targets: int = 1,
    enrichment_overlay: GraphEnrichmentOverlay | None = None,
    activation_rules: Mapping[str, ActivationRule] | None = None,
) -> MemoryFleetSpec:
    """Compose Stage 0 and return its immutable bound fleet specification."""
    return _bind_memory_run(
        repository_context,
        file_index,
        symbol_index,
        graph_build,
        catalog,
        definitions,
        runtime_profile_id=runtime_profile_id,
        default_worker_profile_id=default_worker_profile_id,
        default_reviewer_profile_id=default_reviewer_profile_id,
        default_permission_profile_id=default_permission_profile_id,
        fleet_budget=fleet_budget,
        default_target_budget=default_target_budget,
        runtime_root=runtime_root,
        output_root=output_root,
        max_concurrent_targets=max_concurrent_targets,
        enrichment_overlay=enrichment_overlay,
        activation_rules=activation_rules,
    )


def initialize_fleet(
    fleet_spec: MemoryFleetSpec,
    catalog: MemoryTargetCatalog,
    definitions: Sequence[TargetDefinition],
) -> tuple[
    FleetRunState,
    list[TargetTaskSpec],
    list[TargetTaskState],
    list[TargetCompletionState],
]:
    """Compose Stage 1 and return its complete initialized fleet state."""
    return _initialize_fleet(fleet_spec, catalog, definitions)


def schedule_runnable_targets(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
) -> list[str]:
    """Compose Stage 2 and return target tasks admitted by this pass."""
    return _schedule_runnable_targets(
        fleet_spec,
        fleet_state,
        target_specs,
        target_states,
    )


__all__ = [
    "ActivationRule",
    "bind_memory_run",
    "initialize_fleet",
    "resolve_target_activation",
    "schedule_runnable_targets",
]
