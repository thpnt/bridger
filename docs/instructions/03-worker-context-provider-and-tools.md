# Worker profile, permissions, tools, WorkerContext, and provider request

The active entry point resolves the worker profile and permission profile, reads the static prompt files, compiles `WorkerContext`, and runs the worker. Initial worker requests have no `messages`: the serialized WorkerContext is supplied as `LLMRequest.instructions`. They attach the permission-filtered tool definitions plus `yield_cycle` and `request_finalization`, use `tool_choice="required"`, and include the configured reasoning settings.

The serialization order and all code-generated instructions are preserved in the compiler excerpt. Repair selects all persisted open findings; initial selects the first persisted-order `uninvestigated` obligation; finalization readiness follows when no obligation remains uninvestigated. Later in-cycle requests append the execution overlay shown below.

Dynamic context inputs exposed when applicable: source binding; current completion states; repair findings; working summary; open questions; remaining target budget; candidate artifact inventory. Subsequent execution overlays also add changed completion items, current artifacts/summary/questions, and new evidence.

### `src/repository_brain/harness.py:28-339`

```python
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
```

### `src/models/hydration.py:19-263`

```python
class WorkerContextMode(StrEnum):
    """Derived execution purpose for one hydrated worker context."""

    INITIAL = "initial"
    REPAIR = "repair"


class WorkerCycleFocusKind(StrEnum):
    """Deterministic semantic objective for one hydrated worker cycle."""

    OBLIGATION = "obligation"
    REPAIR_FINDINGS = "repair-findings"
    FINALIZATION_READINESS = "finalization-readiness"


class WorkerCycleFocus(BaseModel):
    """Transient projection of the authoritative work selected for this cycle."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: WorkerCycleFocusKind
    obligation_id: str | None = Field(default=None, min_length=1)
    finding_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_focus(self) -> WorkerCycleFocus:
        """Keep the kind-specific focus payload exact and unambiguous."""
        if self.kind is WorkerCycleFocusKind.OBLIGATION:
            if self.obligation_id is None or self.finding_ids:
                raise ValueError("obligation focus requires only obligation_id")
        elif self.kind is WorkerCycleFocusKind.REPAIR_FINDINGS:
            if self.obligation_id is not None or not self.finding_ids:
                raise ValueError("repair focus requires only finding_ids")
            if len(self.finding_ids) != len(set(self.finding_ids)):
                raise ValueError("repair focus finding_ids must be unique")
        elif self.obligation_id is not None or self.finding_ids:
            raise ValueError("finalization-readiness focus has no identifiers")
        return self


class WorkerProfile(BaseModel):
    """Resolved immutable V0 worker and model context configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    provider: Literal["openai"] = "openai"
    model: str = Field(min_length=1)
    tokenizer_encoding: str = Field(min_length=1)
    model_context_window_tokens: PositiveInt
    reserved_response_tokens: int = Field(ge=0)
    reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] = (
        "xhigh"
    )
    reasoning_context: Literal["auto", "current_turn", "all_turns"] | None = "all_turns"
    initial_provider_input_hard_cap_tokens: int = Field(
        default=32_000,
        ge=1,
        le=32_000,
    )

    @model_validator(mode="after")
    def validate_context_capacity(self) -> WorkerProfile:
        """Require both the initial request and response reserve to fit."""
        if (
            self.initial_provider_input_hard_cap_tokens + self.reserved_response_tokens
            > self.model_context_window_tokens
        ):
            raise ValueError(
                "initial input cap and reserved response exceed model context window"
            )
        return self


class PermissionProfile(BaseModel):
    """Resolved immutable worker permission identity and allowed tool names."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(min_length=1)
    allowed_tool_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_tool_ids(self) -> PermissionProfile:
        """Require stable, unique, non-empty tool identities."""
        if any(not tool_id.strip() for tool_id in self.allowed_tool_ids):
            raise ValueError("allowed_tool_ids must be non-empty strings")
        if len(self.allowed_tool_ids) != len(set(self.allowed_tool_ids)):
            raise ValueError("allowed_tool_ids must be unique")
        return self


class WorkerInstructions(BaseModel):
    """Exact immutable instruction content resolved for one target contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    worker_profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    shared: str = Field(min_length=1)
    target_specific: str = Field(min_length=1)


class TargetContractView(BaseModel):
    """Worker-facing projection of immutable target semantics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    canonical_question: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_abstraction: str = Field(min_length=1)
    always_relevant_scope: tuple[str, ...]
    conditional_scope: tuple[str, ...]
    exclusions: tuple[str, ...]
    boundary_guidance: tuple[str, ...]
    investigation_expectations: tuple[str, ...]
    evidence_expectations: tuple[str, ...]
    output_quality_expectations: tuple[str, ...]


class CompletionObligationView(BaseModel):
    """One target obligation joined with its current durable resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    obligation_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    applicability: ObligationApplicability
    condition_hint: str | None = None
    status: CompletionStatus
    resolution_note: str | None = None
    evidence_refs: tuple[str, ...]


class OpenQuestion(BaseModel):
    """Actionable currently open question exposed to the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str = Field(min_length=1)
    content: str = Field(min_length=1)


class RepairFinding(BaseModel):
    """Actionable open validation or review finding exposed in repair mode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    finding_id: str = Field(min_length=1)
    origin: FindingOrigin
    content: str = Field(min_length=1)
    affected_scope: str | None = Field(default=None, min_length=1)
    affected_artifact_id: str | None = Field(default=None, min_length=1)
    affected_artifact_refs: tuple[str, ...] = ()
    affected_obligation_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


class RemainingExecutionBudget(BaseModel):
    """Derived target-only execution headroom supplied to the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycles: int = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    repair_cycles: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class WorkerContext(BaseModel):
    """Immutable provider-neutral execution view for one worker execution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_task_id: str = Field(min_length=1)
    mode: WorkerContextMode
    worker_profile_id: str = Field(min_length=1)
    permission_profile_id: str = Field(min_length=1)
    allowed_tool_ids: tuple[str, ...]
    source: SourceBinding
    shared_worker_instructions: str = Field(min_length=1)
    global_ownership_guidance: tuple[str, ...]
    target_worker_instructions: str = Field(min_length=1)
    target_contract: TargetContractView
    cycle_focus: WorkerCycleFocus
    completion_obligations: tuple[CompletionObligationView, ...]
    repair_findings: tuple[RepairFinding, ...]
    working_summary: str | None = None
    open_questions: tuple[OpenQuestion, ...]
    remaining_target_budget: RemainingExecutionBudget
    candidate_artifacts: tuple[CandidateArtifactRef, ...]

    @model_validator(mode="after")
    def validate_mode_findings(self) -> WorkerContext:
        """Keep repair findings aligned with the derived context mode."""
        if self.mode is WorkerContextMode.INITIAL and self.repair_findings:
            raise ValueError("initial worker context cannot include repair findings")
        if self.mode is WorkerContextMode.REPAIR and not self.repair_findings:
            raise ValueError("repair worker context requires repair findings")
        if self.repair_findings:
            expected_ids = tuple(item.finding_id for item in self.repair_findings)
            if (
                self.cycle_focus.kind is not WorkerCycleFocusKind.REPAIR_FINDINGS
                or self.cycle_focus.finding_ids != expected_ids
            ):
                raise ValueError("repair cycle focus must match routed findings")
            return self
        unresolved = tuple(
            item.obligation_id
            for item in self.completion_obligations
            if item.status is CompletionStatus.UNINVESTIGATED
        )
        if unresolved:
            if (
                self.cycle_focus.kind is not WorkerCycleFocusKind.OBLIGATION
                or self.cycle_focus.obligation_id != unresolved[0]
            ):
                raise ValueError("normal cycle focus must select first unresolved item")
        elif self.cycle_focus.kind is not WorkerCycleFocusKind.FINALIZATION_READINESS:
            raise ValueError("resolved target requires finalization-readiness focus")
        return self


class ContextWindowDiagnostics(BaseModel):
    """Derived request-token visibility for hydration and future worker calls."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_context_window_tokens: PositiveInt
    reserved_response_tokens: int = Field(ge=0)
    initial_provider_input_hard_cap_tokens: PositiveInt
    fixed_request_input_tokens: int = Field(ge=0)
    maximum_worker_context_tokens: int = Field(ge=0)
    worker_context_tokens: int = Field(ge=0)
    complete_initial_provider_input_tokens: int = Field(ge=0)
    remaining_initial_input_tokens: int = Field(ge=0)
    remaining_model_context_tokens: int = Field(ge=0)
    within_initial_input_limit: bool
    within_model_context_limit: bool

```

