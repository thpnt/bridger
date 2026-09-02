"""Composition of the existing memory-harness stages for ``bridger init``."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import ValidationError

from bridger.contracts.enrichment import GraphEnrichmentConfig, GraphEnrichmentOverlay
from bridger.contracts.files import FileIndex, SourceReadRequest
from bridger.contracts.graph import GraphBuildResult, GraphConstructionConfig
from bridger.contracts.memory.core import (
    ExecutionBudget,
    FleetPhase,
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
    GraphOverview,
    PermissionProfile,
    WorkerInstructions,
    WorkerProfile,
)
from bridger.contracts.memory.review import ReviewerInstructions, ReviewVerdict
from bridger.contracts.memory.worker_cycle import EvidenceReference, OpenQuestion
from bridger.contracts.repository import RepositoryContext
from bridger.contracts.symbols import SymbolIndex
from bridger.graph.enrichment import (
    enrich_graph_snapshot,
    load_graph_enrichment,
    validate_graph_enrichment,
)
from bridger.graph.lifecycle import load_graph_snapshot, validate_graph_snapshot
from bridger.init_pipeline import (
    InitMode,
    InitRunConfiguration,
    ReasoningEffort,
    RepositoryBrainBuildError,
    RepositoryBrainModelBuildResult,
)
from bridger.llm.client import LLMClient
from bridger.llm.factory import create_llm_client_from_profile
from bridger.llm.profiles import LLMProfile, resolve_llm_profile
from bridger.memory import (
    ContextWindowManager,
    FleetExecutionCoordinator,
    FleetRuntimeStore,
    WorkerCycleOutcome,
    WorkerRuntimeLimits,
    accept_fleet,
    accept_target,
    bind_memory_run,
    build_graph_overview,
    compile_worker_context,
    initialize_fleet,
    initialize_persistence,
    load_target_artifacts,
    reconcile_fleet,
    recover_fleet,
    run_worker_cycle,
    schedule_runnable_targets,
    validate_fleet,
    validate_target_candidate,
)
from bridger.memory.errors import PersistenceRecoveryError, TargetReviewBudgetError
from bridger.memory.evaluation.review import review_target
from bridger.memory.runtime.worker_tools import WORKER_TOOL_IDS
from bridger.navigation.navigator import RepositoryNavigator
from bridger.progress import (
    InitProgressObserver,
    InitStage,
    notify_fleet_initialized,
    notify_stage_started,
)
from bridger.repository.reader import read_file
from bridger.repository_brain.publication import publish_repository_brain
from bridger.repository_brain.token_usage import persist_token_usage_report

_PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "memory" / "prompts"
_TARGETS_ROOT = Path(__file__).resolve().parents[1] / "memory" / "default-targets"
_TEST_TARGETS_ROOT = Path(__file__).resolve().parents[1] / "memory" / "test-targets"
_INITIAL_PROVIDER_INPUT_HARD_CAP_TOKENS = 32_000
_TEST_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS = 32_000
_FULL_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS = 256_000
_FULL_TARGET_INPUT_BUDGET_TOKENS = 2_000_000
_FULL_FLEET_INPUT_OVERHEAD_NUMERATOR = 5
_FULL_FLEET_INPUT_OVERHEAD_DENOMINATOR = 4
_FRONTEND_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_FRONTEND_FRAMEWORK_PACKAGES = frozenset(
    {
        "@angular/core",
        "@sveltejs/kit",
        "angular",
        "next",
        "nuxt",
        "react",
        "react-dom",
        "svelte",
        "vue",
    }
)


@dataclass(frozen=True, slots=True)
class _TargetStepRuntime:
    configuration: InitRunConfiguration
    fleet_spec: MemoryFleetSpec
    fleet_state: FleetRunState
    catalog: MemoryTargetCatalog
    worker_profile: WorkerProfile
    reviewer_profile: WorkerProfile
    permissions: PermissionProfile
    graph_overview: GraphOverview
    client: LLMClient
    navigator: RepositoryNavigator
    coordinator: FleetExecutionCoordinator
    store: FleetRuntimeStore
    definitions_by_id: dict[str, TargetDefinition]
    specs_by_task: dict[str, TargetTaskSpec]
    states_by_task: dict[str, TargetTaskState]
    completion_by_task: dict[str, TargetCompletionState]


async def run_memory_harness(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    profile: LLMProfile,
    enrichment: GraphEnrichmentOverlay,
    *,
    progress: InitProgressObserver | None = None,
    recovery_spec: MemoryFleetSpec | None = None,
) -> RepositoryBrainModelBuildResult:
    """Run the existing Layer 5 and memory stages through publication."""
    catalog, definitions = load_target_artifacts(_target_artifacts_root(configuration))
    worker_profile, reviewer_profile = _profiles(
        profile, configuration.test_budgets, configuration.reasoning_effort
    )
    permissions = PermissionProfile(
        profile_id="bridger-memory-tools-v2",
        allowed_tool_ids=WORKER_TOOL_IDS,
    )
    target_budget = _target_budget_for(configuration.test_budgets)
    fleet_budget = _fleet_budget_for(
        configuration.test_budgets,
        target_capacity=len(catalog.targets),
    )
    output_root = configuration.bridger_root / "memory"
    recovered = None
    if recovery_spec is None:
        fleet_spec = bind_memory_run(
            context,
            file_index,
            symbol_index,
            graph_build,
            catalog,
            definitions,
            runtime_profile_id=_runtime_profile_id(configuration),
            default_worker_profile_id=worker_profile.profile_id,
            default_reviewer_profile_id=reviewer_profile.profile_id,
            default_permission_profile_id=permissions.profile_id,
            fleet_budget=fleet_budget,
            default_target_budget=target_budget,
            runtime_root=configuration.bridger_root / "runtime",
            output_root=output_root,
            max_concurrent_targets=len(catalog.targets),
            enrichment_overlay=enrichment,
            activation_rules={"frontend_stack_present_v1": _frontend_stack_present},
        )
        fleet_state, target_specs, target_states, completion_states = initialize_fleet(
            fleet_spec,
            catalog,
            definitions,
        )
        notify_fleet_initialized(
            progress,
            fleet_spec,
            target_specs,
            target_states,
            completion_states,
            fleet_state,
        )
        store = initialize_persistence(
            fleet_spec,
            fleet_state,
            target_specs,
            target_states,
            completion_states,
            **(
                {"event_observer": progress.runtime_event}
                if progress is not None
                else {}
            ),
        )
    else:
        recovered = recover_fleet(
            configuration.bridger_root / "runtime",
            recovery_spec.fleet_run_id,
            source=recovery_spec.source,
            catalog=catalog,
            definitions=definitions,
            runtime_profile_id=_runtime_profile_id(configuration),
            worker_profile_ids={worker_profile.profile_id},
            reviewer_profile_ids={reviewer_profile.profile_id},
            permission_profile_ids={permissions.profile_id},
        )
        fleet_spec = recovered.fleet_spec
        fleet_state = recovered.fleet_state
        target_specs = list(recovered.target_specs.values())
        target_states = list(recovered.target_states.values())
        completion_states = list(recovered.completion_states.values())
        store = recovered.store
        notify_fleet_initialized(
            progress,
            fleet_spec,
            target_specs,
            target_states,
            completion_states,
            fleet_state,
        )
        if progress is not None:
            store.set_event_observer(progress.runtime_event)
    client: LLMClient | None = None
    active_error: BaseException | None = None
    try:
        navigator = RepositoryNavigator(
            context,
            file_index,
            symbol_index,
            graph_build,
            enrichment,
        )
        graph_overview = build_graph_overview(graph_build)
        coordinator = FleetExecutionCoordinator()
        client = create_llm_client_from_profile(profile)
        definitions_by_id = {
            definition.target_id: definition for definition in definitions
        }
        specs_by_task = {spec.target_task_id: spec for spec in target_specs}
        states_by_task = {state.target_task_id: state for state in target_states}
        completion_by_task = {
            state.target_task_id: state for state in completion_states
        }
        target_step_runtime = _TargetStepRuntime(
            configuration=configuration,
            fleet_spec=fleet_spec,
            fleet_state=fleet_state,
            catalog=catalog,
            worker_profile=worker_profile,
            reviewer_profile=reviewer_profile,
            permissions=permissions,
            graph_overview=graph_overview,
            client=client,
            navigator=navigator,
            coordinator=coordinator,
            store=store,
            definitions_by_id=definitions_by_id,
            specs_by_task=specs_by_task,
            states_by_task=states_by_task,
            completion_by_task=completion_by_task,
        )
        while fleet_state.phase is not FleetPhase.ACCEPTED:
            before_fleet_state = fleet_state.model_dump(mode="json")
            before_target_states = [
                state.model_dump(mode="json") for state in target_states
            ]
            runnable = _runnable_target_task_ids(
                fleet_spec,
                fleet_state,
                target_specs,
                target_states,
                store,
            )
            outcomes = await _run_target_batch(runnable, target_step_runtime)
            if WorkerCycleOutcome.FLEET_BUDGET_STOP in outcomes:
                store.exhaust_fleet_budget(fleet_state)
            if all(state.phase is TargetPhase.ACCEPTED for state in target_states):
                fleet_validation = validate_fleet(store, fleet_state)
                if fleet_validation.verdict.value == "pass":
                    fleet_review = await reconcile_fleet(
                        fleet_spec=fleet_spec,
                        fleet_state=fleet_state,
                        catalog=catalog,
                        target_definitions=[
                            definitions_by_id[target_id]
                            for target_id in fleet_spec.target_ids
                        ],
                        reviewer_profile=reviewer_profile,
                        reviewer_instructions=_read_prompt(
                            _PROMPTS_ROOT / "reviewer" / "system.md"
                        ),
                        reconciliation_rubric=_read_prompt(
                            _PROMPTS_ROOT / "reviewer" / "reconciliation.md"
                        ),
                        context_window_manager=ContextWindowManager(reviewer_profile),
                        llm_client=client,
                        coordinator=coordinator,
                        persistence=store,
                    )
                    if fleet_review.verdict is ReviewVerdict.PASS:
                        accepted = accept_fleet(store, fleet_state)
                        notify_stage_started(
                            progress,
                            InitStage.PUBLISH_REPOSITORY_BRAIN,
                        )
                        token_usage_report_path = persist_token_usage_report(
                            configuration.mode.value,
                            fleet_spec,
                            store,
                            enrichment,
                        )
                        publication_path = publish_repository_brain(
                            graph_build,
                            accepted,
                            enrichment,
                            output_root,
                            runtime_root=Path(fleet_spec.runtime_root),
                        )
                        return RepositoryBrainModelBuildResult(
                            publication_path=publication_path,
                            token_usage_report_path=token_usage_report_path,
                        )
            if fleet_state.phase in {
                FleetPhase.BLOCKED,
                FleetPhase.EXHAUSTED,
                FleetPhase.FAILED,
                FleetPhase.STOPPED,
            }:
                raise RepositoryBrainBuildError(
                    f"memory fleet stopped in {fleet_state.phase.value}"
                )
            state_changed = (
                fleet_state.model_dump(mode="json") != before_fleet_state
                or [state.model_dump(mode="json") for state in target_states]
                != before_target_states
            )
            if (
                not runnable
                and not state_changed
                and not all(
                    state.phase is TargetPhase.ACCEPTED for state in target_states
                )
            ):
                raise RepositoryBrainBuildError(
                    "memory fleet made no runnable progress"
                )
    except BaseException as error:
        active_error = error
        raise
    finally:
        if store is not None:
            try:
                phase_counts = Counter(state.phase.value for state in target_states)
                terminal_payload: dict[str, object] = {
                    "fleet_phase": fleet_state.phase.value,
                    "target_phase_counts": dict(phase_counts),
                    "usage": fleet_state.usage.model_dump(mode="json"),
                }
                termination_reason = fleet_state.termination_reason
                if termination_reason is None and active_error is not None:
                    termination_reason = str(active_error)[:512]
                if termination_reason is not None:
                    terminal_payload["termination_reason"] = termination_reason
                store.append_event("fleet_execution_finished", terminal_payload)
            except BaseException as event_error:
                if active_error is not None:
                    active_error.add_note(
                        f"fleet execution terminal trace failed: {event_error!r}"
                    )
        if active_error is not None and store is not None:
            try:
                persist_token_usage_report(
                    configuration.mode.value,
                    fleet_spec,
                    store,
                    enrichment,
                )
            except BaseException as report_error:
                active_error.add_note(
                    f"token usage report persistence also failed: {report_error!r}"
                )
        try:
            if client is not None:
                try:
                    await client.close()
                except BaseException as close_error:
                    if active_error is None:
                        raise
                    active_error.add_note(
                        f"LLM client cleanup also failed: {close_error!r}"
                    )
        finally:
            if recovered is None:
                store.close()
            else:
                recovered.close()
    raise RepositoryBrainBuildError("memory fleet exited without publication")


async def _run_target_batch(
    runnable: Sequence[str],
    runtime: _TargetStepRuntime,
) -> list[WorkerCycleOutcome]:
    """Run one structured concurrent batch and join every admitted target step."""
    tasks: list[asyncio.Task[WorkerCycleOutcome]] = []
    async with asyncio.TaskGroup() as task_group:
        for task_id in runnable:
            tasks.append(task_group.create_task(_run_target_step(task_id, runtime)))
    return [task.result() for task in tasks]


async def _run_target_step(
    task_id: str,
    runtime: _TargetStepRuntime,
) -> WorkerCycleOutcome:
    """Run one admitted target through its bounded lifecycle for this pass."""
    spec = runtime.specs_by_task[task_id]
    state = runtime.states_by_task[task_id]
    completion = runtime.completion_by_task[task_id]
    definition = runtime.definitions_by_id[spec.target_id]
    outcome = WorkerCycleOutcome.FINALIZATION_REQUESTED
    if state.phase is TargetPhase.SCHEDULED:
        worker_context = compile_worker_context(
            runtime.fleet_spec,
            spec,
            state,
            completion,
            runtime.catalog,
            definition,
            runtime.worker_profile,
            runtime.permissions,
            WorkerInstructions(
                worker_profile_id=runtime.worker_profile.profile_id,
                target_id=spec.target_id,
                target_contract_version=spec.target_contract_version,
                shared=_read_prompt(_PROMPTS_ROOT / "worker" / "system.md"),
                target_specific=_read_prompt(
                    _PROMPTS_ROOT / "worker" / "targets" / f"{spec.target_id}.md"
                ),
            ),
            context_window_manager=ContextWindowManager(runtime.worker_profile),
            graph_overview=runtime.graph_overview,
            persistence=runtime.store,
        )
        outcome = await run_worker_cycle(
            fleet_spec=runtime.fleet_spec,
            fleet_state=runtime.fleet_state,
            target_spec=spec,
            target_state=state,
            completion_state=completion,
            target_definition=definition,
            context=worker_context,
            worker_profile=runtime.worker_profile,
            permission_profile=runtime.permissions,
            context_window_manager=ContextWindowManager(runtime.worker_profile),
            llm_client=runtime.client,
            navigator=runtime.navigator,
            evidence=_load_evidence(runtime.store, spec, state),
            questions=_load_questions(runtime.store, spec, state),
            coordinator=runtime.coordinator,
            limits=_worker_runtime_limits(runtime.configuration.test_budgets),
            persistence=runtime.store,
        )
        if outcome is not WorkerCycleOutcome.FINALIZATION_REQUESTED:
            return outcome

    if state.phase not in {
        TargetPhase.FINALIZING,
        TargetPhase.VALIDATING,
        TargetPhase.REVIEWING,
    }:
        return outcome

    if state.phase in {TargetPhase.FINALIZING, TargetPhase.VALIDATING}:
        target_validation = validate_target_candidate(
            runtime.store,
            spec,
            state,
            definition,
            runtime.navigator,
        )
        if target_validation.verdict.value != "pass":
            return outcome
    try:
        review = await review_target(
            fleet_spec=runtime.fleet_spec,
            fleet_state=runtime.fleet_state,
            target_spec=spec,
            target_state=state,
            catalog=runtime.catalog,
            target_definition=definition,
            reviewer_profile=runtime.reviewer_profile,
            reviewer_instructions=ReviewerInstructions(
                reviewer_profile_id=runtime.reviewer_profile.profile_id,
                target_id=spec.target_id,
                target_contract_version=spec.target_contract_version,
                shared=_read_prompt(_PROMPTS_ROOT / "reviewer" / "system.md"),
                target_specific=_read_prompt(
                    _PROMPTS_ROOT / "reviewer" / "targets" / f"{spec.target_id}.md"
                ),
            ),
            context_window_manager=ContextWindowManager(runtime.reviewer_profile),
            llm_client=runtime.client,
            coordinator=runtime.coordinator,
            persistence=runtime.store,
        )
    except TargetReviewBudgetError as error:
        if error.scope == "fleet":
            return WorkerCycleOutcome.FLEET_BUDGET_STOP
        return WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED
    if review.verdict is ReviewVerdict.PASS:
        accept_target(runtime.store, spec, state)
    return outcome


def prepare_model_layers(
    configuration: InitRunConfiguration,
    graph_build: GraphBuildResult,
) -> tuple[LLMProfile, GraphEnrichmentOverlay]:
    """Run synchronous Layer 5 before entering the asynchronous fleet runtime."""
    profile = _resolve_model_profile(configuration)
    enrichment = enrich_graph_snapshot(
        graph_build,
        GraphEnrichmentConfig(
            provider=profile.provider,
            model=profile.model,
            profile_version=("test-v1" if configuration.test_budgets else "full-v1"),
            max_concurrency=1 if configuration.test_budgets else 4,
        ),
    )
    return profile, enrichment


def discover_resumable_fleet(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
) -> MemoryFleetSpec | None:
    """Select the one compatible non-accepted Repository Brain fleet, if any."""
    runtime_root = (configuration.bridger_root / "runtime").resolve()
    if not runtime_root.is_dir():
        return None

    catalog, _definitions = load_target_artifacts(_target_artifacts_root(configuration))
    candidates: list[MemoryFleetSpec] = []
    for run_root in sorted(path for path in runtime_root.iterdir() if path.is_dir()):
        spec_path = run_root / "fleet-spec.json"
        if not spec_path.is_file():
            continue
        try:
            spec = MemoryFleetSpec.model_validate_json(spec_path.read_bytes())
        except (OSError, ValidationError) as error:
            raise PersistenceRecoveryError(
                f"invalid persisted fleet specification: {run_root.name}"
            ) from error
        if not _is_resume_compatible(
            spec,
            configuration,
            context,
            catalog,
        ):
            continue
        state_path = run_root / "initialization" / "fleet-state.json"
        try:
            fleet_state = FleetRunState.model_validate_json(state_path.read_bytes())
        except (OSError, ValidationError) as error:
            raise PersistenceRecoveryError(
                f"compatible fleet state is invalid: {spec.fleet_run_id}"
            ) from error
        if fleet_state.fleet_run_id != spec.fleet_run_id:
            raise PersistenceRecoveryError(
                f"compatible fleet state identity mismatch: {spec.fleet_run_id}"
            )
        if fleet_state.phase is not FleetPhase.ACCEPTED:
            candidates.append(spec)

    if len(candidates) > 1:
        run_ids = ", ".join(spec.fleet_run_id for spec in candidates)
        raise RepositoryBrainBuildError(
            f"multiple compatible incomplete memory fleets exist: {run_ids}"
        )
    return candidates[0] if candidates else None


def load_recovery_model_layers(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
    fleet_spec: MemoryFleetSpec,
) -> tuple[GraphBuildResult, LLMProfile, GraphEnrichmentOverlay]:
    """Load the exact graph and enrichment authorities bound to a fleet."""
    graph_build = load_graph_snapshot(
        configuration.graph_root,
        fleet_spec.source.graph_snapshot_id,
    )
    validate_graph_snapshot(
        graph_build.snapshot_root,
        expected_context=context,
        expected_file_index=file_index,
        expected_config=GraphConstructionConfig(),
    )
    overlay_id = fleet_spec.source.enrichment_overlay_id
    if overlay_id is None:
        raise PersistenceRecoveryError(
            "Repository Brain fleet has no bound enrichment overlay"
        )
    enrichment = load_graph_enrichment(
        configuration.bridger_root
        / "enrichment"
        / fleet_spec.source.graph_snapshot_id
        / overlay_id,
        fleet_spec.source.graph_snapshot_id,
    )
    validate_graph_enrichment(enrichment, graph_build)
    if enrichment.overlay_id != overlay_id:
        raise PersistenceRecoveryError(
            "loaded enrichment overlay identity does not match fleet binding"
        )

    profile = _resolve_model_profile(configuration)
    expected_profile_version = "test-v1" if configuration.test_budgets else "full-v1"
    if (
        enrichment.provider != profile.provider
        or enrichment.model != profile.model
        or enrichment.profile_version != expected_profile_version
    ):
        raise PersistenceRecoveryError(
            "configured model profile does not match persisted enrichment authority"
        )
    return graph_build, profile, enrichment


def _runnable_target_task_ids(
    fleet_spec: MemoryFleetSpec,
    fleet_state: FleetRunState,
    target_specs: Sequence[TargetTaskSpec],
    target_states: Sequence[TargetTaskState],
    store: FleetRuntimeStore,
) -> list[str]:
    """Return admitted work first, scheduling only when none remains admitted."""
    resumed = [
        state.target_task_id
        for state in target_states
        if state.phase
        in {
            TargetPhase.SCHEDULED,
            TargetPhase.FINALIZING,
            TargetPhase.VALIDATING,
            TargetPhase.REVIEWING,
        }
    ]
    if resumed:
        return resumed
    return schedule_runnable_targets(
        fleet_spec,
        fleet_state,
        target_specs,
        target_states,
        persistence=store,
    )


def _is_resume_compatible(
    spec: MemoryFleetSpec,
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    catalog: MemoryTargetCatalog,
) -> bool:
    permissions_profile_id = "bridger-memory-tools-v2"
    return (
        spec.source.repository_id == context.repository_id
        and spec.source.repository_revision == context.revision
        and spec.target_catalog_id == catalog.catalog_id
        and spec.target_catalog_version == catalog.catalog_version
        and spec.runtime_profile_id == _runtime_profile_id(configuration)
        and spec.default_worker_profile_id == "bridger-worker-v1"
        and spec.default_reviewer_profile_id == "bridger-reviewer-v1"
        and spec.default_permission_profile_id == permissions_profile_id
        and spec.fleet_budget
        == _fleet_budget_for(
            configuration.test_budgets,
            target_capacity=len(catalog.targets),
        )
        and spec.default_target_budget == _target_budget_for(configuration.test_budgets)
        and spec.max_concurrent_targets == len(catalog.targets)
        and Path(spec.runtime_root).resolve()
        == (configuration.bridger_root / "runtime").resolve()
        and Path(spec.output_root).resolve()
        == (configuration.bridger_root / "memory").resolve()
    )


def _runtime_profile_id(configuration: InitRunConfiguration) -> str:
    return "test-v1" if configuration.test_budgets else "full-v1"


def _target_artifacts_root(configuration: InitRunConfiguration) -> Path:
    """Select the catalog profile before the normal fleet is instantiated."""
    if configuration.mode is InitMode.TEST:
        return _TEST_TARGETS_ROOT
    return _TARGETS_ROOT


def _resolve_model_profile(configuration: InitRunConfiguration) -> LLMProfile:
    profile = resolve_llm_profile(configuration.model_profile_name)
    if configuration.test_budgets:
        return profile.model_copy(update={"max_output_tokens": 2_048})
    return profile


def _profiles(
    profile: LLMProfile,
    test_budgets: bool,
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH,
) -> tuple[WorkerProfile, WorkerProfile]:
    reserved = 2_048 if test_budgets else 8_192
    worker_input_cap = _INITIAL_PROVIDER_INPUT_HARD_CAP_TOKENS
    reviewer_input_cap = profile.model_context_window_tokens - reserved
    resolved_reasoning_effort = (
        None
        if reasoning_effort is ReasoningEffort.NONE
        else cast(
            Literal["low", "medium", "high", "xhigh"],
            reasoning_effort.value,
        )
    )
    return (
        WorkerProfile(
            profile_id="bridger-worker-v1",
            model=profile.model,
            tokenizer_encoding="o200k_base",
            model_context_window_tokens=profile.model_context_window_tokens,
            reserved_response_tokens=reserved,
            provider_input_hard_cap_tokens=worker_input_cap,
            reasoning_effort=resolved_reasoning_effort,
        ),
        WorkerProfile(
            profile_id="bridger-reviewer-v1",
            model=profile.model,
            tokenizer_encoding="o200k_base",
            model_context_window_tokens=profile.model_context_window_tokens,
            reserved_response_tokens=reserved,
            provider_input_hard_cap_tokens=reviewer_input_cap,
            reasoning_effort=resolved_reasoning_effort,
        ),
    )


def _worker_runtime_limits(test_budgets: bool) -> WorkerRuntimeLimits:
    """Resolve Repository Brain's active Stage 4 working-context policy."""
    return WorkerRuntimeLimits(
        active_context_soft_limit_tokens=(
            _TEST_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS
            if test_budgets
            else _FULL_ACTIVE_CONTEXT_SOFT_LIMIT_TOKENS
        )
    )


