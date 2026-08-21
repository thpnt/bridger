"""Composition of the existing memory-harness stages for ``bridger init``."""

from __future__ import annotations

from pathlib import Path

from graph.enrichment import enrich_graph_snapshot
from init_pipeline import InitRunConfiguration, RepositoryBrainBuildError
from llm.factory import create_llm_client_from_profile
from llm.profiles import LLMProfile, resolve_llm_profile
from memory import (
    ContextWindowManager,
    FleetExecutionCoordinator,
    FleetRuntimeStore,
    WorkerRuntimeLimits,
    accept_fleet,
    accept_target,
    bind_memory_run,
    compile_worker_context,
    initialize_fleet,
    initialize_persistence,
    load_target_artifacts,
    reconcile_fleet,
    run_worker_cycle,
    schedule_runnable_targets,
    validate_fleet,
    validate_target_candidate,
)
from memory.review import review_target
from memory.worker_tools import WORKER_TOOL_IDS
from models.enrichment import GraphEnrichmentConfig, GraphEnrichmentOverlay
from models.files import FileIndex
from models.graph import GraphBuildResult
from models.hydration import PermissionProfile, WorkerInstructions, WorkerProfile
from models.memory import (
    ExecutionBudget,
    FleetPhase,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from models.repository import RepositoryContext
from models.review import ReviewerInstructions, ReviewVerdict
from models.symbols import SymbolIndex
from models.worker_cycle import EvidenceReference, OpenQuestion
from navigation.navigator import RepositoryNavigator
from repository_brain.publication import publish_repository_brain

_PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"
_TARGETS_ROOT = Path(__file__).resolve().parents[1] / "memory" / "default-targets"


async def run_memory_harness(
    configuration: InitRunConfiguration,
    context: RepositoryContext,
    file_index: FileIndex,
    symbol_index: SymbolIndex,
    graph_build: GraphBuildResult,
    profile: LLMProfile,
    enrichment: GraphEnrichmentOverlay,
) -> Path:
    """Run the existing Layer 5 and memory stages through publication."""
    catalog, definitions = load_target_artifacts(_TARGETS_ROOT)
    worker_profile, reviewer_profile = _profiles(profile, configuration.test_budgets)
    permissions = PermissionProfile(
        profile_id="bridger-memory-tools-v1",
        allowed_tool_ids=WORKER_TOOL_IDS,
    )
    budget = _budget_for(configuration.test_budgets)
    output_root = configuration.bridger_root / "memory"
    fleet_spec = bind_memory_run(
        context,
        file_index,
        symbol_index,
        graph_build,
        catalog,
        definitions,
        runtime_profile_id=("test-v1" if configuration.test_budgets else "full-v1"),
        default_worker_profile_id=worker_profile.profile_id,
        default_reviewer_profile_id=reviewer_profile.profile_id,
        default_permission_profile_id=permissions.profile_id,
        fleet_budget=budget,
        default_target_budget=budget,
        runtime_root=configuration.bridger_root / "runtime",
        output_root=output_root,
        max_concurrent_targets=1,
        enrichment_overlay=enrichment,
        activation_rules={"frontend_stack_present_v1": _frontend_stack_present},
    )
    fleet_state, target_specs, target_states, completion_states = initialize_fleet(
        fleet_spec,
        catalog,
        definitions,
    )
    store = initialize_persistence(
        fleet_spec,
        fleet_state,
        target_specs,
        target_states,
        completion_states,
    )
    try:
        navigator = RepositoryNavigator(
            context,
            file_index,
            symbol_index,
            graph_build,
            enrichment,
        )
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
        while fleet_state.phase is not FleetPhase.ACCEPTED:
            scheduled = schedule_runnable_targets(
                fleet_spec,
                fleet_state,
                target_specs,
                target_states,
                persistence=store,
            )
            for task_id in scheduled:
                spec = specs_by_task[task_id]
                state = states_by_task[task_id]
                completion = completion_by_task[task_id]
                definition = definitions_by_id[spec.target_id]
                worker_instructions = WorkerInstructions(
                    worker_profile_id=worker_profile.profile_id,
                    target_id=spec.target_id,
                    target_contract_version=spec.target_contract_version,
                    shared=_read_prompt(_PROMPTS_ROOT / "worker" / "system.md"),
                    target_specific=_read_prompt(
                        _PROMPTS_ROOT / "worker" / "targets" / f"{spec.target_id}.md"
                    ),
                )
                worker_context = compile_worker_context(
                    fleet_spec,
                    spec,
                    state,
                    completion,
                    catalog,
                    definition,
                    worker_profile,
                    permissions,
                    worker_instructions,
                    context_window_manager=ContextWindowManager(worker_profile),
                    persistence=store,
                )
                outcome = await run_worker_cycle(
                    fleet_spec=fleet_spec,
                    fleet_state=fleet_state,
                    target_spec=spec,
                    target_state=state,
                    completion_state=completion,
                    target_definition=definition,
                    context=worker_context,
                    worker_profile=worker_profile,
                    permission_profile=permissions,
                    context_window_manager=ContextWindowManager(worker_profile),
                    llm_client=client,
                    navigator=navigator,
                    evidence=_load_evidence(store, spec, state),
                    questions=_load_questions(store, spec, state),
                    coordinator=coordinator,
                    limits=WorkerRuntimeLimits(),
                    persistence=store,
                )
                if outcome.value != "finalization_requested":
                    continue
                target_validation = validate_target_candidate(
                    store, spec, state, definition, navigator
                )
                if target_validation.verdict.value != "pass":
                    continue
                review = await review_target(
                    fleet_spec=fleet_spec,
                    fleet_state=fleet_state,
                    target_spec=spec,
                    target_state=state,
                    catalog=catalog,
                    target_definition=definition,
                    reviewer_profile=reviewer_profile,
                    reviewer_instructions=ReviewerInstructions(
                        reviewer_profile_id=reviewer_profile.profile_id,
                        target_id=spec.target_id,
                        target_contract_version=spec.target_contract_version,
                        shared=_read_prompt(_PROMPTS_ROOT / "reviewer" / "system.md"),
                        target_specific=_read_prompt(
                            _PROMPTS_ROOT
                            / "reviewer"
                            / "targets"
                            / f"{spec.target_id}.md"
                        ),
                    ),
                    context_window_manager=ContextWindowManager(reviewer_profile),
                    llm_client=client,
                    coordinator=coordinator,
                    persistence=store,
                )
                if review.verdict is ReviewVerdict.PASS:
                    accept_target(store, spec, state)
            if all(state.phase is TargetPhase.ACCEPTED for state in target_states):
                fleet_validation = validate_fleet(store, fleet_state)
                if fleet_validation.verdict.value == "pass":
                    fleet_review = await reconcile_fleet(
                        fleet_spec=fleet_spec,
                        fleet_state=fleet_state,
                        catalog=catalog,
                        target_definitions=definitions,
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
                        return publish_repository_brain(
                            graph_build,
                            accepted,
                            enrichment,
                            output_root,
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
            if not scheduled and not all(
                state.phase is TargetPhase.ACCEPTED for state in target_states
            ):
                raise RepositoryBrainBuildError(
                    "memory fleet made no runnable progress"
                )
    finally:
        store.close()
    raise RepositoryBrainBuildError("memory fleet exited without publication")


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


def _resolve_model_profile(configuration: InitRunConfiguration) -> LLMProfile:
    profile = resolve_llm_profile(configuration.model_profile_name)
    if configuration.test_budgets:
        return profile.model_copy(update={"max_output_tokens": 2_048})
    return profile


def _profiles(
    profile: LLMProfile,
    test_budgets: bool,
) -> tuple[WorkerProfile, WorkerProfile]:
    reserved = 2_048 if test_budgets else 8_192
    context_window = 32_000 if test_budgets else 128_000
    return (
        WorkerProfile(
            profile_id="bridger-worker-v1",
            model=profile.model,
            tokenizer_encoding="o200k_base",
            model_context_window_tokens=context_window,
            reserved_response_tokens=reserved,
            initial_provider_input_hard_cap_tokens=context_window - reserved,
        ),
        WorkerProfile(
            profile_id="bridger-reviewer-v1",
            model=profile.model,
            tokenizer_encoding="o200k_base",
            model_context_window_tokens=context_window,
            reserved_response_tokens=reserved,
            initial_provider_input_hard_cap_tokens=context_window - reserved,
        ),
    )


def _budget_for(test_budgets: bool) -> ExecutionBudget:
    if test_budgets:
        return ExecutionBudget(
            max_cycles=12,
            max_model_calls=48,
            max_tool_calls=192,
            max_repair_cycles=3,
            max_input_tokens=250_000,
            max_output_tokens=32_000,
        )
    return ExecutionBudget(
        max_cycles=48,
        max_model_calls=240,
        max_tool_calls=960,
        max_repair_cycles=12,
        max_input_tokens=1_000_000,
        max_output_tokens=200_000,
    )


def _frontend_stack_present(
    _context: RepositoryContext,
    file_index: FileIndex,
    _symbol_index: SymbolIndex,
    _graph_build: GraphBuildResult,
) -> bool:
    """Activate the optional design target from deterministic repository facts."""
    frontend_markers = {"react", "next", "vue", "nuxt", "angular", "svelte"}
    return any(
        marker in file.path.lower()
        for file in file_index.files
        for marker in frontend_markers
    )


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