### `src/models/memory.py:283-414`

```python
        return self


class ActivationMode(StrEnum):
    """Deterministic target activation mode."""

    ALWAYS = "always"
    CONDITIONAL = "conditional"


class ObligationApplicability(StrEnum):
    """Static applicability vocabulary for completion obligations."""

    ALWAYS = "always"
    CONDITIONAL = "conditional"


class TargetActivation(BaseModel):
    """Immutable deterministic activation configuration for one target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: ActivationMode
    rule_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_rule(self) -> TargetActivation:
        """Require a rule exactly when activation is conditional."""
        if self.mode is ActivationMode.ALWAYS and self.rule_id is not None:
            raise ValueError("always activation cannot declare rule_id")
        if self.mode is ActivationMode.CONDITIONAL and self.rule_id is None:
            raise ValueError("conditional activation requires rule_id")
        return self


class CompletionObligationDefinition(BaseModel):
    """Immutable semantic definition of one target completion obligation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    obligation_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    applicability: ObligationApplicability
    condition_hint: str | None = Field(default=None, min_length=1)


class TargetDefinition(BaseModel):
    """Complete immutable semantic contract for one memory target."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)
    activation: TargetActivation
    depends_on: list[str]
    canonical_question: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    expected_abstraction: str = Field(min_length=1)
    always_relevant_scope: list[str]
    conditional_scope: list[str]
    exclusions: list[str]
    boundary_guidance: list[str]
    investigation_expectations: list[str]
    evidence_expectations: list[str]
    completion_obligations: list[CompletionObligationDefinition]
    output_quality_expectations: list[str]

    @model_validator(mode="after")
    def validate_contract(self) -> TargetDefinition:
        """Reject ambiguous dependencies and completion obligations."""
        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValueError("target dependencies must be unique")
        if self.target_id in self.depends_on:
            raise ValueError("a target cannot depend on itself")
        obligation_ids = [
            obligation.obligation_id for obligation in self.completion_obligations
        ]
        if len(obligation_ids) != len(set(obligation_ids)):
            raise ValueError("completion obligation IDs must be unique")
        return self


class TargetCatalogEntry(BaseModel):
    """Immutable catalog reference to one exact target contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_id: str = Field(min_length=1)
    target_contract_version: str = Field(min_length=1)


class MemoryTargetCatalog(BaseModel):
    """Immutable target/version inventory and global ownership policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(ge=1)
    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    targets: list[TargetCatalogEntry]
    cross_target_ownership_rules: list[str]

    @model_validator(mode="after")
    def validate_targets(self) -> MemoryTargetCatalog:
        """Require one deterministic catalog entry per semantic target."""
        target_ids = [entry.target_id for entry in self.targets]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("catalog target IDs must be unique")
        return self


__all__ = [
    "ActivationMode",
    "CandidateArtifactRef",
    "CompletionItemState",
    "CompletionObligationDefinition",
    "CompletionStatus",
    "ExecutionBudget",
    "ExecutionUsage",
    "FindingOrigin",
    "FindingRef",
    "FleetPhase",
    "FleetRunState",
    "MemoryFleetSpec",
    "MemoryTargetCatalog",
    "ObligationApplicability",
    "SourceBinding",
    "TargetActivation",
    "TargetCatalogEntry",
    "TargetCompletionState",
    "TargetDefinition",
```

### `src/memory/hydration.py:504-778`