def _target_budget_for(test_budgets: bool) -> ExecutionBudget:
    """Resolve limits for one target execution."""
    if test_budgets:
        return ExecutionBudget(
            max_cycles=4,
            max_model_calls=48,
            max_tool_calls=192,
            max_repair_cycles=3,
            max_input_tokens=None,
            max_output_tokens=32_000,
        )
    return ExecutionBudget(
        max_cycles=48,
        max_model_calls=240,
        max_tool_calls=960,
        max_repair_cycles=12,
        max_input_tokens=_FULL_TARGET_INPUT_BUDGET_TOKENS,
        max_output_tokens=200_000,
    )


def _fleet_budget_for(test_budgets: bool, *, target_capacity: int) -> ExecutionBudget:
    """Resolve aggregate fleet limits from the per-target runtime profile."""
    if target_capacity < 1:
        raise ValueError("fleet target capacity must be positive")
    target_budget = _target_budget_for(test_budgets)
    return ExecutionBudget(
        max_cycles=target_budget.max_cycles * target_capacity,
        max_model_calls=target_budget.max_model_calls * target_capacity,
        max_tool_calls=target_budget.max_tool_calls * target_capacity,
        max_repair_cycles=target_budget.max_repair_cycles * target_capacity,
        max_input_tokens=(
            250_000
            if test_budgets
            else (
                _FULL_TARGET_INPUT_BUDGET_TOKENS
                * target_capacity
                * _FULL_FLEET_INPUT_OVERHEAD_NUMERATOR
                // _FULL_FLEET_INPUT_OVERHEAD_DENOMINATOR
            )
        ),
        max_output_tokens=(target_budget.max_output_tokens or 0) * target_capacity,
    )


