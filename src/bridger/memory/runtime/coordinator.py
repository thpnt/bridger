"""High-level composition surface for the memory-agent runtime."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from bridger.contracts.enrichment import GraphEnrichmentOverlay
from bridger.contracts.files import FileIndex
from bridger.contracts.graph import GraphBuildResult
from bridger.contracts.memory.core import (
    ExecutionBudget,
    FleetRunState,
    MemoryFleetSpec,
    MemoryTargetCatalog,
    TargetCompletionState,
    TargetDefinition,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.hydration import (
    PermissionProfile,
    WorkerContext,
    WorkerProfile,
)
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.contracts.repository import RepositoryContext
from bridger.contracts.symbols import SymbolIndex
from bridger.llm.client import LLMClient
from bridger.llm.errors import LLMError
from bridger.memory.errors import WorkerCyclePreflightError
from bridger.memory.persistence.durability import FleetRuntimeStore
from bridger.memory.persistence.recovery import (
    create_checkpoint,
    record_runtime_error,
    recover_target,
)
from bridger.memory.runtime.context_window import ContextWindowManager
from bridger.memory.runtime.finalization import handle_finalization_request
from bridger.memory.runtime.hydration import compile_worker_context
from bridger.memory.runtime.initialization import initialize_fleet as _initialize_fleet
from bridger.memory.runtime.scheduling import (
    schedule_runnable_targets as _schedule_runnable_targets,
)
from bridger.memory.runtime.stage_zero import ActivationRule
from bridger.memory.runtime.stage_zero import bind_memory_run as _bind_memory_run
from bridger.memory.runtime.stage_zero import (
    resolve_target_activation as _resolve_target_activation,
)
from bridger.memory.runtime.worker_cycle import (
    FleetExecutionCoordinator,
    WorkerCycleOutcome,
    WorkerRunner,
    WorkerRuntimeLimits,
)
from bridger.memory.runtime.worker_tools import (
    CompletionStateUpdater,
    EvidenceRecorder,
    ProgressUpdater,
    TargetWorkspace,
    WorkerToolRuntime,
)
from bridger.navigation.navigator import RepositoryNavigator


async def run_worker_cycle(
    *,
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    target_definition: TargetDefinition,
    context: WorkerContext,
    worker_profile: WorkerProfile,
    permission_profile: PermissionProfile,
    context_window_manager: ContextWindowManager,
    llm_client: LLMClient,
    navigator: RepositoryNavigator,
    evidence: dict[str, EvidenceReference],
    questions: dict[str, OpenQuestion],
    coordinator: FleetExecutionCoordinator,
    limits: WorkerRuntimeLimits | None = None,
    persistence: FleetRuntimeStore | None = None,
) -> WorkerCycleOutcome:
    """Bind controlled Stage 4 services and execute one hydrated worker cycle."""
    if permission_profile.profile_id != target_spec.permission_profile_id:
        raise WorkerCyclePreflightError(
            "permission profile does not match the target task"
        )
    workspace = TargetWorkspace(target_spec, target_state, persistence)
    evidence_recorder = EvidenceRecorder(
        target_spec,
        target_state,
        navigator,
        evidence,
        persistence,
    )
    completion_updater = CompletionStateUpdater(
        target_spec,
        target_state,
        completion_state,
        target_definition,
        evidence,
        persistence,
    )
    progress_updater = ProgressUpdater(
        target_spec,
        target_state,
        questions,
        persistence,
    )
    tools = WorkerToolRuntime(
        context,
        permission_profile,
        navigator,
        workspace,
        evidence_recorder,
        completion_updater,
        progress_updater,
    )
    runner = WorkerRunner(
        fleet_spec=fleet_spec,
        fleet_state=fleet_state,
        target_spec=target_spec,
        target_state=target_state,
        completion_state=completion_state,
        context=context,
        worker_profile=worker_profile,
        context_window_manager=context_window_manager,
        llm_client=llm_client,
        tools=tools,
        evidence=evidence,
        questions=questions,
        coordinator=coordinator,
        limits=limits,
    )
    if persistence is not None:
        coordinator.bind_persistence(persistence, fleet_state)
    outcome = await runner.run()
    if persistence is not None:
        runtime_error = runner.last_runtime_error
        if outcome is WorkerCycleOutcome.FINALIZATION_REQUESTED:
            handle_finalization_request(
                persistence,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
            )
        elif (
            outcome is WorkerCycleOutcome.EXECUTION_INTERRUPTED
            and isinstance(runtime_error, LLMError)
            and not runtime_error.retryable
        ):
            target_state.phase = TargetPhase.FAILED
            record_runtime_error(
                persistence,
                fleet_state,
                category="provider",
                operation="model-invocation",
                message=runtime_error.safe_message,
                retryable=False,
                target_spec=target_spec,
                target_state=target_state,
                phase=TargetPhase.WORKING.value,
            )
            create_checkpoint(
                persistence,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
            )
        elif (
            outcome
            in {
                WorkerCycleOutcome.EXECUTION_INTERRUPTED,
                WorkerCycleOutcome.FLEET_BUDGET_STOP,
            }
            and target_state.phase is TargetPhase.WORKING
        ):
            recover_target(
                persistence,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
                error_category=(
                    "provider" if isinstance(runtime_error, LLMError) else "runtime"
                ),
                error_operation=(
                    "model-invocation"
                    if isinstance(runtime_error, LLMError)
                    else "worker-cycle"
                ),
                error_message=(
                    runtime_error.safe_message
                    if isinstance(runtime_error, LLMError)
                    else "active worker trajectory was interrupted"
                ),
                error_retryable=(
                    runtime_error.retryable
                    if isinstance(runtime_error, LLMError)
                    else True
                ),
            )
        else:
            create_checkpoint(
                persistence,
                target_spec,
                target_state,
                completion_state,
                evidence,
                questions,
            )
    return outcome


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
    *,
    persistence: FleetRuntimeStore | None = None,
) -> list[str]:
    """Compose Stage 2 and return target tasks admitted by this pass."""
    return _schedule_runnable_targets(
        fleet_spec,
        fleet_state,
        target_specs,
        target_states,
        persistence=persistence,
    )


__all__ = [
    "ActivationRule",
    "bind_memory_run",
    "compile_worker_context",
    "initialize_fleet",
    "resolve_target_activation",
    "run_worker_cycle",
    "schedule_runnable_targets",
]