```python
def serialize_worker_context(context: WorkerContext) -> str:
    """Serialize WorkerContext deterministically with stable sections first."""
    return "".join(serialize_worker_context_sections(context))


def serialize_worker_context_sections(
    context: WorkerContext,
) -> tuple[str, str, str]:
    """Render global-, target-, and cycle-stable canonical context sections."""
    global_sections = [
        _section("Shared worker instructions", context.shared_worker_instructions),
        _section(
            "Worker profile and tool surface",
            _canonical_json(
                {
                    "worker_profile_id": context.worker_profile_id,
                    "permission_profile_id": context.permission_profile_id,
                    "allowed_tool_ids": context.allowed_tool_ids,
                }
            ),
        ),
    ]
    target_sections = [
        _section(
            "Source binding and global ownership guidance",
            _canonical_json(
                {
                    "source": context.source,
                    "global_ownership_guidance": context.global_ownership_guidance,
                }
            ),
        ),
        _section(
            "Target instructions and semantic contract",
            context.target_worker_instructions
            + "\n\n"
            + _canonical_json(context.target_contract),
        ),
    ]
    cycle_sections = [
        _section(
            "Execution mode",
            _canonical_json({"mode": context.mode}),
        ),
        _section(
            "Current cycle objective",
            _serialize_cycle_focus(context.cycle_focus),
        ),
        _section(
            "Completion obligations and current states",
            _canonical_json(context.completion_obligations),
        ),
    ]
    if context.mode is WorkerContextMode.REPAIR:
        cycle_sections.append(
            _section("Open repair findings", _canonical_json(context.repair_findings))
        )
    if context.working_summary is not None:
        cycle_sections.append(_section("Working summary", context.working_summary))
    cycle_sections.extend(
        (
            _section("Open questions", _canonical_json(context.open_questions)),
            _section(
                "Remaining target budget",
                _canonical_json(context.remaining_target_budget),
            ),
            _section(
                "Complete candidate-artifact inventory",
                _canonical_json(context.candidate_artifacts),
            ),
        )
    )
    return (
        "\n\n".join(global_sections) + "\n\n",
        "\n\n".join(target_sections) + "\n\n",
        "\n\n".join(cycle_sections) + "\n",
    )


def _validate_invocation(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> None:
    if target_state.phase is not TargetPhase.SCHEDULED:
        raise WorkerContextInvocationError(
            "worker context hydration requires a SCHEDULED target"
        )
    if target_state.target_task_id != target_spec.target_task_id:
        raise WorkerContextInvocationError(
            "target spec and state identities do not match"
        )
    if target_spec.fleet_run_id != fleet_spec.fleet_run_id:
        raise WorkerContextInvocationError("target spec belongs to a different fleet")
    if target_state.fleet_run_id != fleet_spec.fleet_run_id:
        raise WorkerContextInvocationError("target state belongs to a different fleet")
    if target_spec.target_id not in fleet_spec.target_ids:
        raise WorkerContextInvocationError("target is not activated in this fleet")


def _compile_hydrating_context(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    catalog: MemoryTargetCatalog,
    target_definition: TargetDefinition | None,
    worker_profile: WorkerProfile | None,
    permission_profile: PermissionProfile | None,
    worker_instructions: WorkerInstructions | None,
    state_reader: HydrationStateReader,
    *,
    context_window_manager: ContextWindowManager | None,
    fixed_request_input: str,
    provider_framing_tokens: int,
) -> tuple[WorkerContext, str, ContextWindowDiagnostics]:
    _validate_models(
        fleet_spec,
        target_spec,
        target_state,
        completion_state,
        catalog,
    )
    definition = _resolve_definition(
        fleet_spec,
        target_spec,
        catalog,
        target_definition,
    )
    profile, permissions, instructions = _validate_configuration(
        target_spec,
        target_definition=definition,
        worker_profile=worker_profile,
        permission_profile=permission_profile,
        worker_instructions=worker_instructions,
    )
    manager = context_window_manager or ContextWindowManager(
        profile,
        fixed_request_input=fixed_request_input,
        provider_framing_tokens=provider_framing_tokens,
    )
    if context_window_manager is not None and (
        fixed_request_input or provider_framing_tokens
    ):
        raise WorkerContextHydrationError(
            "fixed request input must be configured on the supplied context manager"
        )
    if manager.profile != profile:
        raise WorkerContextHydrationError(
            "context-window manager does not match the resolved worker profile"
        )

    completion_obligations, completion_evidence = _project_completion(
        target_spec,
        completion_state,
        definition,
    )
    candidate_artifacts = _resolve_artifacts(
        target_spec,
        target_state,
        state_reader,
    )
    open_questions = _resolve_questions(target_spec, target_state, state_reader)
    repair_findings, finding_evidence = _resolve_findings(
        target_spec,
        target_state,
        state_reader,
    )
    _validate_evidence(
        target_spec,
        (*target_state.evidence_refs, *completion_evidence, *finding_evidence),
        state_reader,
    )
    mode = (
        WorkerContextMode.REPAIR
        if target_state.open_finding_refs
        else WorkerContextMode.INITIAL
    )
    cycle_focus = _select_cycle_focus(
        completion_obligations,
        repair_findings,
    )
    context = WorkerContext(
        target_task_id=target_spec.target_task_id,
        mode=mode,
        worker_profile_id=profile.profile_id,
        permission_profile_id=permissions.profile_id,
        allowed_tool_ids=permissions.allowed_tool_ids,
        source=target_spec.source,
        shared_worker_instructions=instructions.shared,
        global_ownership_guidance=tuple(catalog.cross_target_ownership_rules),
        target_worker_instructions=instructions.target_specific,
        target_contract=_project_target_contract(definition),
        cycle_focus=cycle_focus,
        completion_obligations=completion_obligations,
        repair_findings=repair_findings,
        working_summary=target_state.working_summary,
        open_questions=open_questions,
        remaining_target_budget=_remaining_budget(target_spec, target_state),
        candidate_artifacts=candidate_artifacts,
    )
    serialized = serialize_worker_context(context)
    diagnostics = manager.inspect_initial_worker_context(serialized)
    if not diagnostics.within_initial_input_limit:
        raise WorkerContextHydrationError(
            "complete mandatory initial provider input exceeds the hard cap"
        )
    if not diagnostics.within_model_context_limit:
        raise WorkerContextHydrationError(
            "complete mandatory request exceeds the model context window"
        )
    return context, serialized, diagnostics


def _select_cycle_focus(
    completion_obligations: tuple[CompletionObligationView, ...],
    repair_findings: tuple[RepairFinding, ...],
) -> WorkerCycleFocus:
    """Select one deterministic focus from the already-projected authorities."""
    if repair_findings:
        return WorkerCycleFocus(
            kind=WorkerCycleFocusKind.REPAIR_FINDINGS,
            finding_ids=tuple(finding.finding_id for finding in repair_findings),
        )
    for obligation in completion_obligations:
        if obligation.status is CompletionStatus.UNINVESTIGATED:
            return WorkerCycleFocus(
                kind=WorkerCycleFocusKind.OBLIGATION,
                obligation_id=obligation.obligation_id,
            )
    return WorkerCycleFocus(kind=WorkerCycleFocusKind.FINALIZATION_READINESS)


def _serialize_cycle_focus(focus: WorkerCycleFocus) -> str:
    """Render the harness-owned bounded-cycle instruction for the worker."""
    if focus.kind is WorkerCycleFocusKind.OBLIGATION:
        directive = (
            f"obligation_id: {focus.obligation_id}\n\n"
            "Your primary responsibility during this cycle is to investigate and "
            "resolve this obligation.\n\n"
            "Keep the complete target in mind, but do not deliberately move on to "
            "unrelated unresolved obligations. If the same evidence directly "
            "resolves closely related obligations, you may update them too."
        )
    elif focus.kind is WorkerCycleFocusKind.REPAIR_FINDINGS:
        directive = (
            "finding_ids:\n"
            + "\n".join(f"- {finding_id}" for finding_id in focus.finding_ids)
            + "\n\nResolve the currently routed repair finding set in persisted order."
        )
    else:
        directive = (
            "Inspect the current target as a whole, make any necessary final "
            "coherence or organization fixes, verify completion state, and request "
            "finalization when the complete target is ready."
        )
    return (
        f"kind: {focus.kind.value}\n"
        f"{directive}\n\n"
        "Once this cycle's intended work is complete:\n\n"
        "- use yield_cycle if the target still requires work;\n"
        "- use request_finalization only if the complete target is ready."
    )


def _validate_models(
    fleet_spec: MemoryFleetSpec,
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    completion_state: TargetCompletionState,
    catalog: MemoryTargetCatalog,
) -> None:
    try:
        MemoryFleetSpec.model_validate(fleet_spec.model_dump(mode="python"))
        TargetTaskSpec.model_validate(target_spec.model_dump(mode="python"))
```

### `src/memory/hydration.py:798-1109`