def _frontend_stack_present(
    context: RepositoryContext,
    file_index: FileIndex,
    _symbol_index: SymbolIndex,
    _graph_build: GraphBuildResult,
) -> bool:
    """Detect a frontend framework from revision-bound package manifests."""
    manifest_paths = [
        file.path for file in file_index.files if Path(file.path).name == "package.json"
    ]
    frontend_present = False
    for manifest_path in manifest_paths:
        result = read_file(
            context,
            file_index,
            SourceReadRequest(path=manifest_path),
        )
        try:
            manifest = json.loads(result.content)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid package manifest: {manifest_path}") from error
        if not isinstance(manifest, dict):
            raise ValueError(f"package manifest is not an object: {manifest_path}")
        frontend_present = (
            _declares_frontend_framework(manifest, manifest_path) or frontend_present
        )
    return frontend_present


def _declares_frontend_framework(
    manifest: dict[str, object],
    manifest_path: str,
) -> bool:
    for section_name in _FRONTEND_DEPENDENCY_SECTIONS:
        section = manifest.get(section_name, {})
        if not isinstance(section, dict):
            raise ValueError(
                f"package manifest dependency section is not an object: "
                f"{manifest_path}:{section_name}"
            )
        if _FRONTEND_FRAMEWORK_PACKAGES.intersection(section):
            return True
    return False


def _read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_evidence(
    store: FleetRuntimeStore,
    spec: TargetTaskSpec,
    state: TargetTaskState,
) -> dict[str, EvidenceReference]:
    return {
        evidence_id: EvidenceReference.model_validate_json(
            store.paths.evidence(spec, evidence_id).read_bytes()
        )
        for evidence_id in state.evidence_refs
    }


def _load_questions(
    store: FleetRuntimeStore,
    spec: TargetTaskSpec,
    state: TargetTaskState,
) -> dict[str, OpenQuestion]:
    return {
        question_id: OpenQuestion.model_validate_json(
            store.paths.question(spec, question_id).read_bytes()
        )
        for question_id in state.open_question_refs
    }