```python
    target_definition: TargetDefinition | None,
) -> TargetDefinition:
    if (
        catalog.catalog_id != fleet_spec.target_catalog_id
        or catalog.catalog_version != fleet_spec.target_catalog_version
    ):
        raise WorkerContextHydrationError(
            "target catalog identity does not match the fleet specification"
        )
    if target_definition is None:
        raise WorkerContextHydrationError("target definition is missing")
    try:
        _, definitions = _resolve_catalog_definitions(
            catalog,
            [target_definition],
            require_exact=False,
            required_target_ids={target_spec.target_id},
        )
    except InvalidTargetArtifacts as error:
        raise WorkerContextHydrationError(
            "target definition does not match the catalog"
        ) from error
    definition = definitions[target_spec.target_id]
    if definition.target_contract_version != target_spec.target_contract_version:
        raise WorkerContextHydrationError(
            "target definition does not match the task contract version"
        )
    return definition


def _validate_configuration(
    target_spec: TargetTaskSpec,
    *,
    target_definition: TargetDefinition,
    worker_profile: WorkerProfile | None,
    permission_profile: PermissionProfile | None,
    worker_instructions: WorkerInstructions | None,
) -> tuple[WorkerProfile, PermissionProfile, WorkerInstructions]:
    if worker_profile is None:
        raise WorkerContextHydrationError("worker profile is missing")
    if permission_profile is None:
        raise WorkerContextHydrationError("permission profile is missing")
    if worker_instructions is None:
        raise WorkerContextHydrationError("worker instructions are missing")
    try:
        worker_profile = WorkerProfile.model_validate(
            worker_profile.model_dump(mode="python")
        )
        permission_profile = PermissionProfile.model_validate(
            permission_profile.model_dump(mode="python")
        )
        worker_instructions = WorkerInstructions.model_validate(
            worker_instructions.model_dump(mode="python")
        )
    except (AttributeError, TypeError, ValidationError, ValueError) as error:
        raise WorkerContextHydrationError(
            "worker, permission, or instruction configuration is malformed"
        ) from error
    if worker_profile.profile_id != target_spec.worker_profile_id:
        raise WorkerContextHydrationError("worker profile identity does not match")
    if permission_profile.profile_id != target_spec.permission_profile_id:
        raise WorkerContextHydrationError("permission profile identity does not match")
    if worker_instructions.worker_profile_id != worker_profile.profile_id:
        raise WorkerContextHydrationError(
            "shared worker instructions do not match the worker profile"
        )
    if (
        worker_instructions.target_id != target_definition.target_id
        or worker_instructions.target_contract_version
        != target_definition.target_contract_version
    ):
        raise WorkerContextHydrationError(
            "target worker instructions do not match the target contract"
        )
    return worker_profile, permission_profile, worker_instructions


def _project_completion(
    target_spec: TargetTaskSpec,
    completion_state: TargetCompletionState,
    definition: TargetDefinition,
) -> tuple[tuple[CompletionObligationView, ...], tuple[str, ...]]:
    if completion_state.target_task_id != target_spec.target_task_id:
        raise WorkerContextHydrationError(
            "completion state belongs to a different target task"
        )
    items = {item.obligation_id: item for item in completion_state.items}
    expected_ids = [
        obligation.obligation_id for obligation in definition.completion_obligations
    ]
    if set(items) != set(expected_ids):
        raise WorkerContextHydrationError(
            "completion state does not exactly match target obligations"
        )
    projected: list[CompletionObligationView] = []
    evidence_refs: list[str] = []
    for obligation in definition.completion_obligations:
        item = items[obligation.obligation_id]
        evidence_refs.extend(item.evidence_refs)
        projected.append(
            CompletionObligationView(
                obligation_id=obligation.obligation_id,
                description=obligation.description,
                applicability=obligation.applicability,
                condition_hint=obligation.condition_hint,
                status=item.status,
                resolution_note=item.resolution_note,
                evidence_refs=tuple(item.evidence_refs),
            )
        )
    return tuple(projected), tuple(evidence_refs)


def _resolve_artifacts(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[CandidateArtifactRef, ...]:
    artifact_ids = [reference.artifact_id for reference in target_state.artifact_refs]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise WorkerContextHydrationError("candidate artifact IDs must be unique")
    normalized_paths: set[str] = set()
    resolved: list[tuple[str, CandidateArtifactRef]] = []
    for reference in target_state.artifact_refs:
        normalized_path = _normalized_relative_path(reference.relative_path)
        if normalized_path in normalized_paths:
            raise WorkerContextHydrationError(
                "candidate artifact relative paths must be unique"
            )
        normalized_paths.add(normalized_path)
        record = state_reader.get_candidate_artifact(reference.artifact_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"candidate artifact is missing: {reference.artifact_id}"
            )
        if (
            record.target_task_id != target_spec.target_task_id
            or record.target_workspace != target_spec.target_workspace
        ):
            raise WorkerContextHydrationError(
                "candidate artifact is outside the target workspace: "
                f"{reference.artifact_id}"
            )
        if (
            record.artifact_id != reference.artifact_id
            or record.relative_path != reference.relative_path
            or record.revision != reference.revision
            or record.digest != reference.digest
        ):
            raise WorkerContextHydrationError(
                "candidate artifact reference does not match authoritative state: "
                f"{reference.artifact_id}"
            )
        resolved.append((normalized_path, reference))
    return tuple(
        reference
        for _, reference in sorted(
            resolved,
            key=lambda item: (item[0], item[1].artifact_id),
        )
    )


def _resolve_questions(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[OpenQuestion, ...]:
    if len(target_state.open_question_refs) != len(
        set(target_state.open_question_refs)
    ):
        raise WorkerContextHydrationError("open question references must be unique")
    questions: list[OpenQuestion] = []
    for question_id in target_state.open_question_refs:
        record = state_reader.get_open_question(question_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"open question is missing: {question_id}"
            )
        if (
            record.question_id != question_id
            or record.target_task_id != target_spec.target_task_id
            or not record.is_open
        ):
            raise WorkerContextHydrationError(
                f"open question reference is invalid: {question_id}"
            )
        questions.append(OpenQuestion(question_id=question_id, content=record.content))
    return tuple(questions)


def _resolve_findings(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
    state_reader: HydrationStateReader,
) -> tuple[tuple[RepairFinding, ...], tuple[str, ...]]:
    finding_ids = [reference.finding_id for reference in target_state.open_finding_refs]
    if len(finding_ids) != len(set(finding_ids)):
        raise WorkerContextHydrationError("open finding references must be unique")
    findings: list[RepairFinding] = []
    evidence_refs: list[str] = []
    for reference in target_state.open_finding_refs:
        record = state_reader.get_open_finding(reference.finding_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"open finding is missing: {reference.finding_id}"
            )
        if (
            record.finding_id != reference.finding_id
            or record.target_task_id != target_spec.target_task_id
            or record.origin is not reference.origin
            or not record.is_open
        ):
            raise WorkerContextHydrationError(
                f"open finding reference is invalid: {reference.finding_id}"
            )
        evidence_refs.extend(record.evidence_refs)
        findings.append(
            RepairFinding(
                finding_id=record.finding_id,
                origin=record.origin,
                content=record.content,
                affected_scope=record.affected_scope,
                affected_artifact_id=record.affected_artifact_id,
                affected_artifact_refs=record.affected_artifact_refs,
                affected_obligation_ids=record.affected_obligation_ids,
                evidence_refs=record.evidence_refs,
            )
        )
    return tuple(findings), tuple(evidence_refs)


def _validate_evidence(
    target_spec: TargetTaskSpec,
    evidence_ids: tuple[str, ...],
    state_reader: HydrationStateReader,
) -> None:
    for evidence_id in dict.fromkeys(evidence_ids):
        record = state_reader.get_evidence(evidence_id)
        if record is None:
            raise WorkerContextHydrationError(
                f"referenced evidence is missing: {evidence_id}"
            )
        if record.evidence_id != evidence_id or record.source != target_spec.source:
            raise WorkerContextHydrationError(
                f"referenced evidence has incompatible identity: {evidence_id}"
            )


def _project_target_contract(definition: TargetDefinition) -> TargetContractView:
    return TargetContractView(
        target_id=definition.target_id,
        target_contract_version=definition.target_contract_version,
        canonical_question=definition.canonical_question,
        purpose=definition.purpose,
        expected_abstraction=definition.expected_abstraction,
        always_relevant_scope=tuple(definition.always_relevant_scope),
        conditional_scope=tuple(definition.conditional_scope),
        exclusions=tuple(definition.exclusions),
        boundary_guidance=tuple(definition.boundary_guidance),
        investigation_expectations=tuple(definition.investigation_expectations),
        evidence_expectations=tuple(definition.evidence_expectations),
        output_quality_expectations=tuple(definition.output_quality_expectations),
    )


def _remaining_budget(
    target_spec: TargetTaskSpec,
    target_state: TargetTaskState,
) -> RemainingExecutionBudget:
    budget = target_spec.budget
    usage = target_state.usage
    values = {
        "cycles": budget.max_cycles - usage.cycles,
        "model_calls": budget.max_model_calls - usage.model_calls,
        "tool_calls": budget.max_tool_calls - usage.tool_calls,
        "repair_cycles": budget.max_repair_cycles - usage.repair_cycles,
        "input_tokens": (
            None
            if budget.max_input_tokens is None
            else budget.max_input_tokens - usage.input_tokens
        ),
        "output_tokens": (
            None
            if budget.max_output_tokens is None
            else budget.max_output_tokens - usage.output_tokens
        ),
    }
    if any(value is not None and value < 0 for value in values.values()):
        raise WorkerContextHydrationError(
            "target usage exceeds its configured execution budget"
        )
    return RemainingExecutionBudget.model_validate(values)


def _normalized_relative_path(relative_path: str) -> str:
    if "\\" in relative_path:
        raise WorkerContextHydrationError(
            "candidate artifact path must use normalized POSIX separators"
        )
    path = PurePosixPath(relative_path)
    if (
        relative_path in {"", "."}
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise WorkerContextHydrationError(
            "candidate artifact path must be normalized and relative"
        )
    normalized = path.as_posix()
    if normalized != relative_path:
        raise WorkerContextHydrationError(
```

### `src/memory/worker_cycle.py:1100-1200`

```python
            on_retry=on_retry,
        )

    def _preflight(self) -> tuple[LLMRequest, int, int]:
        self._validate_invocation()
        request, input_tokens, output_tokens = self._build_request(initial=True)
        _require_cycle_capacity(
            self._target_spec.budget,
            self._target_state.usage,
            self._context.mode is WorkerContextMode.REPAIR,
            _BudgetScope.TARGET,
        )
        _require_cycle_capacity(
            self._fleet_spec.fleet_budget,
            self._fleet_state.usage,
            self._context.mode is WorkerContextMode.REPAIR,
            _BudgetScope.FLEET,
        )
        self._require_model_headroom(input_tokens, output_tokens)
        if input_tokens > self._profile.initial_provider_input_hard_cap_tokens:
            raise WorkerCyclePreflightError(
                "complete initial provider request exceeds the Stage 3 hard cap"
            )
        return request, input_tokens, output_tokens

    def _next_request(self) -> tuple[LLMRequest, int, int]:
        request, input_tokens, output_tokens = self._build_request(initial=False)
        self._require_model_headroom(input_tokens, output_tokens)
        return request, input_tokens, output_tokens

    def _build_request(self, *, initial: bool) -> tuple[LLMRequest, int, int]:
        while True:
            messages = self._request_messages(initial=initial)
            instructions = self._exact_control_context(initial=initial)
            request = LLMRequest(
                operation=LLMOperation.MEMORY_AGENT_WORKER,
                profile=self._profile.profile_id,
                messages=messages,
                instructions=instructions,
                continuation_ref=None if initial else self._continuation_ref,
                store=True,
                compacted_context=None if initial else self._compacted_context,
                prompt_cache=LLMPromptCacheConfig(
                    key=self._prompt_cache_key,
                    instruction_breakpoints=_instruction_breakpoints(
                        self._canonical_sections
                    ),
                ),
                tools=list(self._tool_definitions),
                tool_choice="required",
                max_output_tokens=max(1, self._profile.reserved_response_tokens),
                reasoning=LLMReasoningConfig(
                    effort=self._profile.reasoning_effort,
                    context=self._profile.reasoning_context,
                ),
                metadata={
                    "run_id": self._fleet_spec.fleet_run_id,
                    "workflow_id": self._target_spec.target_task_id,
                },
            )
            serialized = _serialize_request(request)
            input_tokens = self._manager.count_text(serialized)
            output_tokens = self._maximum_output_tokens(input_tokens)
            diagnostics = self._manager.inspect_request(
                serialized,
                reserved_response_tokens=output_tokens,
            )
            if diagnostics.within_context_limit:
                return (
                    request.model_copy(update={"max_output_tokens": output_tokens}),
                    diagnostics.current_request_input_tokens,
                    output_tokens,
                )
            if initial or not self._working_set.evict_one_for_context_pressure():
                raise _ContextCapacityStop("minimum valid worker request cannot fit")

    def _request_messages(self, *, initial: bool) -> list[LLMMessage]:
        if initial:
            return []
        if self._compacted_context is not None:
            return self._working_set.protected_messages()
        if self._continuation_ref is not None:
            return list(self._pending_messages)
        return self._working_set.messages()

    def _exact_control_context(self, *, initial: bool) -> str:
        if initial:
            return self._canonical_base
        return f"{self._canonical_base}\n\n{self._execution_overlay()}\n"

    async def _compact_if_needed(self) -> None:
        continuation_ref = self._continuation_ref
        latest_input = self._latest_usage.input_tokens
        latest_output = self._latest_usage.output_tokens
        if continuation_ref is None or latest_input is None or latest_output is None:
            return
        pending_tokens = self._manager.count_text(
            _serialize_messages(self._pending_messages)
        )
        projected_context = (
            latest_input
```

### `src/memory/worker_cycle.py:1398-1645`

```python
    def _execution_overlay(self) -> str:
        overlay: dict[str, object] = {
            "supersedes_stale_worker_context_fields": True,
            "remaining_target_budget": _remaining_budget(
                self._target_spec.budget,
                self._target_state.usage,
            ),
        }
        completion = {
            item.obligation_id: (
                item.status,
                item.resolution_note,
                tuple(item.evidence_refs),
            )
            for item in self._completion_state.items
        }
        changed_completion = [
            item
            for item in self._completion_state.items
            if completion[item.obligation_id]
            != self._base_completion.get(item.obligation_id)
        ]
        if changed_completion:
            overlay["changed_completion_items"] = changed_completion
        artifacts = tuple(self._target_state.artifact_refs)
        if artifacts != self._base_artifacts:
            overlay["current_candidate_artifacts"] = artifacts
        if self._target_state.working_summary != self._base_summary:
            overlay["current_working_summary"] = self._target_state.working_summary
        question_refs = tuple(self._target_state.open_question_refs)
        if question_refs != self._base_questions:
            current_questions: list[OpenQuestion] = []
            for question_id in question_refs:
                question = self._questions.get(question_id)
                if (
                    question is None
                    or question.target_task_id != self._target_spec.target_task_id
                ):
                    raise RuntimeError("authoritative open question is missing")
                current_questions.append(question)
            overlay["current_open_questions"] = current_questions
        new_evidence: list[EvidenceReference] = []
        for evidence_id in self._target_state.evidence_refs:
            if evidence_id in self._base_evidence:
                continue
            reference = self._evidence.get(evidence_id)
            if reference is None:
                raise RuntimeError("authoritative evidence reference is missing")
            new_evidence.append(reference)
        if new_evidence:
            overlay["new_evidence"] = new_evidence
        serialized = orjson.dumps(
            overlay,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2,
            default=_json_default,
        ).decode()
        return (
            "Current execution-state overlay (authoritative corrections):\n"
            + serialized
        )

    @staticmethod
    def _is_valid_finalization(calls: list[LLMToolCall]) -> bool:
        return (
            len(calls) == 1
            and calls[0].name == FINALIZATION_TOOL_ID
            and not calls[0].arguments
        )

    @staticmethod
    def _is_valid_yield(calls: list[LLMToolCall]) -> bool:
        return (
            len(calls) == 1
            and calls[0].name == YIELD_CYCLE_TOOL_ID
            and not calls[0].arguments
        )

    def _outcome_for_budget_stop(
        self,
        scope: _BudgetScope,
    ) -> WorkerCycleOutcome:
        if scope is _BudgetScope.TARGET:
            self._target_state.phase = TargetPhase.EXHAUSTED
            return WorkerCycleOutcome.TARGET_BUDGET_EXHAUSTED
        return WorkerCycleOutcome.FLEET_BUDGET_STOP


def _require_cycle_capacity(
    budget: ExecutionBudget,
    usage: ExecutionUsage,
    repair: bool,
    scope: _BudgetScope,
) -> None:
    if usage.cycles >= budget.max_cycles:
        raise _BudgetStop(scope)
    if repair and usage.repair_cycles >= budget.max_repair_cycles:
        raise _BudgetStop(scope)


def _remaining_optional(limit: int | None, usage: int) -> int | None:
    return None if limit is None else max(0, limit - usage)


def _remaining_budget(
    budget: ExecutionBudget,
    usage: ExecutionUsage,
) -> dict[str, int | None]:
    return {
        "cycles": max(0, budget.max_cycles - usage.cycles),
        "repair_cycles": max(0, budget.max_repair_cycles - usage.repair_cycles),
        "model_calls": max(0, budget.max_model_calls - usage.model_calls),
        "tool_calls": max(0, budget.max_tool_calls - usage.tool_calls),
        "input_tokens": _remaining_optional(
            budget.max_input_tokens,
            usage.input_tokens,
        ),
        "output_tokens": _remaining_optional(
            budget.max_output_tokens,
            usage.output_tokens,
        ),
    }


def _apply_usage_delta(
    target_usage: ExecutionUsage,
    fleet_usage: ExecutionUsage,
    **delta: int,
) -> None:
    for field_name, amount in delta.items():
        if amount < 0:
            raise ValueError("usage deltas cannot be negative")
        setattr(target_usage, field_name, getattr(target_usage, field_name) + amount)
        setattr(fleet_usage, field_name, getattr(fleet_usage, field_name) + amount)


def _control_protocol_error(
    call: LLMToolCall,
    calls: list[LLMToolCall],
) -> LLMToolResult:
    control_name = call.name
    reason = (
        f"{control_name} must have no arguments"
        if call.arguments
        else f"{control_name} must be the sole call in its response"
    )
    if {item.name for item in calls} >= _CONTROL_TOOL_IDS:
        reason = "yield_cycle and request_finalization cannot be requested together"
    return LLMToolResult(
        call_id=call.id,
        name=call.name,
        error=LLMToolError(code="protocol_error", message=reason),
    )


def _bound_tool_result(
    result: LLMToolResult,
    *,
    maximum_bytes: int,
) -> LLMToolResult:
    serialized = orjson.dumps(result.model_dump(mode="json"))
    if len(serialized) <= maximum_bytes:
        return result
    if result.error is not None:
        maximum_message_chars = max(1, maximum_bytes // 2)
        return result.model_copy(
            update={
                "error": result.error.model_copy(
                    update={"message": result.error.message[:maximum_message_chars]}
                )
            }
        )
    prefix = serialized[:maximum_bytes].decode("utf-8", errors="ignore")
    output: JsonValue = {
        "truncated": True,
        "original_bytes": len(serialized),
        "serialized_prefix": prefix,
        "instruction": "Retrieve a narrower range or smaller result set.",
    }
    return result.model_copy(update={"output": output})


def _placeholder_batch(batch: _ToolBatch) -> _ToolBatch:
    results = [
        result.model_copy(
            update={
                "output": (
                    f"Previous {call.name} result body was removed from active "
                    "context; retrieve it again if needed."
                ),
                "error": None,
            }
        )
        for call, result in zip(batch.calls, batch.results, strict=True)
    ]
    return _ToolBatch(calls=batch.calls, results=results, placeholder=True)


def _serialize_request(request: LLMRequest) -> str:
    return orjson.dumps(
        request.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _serialize_compaction_request(request: LLMCompactionRequest) -> str:
    return orjson.dumps(
        request.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _serialize_messages(messages: list[LLMMessage]) -> str:
    return orjson.dumps(
        [message.model_dump(mode="json") for message in messages],
        option=orjson.OPT_SORT_KEYS,
    ).decode()


def _instruction_breakpoints(sections: tuple[str, ...]) -> tuple[int, ...]:
    offsets: list[int] = []
    current = 0
    for section in sections:
        current += len(section)
        offsets.append(current)
    return tuple(offsets)


def _worker_prompt_cache_key(
    context: WorkerContext,
    target_spec: TargetTaskSpec,
    tools: list[LLMToolDefinition],
) -> str:
    identity = {
        "schema_version": "bridger-memory-worker-prompt-cache-v1",
        "worker_profile_id": context.worker_profile_id,
        "target_id": target_spec.target_id,
        "target_contract_version": target_spec.target_contract_version,
        "source": context.source,
        "permission_profile_id": context.permission_profile_id,
        "tools": tools,
    }
    serialized = orjson.dumps(
        identity,
        option=orjson.OPT_SORT_KEYS,
        default=_json_default,
    )
    return hashlib.sha256(serialized).hexdigest()

```

### `src/memory/worker_tools.py:35-77`

```python
    OpenQuestion,
    SourceRangeEvidenceLocator,
    SymbolEvidenceLocator,
)
from navigation.navigator import MAX_RANGE_LINES, RepositoryNavigator
from navigation.tools import build_navigation_tools
from repository.errors import RepositoryError

MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_ARTIFACT_READ_BYTES = 64 * 1024
MAX_WORKING_SUMMARY_CHARS = 8_000
MAX_QUESTION_CHARS = 1_000
MAX_OPEN_QUESTIONS = 20
MAX_RESOLUTION_NOTE_CHARS = 4_000

REPOSITORY_TOOL_IDS = (
    "search_repository",
    "get_graph_entity",
    "get_graph_neighbors",
    "get_graph_path",
    "get_graph_community",
    "list_files",
    "get_file_overview",
    "search_symbols",
    "search_source_content",
    "read_symbol_excerpt",
    "read_file_ranges",
)
TARGET_TOOL_IDS = (
    "list_target_artifacts",
    "read_target_artifact",
    "write_target_artifact",
    "edit_target_artifact_range",
    "delete_target_artifact",
    "move_target_artifact",
    "record_evidence",
    "update_completion_item",
    "update_progress",
)
FINALIZATION_TOOL_ID = "request_finalization"
YIELD_CYCLE_TOOL_ID = "yield_cycle"
WORKER_TOOL_IDS = (*REPOSITORY_TOOL_IDS, *TARGET_TOOL_IDS)

```

### `src/memory/worker_tools.py:804-993`

```python
        context: WorkerContext,
        permission_profile: PermissionProfile,
        navigator: RepositoryNavigator,
        workspace: TargetWorkspace,
        evidence_recorder: EvidenceRecorder,
        completion_updater: CompletionStateUpdater,
        progress_updater: ProgressUpdater,
    ) -> None:
        if permission_profile.profile_id != context.permission_profile_id:
            raise ValueError("permission profile does not match WorkerContext")
        if permission_profile.allowed_tool_ids != context.allowed_tool_ids:
            raise ValueError("permission tools do not match WorkerContext")
        unknown = set(context.allowed_tool_ids) - set(WORKER_TOOL_IDS)
        if unknown:
            raise ValueError(f"unknown configured worker tool: {sorted(unknown)[0]}")
        self._allowed = set(context.allowed_tool_ids)
        self._navigation = build_navigation_tools(navigator)
        self._local = _build_local_tools(
            workspace,
            evidence_recorder,
            completion_updater,
            progress_updater,
        )
        definitions = {
            definition.name: definition
            for definition in [
                *self._navigation.definitions,
                *self._local.definitions,
            ]
        }
        self._definitions = [
            definitions[tool_id]
            for tool_id in WORKER_TOOL_IDS
            if tool_id in self._allowed
        ]
        self._definitions.append(_yield_cycle_definition())
        self._definitions.append(_finalization_definition())

    @property
    def definitions(self) -> list[LLMToolDefinition]:
        """Return the stable exposed definitions after permission filtering."""
        return list(self._definitions)

    async def execute_operational(self, call: LLMToolCall) -> LLMToolResult:
        """Enforce permission again and dispatch one operational call."""
        if call.name not in self._allowed:
            return LLMToolResult(
                call_id=call.id,
                name=call.name,
                error=LLMToolError(
                    code="permission_denied",
                    message=f"Tool is not allowed for this worker: {call.name}",
                ),
            )
        if call.name in REPOSITORY_TOOL_IDS:
            return await self._navigation.execute(call)
        return await self._local.execute(call)


def _build_local_tools(
    workspace: TargetWorkspace,
    evidence_recorder: EvidenceRecorder,
    completion_updater: CompletionStateUpdater,
    progress_updater: ProgressUpdater,
) -> ToolExecutor:
    tools = [
        LLMTool.bind(
            name="list_target_artifacts",
            description="List the complete current target-local Markdown inventory.",
            arguments_type=_EmptyArguments,
            handler=lambda _: workspace.list_target_artifacts(),
        ),
        LLMTool.bind(
            name="read_target_artifact",
            description="Read one bounded current target-local Markdown artifact.",
            arguments_type=_ReadArtifactArguments,
            handler=lambda value: workspace.read_target_artifact(
                value.path,
                start_line=value.start_line,
                end_line=value.end_line,
            ),
        ),
        LLMTool.bind(
            name="write_target_artifact",
            description="Create or whole-file replace target-local Markdown.",
            arguments_type=_WriteArtifactArguments,
            handler=lambda value: workspace.write_target_artifact(
                value.path,
                value.content,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="edit_target_artifact_range",
            description="Replace an inclusive line range in current Markdown.",
            arguments_type=_EditArtifactArguments,
            handler=lambda value: workspace.edit_target_artifact_range(
                value.path,
                expected_revision=value.expected_revision,
                start_line=value.start_line,
                end_line=value.end_line,
                replacement=value.replacement,
            ),
        ),
        LLMTool.bind(
            name="delete_target_artifact",
            description="Delete one target-local Markdown artifact by revision.",
            arguments_type=_DeleteArtifactArguments,
            handler=lambda value: workspace.delete_target_artifact(
                value.path,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="move_target_artifact",
            description="Move one target-local Markdown artifact by revision.",
            arguments_type=_MoveArtifactArguments,
            handler=lambda value: workspace.move_target_artifact(
                value.source_path,
                value.destination_path,
                expected_revision=value.expected_revision,
            ),
        ),
        LLMTool.bind(
            name="record_evidence",
            description="Validate and record one durable repository evidence locator.",
            arguments_type=_RecordEvidenceArguments,
            handler=lambda value: evidence_recorder.record_evidence(
                value.kind,
                value.locator,
            ),
        ),
        LLMTool.bind(
            name="update_completion_item",
            description="Replace one completion obligation's resolution fields.",
            arguments_type=_UpdateCompletionArguments,
            handler=lambda value: completion_updater.update_completion_item(
                value.obligation_id,
                value.status,
                value.resolution_note,
                value.evidence_refs,
            ),
        ),
        LLMTool.bind(
            name="update_progress",
            description="Replace compact continuation state and manage open questions.",
            arguments_type=_UpdateProgressArguments,
            handler=lambda value: progress_updater.update_progress(
                working_summary=value.working_summary,
                questions_to_open=value.questions_to_open,
                question_refs_to_resolve=value.question_refs_to_resolve,
            ),
        ),
    ]
    return ToolExecutor(
        tools,
        handled_errors=(ValueError, KeyError, RepositoryError),
    )


def _finalization_definition() -> LLMToolDefinition:
    tool = LLMTool.bind(
        name=FINALIZATION_TOOL_ID,
        description=(
            "Stop Stage 4 and transfer control to finalization. This must be the "
            "only tool call in the response."
        ),
        arguments_type=_EmptyArguments,
        handler=lambda _: None,
    )
    return tool.definition


def _yield_cycle_definition() -> LLMToolDefinition:
    tool = LLMTool.bind(
        name=YIELD_CYCLE_TOOL_ID,
        description=(
            "End the current bounded worker cycle after preserving useful progress. "
            "Use this when the current cycle objective is complete, or when a fresh "
            "hydrated context should continue it. This must be the only tool call in "
            "the response."
        ),
        arguments_type=_EmptyArguments,
        handler=lambda _: None,
    )
    return tool.definition


__all__ = [
    "FINALIZATION_TOOL_ID",
```

### `src/navigation/tools.py:219-448`

```python
def build_navigation_tools(navigator: RepositoryNavigator) -> ToolExecutor:
    """Bind the explicit Layer 6 tool set to one immutable navigator context."""
    tools = [
        LLMTool.bind(
            name="search_repository",
            description=(
                "Locate graph entities, communities, files, and symbols by structured "
                "repository metadata; this does not search source text."
            ),
            arguments_type=_SearchRepositoryArguments,
            handler=lambda value: navigator.search_repository(
                value.query,
                kinds=value.kinds,
                limit=value.limit,
                min_score=value.min_score,
            ),
        ),
        LLMTool.bind(
            name="get_graph_entity",
            description=(
                "Inspect one existing graph target and return deterministic facts plus "
                "separate matching enrichment."
            ),
            arguments_type=_GetGraphEntityArguments,
            handler=lambda value: navigator.get_graph_entity(
                value.target_type,
                value.target_ref,
                max_members=value.max_members,
            ),
        ),
        LLMTool.bind(
            name="get_graph_neighbors",
            description="Return a bounded one-hop graph neighborhood around a node.",
            arguments_type=_GraphNeighborsArguments,
            handler=lambda value: navigator.get_graph_neighbors(
                value.node_id,
                direction=value.direction,
                relations=value.relations,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
                max_hyperedges=value.max_hyperedges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_path",
            description=(
                "Find one bounded deterministic shortest path between graph nodes."
            ),
            arguments_type=_GraphPathArguments,
            handler=lambda value: navigator.get_graph_path(
                value.source_node_id,
                value.target_node_id,
                direction=value.direction,
                relations=value.relations,
                max_depth=value.max_depth,
                max_nodes=value.max_nodes,
            ),
        ),
        LLMTool.bind(
            name="get_graph_subgraph",
            description=(
                "Materialize a bounded graph neighborhood to the requested depth."
            ),
            arguments_type=_GraphSubgraphArguments,
            handler=lambda value: navigator.get_graph_subgraph(
                value.node_id,
                depth=value.depth,
                direction=value.direction,
                relations=value.relations,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
                max_hyperedges=value.max_hyperedges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_community",
            description=(
                "Inspect bounded community members plus internal and cross-community "
                "edges."
            ),
            arguments_type=_GraphCommunityArguments,
            handler=lambda value: navigator.get_graph_community(
                value.community_id,
                max_nodes=value.max_nodes,
                max_edges=value.max_edges,
            ),
        ),
        LLMTool.bind(
            name="get_graph_central_nodes",
            description=(
                "Return the persisted central graph nodes in deterministic order."
            ),
            arguments_type=_LimitArguments,
            handler=lambda value: navigator.get_graph_central_nodes(limit=value.limit),
        ),
        LLMTool.bind(
            name="graph_to_file",
            description=(
                "Resolve a graph node to its canonical indexed source file, if any."
            ),
            arguments_type=_NodeArguments,
            handler=lambda value: navigator.graph_to_file(value.node_id),
        ),
        LLMTool.bind(
            name="graph_to_symbols",
            description="Resolve a graph node to all exact indexed symbol matches.",
            arguments_type=_NodeArguments,
            handler=lambda value: navigator.graph_to_symbols(value.node_id),
        ),
        LLMTool.bind(
            name="file_to_graph",
            description="Return graph nodes exactly associated with an indexed file.",
            arguments_type=_PathArguments,
            handler=lambda value: navigator.file_to_graph(value.path),
        ),
        LLMTool.bind(
            name="symbol_to_graph",
            description="Return graph nodes exactly associated with an indexed symbol.",
            arguments_type=_SymbolArguments,
            handler=lambda value: navigator.symbol_to_graph(value.symbol_id),
        ),
        LLMTool.bind(
            name="list_files",
            description="List a bounded filtered view of canonical indexed files.",
            arguments_type=_ListFilesArguments,
            handler=lambda value: navigator.list_files(
                path_prefix=value.path_prefix,
                content_types=value.content_types,
                read_modes=value.read_modes,
                limit=value.limit,
            ),
        ),
        LLMTool.bind(
            name="get_file_overview",
            description=(
                "Inspect one indexed file and its exact symbol and graph associations."
            ),
            arguments_type=_FileOverviewArguments,
            handler=lambda value: navigator.get_file_overview(
                value.path,
                max_symbols=value.max_symbols,
                max_graph_nodes=value.max_graph_nodes,
            ),
        ),
        LLMTool.bind(
            name="list_symbols",
            description=(
                "List bounded canonical symbols, optionally filtered by file or kind."
            ),
            arguments_type=_ListSymbolsArguments,
            handler=lambda value: navigator.list_symbols(
                path=value.path,
                kinds=value.kinds,
                limit=value.limit,
            ),
        ),
        LLMTool.bind(
            name="search_symbols",
            description=(
                "Search indexed symbol names and qualified names with bounded results."
            ),
            arguments_type=_SearchSymbolsArguments,
            handler=lambda value: navigator.search_symbols(
                value.query,
                path=value.path,
                kinds=value.kinds,
                limit=value.limit,
                min_score=value.min_score,
            ),
        ),
        LLMTool.bind(
            name="search_source_content",
            description=(
                "Search authorized repository source text and return bounded "
                "line-addressable matches."
            ),
            arguments_type=_SearchSourceArguments,
            handler=lambda value: navigator.search_source_content(
                value.query,
                regex=value.regex,
                paths=value.paths,
                context_lines=value.context_lines,
                limit=value.limit,
                max_files=value.max_files,
            ),
        ),
        LLMTool.bind(
            name="read_symbol_excerpt",
            description="Read a bounded exact-source excerpt around an indexed symbol.",
            arguments_type=_ReadSymbolArguments,
            handler=lambda value: navigator.read_symbol_excerpt(
                value.symbol_id,
                context_lines=value.context_lines,
                max_bytes=value.max_bytes,
            ),
        ),
        LLMTool.bind(
            name="read_file_ranges",
            description=(
                "Read one or more bounded exact line ranges from an indexed file."
            ),
            arguments_type=_ReadFileRangesArguments,
            handler=lambda value: navigator.read_file_ranges(
                value.path,
                [(item.start_line, item.end_line) for item in value.ranges],
                max_bytes_per_range=value.max_bytes_per_range,
            ),
        ),
        LLMTool.bind(
            name="read_around_match",
            description=(
                "Read a bounded exact-source window around a line-addressable match."
            ),
            arguments_type=_ReadAroundMatchArguments,
            handler=lambda value: navigator.read_around_match(
                value.path,
                value.line_number,
                context_lines=value.context_lines,
                max_bytes=value.max_bytes,
            ),
        ),
    ]
    return ToolExecutor(
        tools,
        handled_errors=(ValueError, KeyError, RepositoryError),
    )


__all__ = ["build_navigation_tools"]
```

### `src/llm/models.py:23-220`

```python
    REPO_DISCOVERY = "repo_discovery"
    COMMUNITY_NAMING = "community_naming"
    CONTEXT_PLAN_GENERATION = "context_plan_generation"
    CONTEXT_PLAN_REVIEW = "context_plan_review"
    MEMORY_AGENT_EVIDENCE = "memory_agent_evidence"
    MEMORY_AGENT_RECONCILIATION = "memory_agent_reconciliation"
    MEMORY_AGENT_WORKER = "memory_agent_worker"
    MEMORY_AGENT_REVIEW = "memory_agent_review"
    AGENTS_EXPORT = "agents_export"
    PROMPT_GENERATION = "prompt_generation"
    TICKET_GENERATION = "ticket_generation"
    UPDATE = "update"
    IMPLEMENTATION_PLANNING = "implementation_planning"


class LLMToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: ToolName
    arguments: dict[str, JsonValue]
    raw_arguments: str | None = None


class LLMToolError(BaseModel):
    """Ordinary tool failure that a caller may return to a future model turn."""

    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "unknown_tool",
        "invalid_arguments",
        "tool_execution_error",
        "permission_denied",
        "protocol_error",
    ]
    message: str = Field(min_length=1)


class LLMToolResult(BaseModel):
    """Provider-neutral result correlated with one requested tool call."""

    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1)
    name: ToolName
    output: JsonValue = None
    error: LLMToolError | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> "LLMToolResult":
        """Prevent a failed result from also carrying a successful output."""
        if self.error is not None and self.output is not None:
            raise ValueError("tool result cannot contain both output and error")
        return self

    def as_message(self) -> "LLMMessage":
        """Convert this result to the existing provider-neutral tool message."""
        result: JsonValue = self.output
        if self.error is not None:
            result = {"error": self.error.model_dump(mode="json")}
        return LLMMessage.tool_result_message(
            tool_call_id=self.call_id,
            tool_name=self.name,
            result=result,
            failed=self.error is not None,
        )


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[LLMToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: ToolName | None = None
    tool_result: (
        dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
    ) = None
    tool_failed: bool = False

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str) -> "LLMMessage":
        return cls(role="assistant", content=content)

    @classmethod
    def assistant_tool_calls(cls, tool_calls: list[LLMToolCall]) -> "LLMMessage":
        return cls(role="assistant", tool_calls=tool_calls)

    @classmethod
    def tool_result_message(
        cls,
        *,
        tool_call_id: str,
        tool_name: str,
        result: (
            dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None
        ),
        failed: bool = False,
    ) -> "LLMMessage":
        return cls(
            role="tool",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_result=result,
            tool_failed=failed,
        )

    @model_validator(mode="after")
    def validate_role_payload(self) -> "LLMMessage":
        if self.role in {"system", "user"}:
            if not self.content:
                raise ValueError(f"{self.role} messages require text content")
            if self.tool_calls or self.tool_call_id is not None:
                raise ValueError(f"{self.role} messages cannot contain tool data")
        if self.role == "assistant":
            has_content = self.content is not None and self.content != ""
            has_tool_calls = bool(self.tool_calls)
            if has_content == has_tool_calls:
                raise ValueError(
                    "assistant messages require exactly one of content or tool_calls"
                )
            if self.tool_call_id is not None:
                raise ValueError("assistant messages cannot contain tool results")
        if self.role == "tool":
            if not self.tool_call_id or not self.tool_name:
                raise ValueError("tool results require tool_call_id and tool_name")
            if self.content is not None or self.tool_calls:
                raise ValueError("tool results cannot contain assistant content")
        return self


class LLMToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ToolName
    description: str = Field(min_length=1)
    input_schema: dict[str, JsonValue]
    strict: bool = True

    @field_validator("input_schema")
    @classmethod
    def validate_json_schema(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("type") != "object":
            raise ValueError("tool input_schema must be a JSON Schema object")
        properties = value.get("properties")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError("tool input_schema properties must be an object")
        return value


class LLMReasoningConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    context: Literal["auto", "current_turn", "all_turns"] | None = None
    summary: Literal["auto", "concise", "detailed"] | None = None


class LLMCompactedContext(BaseModel):
    """Opaque provider-owned transient trajectory returned by compaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    payload: JsonValue


class LLMPromptCacheConfig(BaseModel):
    """Provider-neutral prompt-prefix cache intent for exact instructions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, max_length=64)
    mode: Literal["explicit"] = "explicit"
    instruction_breakpoints: tuple[int, ...]

    @field_validator("instruction_breakpoints")
    @classmethod
    def validate_breakpoints(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        """Require positive, strictly increasing instruction offsets."""
        if not value:
            raise ValueError("prompt cache requires at least one breakpoint")
        if any(offset < 1 for offset in value):
            raise ValueError("prompt cache breakpoints must be positive")
        if tuple(sorted(set(value))) != value:
            raise ValueError("prompt cache breakpoints must be strictly increasing")
        return value

```
